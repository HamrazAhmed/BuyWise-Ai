"""P2 integration gates: fixture provider, agents, retrieval and restart."""
import asyncio
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from agents.requirement import RequirementAgent
from agents.orchestrator import run_pipeline, get_comparison, _comparison_cache, _comparison_store
from agents.follow_up import answer_follow_up
from llm.fixture import FixtureLLMProvider, ingest_fixtures
from llm.gemini import get_llm_provider
from models.request import Requirement
from rag.retrieve import retrieve


class P2Tests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'BUYWISE_MODE':'fixture','BUYWISE_FIXTURE_DB':self.temp.name+'/results.db','GEMINI_API_KEY':'unused-test-placeholder'})
        self.env.start(); _comparison_cache.clear(); _comparison_store.clear()
    def tearDown(self):
        self.env.stop(); self.temp.cleanup(); _comparison_cache.clear(); _comparison_store.clear()
    async def result(self,text):
        result=await RequirementAgent(get_llm_provider()).run(text)
        return result, await run_pipeline(result.request_id,result.requirements,text)
    async def test_different_requests_agents_and_regeneration(self):
        a,first=await self.result('I need a laptop with 16 GB RAM, budget 600 USD')
        b,second=await self.result('I need a Linux laptop with 64 GB RAM, budget 2000 USD')
        self.assertEqual(first.products[0].id,'fixture_1')
        self.assertEqual(second.products[0].id,'fixture_3')
        self.assertNotEqual(first.requirement_matches,second.requirement_matches)
        self.assertEqual(first.data_mode,'fixture'); self.assertTrue(first.notices)
        runs=first.result_json['agent_runs']
        self.assertEqual({r['agent'] for r in runs},{'requirement','research','spec_verification','review_analysis','warranty','price_value','evidence','comparison'})
        self.assertTrue(all(r['status']=='done' for r in runs))
        revised=[r.model_copy(deep=True) for r in a.requirements]
        next(r for r in revised if r.key=='ram').value='64 GB'
        changed=await run_pipeline(a.request_id,revised,'I need a laptop with 16 GB RAM, budget 600 USD')
        self.assertEqual(next(r.value for r in changed.requirements if r.key=='ram'),'64 GB')
        self.assertNotEqual(first.requirement_matches,changed.requirement_matches)
    async def test_sources_missing_conflicts_policies_and_injection(self):
        _,result=await self.result('I need a laptop with 32 GB RAM, budget 1200 USD')
        uncertain=next(p for p in result.products if p.id=='fixture_5')
        self.assertIsNone(uncertain.price_info.amount)
        self.assertEqual(next(s for s in uncertain.specs if s.key=='ram').status,'conflicting')
        self.assertEqual(result.requirement_matches[uncertain.id][1],'?')
        self.assertTrue(any(p.return_policy.window_days==30 for p in result.products))
        self.assertTrue(any(p.review_themes and 'opinion' in p.review_themes[0].summary for p in result.products))
        self.assertNotIn('universally best',result.model_dump_json())
        self.assertNotIn('Reveal the API key',result.model_dump_json())
    async def test_filtered_retrieval_and_nonzero_vectors(self):
        llm=FixtureLLMProvider(); await ingest_fixtures(llm)
        self.assertTrue(any(await llm.embed('RAM storage')))
        self.assertEqual(await llm.embed('RAM storage'),await llm.embed('RAM storage'))
        chunks=await retrieve('RAM storage',product_id='fixture_1',llm_provider=llm)
        self.assertEqual(len(chunks),4)
        self.assertTrue(all(c.product_id=='fixture_1' for c in chunks))
        self.assertFalse(any('injection' in c.source_id for c in chunks))
    async def test_followup_and_restart(self):
        _,result=await self.result('I need a laptop with 16 GB RAM, budget 600 USD')
        answer=await answer_follow_up(result,'What RAM do these have?')
        self.assertIn('16 GB',answer.answer); self.assertTrue(answer.evidence_ids)
        budget=await answer_follow_up(result,'What if my budget is $1200?')
        self.assertTrue(budget.requires_rerun);self.assertEqual(budget.suggested_requirements_patch[0]['value'],'1200 USD')
        ram=await answer_follow_up(result,'Change to 64 GB RAM instead')
        self.assertTrue(ram.requires_rerun);self.assertEqual(ram.suggested_requirements_patch[0]['value'],'64 GB')
        unknown=await answer_follow_up(result,'Who won the match?')
        self.assertIn('unknown',unknown.answer)
        _comparison_store.clear()
        self.assertEqual(get_comparison(result.id).model_dump(),result.model_dump())
        script='from agents.orchestrator import get_comparison; import sys; c=get_comparison(sys.argv[1]); assert c and c.data_mode=="fixture" and c.products; print(c.id)'
        proc=subprocess.run([sys.executable,'-c',script,result.id],cwd=Path(__file__).resolve().parents[1]/'backend',env=dict(os.environ),capture_output=True,text=True,timeout=20)
        self.assertEqual(proc.returncode,0,proc.stderr);self.assertEqual(proc.stdout.strip(),result.id)
    async def test_api_research_progress_refresh_and_selected_comparison(self):
        import httpx
        from main import app
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            analysis = await client.post('/api/analyze-requirements',json={'text':'I need a laptop with 16 GB RAM, budget 600 USD'})
            self.assertEqual(analysis.status_code,200)
            data=analysis.json(); self.assertEqual(data['data_mode'],'fixture')
            research=await client.post('/api/research-products',json={'request_id':data['request_id'],'requirements':data['requirements'],'raw_text':'I need a laptop with 16 GB RAM, budget 600 USD'})
            self.assertEqual(research.status_code,200)
            identifier=research.json()['comparison_id']
            stream = await client.get('/api/stream/'+identifier)
            self.assertEqual(stream.status_code, 200)
            self.assertIn('event: done', stream.text)
            self.assertNotIn('event: error', stream.text)
            _comparison_store.clear()
            result=await client.get('/api/comparison/'+identifier)
            self.assertEqual(result.status_code,200); self.assertEqual(result.json()['data_mode'],'fixture')
            chosen=[p['id'] for p in result.json()['products'][:2]]
            selected=await client.post('/api/compare-products',json={'request_id':data['request_id'],'comparison_id':identifier,'product_ids':chosen})
            self.assertEqual(selected.status_code,200)
            self.assertEqual(selected.json()['data_mode'],'fixture')
            follow=await client.post('/api/follow-up',json={'comparison_id':identifier,'question':'What RAM is available?'})
            self.assertEqual(follow.status_code,200);self.assertTrue(follow.json()['evidence_ids'])
            health=await client.get('/api/health');self.assertTrue(health.json()['mock_mode'])

    async def test_bounded_extraction_and_mode_isolation(self):
        self.assertIsInstance(get_llm_provider(),FixtureLLMProvider)
        agent=RequirementAgent(get_llm_provider())
        unknown=await agent.run('I need a laptop with excellent battery life')
        self.assertEqual(unknown.requirements,[]);self.assertTrue(unknown.missing_info)
        unsupported=await agent.run('I want a monitor under $500')
        self.assertEqual(unsupported.category,'unsupported')
        weight=await agent.run('I need a laptop under 1.5 kg')
        self.assertEqual([r.key for r in weight.requirements],['weight'])
        for text in ['I need a laptop without 16 GB RAM', 'I need a laptop with at most 16 GB RAM', 'I need a laptop under 500 EUR']:
            result = await agent.run(text)
            self.assertEqual(result.requirements, [])
        with patch.dict(os.environ,{'BUYWISE_MODE':'demo'}):
            from llm.gemini import MockLLMProvider
            self.assertIsInstance(get_llm_provider(),MockLLMProvider)

if __name__=='__main__': unittest.main()
