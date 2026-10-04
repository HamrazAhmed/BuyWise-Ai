"""P6 source provenance, durable job recovery, and cross-process storage gates."""
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from data import runtime, jobs
from data.pakistan import catalog, parse_listing, prepare
from models.comparison import Comparison
from models.request import Requirement
from rag.store import Chunk, DurableVectorStore
from rag.safe_fetch import FetchedDocument
from llm.fixture import FixtureLLMProvider


class SourceProvider(FixtureLLMProvider):
    data_mode = 'live'
    model = 'source-test'
    async def generate_json(self, *args, **kwargs):
        raise RuntimeError('Controlled generation outage; source fallback required')


class P6Tests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'BUYWISE_DB': self.temp.name + '/runtime.db', 'DATABASE_URL': os.getenv('P6_TEST_DATABASE_URL', ''), 'BUYWISE_MODE': 'fixture', 'BUYWISE_MARKET': 'PK', 'BUYWISE_INLINE_WORKER': 'false', 'BUYWISE_SOURCE_REFRESH': 'false'})
        self.env.start()
        runtime.ensure()
        if runtime.postgres():
            with runtime.connect(write=True) as db:
                for table in ('bw_events', 'bw_jobs', 'bw_comparisons', 'bw_requests', 'bw_chunks', 'bw_limits'):
                    db.execute('DELETE FROM ' + table)
        from agents import orchestrator
        orchestrator._comparison_cache.clear(); orchestrator._comparison_store.clear()

    async def asyncTearDown(self):
        self.env.stop(); self.temp.cleanup()

    def payload(self):
        return {'request_id': 'p6-request', 'raw_text': 'laptop with 16 GB RAM', 'requirements': [Requirement(key='ram', operator='>=', value='16 GB', priority='must').model_dump(mode='json')]}

    async def test_lease_recovery_fences_old_owner_and_commits_result_with_done(self):
        jobs.submit('recover', self.payload())
        first = jobs.claim(); self.assertIsNone(jobs.claim())
        with runtime.connect(write=True) as db:
            db.execute('UPDATE bw_jobs SET lease_until=0 WHERE id=?', ('recover',))
        second = jobs.claim(); self.assertNotEqual(first[2], second[2])
        with self.assertRaises(RuntimeError): jobs.progress('recover', first[2], {'type': 'status'})
        with self.assertRaises(RuntimeError): jobs.finish('recover', first[2], Comparison(id='recover', request_id='r'))
        result = Comparison(id='recover', request_id='r')
        jobs.finish('recover', second[2], result)
        self.assertEqual(jobs.status('recover')['status'], 'done')
        self.assertEqual(jobs.events('recover')[-1][1]['type'], 'done')
        self.assertEqual(runtime.load_comparison('recover').model_dump(), result.model_dump())

    async def test_crash_retry_bound_terminal_error_and_counter(self):
        jobs.submit('bound', self.payload())
        for _ in range(2):
            self.assertIsNotNone(jobs.claim())
            with runtime.connect(write=True) as db: db.execute('UPDATE bw_jobs SET lease_until=0 WHERE id=?', ('bound',))
        self.assertIsNone(jobs.claim())
        self.assertEqual(jobs.status('bound')['status'], 'error')
        self.assertEqual(jobs.events('bound')[-1][1]['code'], 'WORKER_INTERRUPTED')
        expiry = time.time() + 60
        accepted = await asyncio.gather(*[asyncio.to_thread(runtime.reserve, 'atomic', 3, expiry) for _ in range(12)])
        self.assertEqual(sum(accepted), 3)

    async def test_concurrent_claims_have_one_owner_and_cancelled_work_recovers(self):
        from worker import run_one
        jobs.submit('racing', self.payload())
        claims = await asyncio.gather(*[asyncio.to_thread(jobs.claim) for _ in range(8)])
        self.assertEqual(sum(c is not None for c in claims), 1)
        claimed = next(c for c in claims if c)
        jobs.finish('racing', claimed[2], Comparison(id='racing', request_id='r'))
        jobs.submit('cancelled', self.payload())
        started = asyncio.Event()
        async def suspended(*args, **kwargs):
            started.set()
            await asyncio.Event().wait()
        with patch('agents.orchestrator.run_pipeline', side_effect=suspended):
            worker = asyncio.create_task(run_one())
            await asyncio.wait_for(started.wait(), 5)
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
        self.assertEqual(jobs.status('cancelled')['status'], 'running')
        self.assertIsNone(runtime.load_comparison('cancelled'))
        with runtime.connect(write=True) as db: db.execute('UPDATE bw_jobs SET lease_until=0 WHERE id=?', ('cancelled',))
        self.assertTrue(await run_one())
        self.assertEqual(jobs.status('cancelled')['status'], 'done')
        self.assertEqual(jobs.status('cancelled')['attempts'], 2)

    async def test_worker_pipeline_two_subscribers_replay_and_scoped_product(self):
        import httpx
        from main import app
        from worker import run_one
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            response = await client.post('/api/research-products', json=self.payload())
            identifier = response.json()['comparison_id']
            self.assertTrue(await run_one())
            a, b = await asyncio.gather(client.get('/api/stream/' + identifier), client.get('/api/stream/' + identifier))
            self.assertIn('event: done', a.text); self.assertEqual(a.text, b.text)
            replay = await client.get('/api/stream/' + identifier, headers={'Last-Event-ID': '1'})
            self.assertNotIn('id: 1\n', replay.text); self.assertIn('event: done', replay.text)
            self.assertEqual((await client.get('/api/stream/' + identifier, headers={'Last-Event-ID': 'bad'})).status_code, 400)
            self.assertEqual((await client.get('/api/research-status/' + identifier)).json()['status'], 'done')
            result = (await client.get('/api/comparison/' + identifier)).json()
            sku = result['products'][0]['id']
            self.assertEqual((await client.get('/api/product/' + sku)).status_code, 422)
            self.assertEqual((await client.get('/api/product/' + sku, params={'comparison_id': identifier})).status_code, 200)
            self.assertEqual((await client.get('/api/product/' + sku, params={'comparison_id': 'unrelated'})).status_code, 404)
        script = 'from data import jobs,runtime; from agents.orchestrator import get_comparison; import sys; assert jobs.status(sys.argv[1])["status"]=="done"; assert jobs.events(sys.argv[1])[-1][1]["type"]=="done"; assert get_comparison(sys.argv[1]).products; print("fresh-process result/events pass")'
        environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'backend'))
        probe = subprocess.run([sys.executable, '-c', script, identifier], env=environment, capture_output=True, text=True, timeout=20)
        self.assertEqual(probe.returncode, 0, probe.stderr)

    async def test_vectors_survive_new_store_filter_and_space(self):
        vector = [1.] + [0.] * 767
        def chunk(identifier, product, embedding):
            return Chunk(id=identifier, product_id=product, source_id=identifier, source_type='secondary', url='https://www.paklap.pk/test', content='RAM: 16 GB', embedding=embedding, fetched_at='', origin='curated', claims=[{'key': 'ram', 'value': '16 GB'}])
        store = DurableVectorStore('test-space')
        await store.upsert([chunk('a', 'one', vector), chunk('b', 'two', vector)])
        reopened = DurableVectorStore('test-space')
        self.assertEqual([c.id for c in await reopened.search(vector, product_id='one')], ['a'])
        self.assertEqual(await DurableVectorStore('different-space').for_product('one'), [])
        with self.assertRaises(ValueError): await store.upsert([chunk('bad', 'one', [float('nan')] * 768)])
        with self.assertRaises(ValueError): await store.upsert([chunk('bad', 'one', [1., 0.])])
        self.assertEqual([c.id for c in await reopened.for_product('one')], ['a'])
        environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'backend'))
        script = 'import asyncio; from rag.store import DurableVectorStore; c=asyncio.run(DurableVectorStore("test-space").for_product("one")); assert len(c)==1 and c[0].claims and len(c[0].embedding)==768; print("fresh-process vector/source pass")'
        probe = subprocess.run([sys.executable, '-c', script], env=environment, capture_output=True, text=True, timeout=20)
        self.assertEqual(probe.returncode, 0, probe.stderr)

    async def test_source_pipeline_keeps_unknown_prices_policies_and_secondary_evidence(self):
        from agents.orchestrator import run_pipeline, get_comparison, _comparison_store
        reqs = [Requirement(key='ram', operator='>=', value='16 GB', priority='must'), Requirement(key='budget', operator='<=', value='300000 PKR', priority='must')]
        with patch('agents.orchestrator.get_llm_provider', return_value=SourceProvider()):
            result = await run_pipeline('pakistan', reqs)
        self.assertEqual(len(result.products), 3)
        self.assertEqual(result.products[0].id, 'pk_hp_victus_fa2082wm')
        for p in result.products:
            self.assertEqual(p.price_info.currency, 'PKR'); self.assertTrue(p.price_info.is_stale)
            self.assertIsNone(p.price_info.fetched_at)
            self.assertEqual(result.requirement_matches[p.id][1], '?')
            self.assertTrue(all(e.source_type == 'secondary' and e.origin == 'curated' for e in p.evidence))
            self.assertTrue(all(s.status != 'verified' for s in p.specs))
            self.assertIsNone(p.return_policy.window_days)
            self.assertIn('Conditional', p.return_policy.conditions)
            if p.brand == 'HP': self.assertIsNone(p.warranty.duration_months)
            self.assertTrue(all(r.source_id is None for r in p.review_themes))
        self.assertTrue(any('three approved' in n for n in result.notices))
        _comparison_store.clear()
        self.assertEqual(get_comparison(result.id).model_dump(), result.model_dump())

    def test_listing_parser_rejects_wrong_identity_url_price_currency_and_unscoped_numbers(self):
        p = catalog()[0]
        html = '<h1>HP Victus FA2013DX</h1><div class="product-info-main"><meta itemprop="priceCurrency" content="PKR"><span data-price-type="finalPrice" data-price-amount="240000"></span></div><table id="product-attribute-specs-table"><tr><th>Installed RAM</th><td>8 GB</td></tr></table><div data-price-amount="1">Related laptop</div>'
        doc = FetchedDocument(url=p['canonical_url'], text=html, fetched_at='2026-10-04T00:00:00Z')
        parsed = parse_listing(doc, p)
        self.assertEqual(parsed['amount'], 240000); self.assertEqual(parsed['specs'], {'ram': '8 GB', 'brand': 'HP'})
        self.assertIsNone(parse_listing(FetchedDocument(url=p['canonical_url'], text=html.replace('FA2013DX', 'OTHER'), fetched_at=doc.fetched_at), p))
        self.assertIsNone(parse_listing(FetchedDocument(url='https://www.paklap.pk/other', text=html, fetched_at=doc.fetched_at), p))
        for altered in [html.replace('content="PKR"', 'content="USD"'), html.replace('data-price-type="finalPrice"', 'data-price-type="unrelated"')]:
            self.assertIsNone(parse_listing(FetchedDocument(url=doc.url, text=altered, fetched_at=doc.fetched_at), p)['amount'])

    async def test_blocked_source_never_becomes_fresh_and_robots_deny_skips_products(self):
        robots = FetchedDocument(url='https://www.paklap.pk/robots.txt', text='User-agent: *\nDisallow: /', fetched_at='2026-10-04T00:00:00Z')
        with patch.dict(os.environ, {'BUYWISE_SOURCE_REFRESH': 'true'}), patch('data.pakistan.fetch_document', new=AsyncMock(return_value=robots)) as fetch:
            notices = []; products = await prepare(SourceProvider(), notices)
        fetch.assert_awaited_once()
        self.assertTrue(all(p['observed_at'] == '' for p in products))
        self.assertEqual(sum('refresh unavailable' in n for n in notices), 3)

    async def test_job_failure_has_no_raw_exception_or_result(self):
        from worker import run_one
        jobs.submit('failed', self.payload())
        with patch('agents.orchestrator.run_pipeline', new=AsyncMock(side_effect=RuntimeError('SECRET-UPSTREAM-DETAIL'))):
            await run_one()
        self.assertEqual(jobs.status('failed')['status'], 'error')
        self.assertNotIn('SECRET', json.dumps(jobs.events('failed')))
        self.assertIsNone(runtime.load_comparison('failed'))

    async def test_body_limit_handles_chunked_and_malformed_lengths(self):
        import httpx
        from main import app
        async def chunks():
            yield b'x' * 6000
            yield b'y' * 6000
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            self.assertEqual((await client.post('/api/analyze-requirements', content=chunks())).status_code, 413)
            self.assertEqual((await client.post('/api/analyze-requirements', content=b'{}', headers={'Content-Length': 'bad'})).status_code, 400)
            self.assertEqual((await client.post('/api/analyze-requirements', content=b'x' * 12000)).status_code, 413)
            self.assertEqual((await client.get('/api/ready')).json()['status'], 'ok')

    async def test_abandoned_queue_expires_and_old_terminal_jobs_are_cleaned(self):
        jobs.submit('abandoned', self.payload())
        with runtime.connect(write=True) as db: db.execute('UPDATE bw_jobs SET created_at=? WHERE id=?', (time.time() - 7200, 'abandoned'))
        jobs.submit('next', self.payload())
        self.assertEqual(jobs.status('abandoned')['status'], 'error')
        self.assertEqual(jobs.events('abandoned')[-1][1]['code'], 'QUEUE_EXPIRED')
        with runtime.connect(write=True) as db:
            db.execute('UPDATE bw_jobs SET updated_at=? WHERE id=?', (time.time() - 90000, 'abandoned'))
            runtime.cleanup(db)
        self.assertIsNone(jobs.status('abandoned'))
        self.assertEqual(jobs.events('abandoned'), [])
