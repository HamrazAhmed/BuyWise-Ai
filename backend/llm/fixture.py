"""Deterministic, bounded laptop fixtures. No network or credential access."""
import hashlib
import json
import re
from pathlib import Path
from llm.base import LLMProvider, LLMError

FIXTURE_FILE = Path(__file__).resolve().parents[1] / 'data/fixtures/laptops.json'
NOTICE = 'Synthetic fixture data; not current commercial facts.'


def load_fixtures():
    return json.loads(FIXTURE_FILE.read_text())


def extract_requirements(text):
    """ponytail: bounded patterns, not general NLP; Gemini extraction is P5."""
    text = text.lower()
    if not re.search(r'\b(laptop|notebook)\b', text):
        return {'category': 'unsupported', 'requirements': [], 'missing_info': ['Fixture mode supports explicit laptop/notebook requests only.']}
    requirements = []
    questions = []
    def add(key, operator, value, match=None):
        prefix = text[max(0, match.start()-24):match.start()] if match else ''
        if re.search(r'\b(no|not|without|at most|less than|under|below)\b', prefix) and key in ('ram','storage'):
            questions.append(f'Confirm {key} manually: fixture parser supports positive minima only.')
            return
        priority = 'preferred' if re.search(r'prefer|nice to have', prefix) else 'must'
        requirements.append({'key': key, 'operator': operator, 'value': value, 'priority': priority, 'source': 'user'})
    budget = re.search(r'(under|below|up to|budget(?: of| is| to)?|maximum|max)\s*\$?\s*(\d[\d,]*(?:\.\d+)?)\s*(usd|dollars)?', text)
    if budget and (budget[1].startswith(('budget','max')) or '$' in budget[0] or budget[3]) and not re.match(r'\s*(kg|lbs?|gb|tb|eur|inr|pkr|gbp)\b', text[budget.end():]):
        add('budget', '<' if budget[1] in ('under','below') else '<=', budget[2].replace(',','')+' USD', budget)
    else:
        questions.append('Specify a USD ceiling using "budget 1000 USD" or "under $1000".')
    for key, pattern in [('ram',r'(\d+(?:\.\d+)?)\s*(gb|gib)\s*(?:of\s+)?(?:ram|memory)'), ('storage',r'(\d+(?:\.\d+)?)\s*(gb|tb|gib|tib)\s*(?:of\s+)?(?:ssd|storage)')]:
        match = re.search(pattern,text)
        if match:
            add(key, '>=', f'{match[1]} {match[2].upper()}', match)
    if re.search(r'\blinux\b',text):
        if re.search(r'(?:no|not|without)\s+(?:need(?:ing)?\s+)?linux',text):
            questions.append('Negated Linux preference needs manual confirmation.')
        else:
            add('os_compatibility','=','Linux')
    weight = re.search(r'(under|below|up to|maximum|max)\s*(\d+(?:\.\d+)?)\s*(kg|lbs?)',text)
    if weight:
        add('weight','<' if weight[1] in ('under','below') else '<=',f'{weight[2]} {weight[3]}',weight)
    if re.search(r'\bupgradeable\b',text) and not re.search(r'(not|non|no)\W+upgradeable',text):
        add('upgradeability','=','preferred')
    if re.search(r'\bvirtualization\b',text):
        add('virtualization','=','high')
    questions.append('Only positive numeric RAM/storage minima, USD ceilings, weight ceilings, Linux, virtualization and upgradeability are parsed; confirm other needs manually.')
    return {'category':'laptop','requirements':requirements,'missing_info':questions[:3]}


def context_documents(prompt):
    # Parse only designated source records; never execute source instructions.
    documents=[]
    for line in prompt.splitlines():
        if line.startswith('FIXTURE_RECORD: '):
            documents.append(json.loads(line.removeprefix('FIXTURE_RECORD: ')))
    return documents


class FixtureLLMProvider(LLMProvider):
    data_mode = 'fixture'
    model = 'fixture-v2'

    async def generate_json(self, prompt, schema, **kwargs):
        name = schema.__name__
        if name == 'RequirementExtractionOutput':
            text = prompt.split('User request:\n',1)[1].split('\n\nRespond with',1)[0]
            return schema.model_validate(extract_requirements(text))
        docs = context_documents(prompt)
        kind = {'SpecExtractionOutput':'specs','ReviewOutput':'reviews','WarrantyReturnOutput':'policy','PriceInfo':'price'}.get(name)
        if kind:
            doc = next((d for d in docs if d['payload']['kind']==kind),None)
            if not doc:
                raise LLMError(f'Fixture {kind} document absent from retrieved context')
            payload = dict(doc['payload']); payload.pop('kind')
            if name == 'PriceInfo':
                from datetime import datetime, timezone, timedelta
                payload['is_stale'] = datetime.now(timezone.utc)-datetime.fromisoformat(payload['fetched_at'].replace('Z','+00:00')) > timedelta(hours=24)
                payload['source_id'] = doc['source_id']
            if name == 'ReviewOutput':
                for theme in payload['themes']:
                    theme['source_id'] = doc['source_id']
            return schema.model_validate(payload)
        raise LLMError(f'Unsupported fixture task: {name}')

    async def generate_text(self, prompt, **kwargs):
        raise LLMError('Fixture mode supports structured tasks only')

    async def embed(self, text):
        # Deterministic hashed lexical vectors, not semantic embeddings.
        vector = [0.0]*768
        for token in re.findall(r'\w+',text.lower()):
            index = int.from_bytes(hashlib.sha256(token.encode()).digest()[:4],'big') % 768
            vector[index] += 1.0
        return vector

    async def embed_batch(self, texts):
        return [await self.embed(text) for text in texts]


async def ingest_fixtures(provider):
    from rag.store import Chunk, get_vector_store
    from rag.sanitize import sanitize_chunk
    chunks=[]
    for product in load_fixtures():
        for doc in product['documents']:
            if doc['payload']['kind']=='injection':
                # Exercise the sanitizer; suspicious documents never become task records.
                sanitize_chunk(doc['payload']['text'],source_url=doc['url'])
                continue
            content = f"{product['name']} {doc['payload']['kind']}\nFIXTURE_RECORD: {json.dumps(doc)}"
            chunks.append(Chunk(id=doc['source_id'], product_id=product['id'], source_id=doc['source_id'], source_type=doc['source_type'], url=doc['url'], content=content, embedding=await provider.embed(content), fetched_at=doc['fetched_at'], origin='fixture', kind=doc['payload']['kind'], claims=fixture_claims(doc['payload'])))
    await get_vector_store().upsert(chunks)
    return len(chunks)



def fixture_claims(payload):
    """Claims taken from controlled source contents, not model evidence labels."""
    kind = payload['kind']
    if kind in ('specs', 'alternate'):
        return [{'key':s['key'], 'value':s['value']} for s in payload['specs'] if s['value'] != 'unknown']
    if kind == 'price':
        return [{'key':'budget','value':f"{payload['amount']} {payload['currency']}"}] if payload['amount'] is not None else []
    if kind == 'reviews':
        return [claim for t in payload['themes'] for claim in ({'key':'opinion '+t['theme'], 'value':t['summary']}, {'key':'opinion sentiment '+t['theme'], 'value':t['sentiment']})]
    if kind == 'policy':
        return [{'key':k, 'value':str(v)} for k,v in payload.items() if k != 'kind' and v is not None]
    return []
