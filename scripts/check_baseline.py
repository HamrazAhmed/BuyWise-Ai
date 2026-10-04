"""Read-only, credential-free baseline checks; exits nonzero for known failures."""
import asyncio
import ast
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
os.environ.pop('GEMINI_API_KEY', None)
logging.disable(logging.CRITICAL)

async def main():
    from httpx import ASGITransport, AsyncClient
    from main import app
    from data.demo_cache import DEMO_REQUIREMENTS
    from agents.comparison import ComparisonAgent, _match_requirement
    from agents.base import RunState
    from agents.price_value import _extract_budget
    from models.request import Requirement
    from models.product import Product, Spec
    from rag.sanitize import strip_html
    failures = []

    def check(name, passed):
        print(('PASS' if passed else 'FAIL') + ': ' + name)
        if not passed:
            failures.append(name)

    for path in (ROOT / 'backend').rglob('*.py'):
        ast.parse(path.read_text(), filename=str(path))
    check('Python syntax', True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        r = await client.get('/api/health')
        check('ASGI health', r.status_code == 200)
        r = await client.post('/api/analyze-requirements', json={'text': 'short'})
        check('Invalid intake rejected', r.status_code == 422)
        r = await client.post('/api/analyze-requirements', json={'text': 'I need a laptop for school'})
        check('No-key analysis fallback', r.status_code == 200)
        r = await client.post('/api/research-products', json={'request_id': 'baseline', 'requirements': [x.model_dump(mode='json') for x in DEMO_REQUIREMENTS]})
        cid = r.json()['comparison_id']
        await asyncio.sleep(2.5)
        r = await client.get('/api/comparison/' + cid)
        check('Research result retrieved by returned ID', r.status_code == 200)
        r = await client.options('/api/research-products', headers={'Origin': 'http://localhost:3000', 'Access-Control-Request-Method': 'POST'})
        check('Local CORS preflight', r.status_code == 200 and r.headers.get('access-control-allow-origin') == 'http://localhost:3000')
    check('Budget parses uppercase USD', _extract_budget(DEMO_REQUIREMENTS) == 1000)
    req = Requirement(key='ram', operator='>', value='32 GB', priority='must')
    spec = Spec(key='RAM', value='32 GB', status='supported', evidence_ids=['fixture'])
    check('Strict RAM operator respects boundary', _match_requirement(req, [spec])[0] == '✕')
    state = RunState(requirements=DEMO_REQUIREMENTS, candidate_products=[Product(id='fixture', name='Fixture')])
    state.prices['fixture'] = {'price_info': None}
    try:
        await ComparisonAgent().run(state)
        check('Comparison constructs without undeclared fields', True)
    except Exception as e:
        print('Comparison exception:', type(e).__name__)
        check('Comparison constructs without undeclared fields', False)
    try:
        strip_html('<html><body>Known source content</body></html>')
        check('HTML sanitizer parser available', True)
    except Exception as e:
        print('Sanitizer exception:', type(e).__name__)
        check('HTML sanitizer parser available', False)
    print('Baseline failures:', len(failures))
    return bool(failures)

if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
