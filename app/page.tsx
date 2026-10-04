'use client'
import { Suspense, useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { usePathname, useSearchParams } from 'next/navigation'
import { ArrowRight, Check, ChevronDown, ChevronRight, ExternalLink, FileCheck2, Menu, MessageCircle, Minus, Moon, Plus, Search, ShieldCheck, Laptop, ArrowUpRight, SlidersHorizontal, BookOpen, Sun, X } from 'lucide-react'
import { api, ApiClientError } from '@/lib/api'
import { heroExample, navItems, footerNote } from '@/lib/mock-data'
import type { Comparison, Evidence, EvidenceStatus, FollowUpResponse, Product, Requirement } from '@/lib/types'
import { PRIORITY_LABELS } from '@/lib/types'
import { EMPTY_SESSION, OPERATORS, applyPatches, validateRequirements } from '@/lib/workflow'
import type { ShoppingSession } from '@/lib/workflow'

const cx = (...classes: (string | false | undefined)[]) => classes.filter(Boolean).join(' ')
function Logo() { return <Link href="/" aria-label="BuyWise home" className="brand"><span className="brand-mark" aria-hidden="true">b<span>.</span></span><span>buywise<span className="brand-period">.</span></span></Link> }
function Header({ dark, setDark }: { dark: boolean; setDark: (v:boolean)=>void }) {
  const [menuOpen,setMenuOpen]=useState(false)
  return <header className="site-header"><div className="header-inner"><Logo/><nav aria-label="Main navigation" className="desktop-nav">{navItems.map(item=><Link key={item.href} href={item.href.startsWith('#') ? '/' + item.href : item.href}>{item.label}</Link>)}<Link href="/start">Your research</Link></nav><div className="header-actions"><button aria-label="Toggle theme" aria-pressed={dark} onClick={()=>setDark(!dark)} className="icon-button">{dark?<Sun size={18}/>:<Moon size={18}/>}</button><Link href="/results/demo" className="header-demo">Explore a comparison <ArrowUpRight size={16} aria-hidden="true"/></Link><button aria-label="Open navigation" aria-expanded={menuOpen} onClick={()=>setMenuOpen(!menuOpen)} className="icon-button mobile-menu-button"><Menu size={20}/></button></div>{menuOpen&&<nav className="mobile-nav" aria-label="Mobile navigation"><Link onClick={()=>setMenuOpen(false)} href="/start">Your requirements</Link><Link onClick={()=>setMenuOpen(false)} href="/results/demo">View demo results</Link><Link onClick={()=>setMenuOpen(false)} href="/#how-it-works">How it works</Link></nav>}</div></header>
}
function WorkflowSteps({ active }: { active: number }) { return <ol className="workflow-steps" aria-label="Research workflow">{['Your requirements','Research','Comparison'].map((label,i)=><li key={label} aria-current={i===active?'step':undefined} className={i===active?'current':i<active?'complete':''}><span>{i<active?<Check size={12} aria-hidden="true"/>:i+1}</span>{label}{i<2&&<ChevronRight size={14} aria-hidden="true"/>}</li>)}</ol> }
function SectionTitle({ eyebrow, title, copy }: { eyebrow: string; title: string; copy?: string }) { return <div className="max-w-xl"><p className="mb-3 text-xs font-bold uppercase tracking-[.18em] text-[#28634b]">{eyebrow}</p><h2 className="text-3xl font-semibold tracking-tight text-[#20382c] dark:text-slate-100 md:text-4xl">{title}</h2>{copy && <p className="mt-3 leading-7 text-slate-500 dark:text-slate-400">{copy}</p>}</div> }
function Pill({ children, tone='blue' }: { children: React.ReactNode; tone?: 'blue'|'mint'|'gray'|'amber' }) { const colors={blue:'bg-blue-50 text-blue-700 border-blue-100',mint:'bg-emerald-50 text-emerald-700 border-emerald-100',gray:'bg-slate-50 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700',amber:'bg-amber-50 text-amber-700 border-amber-100'}; return <span className={cx('inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-semibold',colors[tone])}>{children}</span> }
function EvidenceBadge({ status, onClick }: { status: EvidenceStatus; onClick?: () => void }) {
  const labels={verified:'Verified',supported:'Supported',conflicting:'Conflicting',insufficient:'Insufficient'}
  const className='evidence-badge evidence-'+status
  return onClick?<button type="button" onClick={onClick} className={className} aria-label={`Inspect ${labels[status].toLowerCase()} evidence`}>{labels[status]}</button>:<span className={className}>{labels[status]}</span>
}


function Home({ start }: { start: (text:string)=>void }) {
  const [prompt,setPrompt]=useState('')
  const examples=['A laptop for work & travel','Gaming without overspending','Something that lasts']
  const prompts=['I need a lightweight laptop for work and travel in Pakistan, under PKR 250000, with 16 GB RAM and good battery life.','I want an ASUS gaming laptop in Pakistan with RTX 5060, 8 GB VRAM and 16 GB RAM, under PKR 400000.','I need a durable laptop in Pakistan under PKR 200000 with 16 GB RAM, upgradeable storage and clear warranty terms.']
  return <><main className="home-page"><section className="home-hero"><div className="hero-intro"><p className="eyebrow">A little research. A better decision.</p><h1>Buy less on impulse.<br/>Choose <em>with clarity.</em></h1><p className="hero-description">The right laptop isn’t the one with the loudest claims. It’s the one that fits your life. Tell us what matters—we’ll help you see the evidence.</p><a href="#shopping-form" className="hero-anchor">Make your next purchase count <ArrowRight size={18} aria-hidden="true"/></a><div className="hero-principle"><BookOpen size={20} aria-hidden="true"/><span>Sources you can inspect.<br/><strong>A decision that stays yours.</strong></span></div></div><form id="shopping-form" className="request-card" onSubmit={e=>{e.preventDefault();start(prompt)}}><div className="request-card-heading"><span className="eyebrow">Your next purchase</span><Laptop size={25} strokeWidth={1.5} aria-hidden="true"/></div><label htmlFor="shopping-request"><h2>What does your<br/>ideal laptop look like?</h2></label><p>Budget, daily use, non-negotiables.<br/>Write it the way you’d tell a friend.</p><textarea id="shopping-request" name="shopping-request" aria-label="Shopping request" autoComplete="off" maxLength={1000} value={prompt} onChange={e=>setPrompt(e.target.value)} placeholder="A laptop for design work, under PKR 250,000, with 16 GB RAM…"/><div className="request-meta"><span>Pakistan · Laptops · PKR</span><span>{prompt.length}/1,000</span></div><button className="ui-button ui-primary request-submit" disabled={prompt.trim().length<10}>Start research <ArrowRight size={18} aria-hidden="true"/></button><p className="request-reassurance"><ShieldCheck size={15} aria-hidden="true"/> You review the requirements before we search.</p></form></section><section className="example-strip" aria-label="Example shopping requests"><span>Not sure where to start?</span><div>{examples.map((label,i)=><button key={label} onClick={()=>{setPrompt(prompts[i]);document.getElementById('shopping-request')?.focus()}}>{label}<ArrowUpRight size={14} aria-hidden="true"/></button>)}<button className="example-original" onClick={()=>setPrompt(heroExample)}>Use a detailed example <ArrowUpRight size={14} aria-hidden="true"/></button></div></section><section id="how-it-works" className="method-section"><div><p className="eyebrow">The method</p><h2>A considered purchase,<br/><em>without the homework.</em></h2><p>From your first thought to a comparison you can actually use.</p><Link href="/results/demo" className="text-link">See how a comparison looks <ArrowUpRight size={17} aria-hidden="true"/></Link></div><ol className="method-list">{[['Define what matters','Your budget, must-haves and preferences, made clear and editable.'],['Look beyond the listing','Research candidate products and trace their claims to sources.'],['Make the trade-offs visible','Compare the fit, inspect the evidence, and see what remains unknown.']].map(([title,copy],i)=><li key={title}><span className="method-number">0{i+1}</span><div><h3>{title}</h3><p>{copy}</p></div></li>)}</ol></section><section className="closing-note"><p>No sponsored ranking.<br/><em>No “just buy this.”</em></p><div>A useful comparison gives you context, not pressure. Sources, limitations and uncertainty belong in the same conversation.</div></section></main><footer className="site-footer"><Logo/><p>{footerNote}</p><a href="#shopping-form">Back to your next purchase <ArrowUpRight size={15} aria-hidden="true"/></a></footer></>
}


const buttonClass = 'ui-button'
const primaryClass = buttonClass + ' ui-primary'
const fieldClass = 'ui-field'
function errorMessage(error: unknown) {
  if (error instanceof ApiClientError) return `${error.message}${error.retryAfter ? ` Retry in ${error.retryAfter} seconds.` : ''}`
  if (error instanceof TypeError) return 'Could not reach the research backend. Check that it is running, then retry.'
  if (error instanceof Error && error.name === 'TimeoutError') return 'The request timed out. Retry when the backend is available.'
  return error instanceof Error ? error.message : 'Request failed. Please retry.'
}
function Notices({ items }: { items?: string[] }) { if (!items?.length) return null; return <details className="source-notices"><summary><ShieldCheck size={16} aria-hidden="true"/><span>Source notes & limitations</span><span className="notice-count">{items.length}</span><ChevronDown size={16} aria-hidden="true"/></summary><div>{items.map((item,i)=><p key={i}>{item}</p>)}</div></details> }
function Failure({ message, retry }: { message: string; retry?: () => void }) { return <div role="alert" className="my-4 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800"><p>{message}</p>{retry && <button className={buttonClass + ' mt-3'} onClick={retry}>Retry</button>}</div> }
function Loading() { return <div role="status" className="loading-workspace"><BookOpen size={28} aria-hidden="true"/><p>Opening your research workspace…</p></div> }
function Requirements({ session, update, busy, research, analyze }: { session: ShoppingSession; update: (s: ShoppingSession) => void; busy: boolean; research: (items: Requirement[]) => void; analyze: (text: string, preserve?: boolean) => void }) {
  const [confirmation, setConfirmation] = useState<number | null>(null)
  const [clarification, setClarification] = useState('')
  const items = session.requirements
  const setItems = (requirements: Requirement[]) => update({ ...session, requirements, job: undefined })
  const change = (index: number, patch: Partial<Requirement>) => setItems(items.map((r, i) => i === index ? { ...r, ...patch, source: 'user', confirmed: false } : r))
  const remove = (index: number) => { setItems(items.filter((_, i) => i !== index)); setConfirmation(null) }
  return <main className="workspace-page requirements-page"><WorkflowSteps active={0}/><p className="eyebrow">Your priorities</p><h1 className="mt-4 text-4xl font-semibold tracking-tight">A good decision starts here.</h1><p className="mt-3 text-slate-500 dark:text-slate-400">Fine-tune what matters. Keep your must-haves distinct from the nice-to-haves.</p>
    {busy && <p role="status" className="mt-6">Processing your request…</p>}
    <Notices items={session.analysis?.notices} />
    {session.analysis?.category === 'unsupported' && <Failure message="This request is outside the supported category. Try an explicit laptop request." />}
    <details className="mt-6 rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-5" open={!session.analysis}><summary className="cursor-pointer font-semibold">Shopping request</summary><textarea aria-label="Revise shopping request" disabled={busy} maxLength={1000} className={fieldClass + ' mt-4 h-28'} value={session.rawText} onChange={e => update({ ...EMPTY_SESSION, rawText: e.target.value })} /><button disabled={busy || session.rawText.trim().length < 10} className={primaryClass + ' mt-3'} onClick={() => analyze(session.rawText)}>Analyze request</button></details>
    <fieldset disabled={busy}><div className="mt-8 space-y-3">{items.map((r, i) => <div key={r.id ?? i} className="requirement-editor">
      <label className="text-xs text-slate-500 dark:text-slate-400">Requirement<input aria-label={`Requirement ${i + 1} key`} className={fieldClass} value={r.key} maxLength={100} onChange={e => change(i, { key: e.target.value })} /></label>
      <label className="text-xs text-slate-500 dark:text-slate-400">Operator<select aria-label={`Requirement ${i + 1} operator`} className={fieldClass} value={r.operator} onChange={e => change(i, { operator: e.target.value })}>{OPERATORS.map(op => <option key={op}>{op}</option>)}</select></label>
      <label className="text-xs text-slate-500 dark:text-slate-400">Value<input aria-label={`Requirement ${i + 1} value`} className={fieldClass} value={r.value} maxLength={200} onChange={e => change(i, { value: e.target.value })} /></label>
      <label className="text-xs text-slate-500 dark:text-slate-400">Priority<select aria-label={`Requirement ${i + 1} priority`} className={fieldClass} value={r.priority} onChange={e => change(i, { priority: e.target.value as Requirement['priority'] })}>{Object.entries(PRIORITY_LABELS).map(([key, value]) => <option key={key} value={key}>{value}</option>)}</select></label>
      <div><span className="text-xs text-slate-400">{r.source === 'inferred' ? 'Inferred' : 'User stated'}</span><button aria-label={`Remove requirement ${i + 1}`} className={buttonClass + ' block'} onClick={() => r.priority === 'must' ? setConfirmation(i) : remove(i)}><X size={16} /></button></div>
    </div>)}</div>
    {confirmation !== null && <div role="alert" className="mt-4 rounded-xl bg-amber-50 p-4 text-sm">Removing a must-have changes which candidates qualify.<button className={buttonClass + ' ml-3'} onClick={() => remove(confirmation)}>Confirm removal</button><button className={buttonClass + ' ml-2'} onClick={() => setConfirmation(null)}>Keep requirement</button></div>}
    <button disabled={items.length >= 20 || busy} className={buttonClass + ' mt-4'} onClick={() => setItems([...items, { id: crypto.randomUUID(), key: '', operator: '=', value: '', priority: 'preferred', source: 'user' }])}><Plus className="mr-2 inline" size={15} />Add requirement</button>
    {session.analysis?.missingInfo.length ? <section className="mt-8 rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-6"><h2 className="font-semibold">Clarify your request</h2><ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-slate-600 dark:text-slate-300">{session.analysis.missingInfo.map(q => <li key={q}>{q}</li>)}</ul><label className="mt-4 block text-sm">Additional needs<textarea aria-label="Clarification answer" maxLength={Math.max(0, 1000 - session.rawText.length - 1)} className={fieldClass + ' mt-2'} value={clarification} onChange={e => setClarification(e.target.value)} /></label><button disabled={busy || !clarification.trim()} className={buttonClass + ' mt-3'} onClick={() => { analyze(`${session.rawText}\n${clarification}`, true); setClarification('') }}>Analyze clarification</button><p className="mt-2 text-xs text-slate-500 dark:text-slate-400">Existing criteria and edits are retained; supported new criteria are added. Review conflicting answers manually.</p></section> : null}
    <button disabled={busy || !!validateRequirements(items) || session.analysis?.category === 'unsupported'} className={primaryClass + ' mt-8'} onClick={() => research(items.map(r => ({ ...r, key: r.key.trim(), value: r.value.trim(), confirmed: true })))}>Confirm and research <ArrowRight className="ml-2 inline" size={15} /></button>
    {validateRequirements(items) && <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">{validateRequirements(items)}</p>}
  </fieldset></main>
}
function Research({ id, streamUrl, navigate }: { id: string; streamUrl?: string; navigate: (path: string) => void }) {
  const [events, setEvents] = useState<string[]>([])
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let disposed = false; let stream: EventSource | undefined; let polling: ReturnType<typeof setTimeout> | undefined
    const started = Date.now()
    const deadline = setTimeout(() => { if (!disposed) { stream?.close(); if (polling) clearTimeout(polling); setError('Research did not finish within two minutes. Retry status lookup or return to your requirements.') } }, 120000)
    setError(''); setEvents(['Waiting for research status'])
    const done = () => { if (!disposed) navigate(`/results/${encodeURIComponent(id)}`) }
    const poll = async () => {
      if (disposed) return
      try { await api.getComparison(id); done() } catch {
        if (disposed) return
        try {
          const status = await api.getResearchStatus(id)
          if (disposed) return
          if (status.status === 'error') { setError(`${status.error?.message ?? 'Research failed.'}${status.error?.retry_after ? ` Retry in ${status.error.retry_after} seconds.` : ''}`); return }
        } catch (e) { if (!disposed) setError(errorMessage(e)); return }
        if (Date.now() - started > 120000) setError('Research did not finish within two minutes. Retry status lookup or return to your requirements.')
        else polling = setTimeout(poll, 1000)
      }
    }
    if (api.isMockMode) { void api.getComparison(id).then(done).catch(e => setError(errorMessage(e))) }
    else {
      // Result lookup first makes reload work after a stream has been consumed.
      const existing = streamUrl ? Promise.reject() : api.getComparison(id)
      void existing.then(done).catch(() => {
        if (disposed) return
        try {
          stream = new EventSource(api.streamUrl(streamUrl ?? `/api/stream/${encodeURIComponent(id)}`))
          stream.addEventListener('status', event => { try { const data = JSON.parse((event as MessageEvent).data); if (!disposed) setEvents(old => [...old.slice(-15), String(data.message)]) } catch { setError('Invalid progress event received.'); stream?.close() } })
          stream.addEventListener('done', () => { stream?.close(); done() })
          stream.addEventListener('error', event => {
            if ('data' in event && typeof event.data === 'string') { try { const data = JSON.parse(event.data); setError(`${data.message ?? 'Research failed'}${data.retry_after ? ` Retry in ${data.retry_after} seconds.` : ''}`); stream?.close(); return } catch { /* disconnect: look for completed result */ } }
            stream?.close(); void poll()
          })
        } catch (e) { setError(errorMessage(e)) }
      })
    }
    return () => { disposed = true; clearTimeout(deadline); stream?.close(); if (polling) clearTimeout(polling) }
  }, [id, streamUrl, attempt, navigate])
  return <main className="workspace-page research-page"><WorkflowSteps active={1}/><p className="eyebrow">Research in progress</p><h1 className="mt-4 text-4xl font-semibold">Checking the options.</h1><p className="mt-3 text-slate-500 dark:text-slate-400">Statuses come from the research pipeline. Results appear when the comparison is ready.</p><div className="research-timeline"><ul role="status" aria-live="polite" className="space-y-4">{events.map((message, i) => <li key={i} className="flex gap-3 text-sm"><span className="event-marker" aria-hidden="true"><Check size={14}/></span>{message}</li>)}</ul></div>{error && <Failure message={error} retry={() => setAttempt(a => a + 1)} />}<Link className={buttonClass + ' mt-6 inline-block'} href="/start">Edit requirements</Link></main>
}
function EvidenceDrawer({ record, close }: { record: Evidence | null; close: () => void }) {
  const panel = useRef<HTMLElement>(null)
  useEffect(() => {
    if (!record) return
    const previous = document.activeElement as HTMLElement | null
    panel.current?.querySelector<HTMLButtonElement>('button')?.focus()
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close()
      if (e.key === 'Tab') {
        const controls = panel.current?.querySelectorAll<HTMLElement>('button,a[href]')
        if (!controls?.length) return
        const first = controls[0], last = controls[controls.length - 1]
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
      }
    }
    document.addEventListener('keydown', handler)
    return () => { document.removeEventListener('keydown', handler); previous?.focus() }
  }, [record, close])
  if (!record) return null
  const canOpen = (record.origin === 'web' || record.origin === 'curated' || record.origin === 'search') && /^https:\/\//i.test(record.sourceUrl)
  return <div className="fixed inset-0 z-50"><button aria-label="Close evidence overlay" className="evidence-backdrop" onClick={close} tabIndex={-1} /><aside ref={panel} role="dialog" aria-modal="true" aria-labelledby="evidence-title" className="evidence-drawer"><div className="flex items-start justify-between"><h2 id="evidence-title" className="text-xl font-semibold">{record.title}</h2><button aria-label="Close evidence" onClick={close} className={buttonClass}><X size={18} /></button></div><p className="mt-6 text-sm">{record.sourceType} · {record.origin ?? 'demo'} · {record.kind ?? 'source record'}</p><pre className="mt-6 whitespace-pre-wrap break-words rounded-2xl bg-slate-50 p-4 font-sans text-sm leading-6">{record.snippet}</pre><p className="mt-5 break-all text-sm text-slate-500 dark:text-slate-400">{record.sourceUrl}</p>{canOpen ? <a target="_blank" rel="noopener noreferrer" href={record.sourceUrl} className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-[#28634b]">Open source <ExternalLink size={14} /></a> : <p className="mt-4 text-sm text-amber-800">Local/synthetic source record; no live page was fetched.</p>}<p className="mt-5 text-sm">Observed: {record.fetchedAt || 'Unknown; no verified listing observation date'}</p></aside></div>
}
function Price({ product }: { product: Product }) {
  const info = product.priceInfo
  return <div><p className="text-2xl font-semibold">{info?.amount != null ? `${info.amount.toLocaleString()} ${info.currency}` : product.price != null ? `$${product.price.toLocaleString()}` : 'Price unknown'}</p><p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{info?.isStale ? 'Stale price · current budget fit uncertain' : info?.fetchedAt ? `Observed ${info.fetchedAt}` : 'Observation time unknown; verify current listing'}</p></div>
}
function Results({ comparison, edit, regenerate, navigate }: { comparison: Comparison; edit: () => void; regenerate: (patches: Array<Partial<Requirement>>) => void; navigate: (path: string) => void }) {
  const [evidenceId, setEvidenceId] = useState<string | null>(null)
  const [selected, setSelected] = useState<string[]>([])
  const [selectError, setSelectError] = useState('')
  const [selectBusy, setSelectBusy] = useState(false)
  const requirements = comparison.requirements ?? []
  const budgetCurrency = /\bPKR\b|\bRs\.?/i.test(requirements.find(r => r.key === 'budget')?.value ?? '') ? 'PKR' : /\bUSD\b|\$/i.test(requirements.find(r => r.key === 'budget')?.value ?? '') ? 'USD' : null
  const [budget, setBudget] = useState(Number(requirements.find(r => r.key === 'budget')?.value.replace(/[^\d.]/g, '')) || 1000)
  const records = comparison.products.flatMap(p => p.evidence ?? [])
  const record = records.find(e => e.id === evidenceId) ?? null
  const openEvidence = (id: string) => setEvidenceId(id)
  const closeEvidence = () => setEvidenceId(null)
  const rows = [...new Set(comparison.products.flatMap(p => p.specs.map(s => s.key)))]
  const demo = comparison.dataMode === 'demo'
  async function compareSelected() {
    setSelectError(''); setSelectBusy(true)
    try { const result = await api.compareProducts({ requestId: comparison.requestId, comparisonId: comparison.id, productIds: selected }); navigate(`/results/${encodeURIComponent(result.id)}`) } catch (e) { setSelectError(errorMessage(e)) } finally { setSelectBusy(false) }
  }
  return <main className="workspace-page results-page"><WorkflowSteps active={2}/><div className="results-heading"><div><p className="eyebrow">Your research, ready to explore</p><h1>Your research, in context.</h1><p>{comparison.products.length} candidates. {requirements.length} priorities. A clearer picture of the trade-offs.</p></div><button className={buttonClass} onClick={edit}><SlidersHorizontal size={16} aria-hidden="true"/>Edit requirements</button></div>
    {demo && <div className="demo-note"><BookOpen size={16} aria-hidden="true"/><span>Example comparison. Products and claims are illustrative, not actual shopping advice.</span></div>}
    <div className="research-brief"><div><p className="eyebrow">The brief</p><span>Your confirmed priorities</span></div><div className="brief-chips">{requirements.map((r,i)=><span key={r.id??i} className="brief-chip"><strong>{r.key}</strong> {r.operator} {r.value}<small>{PRIORITY_LABELS[r.priority]}</small></span>)}</div></div><Notices items={comparison.notices}/>
    {comparison.searchReport && <details className="search-overview" open={!comparison.products.length}><summary><Search size={18} aria-hidden="true"/><span>From the web</span><span>{comparison.searchReport.sources.length} cited sources</span><ChevronDown size={16} aria-hidden="true"/></summary><div><p className="muted-copy">Search findings provide context. Product cards contain separately checked facts; stock and current seller terms still need confirmation.</p><pre>{comparison.searchReport.summary}</pre><div className="search-links">{comparison.searchReport.sources.filter(source=>/^https:\/\//i.test(source.url)).map(source=><a key={source.url} href={source.url} target="_blank" rel="noopener noreferrer">{source.title}<ArrowUpRight size={13} aria-hidden="true"/></a>)}</div>{comparison.searchReport.suggestions_html&&<iframe title="Google Search suggestions" sandbox="allow-popups allow-popups-to-escape-sandbox" referrerPolicy="no-referrer" className="mt-5 h-40 w-full border-0" srcDoc={'<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; img-src https: data:;">'+comparison.searchReport.suggestions_html}/>}</div></details>}
    {!comparison.products.length ? <section className="empty-results"><Search size={32} aria-hidden="true"/><h2>No supported match this time.</h2><p>Your must-haves stay intact. Check the source notes or adjust your requirements to explore other options.</p><button className={primaryClass} onClick={edit}>Review requirements <ArrowRight size={16} aria-hidden="true"/></button></section> : <>
    <div className="section-heading"><div><p className="eyebrow">The shortlist</p><h2>Different strengths. Same scrutiny.</h2></div><a href="#comparison-table" className="text-link">Jump to comparison <ChevronDown size={16} aria-hidden="true"/></a></div>
    <div className="product-grid">{comparison.products.map((p,index)=><article key={p.id} className={cx('product-card',selected.includes(p.id)&&'is-selected')}><div className="product-card-top"><span className="product-index">Option {String(index+1).padStart(2,'0')}</span><Pill tone={p.mustHaveStatus==='met'?'mint':p.mustHaveStatus==='not_met'?'amber':'gray'}>{p.mustHaveStatus==='not_met'?'Misses must-haves':p.mustHaveStatus==='uncertain'?'Needs confirmation':p.mustHaveStatus==='met'?'Must-haves met':'Example match'}</Pill></div><div className="product-identity"><span className="product-category"><Laptop size={24} strokeWidth={1.5} aria-hidden="true"/>{p.brand??'Laptop'}</span><h2>{p.name}</h2><p>{p.score||'Evidence available below'}</p></div><div className="product-price"><Price product={p}/></div><dl className="quick-specs">{p.specs.filter(spec=>['cpu','gpu','ram','storage'].includes(spec.key.toLowerCase())).slice(0,3).map(spec=><div key={spec.key}><dt>{spec.key}</dt><dd>{spec.value}</dd></div>)}</dl><div className="product-observations">{p.pros.map((text,i)=><p className="positive-observation" key={'p'+i}><Check size={15} aria-hidden="true"/>{text}</p>)}{p.limitations.map((text,i)=><p key={'l'+i}><Minus size={15} aria-hidden="true"/>{text}</p>)}</div><div className="product-card-footer"><Link href={`/product/${encodeURIComponent(p.id)}?comparison=${encodeURIComponent(demo?'demo':comparison.id)}`} className="ui-button card-evidence-link">Explore evidence <ArrowUpRight size={16} aria-hidden="true"/></Link><label><input type="checkbox" aria-label={`Select ${p.name}`} disabled={demo} checked={selected.includes(p.id)} onChange={e=>setSelected(old=>e.target.checked?[...old,p.id]:old.filter(id=>id!==p.id))}/><span>{demo?'Selection available with live results':'Select for comparison'}</span></label></div></article>)}</div>
    {!demo&&<div className="selection-bar"><span>{selected.length} of {comparison.products.length} selected</span><button disabled={selected.length<2||selected.length>5||selectBusy} className={primaryClass} onClick={compareSelected}>{selectBusy?'Comparing…':'Compare selected products'}<ArrowRight size={16} aria-hidden="true"/></button></div>}{selectError&&<Failure message={selectError}/>}
    <section id="comparison-table" className="comparison-section"><div className="section-heading"><SectionTitle eyebrow="Side by side" title="The details that make the difference." copy="Read across for the facts. Open a source to see what supports them."/><div className="evidence-legend"><span><i className="verified-dot"/>Verified</span><span><i className="supported-dot"/>Supported</span><span><i className="conflicting-dot"/>Conflicting</span></div></div><div className="comparison-scroll" role="region" aria-label="Specification comparison" tabIndex={0}><table className="comparison-table"><caption className="sr-only">Product specifications and supporting evidence</caption><thead><tr><th scope="col">What matters</th>{comparison.products.map((p,i)=><th scope="col" key={p.id}><small>Option {String(i+1).padStart(2,'0')}</small>{p.name}</th>)}</tr></thead><tbody>{rows.map(row=><tr key={row}><th scope="row">{row==='budget'?'Recorded price':row}</th>{comparison.products.map(p=>{const spec=p.specs.find(s=>s.key===row);return <td key={p.id}><p className="spec-value">{spec?.value??'Unknown'}</p>{spec?<><EvidenceBadge status={spec.status} onClick={spec.evidenceIds[0]?()=>openEvidence(spec.evidenceIds[0]):undefined}/>{spec.conflictingValues?.map((v,i)=><p className="conflict-copy" key={i}>{v.value} · {v.sourceType}</p>)}<CitationButtons ids={spec.evidenceIds} records={records} open={openEvidence}/></>:<span className="unknown-evidence">No supported data</span>}</td>})}</tr>)}</tbody></table></div></section>
    <section className="match-section"><div className="match-matrix"><p className="eyebrow">Back to your brief</p><h2>Requirement match</h2><div className="matrix-scroll" role="region" aria-label="Requirement matching" tabIndex={0}><table><thead><tr><th scope="col">Your priorities</th>{comparison.products.map((p,i)=><th scope="col" key={p.id} title={p.name}>Option {i+1}</th>)}</tr></thead><tbody>{requirements.map((r,i)=><tr key={r.id??i}><th scope="row"><strong>{r.key} {r.operator} {r.value}</strong><small>{PRIORITY_LABELS[r.priority]}</small></th>{comparison.products.map(p=>{const value=comparison.requirementMatches[p.id]?.[i]??'?';return <td key={p.id}><span className={cx('match-symbol',value==='✓'?'match-yes':value==='✕'?'match-no':'match-unknown')} aria-label={value==='✓'?'Meets requirement':value==='✕'?'Does not meet requirement':'Unknown'}>{value}</span><p>{comparison.requirementAnalysis?.[i]?.productAssessments.find(a=>a.productId===p.id)?.explanation}</p></td>})}</tr>)}</tbody></table></div></div><aside className="tradeoff-panel"><span className="eyebrow">The bigger picture</span><h2>What the evidence<br/><em>is saying.</em></h2><div>{comparison.tradeoffs.length?comparison.tradeoffs.map((text,i)=><p key={i}><span>{String(i+1).padStart(2,'0')}</span>{text}</p>):<p>No supported trade-off narrative available.</p>}</div><span className="tradeoff-footnote">Context for your choice. The choice is yours.</span></aside></section>
    </>}
    <section className="budget-panel"><div><span className="eyebrow">Room to reconsider</span><h2>Different budget.<br/>Different possibilities.</h2><p>Change your {budgetCurrency??'explicit currency'} ceiling to research a fresh set of options.</p></div><div><label htmlFor="budget-ceiling">Budget ceiling {budgetCurrency&&<span>({budgetCurrency})</span>}</label><input id="budget-ceiling" aria-label="Budget ceiling" type="number" min="0" max="1000000" step="0.01" className={fieldClass} value={budget} onChange={e=>setBudget(Number(e.target.value))}/><button disabled={demo||!budgetCurrency||!Number.isFinite(budget)||budget<0} className={primaryClass} onClick={()=>regenerate([{key:'budget',operator:'<=',value:`${budget} ${budgetCurrency}`}])}>Apply budget and regenerate <ArrowRight size={16} aria-hidden="true"/></button>{demo&&<p className="muted-copy">Available with your own research results.</p>}</div></section>
    <ChatPanel comparison={comparison} regenerate={regenerate} records={records} open={openEvidence}/><EvidenceDrawer record={record} close={closeEvidence}/><footer className="research-footer"><Logo/><p>{footerNote}</p></footer></main>
}

function CitationButtons({ ids, records, open }: { ids: string[]; records: Evidence[]; open: (id: string) => void }) { return <div className="citation-list">{[...new Set(ids)].filter(id=>records.some(r=>r.id===id)).map(id=><button key={id} onClick={()=>open(id)} className="citation-button" title={records.find(r=>r.id===id)?.title}><FileCheck2 size={13} aria-hidden="true"/>{records.find(r=>r.id===id)?.title ?? 'View source'}</button>)}</div> }
function ChatPanel({ comparison, regenerate, records, open }: { comparison: Comparison; regenerate: (patches: Array<Partial<Requirement>>) => void; records: Evidence[]; open: (id: string) => void }) {
  const [question, setQuestion] = useState(''); const [answer, setAnswer] = useState<FollowUpResponse | null>(null); const [error, setError] = useState(''); const [busy, setBusy] = useState(false)
  async function ask() { setBusy(true); setError(''); setAnswer(null); try { setAnswer(await api.askFollowUp(question.trim(), comparison.id)) } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) } }
  return <section className="followup-panel"><h2 className="flex items-center gap-2 text-xl font-semibold"><MessageCircle size={19} />Ask about these results</h2><form className="mt-4" onSubmit={e => { e.preventDefault(); void ask() }}><label className="text-sm">Follow-up question<input aria-label="Follow-up question" maxLength={500} className={fieldClass + ' mt-2'} value={question} onChange={e => setQuestion(e.target.value)} /></label><button disabled={busy || !question.trim() || comparison.dataMode === 'demo'} className={primaryClass + ' mt-3'}>{busy ? 'Checking stored sources…' : 'Ask question'}</button></form>{error && <Failure message={error} />}{answer && <div className="mt-5 rounded-xl bg-blue-50 p-4 text-sm leading-6"><p>{answer.answer}</p><CitationButtons ids={answer.evidenceIds} records={records} open={open} />{answer.requiresRerun && <p className="mt-3">Changed requirements need a new research run.</p>}{!!answer.suggestedRequirementsPatch?.length && <button className={buttonClass + ' mt-3'} onClick={() => regenerate(answer.suggestedRequirementsPatch ?? [])}>Confirm suggested changes and regenerate</button>}</div>}</section>
}
function ProductDetail({ product, comparison }: { product: Product; comparison: Comparison }) {
  const [tab, setTab] = useState('Specifications'); const [record, setRecord] = useState<Evidence | null>(null)
  const tabs = ['Specifications', 'Evidence', 'Reviews summary', 'Warranty', 'Return policy', 'Requirement matching']
  const records = product.evidence ?? []
  const open = (id: string) => setRecord(records.find(e => e.id === id) ?? null)
  return <main className="workspace-page product-detail-page"><Link href={`/results/${comparison.dataMode === 'demo' ? 'demo' : encodeURIComponent(comparison.id)}`} className="text-sm font-semibold text-[#28634b]">← Back to results</Link><div className="detail-heading"><span className="product-category"><Laptop size={24} aria-hidden="true"/>{product.brand??'Laptop research'}</span><h1>{product.name}</h1></div><p className="mt-3 text-slate-500 dark:text-slate-400">{product.score} · Must-have status: {product.mustHaveStatus ?? 'uncertain'}</p><Notices items={comparison.notices} /><div className="mt-6"><Price product={product} /></div><div role="tablist" aria-label="Product information" className="product-tabs">{tabs.map((t,index) => <button id={`product-tab-${index}`} role="tab" aria-controls="product-panel" tabIndex={tab===t?0:-1} aria-selected={tab === t} onKeyDown={e=>{const next=e.key==='ArrowRight'?(index+1)%tabs.length:e.key==='ArrowLeft'?(index+tabs.length-1)%tabs.length:e.key==='Home'?0:e.key==='End'?tabs.length-1:null;if(next!==null){e.preventDefault();setTab(tabs[next]);document.getElementById(`product-tab-${next}`)?.focus()}}} className={cx('whitespace-nowrap border-b-2 p-3 text-sm font-semibold', tab === t ? 'border-[#28634b] text-[#28634b]' : 'border-transparent text-slate-500 dark:text-slate-400')} key={t} onClick={() => setTab(t)}>{t}</button>)}</div><section id="product-panel" role="tabpanel" aria-labelledby={`product-tab-${tabs.indexOf(tab)}`} tabIndex={0} className="product-tab-content">
    {tab === 'Specifications' && product.specs.map((s, i) => <div key={i} className="border-b border-slate-100 py-4"><p className="text-sm">{s.key}: <strong>{s.value}</strong></p><EvidenceBadge status={s.status} onClick={s.evidenceIds[0] ? () => open(s.evidenceIds[0]) : undefined} />{s.conflictingValues?.map((v, j) => <p key={j} className="mt-2 text-sm text-amber-800">{v.value} · {v.sourceType}</p>)}<CitationButtons ids={s.evidenceIds} records={records} open={open} /></div>)}
    {tab === 'Evidence' && (records.length ? records.map(e => <button className={buttonClass + ' mb-3 block'} key={e.id} onClick={() => setRecord(e)}>{e.title}</button>) : <p>No resolvable sources available.</p>)}
    {tab === 'Reviews summary' && (product.reviewThemes?.length ? product.reviewThemes.map((r, i) => <div key={i} className="mb-4 text-sm"><strong>{r.theme} · {r.sentiment}</strong><p className="mt-2">{r.summary}</p><CitationButtons ids={r.sourceId ? [r.sourceId] : []} records={records} open={open} /></div>) : <p>Review opinions unknown.</p>)}
    {tab === 'Warranty' && <><p>{product.warranty?.durationMonths != null ? `${product.warranty.durationMonths} months` : 'Warranty duration unknown'}</p><p className="mt-3">{product.warranty?.coverage ?? 'Coverage unknown'}</p><p className="mt-3">{product.warranty?.conditions ?? 'Conditions unknown; verify region and seller'}</p><CitationButtons ids={product.warranty?.sourceId ? [product.warranty.sourceId] : []} records={records} open={open} /></>}
    {tab === 'Return policy' && <><p>{product.returnPolicy?.windowDays != null ? `${product.returnPolicy.windowDays} days` : 'Return window unknown'}</p><p className="mt-3">{product.returnPolicy?.conditions ?? 'Seller-dependent; verify before purchase'}</p><CitationButtons ids={product.returnPolicy?.sourceId ? [product.returnPolicy.sourceId] : []} records={records} open={open} /></>}
    {tab === 'Requirement matching' && comparison.requirementAnalysis?.map((a, i) => <div key={i} className="mb-4 text-sm"><strong>{a.requirement.key} {a.requirement.operator} {a.requirement.value}</strong><p>{a.productAssessments.find(p => p.productId === product.id)?.explanation ?? 'Unknown'}</p></div>)}
  </section><EvidenceDrawer record={record} close={() => setRecord(null)} /></main>
}

const SESSION_KEY = 'buywise-session-v1'
function Workspace() {
  const pathname = usePathname(); const query = useSearchParams()
  const [ready, setReady] = useState(false); const [session, setSession] = useState<ShoppingSession>(EMPTY_SESSION)
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [dark, setDark] = useState(false)
  const [comparison, setComparison] = useState<Comparison | null>(null); const [loadError, setLoadError] = useState<{ id: string; message: string } | null>(null); const [retry, setRetry] = useState(0)
  const analysisVersion = useRef(0)
  useEffect(() => { document.documentElement.style.colorScheme = dark ? 'dark' : 'light'; document.documentElement.classList.toggle('dark', dark); document.documentElement.classList.toggle('light', !dark); if (ready) { try { localStorage.setItem('buywise-theme', dark ? 'dark' : 'light') } catch { /* Theme remains usable without storage. */ } } }, [dark, ready])
  useEffect(() => {
    try { setDark(localStorage.getItem('buywise-theme')==='dark'); const raw = localStorage.getItem(SESSION_KEY); if (raw) { const saved = JSON.parse(raw); if (typeof saved.rawText === 'string' && Array.isArray(saved.requirements)) setSession(saved) } } catch { /* Corrupt/disabled storage: start with an empty session. */ }
    setReady(true)
  }, [])
  const update = (next: ShoppingSession) => { setSession(next); try { localStorage.setItem(SESSION_KEY, JSON.stringify(next)) } catch { setError('Browser storage is unavailable. Keep this tab open; refresh will lose unsubmitted edits.') } }
  // The installed Next.js guide supports history updates with these hooks.
  const navigate = useRef((path: string) => { window.history.pushState(null, '', path); window.scrollTo(0, 0) }).current
  const id = pathname.startsWith('/results/') ? decodeURIComponent(pathname.split('/')[2]) : pathname.startsWith('/product/') ? query.get('comparison') : null
  useEffect(() => {
    if (!ready || !id) return
    let disposed = false
    setComparison(null); setLoadError(null)
    const load = id === 'demo' ? import('@/lib/mock-data').then(m => m.getComparison()) : api.getComparison(id)
    void load.then(result => { if (!disposed) setComparison(result) }).catch(e => { if (!disposed) setLoadError({ id, message: errorMessage(e) }) })
    return () => { disposed = true }
  }, [ready, id, retry])
  async function analyze(text: string, preserve = false) {
    const clean = text.trim()
    if (clean.length < 10 || clean.length > 1000) { setError('Use between 10 and 1000 characters.'); return }
    const version = ++analysisVersion.current
    setBusy(true); setError(''); update(preserve ? { ...session, rawText: clean, job: undefined } : { ...EMPTY_SESSION, rawText: clean }); navigate('/start')
    try { const analysis = await api.analyzeRequirements({ text: clean }); if (version === analysisVersion.current) update({ rawText: clean, analysis, requirements: preserve ? [...session.requirements, ...analysis.requirements.filter(r => !session.requirements.some(existing => existing.key.toLowerCase() === r.key.toLowerCase()))] : analysis.requirements }) } catch (e) { if (version === analysisVersion.current) setError(errorMessage(e)) } finally { if (version === analysisVersion.current) setBusy(false) }
  }
  async function research(items: Requirement[], rawText = session.rawText, requestId = session.analysis?.requestId) {
    if (busy) return
    const invalid = validateRequirements(items)
    if (invalid || !requestId) { setError(invalid ?? 'Analyze your shopping request first.'); return }
    setBusy(true); setError('')
    try {
      const job = await api.researchProducts({ requestId, rawText, requirements: items })
      update({ rawText, analysis: { ...(session.analysis ?? { category: 'laptop', missingInfo: [] }), requestId, requirements: items }, requirements: items, job })
      navigate(`/research?comparison=${encodeURIComponent(job.comparisonId)}`)
    } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }
  function edit() {
    if (comparison) update({ rawText: session.rawText || 'Previously confirmed laptop request', analysis: { requestId: comparison.requestId, category: 'laptop', requirements: comparison.requirements ?? [], missingInfo: [], dataMode: comparison.dataMode, notices: comparison.notices }, requirements: comparison.requirements ?? [] })
    navigate('/start')
  }
  function regenerate(patches: Array<Partial<Requirement>>) {
    if (!comparison) return
    try { const items = applyPatches(comparison.requirements ?? [], patches); void research(items, session.rawText || 'Previously confirmed laptop request', comparison.requestId) } catch (e) { setError(errorMessage(e)) }
  }
  if (!ready) return <Loading />
  let content: React.ReactNode
  if (pathname === '/start') content = <Requirements session={session} update={update} busy={busy} research={items => void research(items)} analyze={(text, preserve) => void analyze(text, preserve)} />
  else if (pathname === '/research') {
    const jobId = query.get('comparison') ?? session.job?.comparisonId
    content = jobId ? <Research key={jobId} id={jobId} streamUrl={session.job?.comparisonId === jobId ? session.job.streamUrl : undefined} navigate={navigate} /> : <main className="mx-auto max-w-3xl p-10"><Failure message="No research job is active. Confirm your requirements first." /><Link href="/start">Return to requirements</Link></main>
  } else if (pathname.startsWith('/results/') || pathname.startsWith('/product/')) {
    if (!id) content = <Failure message="This product link needs a comparison ID. Open a product from its research results." />
    else if (loadError && loadError.id === id) content = <main className="mx-auto max-w-3xl p-10"><Failure message={loadError.message} retry={() => setRetry(a => a + 1)} /><Link href="/start">Start or edit a request</Link></main>
    else if (!comparison || (id !== 'demo' && comparison.id !== id)) content = <Loading />
    else if (pathname.startsWith('/product/')) { const product = comparison.products.find(p => p.id === decodeURIComponent(pathname.split('/')[2])); content = product ? <ProductDetail key={`${comparison.id}:${product.id}`} product={product} comparison={comparison} /> : <Failure message="This product does not belong to this comparison." /> }
    else content = <Results key={comparison.id} comparison={comparison} edit={edit} regenerate={regenerate} navigate={navigate} />
  } else content = <Home start={text => void analyze(text)} />
  return <div className={cx('app-shell', dark && 'dark')}><a href="#main-content" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:bg-white dark:bg-slate-900 focus:p-3">Skip to main content</a><Header dark={dark} setDark={setDark} />{api.isMockMode && <div className="mx-auto max-w-[1200px] px-6"><Notices items={['UI demo mode: backend calls are disabled and responses are illustrative.']} /></div>}{busy && pathname.startsWith('/results/') && <p role="status" className="mx-auto max-w-[1200px] p-6">Starting updated research…</p>}{error && <div className="mx-auto max-w-[1200px] px-6"><Failure message={error} retry={pathname === '/start' ? () => void analyze(session.rawText) : undefined} /></div>}{<div id="main-content" tabIndex={-1}>{content}</div>}</div>
}
export default function Page() { return <Suspense fallback={<Loading />}><Workspace /></Suspense> }
