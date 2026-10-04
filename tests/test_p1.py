"""Credential-free regressions for P1 contracts, identity and matching."""
import asyncio
import logging
import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.pop('GEMINI_API_KEY', None)
os.environ['RATE_LIMIT_REQUESTS'] = '1000'
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
logging.disable(logging.CRITICAL)
from httpx import AsyncClient, ASGITransport
from pydantic import ValidationError
from main import app
from agents import orchestrator
from agents.base import RunState
from agents.comparison import ComparisonAgent, _match_requirement
from agents.price_value import _extract_budget
from agents.research import select_candidates
from agents.requirement import RequirementAgent
from data.demo_cache import DEMO_REQUIREMENTS
from llm.base import LLMError, LLMProvider
from llm.gemini import MockLLMProvider
from models.request import Requirement
from models.product import Product, Spec, PriceInfo
from models.comparison import Comparison
from rag.sanitize import strip_html


def requirement(key='ram', value='32 GB', operator='>=', priority='must'):
    return Requirement(key=key, value=value, operator=operator, priority=priority)


def spec(value='32 GB', key='RAM', status='supported', evidence=True):
    return Spec(key=key, value=value, status=status, evidence_ids=['source'] if evidence else [])


class MatchingTests(unittest.TestCase):
    def test_numeric_boundaries(self):
        for op, expected in [('>', '✕'), ('>=', '✓'), ('<', '✕'), ('<=', '✓'), ('=', '✓')]:
            with self.subTest(op=op):
                self.assertEqual(_match_requirement(requirement(operator=op), [spec()])[0], expected)

    def test_units_and_decimal(self):
        self.assertEqual(_match_requirement(requirement(value='0.5 TB'), [spec('500 GB')])[0], '✓')
        self.assertEqual(_match_requirement(requirement('storage', '1 TB'), [spec('1000 GB', 'storage')])[0], '✓')
        self.assertEqual(_match_requirement(requirement('weight', '2 kg', '<'), [spec('3 lbs', 'weight')])[0], '✓')
        self.assertEqual(_match_requirement(requirement('weight', '2 kg', '<'), [spec('3', 'weight_lbs')])[0], '✓')

    def test_unknown_conflict_and_unattributed(self):
        for s in [spec('unknown'), spec(status='insufficient'), spec(status='conflicting'), spec(evidence=False), spec('16–32 GB')]:
            with self.subTest(s=s):
                self.assertEqual(_match_requirement(requirement(), [s])[0], '?')
        self.assertEqual(_match_requirement(requirement(), [spec(), spec('16 GB')])[0], '?')

    def test_negative_upgradeability(self):
        for value in ['not upgradeable', 'soldered RAM', 'false']:
            self.assertEqual(_match_requirement(requirement('upgradeability', 'preferred', '='), [spec(value, 'upgradeability')])[0], '✕')

    def test_generic_condition_not_presence(self):
        self.assertEqual(_match_requirement(requirement('color', 'red', '='), [spec('blue', 'color')])[0], '✕')
        self.assertEqual(_match_requirement(requirement('cpu', '8', '>='), [spec('Ryzen 7', 'cpu')])[0], '?')
        self.assertEqual(_match_requirement(requirement('virtualization', 'high', '='), [spec('unknown hardware virtualization', 'virtualization')])[0], '?')
        self.assertEqual(_match_requirement(requirement('virtualization', 'high', '='), [spec('unknown', 'virtualization')])[0], '?')

    def test_linux_uncertainty(self):
        req = requirement('os_compatibility', 'Linux', '=')
        self.assertEqual(_match_requirement(req, [spec('not supported', 'linux_support')])[0], '✕')
        self.assertEqual(_match_requirement(req, [spec('strong but not officially certified', 'linux_support')])[0], '?')
        self.assertEqual(_match_requirement(req, [spec('native', 'linux_support')])[0], '✓')

    def test_budget_currency(self):
        self.assertEqual(_extract_budget([requirement('budget', '$1,000 USD', '<=')]), 1000)
        self.assertIsNone(_extract_budget([requirement('budget', '1000 EUR', '<=')]))

    def test_discovery_must_have_priority(self):
        seed = [dict(id='miss', specs={'ram_gb': 16, 'linux_support': 'native'}), dict(id='fit', specs={'ram_gb': 32})]
        selected = select_candidates(seed, [requirement(), requirement('linux', 'Linux', '=', 'optional')])
        self.assertEqual(selected[0]['id'], 'fit')

    def test_prices_reject_negative_and_nonfinite(self):
        for amount in [-1, float('inf'), float('nan')]:
            with self.assertRaises(ValidationError):
                PriceInfo(amount=amount)

    def test_validation_and_trim(self):
        self.assertEqual(requirement(value=' 32 GB ').value, '32 GB')
        for kwargs in [dict(value='  '), dict(operator='garbage')]:
            with self.assertRaises(ValidationError):
                requirement(**kwargs)

    def test_sanitizer(self):
        self.assertEqual(strip_html('<html><body>Source<script>bad()</script></body></html>'), 'Source')

    def test_serialized_products_rehydrate(self):
        result = Comparison(request_id='req', products=[Product(id='a', name='A')])
        loaded = Comparison.model_validate_json(result.model_dump_json())
        self.assertIsInstance(loaded.products[0], Product)


