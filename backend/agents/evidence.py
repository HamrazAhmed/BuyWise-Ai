"""Validate claims against product-scoped records; model labels are not proof."""
import re
import time
from datetime import datetime, timezone, timedelta
from agents.base import AgentBase
from agents.matching import canonical_key, quantity, money
from models.product import Spec, Evidence, ConflictingValue, ReviewTheme
from rag.store import get_vector_store
from rag.sanitize import is_injection_attempt


def normalized(key, value):
    canonical = canonical_key(key)
    text = str(value).strip().lower()
    if canonical == 'budget':
        parsed = money(text)
        if parsed: return ('money', round(parsed[0], 8), parsed[1])
    if canonical in ('ram','storage','weight','display','budget'):
        if re.fullmatch(r'\d+(?:\.\d+)?',text):
            unit=key.lower().replace('_',' ').split()[-1]
            if unit in ('gb','tb','kg','lbs','inches'): text+=' '+unit
        number=quantity(text,canonical)
        if number is not None: return ('quantity',round(number,8))
    if canonical=='upgradeability':
        if text in ('false','not upgradeable','non-upgradeable'): return ('bool',False)
        if text in ('true','upgradeable'): return ('bool',True)
    return ('text',re.sub(r'\s+',' ',text))


def source_claims(chunk):
    if chunk.claims:
        return chunk.claims
    # Conservative plain-text fields; unrelated mentions of a number are not proof.
    return [{'key':m[1].strip(),'value':m[2].strip()} for m in re.finditer(r'^\s*([^:\n]{1,70}):\s*([^\n]+)$',chunk.content,re.M)]


def relevant_claims(key,chunks):
    return [(chunk,c) for chunk in chunks for c in source_claims(chunk)
            if canonical_key(c['key'])==canonical_key(key) and str(c['value']).lower() not in ('unknown','none','null','')]


def has_value(chunk,key,value):
    return any(normalized(c['key'],c['value'])==normalized(key,value) for _,c in relevant_claims(key,[chunk]))


def verify_spec(spec,chunks):
    cited=[c for c in chunks if c.id in spec.evidence_ids or c.source_id in spec.evidence_ids]
    matching=[c for c in cited if has_value(c,spec.key,spec.value)]
    records=relevant_claims(spec.key,chunks)
    values={normalized(c['key'],c['value']) for _,c in records}
    if len(values)>1 and matching:
        conflicts=[]
        seen=set()
        for chunk,claim in records:
            normalized_value=normalized(claim['key'],claim['value'])
            if normalized_value not in seen:
                conflicts.append(ConflictingValue(value=str(claim['value']),source_url=chunk.url,source_type=chunk.source_type))
                seen.add(normalized_value)
        return Spec(key=spec.key,value=spec.value,status='conflicting',
                    evidence_ids=list(dict.fromkeys(c.id for c,_ in records)),conflicting_values=conflicts)
    if not matching:
        return Spec(key=spec.key,value='unknown',status='insufficient')
    def observed_primary(chunk):
        try:
            observed=datetime.fromisoformat(chunk.fetched_at.replace("Z", "+00:00"))
            return chunk.origin=="web" and chunk.source_type=="primary" and observed.tzinfo is not None and observed<=datetime.now(timezone.utc)
        except (ValueError, TypeError):
            return False
    primary=any(observed_primary(c) for c in matching)
    return Spec(key=spec.key,value=spec.value,status='verified' if primary else 'supported',evidence_ids=list(dict.fromkeys(c.id for c in matching)))


def resolve(chunks,identifier):
    return next((c for c in chunks if c.id==identifier or c.source_id==identifier),None)


def snapshot_chunks(product):
    from rag.store import Chunk
    return [Chunk(id=e.id,source_id=e.source_id or e.id,product_id=product.id,source_type=e.source_type,
                  url=e.source_url,content=e.snippet,embedding=[],fetched_at=e.fetched_at,origin=e.origin,
                  kind=e.kind,title=e.title,claims=[c.model_dump() for c in e.claims])
            for e in product.evidence if e.product_id==product.id and not is_injection_attempt(e.snippet)]


