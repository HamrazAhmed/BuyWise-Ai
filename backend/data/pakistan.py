"""Approved Pakistan listings: source snapshots plus bounded, robots-aware refresh."""
import asyncio
import json
import os
import re
from pathlib import Path
from urllib.robotparser import RobotFileParser
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
from rag.store import Chunk, get_vector_store
from rag.safe_fetch import fetch_document
from agents.matching import money

HOSTS = {'paklap.pk'}
POLICY_URL = 'https://www.paklap.pk/warranty-returns'
# This is conditional replacement, not a general seven-day refund entitlement.
RETURN_CONDITIONS = 'Conditional defect/wrong-specification replacement only; no change-of-mind refund. Physical damage must be reported same day; body/screen issues within two days. Company-sealed exclusions apply. Confirm current seller terms.'


def catalog():
    products = json.loads((Path(__file__).parent / 'pakistan_laptops.json').read_text())
    for p in products:
        if p['market'] != 'PK' or p['currency'] != 'PKR' or not p['canonical_url'].startswith('https://www.paklap.pk/'):
            raise ValueError('Invalid regional catalog record')
        p['source_id'] = p['id'] + '__listing'
        p['specs'] = identity_specs(p)
    return products


def identity_specs(product):
    """Expose listed identity and explicit GPU memory; never infer missing VRAM."""
    specs = dict(product.get('specs', {}))
    if product.get('brand'):
        specs['brand'] = product['brand']
    gpu = str(specs.get('gpu') or '')
    memory = re.search(r'\b(\d+(?:\.\d+)?)\s*GB\b', gpu, re.I)
    if memory:
        specs['vram'] = memory[1] + ' GB'
    return specs


def parse_listing(document, product):
    """Only the exact SKU's heading, main price and specification table qualify."""
    if document.url.rstrip('/') != product['canonical_url'].rstrip('/'):
        return None
    soup = BeautifulSoup(document.text, 'html.parser')
    heading = soup.find('h1')
    if not heading or product['model_number'].lower() not in heading.get_text(' ', strip=True).lower():
        return None
    table = soup.find('table', id='product-attribute-specs-table')
    if not table:
        return None
    fields = {}
    aliases = {'installed ram': 'ram', 'ram': 'ram', 'ssd': 'storage', 'hard drive size': 'storage', 'processor type': 'cpu', 'graphics memory': 'gpu', 'weight': 'weight', 'operating system': 'os'}
    for row in table.find_all('tr'):
        cells = row.find_all(['th', 'td'])
        if len(cells) != 2:
            continue
        key = aliases.get(cells[0].get_text(' ', strip=True).lower())
        value = cells[1].get_text(' ', strip=True)
        from rag.sanitize import is_injection_attempt
        if key and (len(value) > 500 or is_injection_attempt(value)):
            return None
        if key and value and value != '-':
            if key in fields and fields[key] != value:
                from agents.evidence import normalized
                # Ambiguous synonyms stay unconfirmed; do not silently pick one.
                if fields[key] is None or normalized(key, fields[key]) != normalized(key, value):
                    fields[key] = None
            else:
                fields[key] = value
    price_nodes = soup.select('.product-info-main [data-price-type="finalPrice"][data-price-amount]')
    values = {money(node.get('data-price-amount', '') + ' PKR') for node in price_nodes}
    values.discard(None)
    currency = soup.select_one('.product-info-main [itemprop="priceCurrency"]')
    price_container = soup.select_one('.product-info-main .price-box')
    pkr = (currency and currency.get('content') == 'PKR') or (not currency and price_container and re.search(r'\b(PKR|Rs\.)', price_container.get_text(' ', strip=True), re.I))
    # Without exactly one scoped price, keep it unavailable.
    amount = next(iter(values))[0] if len(values) == 1 and pkr else None
    if not fields:
        return None
    result = dict(product, specs=fields, amount=amount, observed_at=document.fetched_at, origin='web')
    # The validated exact-SKU heading confirms identity; the GPU field gives VRAM.
    result['specs'] = identity_specs(result)
    if fields.get('os') and re.search(r'\bDOS\b', soup.get_text(' ', strip=True), re.I) and 'DOS' not in fields['os'].upper():
        result['specs']['os'] = None
    # A refreshed product page does not refresh its cached warranty/policy facts.
    result['policy_observed_at'] = ''
    return result