class UnavailableProvider(LLMProvider):
    model = 'fixture-unavailable'
    async def generate_json(self, *args, **kwargs):
        raise LLMError('Simulated upstream failure')
    async def generate_text(self, *args, **kwargs):
        raise LLMError('Simulated upstream failure')
    async def embed(self, text):
        return [0.0] * 768
    async def embed_batch(self, texts):
        return [[0.0] * 768 for text in texts]


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        orchestrator._comparison_cache.clear()
        orchestrator._comparison_store.clear()
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url='http://test')

    async def asyncTearDown(self):
        await self.client.aclose()

    async def research(self, request_id='req'):
        response = await self.client.post('/api/research-products', json={
            'request_id': request_id, 'requirements': [r.model_dump(mode='json') for r in DEMO_REQUIREMENTS]})
        self.assertEqual(response.status_code, 200)
        cid = response.json()['comparison_id']
        stream = await self.client.get(response.json()['stream_url'])
        self.assertIn('event: done', stream.text)
        result = await self.client.get('/api/comparison/' + cid)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['id'], cid)
        self.assertEqual(result.json()['request_id'], request_id)
        return result.json()

    async def test_no_key_fallback_and_followup(self):
        response = await self.client.post('/api/analyze-requirements', json={'text': 'I need a laptop for work'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data_mode'], 'demo')
        self.assertTrue(response.json()['notices'])
        result = await self.research()
        self.assertEqual(result['data_mode'], 'demo')
        response = await self.client.post('/api/follow-up', json={'comparison_id': result['id'], 'question': 'What if budget is $1,200?'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['requires_rerun'])
        self.assertEqual(response.json()['suggested_requirements_patch'][0]['value'], '1200 USD')

    async def test_upstream_failure_fallback(self):
        with patch('api.analyze.get_llm_provider', return_value=UnavailableProvider()):
            response = await self.client.post('/api/analyze-requirements', json={'text': 'I need a laptop for school'})
            self.assertEqual(response.status_code, 200)

    async def test_validation_errors_have_json_envelope(self):
        cases = [('/api/analyze-requirements', {'text': ' ' * 12}),
                 ('/api/research-products', {'request_id': 'req', 'requirements': []}),
                 ('/api/research-products', {'request_id': 'req', 'requirements': [None]}),
                 ('/api/research-products', {'request_id': '  ', 'requirements': [r.model_dump(mode='json') for r in DEMO_REQUIREMENTS]}),
                 ('/api/research-products', {'request_id': 'req', 'requirements': [DEMO_REQUIREMENTS[0].model_dump(mode='json')] * 21}),
                 ('/api/compare-products', {'request_id': 'req', 'product_ids': ['a','a']}),
                 ('/api/compare-products', {'request_id': 'req', 'product_ids': ['a']}),
                 ('/api/compare-products', {'request_id': 'req', 'product_ids': ['a','b','c','d','e','f']}),
                 ('/api/compare-products', {'request_id': 'req', 'product_ids': ['a','  ']}),
                 ('/api/follow-up', {'comparison_id': 'req', 'question': '   '})]
        for path, body in cases:
            with self.subTest(path=path, body=body):
                response = await self.client.post(path, json=body)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()['error']['code'], 'SCHEMA_ERROR')

    async def test_result_ids_and_cache_independence(self):
        a, b = await self.research('req-a'), await self.research('req-b')
        self.assertNotEqual(a['id'], b['id'])
        first = orchestrator.get_comparison(a['id'])
        first.products[0].name = 'mutated'
        self.assertNotEqual(orchestrator.get_comparison(a['id']).products[0].name, 'mutated')
        self.assertEqual(orchestrator.get_comparison(a['id']).request_id, 'req-a')
        self.assertEqual(orchestrator.get_comparison(b['id']).request_id, 'req-b')

    async def test_cache_key_respects_order_text_and_expiry(self):
        await orchestrator.run_pipeline('req-a', DEMO_REQUIREMENTS, raw_text='first')
        await orchestrator.run_pipeline('req-b', list(reversed(DEMO_REQUIREMENTS)), raw_text='first')
        await orchestrator.run_pipeline('req-c', DEMO_REQUIREMENTS, raw_text='second')
        changed = [r.model_copy(update={'confirmed': True}) for r in DEMO_REQUIREMENTS]
        await orchestrator.run_pipeline('req-meta', changed, raw_text='first')
        self.assertEqual(len(orchestrator._comparison_cache), 4)
        for key, (_, value) in list(orchestrator._comparison_cache.items()):
            orchestrator._comparison_cache[key] = (time.monotonic()-4000, value)
        await orchestrator.run_pipeline('req-d', DEMO_REQUIREMENTS)
        self.assertEqual(len(orchestrator._comparison_cache), 1)

    async def test_selected_product_comparison(self):
        original = await self.research()
        ids = [p['id'] for p in original['products'][:2]][::-1]
        response = await self.client.post('/api/compare-products', json={'request_id': 'req', 'comparison_id': original['id'], 'product_ids': ids})
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual([p['id'] for p in result['products']], ids)
        self.assertEqual(set(result['requirement_matches']), set(ids))
        for analysis in result['requirement_analysis']:
            self.assertEqual([a['product_id'] for a in analysis['product_assessments']], ids)
        self.assertEqual(len(result['requirement_analysis']), len(result['requirements']))
        self.assertEqual((await self.client.get('/api/comparison/'+result['id'])).status_code, 200)
        self.assertEqual(len(orchestrator.get_comparison(original['id']).products), 3)

    async def test_selected_products_without_snapshot_id(self):
        original = await self.research()
        ids = [p['id'] for p in original['products'][:2]]
        response = await self.client.post('/api/compare-products', json={'request_id': 'req', 'product_ids': ids})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([p['id'] for p in response.json()['products']], ids)

    async def test_concurrent_runs_keep_distinct_identity(self):
        first, second = await asyncio.gather(
            orchestrator.run_pipeline('one', DEMO_REQUIREMENTS),
            orchestrator.run_pipeline('two', DEMO_REQUIREMENTS))
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(orchestrator.get_comparison(first.id).request_id, 'one')
        self.assertEqual(orchestrator.get_comparison(second.id).request_id, 'two')

    async def test_selection_request_scope(self):
        original = await self.research()
        for req_id, ids in [('other', [p['id'] for p in original['products'][:2]]), ('req', ['bad','other'])]:
            response = await self.client.post('/api/compare-products', json={'request_id': req_id, 'comparison_id': original['id'], 'product_ids': ids})
            self.assertEqual(response.status_code, 404)

    async def test_comparison_priority_price_and_analysis(self):
        state = RunState(requirements=[requirement(), requirement('budget', '1000 USD', '<=', 'optional')],
                         candidate_products=[Product(id='a', name='A')])
        state.verified_specs['a'] = [spec('16 GB')]
        state.prices['a'] = {'price_info': PriceInfo(amount=900, currency='USD', source_id='price-source')}
        await ComparisonAgent().run(state)
        result = state.comparison
        self.assertEqual(result.requirement_matches['a'], ['✕', '✓'])
        self.assertEqual(result.products[0].must_have_status, 'not_met')
        self.assertEqual(result.products[0].weighted_match_score, .2)
        self.assertEqual(len(result.requirement_analysis), 2)
        self.assertEqual(result.products[0].price_info.amount, 900)

    async def test_stale_or_unattributed_price_uncertain(self):
        for info in [PriceInfo(amount=900, is_stale=True, source_id='price'), PriceInfo(amount=900)]:
            state = RunState(requirements=[requirement('budget','1000 USD','<=')], candidate_products=[Product(id='a',name='A',price_info=info)])
            await ComparisonAgent().run(state)
            self.assertEqual(state.comparison.requirement_matches['a'], ['?'])
            self.assertEqual(state.comparison.products[0].must_have_status, 'uncertain')

    async def test_live_branch_failure_degrades_without_demo_shortcut(self):
        with patch.dict(os.environ, {'BUYWISE_MARKET': 'US'}), patch('agents.orchestrator.get_llm_provider', return_value=UnavailableProvider()):
            result = await orchestrator.run_pipeline('req-live', DEMO_REQUIREMENTS)
        self.assertEqual(len(result.products), 5)
        self.assertEqual(len(result.requirement_analysis), len(DEMO_REQUIREMENTS))
        self.assertEqual(result.request_id, 'req-live')
        self.assertEqual(result.data_mode, 'live')
        self.assertTrue(all(p.price_info.amount is None for p in result.products))
        self.assertEqual(orchestrator.get_comparison(result.id).id, result.id)

    async def test_storage_bound(self):
        for i in range(orchestrator.MAX_STORED_COMPARISONS + 1):
            orchestrator.store_comparison(Comparison(id=str(i), request_id='bound'))
        self.assertEqual(len(orchestrator._comparison_store), orchestrator.MAX_STORED_COMPARISONS)
        self.assertIsNone(orchestrator.get_comparison('0'))

    async def test_mock_error_is_controlled(self):
        with self.assertRaises(LLMError):
            await MockLLMProvider().generate_json('request', Comparison)


class StreamlitTests(unittest.TestCase):
    def test_demo_search_renders(self):
        from streamlit.testing.v1 import AppTest
        app_test = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'backend/streamlit_app.py')).run(timeout=15)
        app_test.text_input[0].set_value('I need a laptop for Linux')
        app_test.button[0].click().run(timeout=15)
        self.assertEqual(len(app_test.exception), 0)
        self.assertEqual(len(app_test.subheader), 4)
        self.assertTrue(any('canned' in w.value.lower() or 'demo' in w.value.lower() for w in app_test.warning))
        self.assertNotIn('GEMINI_API_KEY', os.environ)


if __name__ == '__main__':
    unittest.main()