class EvidenceVerificationAgent(AgentBase):
    name='evidence'

    async def run(self,state, *, snapshot=False):
        run=self._start_run(state);start=time.perf_counter()
        try:
            await state.emit_progress('Checking claim values against source records',step='evidence')
            store=get_vector_store()
            for product in state.candidate_products:
                chunks=snapshot_chunks(product) if snapshot else [c for c in await store.for_product(product.id) if not is_injection_attempt(c.content)]
                product.evidence=[Evidence(id=c.id,product_id=c.product_id,chunk_id=c.id,source_id=c.source_id,
                    title=c.title or f'{product.name}: {c.kind} ({c.origin})',kind=c.kind,source_url=c.url,source_type=c.source_type,
                    snippet=c.content,claims=source_claims(c),fetched_at=c.fetched_at,origin=c.origin) for c in chunks]
                state.verified_specs[product.id]=[verify_spec(s,chunks) for s in state.verified_specs.get(product.id,[])]
                for spec in state.verified_specs[product.id]:
                    for identifier in spec.evidence_ids:
                        state.evidence_by_claim.setdefault(identifier,[]).append(spec.key)
                reviews=[]
                for review in state.review_themes.get(product.id,[]):
                    chunk=resolve(chunks,review.source_id)
                    if chunk and chunk.kind=='reviews' and has_value(chunk,'opinion '+review.theme,review.summary.removeprefix('Opinion: ')):
                        sentiment=review.sentiment if has_value(chunk,'opinion sentiment '+review.theme,review.sentiment) else 'neutral'
                        reviews.append(ReviewTheme(theme=review.theme,sentiment=sentiment,summary='Opinion: '+review.summary.removeprefix('Opinion: '),source_id=chunk.id))
                state.review_themes[product.id]=reviews or [ReviewTheme(theme='Overall',sentiment='neutral',summary='Insufficient attributable review opinion data.')]
                policy=state.warranties.get(product.id)
                if policy:
                    warranty,returns=policy
                    if warranty:
                        chunk=resolve(chunks,warranty.source_id)
                        checks={'duration_months':'warranty_months','coverage':'warranty_coverage','conditions':'warranty_conditions'}
                        for field,key in checks.items():
                            value=getattr(warranty,field)
                            if value is not None and (not chunk or not has_value(chunk,key,value)):
                                setattr(warranty,field,None)
                        warranty.source_id=chunk.id if chunk else None
                        warranty.completeness='partial' if warranty.duration_months is not None or warranty.coverage else 'unknown'
                    if returns:
                        chunk=resolve(chunks,returns.source_id)
                        if not chunk or not has_value(chunk,'return_window_days',returns.window_days): returns.window_days=None
                        if not chunk or not has_value(chunk,'return_conditions',returns.conditions): returns.conditions='Seller-dependent — verify before purchase'
                        returns.source_id=chunk.id if chunk else None
                        returns.seller_dependent=True  # No regional/seller applicability is proven locally.
                price_data=state.prices.get(product.id,{})
                price=price_data.get('price_info')
                if price:
                    chunk=resolve(chunks,price.source_id)
                    if price.amount is not None and (not chunk or not has_value(chunk,'budget',f'{price.amount} {price.currency}')):
                        price.amount=None
                        price_data['budget_fit_note']='Price lacks supporting source data; verify current listing.'
                    price.source_id=chunk.id if chunk else None
                    if chunk: price.fetched_at=chunk.fetched_at or None
                    try:
                        observed=datetime.fromisoformat((price.fetched_at or '').replace('Z','+00:00'))
                        age=datetime.now(timezone.utc)-observed
                        price.is_stale=age>timedelta(hours=24) or age<timedelta(0)
                    except (ValueError,TypeError):
                        price.is_stale=True
                if any(c.origin=='curated' for c in chunks):
                    notice='Curated seed records have no verified manufacturer observation time; their claims are secondary support, not fetched primary evidence.'
                    if notice not in state.notices: state.notices.append(notice)
            self._finish_run(run,start)
        except Exception as error:
            self._fail_run(run,'Evidence validation failed',start)
            raise
        return state
