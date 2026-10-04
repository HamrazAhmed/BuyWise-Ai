"""Opt-in small Pakistan/PKR provider + durable pipeline gate. Never prints keys."""
import argparse
import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'backend'))

async def check():
    from agents.requirement import RequirementAgent
    from llm.gemini import get_llm_provider
    from data import runtime, jobs
    from worker import run_one
    from agents.orchestrator import get_comparison, _comparison_store
    from agents.follow_up import answer_follow_up
    from rag.store import get_vector_store
    from rag.retrieve import retrieve
    started = time.monotonic()
    provider = get_llm_provider()
    try:
        result = await RequirementAgent(provider).run('I need a laptop in Pakistan under 300000 PKR with at least 16 GB RAM for programming.')
        ceiling = next(r for r in result.requirements if r.key == 'budget')
        assert 'PKR' in ceiling.value and ceiling.operator == '<'
        identifier = str(uuid.uuid4())
        jobs.submit(identifier, {'request_id': result.request_id, 'requirements': [r.model_dump(mode='json') for r in result.requirements], 'raw_text': 'Pakistan laptop under 300000 PKR with 16 GB RAM'})
        assert await run_one()
        assert jobs.status(identifier)['status'] == 'done', 'Live worker did not complete'
        _comparison_store.clear()
        comparison = get_comparison(identifier)
        assert comparison and comparison.data_mode == 'live' and len(comparison.products) == 3
        for p in comparison.products:
            assert p.price_info.currency == 'PKR' and p.price_info.is_stale
            assert all(e.source_type == 'secondary' and e.source_url.startswith('https://www.paklap.pk/') for e in p.evidence)
            assert all(set(s.evidence_ids) <= {e.id for e in p.evidence} for s in p.specs)
            assert next(s for s in p.specs if s.key.lower() == 'ram').status == 'supported'
        chunks = await retrieve('HP Victus RAM specification', product_id='pk_hp_victus_fa2082wm', llm_provider=provider)
        assert chunks and chunks[0].retrieval_mode == 'vector'
        assert chunks[0].kind == 'specs' and any(c['key'] == 'ram' and c['value'] == '16 GB' for c in chunks[0].claims)
        answer = await answer_follow_up(comparison, 'What if my budget is PKR 350000?')
        assert answer.suggested_requirements_patch[0]['value'] == '350000 PKR'
        return {'status': 'pass', 'market': 'Pakistan / PKR', 'comparison_id': identifier, 'products': len(comparison.products), 'storage': 'postgresql/pgvector' if runtime.postgres() else 'local-sqlite', 'checks': ['actual Gemini PKR extraction', 'durable worker pipeline', 'source-attributed PKR prices remain stale/unknown', 'three exact SKU RAM claims supported by secondary records', 'semantic query retrieves listing RAM evidence', 'stored follow-up preserves PKR'], 'notices': comparison.notices, 'elapsed_seconds': round(time.monotonic() - started, 2)}
    finally:
        await provider.aclose()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--live', action='store_true'); args = parser.parse_args()
    if not args.live: parser.error('--live is required because this makes billable provider and source requests')
    from dotenv import load_dotenv
    load_dotenv(root / '.env', override=False)
    os.environ['BUYWISE_MODE'] = 'gemini'; os.environ['BUYWISE_MARKET'] = 'PK'; os.environ['BUYWISE_INLINE_WORKER'] = 'false'
    try:
        report = asyncio.run(check())
    except Exception as exc:
        report = {'status': 'failed', 'error_type': type(exc).__name__, 'message': 'A live gate failed; no secret/upstream payload is recorded.'}
    (root / 'Doc/P6-LIVE-CHECKS.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    sys.exit(0 if report['status'] == 'pass' else 1)