def chunks_for(product):
    source = product['source_id']
    observed = product['observed_at']
    origin = product.get('origin', 'curated')
    claims = [{'key': k, 'value': str(v)} for k, v in product['specs'].items() if v is not None]
    if product['amount'] is not None:
        claims.append({'key': 'budget', 'value': f"{product['amount']} PKR"})
    content = product['name'] + '\n' + '\n'.join(f"{c['key']}: {c['value']}" for c in claims)
    if origin == 'curated':
        content += '\nManual snapshot inspected ' + product['inspected_on'] + '; original live observation timestamp unknown.'
    listing = Chunk(id=source, product_id=product['id'], source_id=source, source_type='secondary', url=product['canonical_url'], content=content, embedding=[], fetched_at=observed, origin=origin, kind='specs', claims=claims, title=product['name'] + ' — Paklap listing')
    warranty_claims = [{'key': 'warranty_coverage', 'value': product['warranty_coverage']}, {'key': 'warranty_conditions', 'value': product['warranty_conditions']}]
    if product['warranty_months'] is not None:
        warranty_claims.append({'key': 'warranty_months', 'value': str(product['warranty_months'])})
    warranty = Chunk(id=product['id'] + '__warranty', product_id=product['id'], source_id=product['id'] + '__warranty', source_type='secondary', url=product['canonical_url'], content='\n'.join(f"{c['key']}: {c['value']}" for c in warranty_claims), embedding=[], fetched_at='', origin='curated', kind='policy', claims=warranty_claims, title='Paklap warranty snapshot — verify selected option')
    policy = Chunk(id=product['id'] + '__returns', product_id=product['id'], source_id=product['id'] + '__returns', source_type='secondary', url=POLICY_URL, content='return_conditions: ' + RETURN_CONDITIONS, embedding=[], fetched_at='', origin='curated', kind='policy', claims=[{'key': 'return_conditions', 'value': RETURN_CONDITIONS}], title='Paklap conditional replacement snapshot')
    return [listing, warranty, policy]


async def prepare(llm, notices):
    store = get_vector_store()
    products = catalog()
    all_chunks, all_pending = [], []
    robots = None
    refresh = os.getenv('BUYWISE_SOURCE_REFRESH', 'true').lower() == 'true'
    if refresh:
        doc = await fetch_document('https://www.paklap.pk/robots.txt', HOSTS, 5)
        if doc:
            robots = RobotFileParser(); robots.parse(doc.text.splitlines())
    for index, p in enumerate(products):
        previous = await store.for_product(p['id'])
        listing = next((c for c in previous if c.id == p['source_id'] and c.origin == 'web' and c.url == p['canonical_url'] and c.source_type == 'secondary'), None)
        fresh = False
        if listing:
            try:
                age = datetime.now(timezone.utc) - datetime.fromisoformat(listing.fetched_at.replace('Z', '+00:00'))
                fresh = timedelta(0) <= age < timedelta(hours=24)
            except (ValueError, TypeError):
                pass
            p['specs'] = {c['key']: c['value'] for c in listing.claims if c['key'] != 'budget'}
            recorded = next((money(c['value']) for c in listing.claims if c['key'] == 'budget'), None)
            p.update(amount=recorded[0] if recorded else None, observed_at=listing.fetched_at, origin='web')
            p['specs'] = identity_specs(p)
        if refresh and not fresh:
            document = await fetch_document(p['canonical_url'], HOSTS, 5) if robots and robots.can_fetch('BuyWiseAI', p['canonical_url']) else None
            updated = parse_listing(document, p) if document else None
            if updated:
                p = updated
            else:
                notices.append(f"{p['name']}: source refresh unavailable or unverified; retained attributed snapshot, not a current price.")
        chunks = chunks_for(p)
        pending = []
        for chunk in chunks:
            old = next((c for c in previous if c.id == chunk.id and c.content == chunk.content and c.embedding), None)
            if old:
                chunk.embedding = old.embedding
            else:
                pending.append(chunk)
        all_chunks.extend(chunks)
        all_pending.extend(pending)
        products[index] = p
    if all_pending:
        try:
            vectors = await llm.embed_batch([c.content for c in all_pending])
            if len(vectors) == len(all_pending):
                for c, vector in zip(all_pending, vectors): c.embedding = vector
        except Exception:
            notices.append('Source embedding unavailable; lexical retrieval will be used.')
    await store.upsert(all_chunks)
    notices.append('Pakistan/PKR research covers three approved Paklap SKUs only; it is not a market-wide search. Retailer snapshots are secondary evidence. Undated prices are stale/unknown; confirm current price and selected warranty with seller. Review data and manufacturer verification remain unavailable.')
    return products
