'use client'
import { Suspense, useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { usePathname, useSearchParams } from 'next/navigation'
import { ArrowRight, Check, ChevronDown, ChevronRight, Edit3, ExternalLink, FileCheck2, Menu, MessageCircle, Minus, Moon, Plus, Search, ShieldCheck, Sparkles, Sun, X } from 'lucide-react'
import { api, ApiClientError } from '@/lib/api'
import { heroExample, navItems, footerNote } from '@/lib/mock-data'
import type { Comparison, Evidence, EvidenceStatus, FollowUpResponse, Product, Requirement } from '@/lib/types'
import { PRIORITY_LABELS } from '@/lib/types'
import { EMPTY_SESSION, OPERATORS, applyPatches, validateRequirements } from '@/lib/workflow'
import type { ShoppingSession } from '@/lib/workflow'

const cx = (...classes: (string | false | undefined)[]) => classes.filter(Boolean).join(' ')
function Logo() { return <Link href="/" className="flex items-center gap-2.5 font-bold tracking-tight text-[#172033] dark:text-slate-100"><span className="grid size-8 place-items-center rounded-xl bg-[#2457d6] text-white shadow-[0_6px_16px_rgba(36,87,214,.22)]"><Sparkles size={17} /></span><span>BuyWise <span className="text-[#2457d6]">AI</span></span></Link> }
function Header({ dark, setDark }: { dark: boolean; setDark: (v:boolean)=>void }) { const [menuOpen,setMenuOpen]=useState(false); return <header className="sticky top-0 z-30 border-b border-slate-200 dark:border-slate-700/80 bg-white/85 dark:bg-slate-900/90 backdrop-blur-xl"><div className="mx-auto flex h-18 max-w-[1200px] items-center justify-between px-6"><Logo/><nav className="hidden items-center gap-8 text-sm font-medium text-slate-500 dark:text-slate-400 md:flex">{navItems.map((item) => <Link key={item.href} href={item.href} className="transition hover:text-[#2457d6]">{item.label}</Link>)}</nav><div className="flex items-center gap-2"><button aria-label="Toggle theme" onClick={() => setDark(!dark)} className="grid size-9 place-items-center rounded-xl text-slate-500 dark:text-slate-400 hover:bg-slate-100">{dark ? <Sun size={17}/> : <Moon size={17}/>}</button><button aria-label="Open navigation" aria-expanded={menuOpen} onClick={()=>setMenuOpen(!menuOpen)} className="grid size-9 place-items-center rounded-xl text-slate-500 dark:text-slate-400 hover:bg-slate-100 md:hidden"><Menu size={18}/></button>{menuOpen&&<nav className="absolute right-6 top-16 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-4 shadow-lg"><Link onClick={()=>setMenuOpen(false)} className="block p-2" href="/start">Your requirements</Link><Link onClick={()=>setMenuOpen(false)} className="block p-2" href="/results/demo">View demo results</Link></nav>}<Link href="/results/demo" className="hidden rounded-xl bg-[#172033] px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-[#2457d6] md:block">View demo results</Link></div></div></header> }
function SectionTitle({ eyebrow, title, copy }: { eyebrow: string; title: string; copy?: string }) { return <div className="max-w-xl"><p className="mb-3 text-xs font-bold uppercase tracking-[.18em] text-[#2457d6]">{eyebrow}</p><h2 className="text-3xl font-semibold tracking-tight text-[#172033] dark:text-slate-100 md:text-4xl">{title}</h2>{copy && <p className="mt-3 leading-7 text-slate-500 dark:text-slate-400">{copy}</p>}</div> }
function Pill({ children, tone='blue' }: { children: React.ReactNode; tone?: 'blue'|'mint'|'gray'|'amber' }) { const colors={blue:'bg-blue-50 text-blue-700 border-blue-100',mint:'bg-emerald-50 text-emerald-700 border-emerald-100',gray:'bg-slate-50 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700',amber:'bg-amber-50 text-amber-700 border-amber-100'}; return <span className={cx('inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-semibold',colors[tone])}>{children}</span> }
function EvidenceBadge({ status, onClick }: { status: EvidenceStatus; onClick: () => void }) { const map={verified:['Verified','bg-emerald-50 text-emerald-700 border-emerald-200'],supported:['Supported','bg-blue-50 text-blue-700 border-blue-200'],conflicting:['Conflicting','bg-amber-50 text-amber-700 border-amber-200'],insufficient:['Insufficient','bg-slate-50 text-slate-500 dark:text-slate-400 border-slate-200 dark:border-slate-700']}; const [label,color]=map[status]; return <button onClick={onClick} className={cx('rounded-full border px-2 py-0.5 text-[10px] font-bold',color)}>{label}</button> }

function Home({ start }: { start: (text:string)=>void }) { const [prompt,setPrompt]=useState(''); return <><main><section className="relative overflow-hidden"><div className="absolute -right-24 -top-32 size-[34rem] rounded-full bg-[#e8efff] blur-3xl"/><div className="mx-auto grid max-w-[1200px] gap-14 px-6 pb-24 pt-20 md:grid-cols-[1.1fr_.9fr] md:items-center md:pt-28"><div className="relative"><Pill><Sparkles size={13}/> Research, not recommendations</Pill><h1 className="mt-6 max-w-3xl text-5xl font-semibold leading-[1.05] tracking-[-.045em] text-[#172033] dark:text-slate-100 md:text-7xl">Tell us what you&apos;re looking for. <span className="text-[#2457d6]">We&apos;ll research the options.</span></h1><p className="mt-6 max-w-xl text-lg leading-8 text-slate-600 dark:text-slate-300">{`BuyWise AI turns your priorities into an evidence-backed comparison—so you can see what each product satisfies, and where the uncertainty remains.`}</p><button onClick={()=>setPrompt(heroExample)} className="mt-9 text-sm font-semibold text-[#2457d6] underline decoration-blue-200 underline-offset-4 hover:text-[#1948bc]">See an example</button></div><div className="relative rounded-[2rem] border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-3 shadow-[0_24px_70px_rgba(23,32,51,.10)]"><div className="rounded-[1.5rem] bg-[#f7f9fc] dark:bg-slate-900 p-6"><div className="flex items-center justify-between"><div><p className="text-sm font-semibold text-[#172033] dark:text-slate-100">What are you shopping for?</p><p className="mt-1 text-xs text-slate-400">Pakistan laptops · PKR budgets</p></div><div className="grid size-10 place-items-center rounded-xl bg-white dark:bg-slate-900 text-[#2457d6] shadow-sm"><Search size={17}/></div></div><textarea aria-label="Shopping request" maxLength={1000} value={prompt} onChange={(e)=>setPrompt(e.target.value)} placeholder={heroExample} className="mt-6 h-40 w-full resize-none rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-4 text-sm leading-6 text-[#172033] dark:text-slate-100 outline-none transition placeholder:text-slate-400 focus:border-[#2457d6] focus:ring-4 focus:ring-blue-50"/><div className="mt-3 flex items-center justify-between text-xs text-slate-400"><span>{prompt.length ? `${prompt.length} characters` : 'Try describing your priorities'}</span><button onClick={()=>start(prompt)} disabled={prompt.trim().length<10}  className="flex items-center gap-1.5 rounded-lg bg-[#172033] px-3 py-2 font-semibold text-white">Start research <ArrowRight size={13}/></button></div><div className="mt-6 flex items-start gap-3 border-t border-slate-200 dark:border-slate-700 pt-5"><ShieldCheck size={16} className="mt-0.5 text-[#15a88a]"/><p className="text-xs leading-5 text-slate-500 dark:text-slate-400">We explain the evidence behind every match. We never tell you what to buy.</p></div></div></div></div></section><section id="how-it-works" className="border-y border-slate-100 bg-[#fbfcfe] dark:bg-slate-950 py-20"><div className="mx-auto max-w-[1200px] px-6"><SectionTitle eyebrow="How it works" title="From a vague idea to a clear decision." copy="A focused research workflow that keeps your requirements visible at every step."/><div className="mt-12 grid gap-4 md:grid-cols-4">{['Understand','Research','Verify','Compare'].map((step,i)=><div key={step} className="relative rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-5"><div className="flex items-center justify-between"><span className="text-sm font-bold text-[#2457d6]">0{i+1}</span></div><h3 className="mt-8 font-semibold text-[#172033] dark:text-slate-100">{step}</h3><p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-400">{['Extract your must-haves and preferences.','Compare approved Pakistan laptop listings.','Cross-check claims and surface conflicts.','See trade-offs without a black-box ranking.'][i]}</p></div>)}</div></div></section><section className="border-b border-slate-100 bg-white dark:bg-slate-900 py-6"><div className="mx-auto grid max-w-[1200px] gap-3 px-6 text-sm font-medium text-slate-600 dark:text-slate-300 md:grid-cols-3"><p className="flex items-center gap-2"><Check size={16} className="text-[#15a88a]"/> Supported claims cite a source</p><p className="flex items-center gap-2"><Check size={16} className="text-[#15a88a]"/> Conflicts are flagged, not hidden</p><p className="flex items-center gap-2"><Check size={16} className="text-[#15a88a]"/> You make the final decision</p></div></section></main><footer className="mx-auto flex max-w-[1200px] flex-col gap-4 px-6 py-10 text-xs text-slate-400 md:flex-row md:items-center md:justify-between"><Logo/><span>{footerNote}</span></footer></> }


const buttonClass = 'focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 rounded-xl border border-slate-200 dark:border-slate-700 px-4 py-2.5 text-sm font-semibold hover:border-[#2457d6] disabled:opacity-40 disabled:cursor-not-allowed'
const primaryClass = buttonClass + ' bg-[#2457d6] text-white'
const fieldClass = 'w-full rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-100'
function errorMessage(error: unknown) {
  if (error instanceof ApiClientError) return `${error.message}${error.retryAfter ? ` Retry in ${error.retryAfter} seconds.` : ''}`
  if (error instanceof TypeError) return 'Could not reach the research backend. Check that it is running, then retry.'
  if (error instanceof Error && error.name === 'TimeoutError') return 'The request timed out. Retry when the backend is available.'
  return error instanceof Error ? error.message : 'Request failed. Please retry.'
}
function Notices({ items }: { items?: string[] }) { return <>{items?.map((item, i) => <p key={i} role="status" className="my-3 rounded-xl bg-amber-50 p-3 text-sm text-amber-900">{item}</p>)}</> }
function Failure({ message, retry }: { message: string; retry?: () => void }) { return <div role="alert" className="my-4 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800"><p>{message}</p>{retry && <button className={buttonClass + ' mt-3'} onClick={retry}>Retry</button>}</div> }
function Loading() { return <p role="status" className="mx-auto max-w-[1200px] px-6 py-16 text-slate-500 dark:text-slate-400">Loading research workspace…</p> }
function Requirements({ session, update, busy, research, analyze }: { session: ShoppingSession; update: (s: ShoppingSession) => void; busy: boolean; research: (items: Requirement[]) => void; analyze: (text: string, preserve?: boolean) => void }) {
  const [confirmation, setConfirmation] = useState<number | null>(null)
  const [clarification, setClarification] = useState('')
  const items = session.requirements
  const setItems = (requirements: Requirement[]) => update({ ...session, requirements, job: undefined })
  const change = (index: number, patch: Partial<Requirement>) => setItems(items.map((r, i) => i === index ? { ...r, ...patch, source: 'user', confirmed: false } : r))
  const remove = (index: number) => { setItems(items.filter((_, i) => i !== index)); setConfirmation(null) }
  return <main className="mx-auto max-w-[1200px] px-6 py-12"><p className="text-sm text-[#2457d6]">01 · Confirm your priorities</p><h1 className="mt-4 text-4xl font-semibold tracking-tight">Let’s make sure we understood.</h1><p className="mt-3 text-slate-500 dark:text-slate-400">Edit these criteria before research. Unknown needs can be added manually.</p>
    {busy && <p role="status" className="mt-6">Processing your request…</p>}
    <Notices items={session.analysis?.notices} />
    {session.analysis?.category === 'unsupported' && <Failure message="This request is outside the supported category. Try an explicit laptop request." />}
    <details className="mt-6 rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-5" open={!session.analysis}><summary className="cursor-pointer font-semibold">Shopping request</summary><textarea aria-label="Revise shopping request" disabled={busy} maxLength={1000} className={fieldClass + ' mt-4 h-28'} value={session.rawText} onChange={e => update({ ...EMPTY_SESSION, rawText: e.target.value })} /><button disabled={busy || session.rawText.trim().length < 10} className={primaryClass + ' mt-3'} onClick={() => analyze(session.rawText)}>Analyze request</button></details>
    <fieldset disabled={busy}><div className="mt-8 space-y-3">{items.map((r, i) => <div key={r.id ?? i} className="grid gap-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-4 md:grid-cols-[1fr_100px_1.4fr_150px_auto]">
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
  return <main className="mx-auto max-w-3xl px-6 py-16"><p className="text-sm text-[#2457d6]">02 · Research in progress</p><h1 className="mt-4 text-4xl font-semibold">Checking the options.</h1><p className="mt-3 text-slate-500 dark:text-slate-400">Statuses come from the research pipeline. Results appear when the comparison is ready.</p><div className="mt-8 rounded-3xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-7"><ul role="status" aria-live="polite" className="space-y-4">{events.map((message, i) => <li key={i} className="flex gap-3 text-sm"><span className="text-[#2457d6]">•</span>{message}</li>)}</ul></div>{error && <Failure message={error} retry={() => setAttempt(a => a + 1)} />}<Link className={buttonClass + ' mt-6 inline-block'} href="/start">Edit requirements</Link></main>
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
  const canOpen = (record.origin === 'web' || record.origin === 'curated') && /^https:\/\//i.test(record.sourceUrl)
  return <div className="fixed inset-0 z-50"><button aria-label="Close evidence overlay" className="absolute inset-0 bg-slate-900/20 backdrop-blur-[2px]" onClick={close} tabIndex={-1} /><aside ref={panel} role="dialog" aria-modal="true" aria-labelledby="evidence-title" className="absolute right-0 top-0 h-full w-full max-w-md overflow-y-auto overscroll-contain border-l border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-6 shadow-2xl"><div className="flex items-start justify-between"><h2 id="evidence-title" className="text-xl font-semibold">{record.title}</h2><button aria-label="Close evidence" onClick={close} className={buttonClass}><X size={18} /></button></div><p className="mt-6 text-sm">{record.sourceType} · {record.origin ?? 'demo'} · {record.kind ?? 'source record'}</p><pre className="mt-6 whitespace-pre-wrap break-words rounded-2xl bg-slate-50 p-4 font-sans text-sm leading-6">{record.snippet}</pre><p className="mt-5 break-all text-sm text-slate-500 dark:text-slate-400">{record.sourceUrl}</p>{canOpen ? <a target="_blank" rel="noopener noreferrer" href={record.sourceUrl} className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-[#2457d6]">Open source <ExternalLink size={14} /></a> : <p className="mt-4 text-sm text-amber-800">Local/synthetic source record; no live page was fetched.</p>}<p className="mt-5 text-sm">Observed: {record.fetchedAt || 'Unknown; curated record has no web observation date'}</p></aside></div>
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
  return <main className="mx-auto max-w-[1200px] px-6 py-10"><div className="flex flex-wrap justify-between gap-4"><div><p className="text-sm text-[#2457d6]">03 · Research results</p><h1 className="mt-4 text-4xl font-semibold tracking-tight">Your research, in context.</h1><p className="mt-3 text-slate-500 dark:text-slate-400">{comparison.products.length} candidates compared against {requirements.length} confirmed requirements.</p></div><button className={buttonClass} onClick={edit}><Edit3 size={15} className="mr-2 inline" />Edit requirements</button></div><Notices items={comparison.notices} />{demo && <Notices items={['Illustrative demo. Criteria, products and claims are examples; no actual research was performed.']} />}<div className="mt-7 flex flex-wrap gap-2">{requirements.map((r, i) => <Pill key={r.id ?? i} tone={r.source === 'inferred' ? 'amber' : 'gray'}>{r.key} {r.operator} {r.value} · {PRIORITY_LABELS[r.priority]}</Pill>)}</div>
    {!comparison.products.length && <Failure message="No candidates found. Broaden your criteria and research again." />}
    <div className="mt-8 grid gap-5 lg:grid-cols-3">{comparison.products.map(p => <article key={p.id} className="rounded-3xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-5 shadow-[0_14px_40px_rgba(23,32,51,.05)]"><div className="flex justify-between"><span className="grid size-14 place-items-center rounded-2xl bg-[#e9f0ff] text-sm font-bold text-[#2457d6]">{p.image}</span><Pill tone={p.mustHaveStatus === 'met' ? 'mint' : 'amber'}>{p.mustHaveStatus === 'not_met' ? 'Misses must-haves' : p.mustHaveStatus === 'uncertain' ? 'Must-haves uncertain' : p.score}</Pill></div><h2 className="mt-5 text-xl font-semibold">{p.name}</h2><div className="mt-5"><Price product={p} /></div><div className="mt-5 space-y-2 text-sm text-slate-600 dark:text-slate-300">{p.pros.map((text, i) => <p key={i}><Check className="mr-2 inline text-emerald-600" size={14} />{text}</p>)}{p.limitations.map((text, i) => <p key={i}><Minus className="mr-2 inline text-amber-600" size={14} />{text}</p>)}</div><Link href={`/product/${encodeURIComponent(p.id)}?comparison=${encodeURIComponent(demo ? 'demo' : comparison.id)}`} className={buttonClass + ' mt-6 block text-center'}>Explore evidence</Link><label className="mt-4 flex items-center gap-2 text-sm"><input type="checkbox" aria-label={`Select ${p.name}`} disabled={demo} checked={selected.includes(p.id)} onChange={e => setSelected(old => e.target.checked ? [...old, p.id] : old.filter(id => id !== p.id))} />Select for comparison</label></article>)}</div>
    <button disabled={demo || selected.length < 2 || selected.length > 5 || selectBusy} className={buttonClass + ' mt-5'} onClick={compareSelected}>{selectBusy ? 'Comparing…' : 'Compare selected products'}</button>{selectError && <Failure message={selectError} />}
    <section className="mt-14"><SectionTitle eyebrow="Side-by-side" title="Compare the evidence, not just the specs." /><div className="mt-8 overflow-x-auto rounded-3xl border border-slate-200 dark:border-slate-700 bg-white"><table className="w-full min-w-[720px] text-left text-sm"><thead className="bg-slate-50"><tr><th className="p-5">Specification</th>{comparison.products.map(p => <th className="p-5" key={p.id}>{p.name}</th>)}</tr></thead><tbody>{rows.map(row => <tr className="border-t border-slate-100" key={row}><th className="p-5 font-medium text-slate-500 dark:text-slate-400">{row === 'budget' ? 'Recorded price / budget evidence' : row}</th>{comparison.products.map(p => { const spec = p.specs.find(s => s.key === row); return <td key={p.id} className="p-5"><p>{spec?.value ?? 'Unknown'}</p>{spec && <><EvidenceBadge status={spec.status} onClick={() => spec.evidenceIds[0] && openEvidence(spec.evidenceIds[0])} />{spec.conflictingValues?.map((v, i) => <p className="mt-1 text-xs text-amber-800" key={i}>{v.value} · {v.sourceType}</p>)}<CitationButtons ids={spec.evidenceIds} records={records} open={openEvidence} /></>}</td> })}</tr>)}</tbody></table></div></section>
    <section className="mt-14 grid gap-5 md:grid-cols-2"><div className="overflow-x-auto rounded-3xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-6"><h2 className="text-xl font-semibold">Requirement match</h2><table className="mt-5 w-full min-w-[450px] text-sm"><thead><tr><th className="text-left">Requirement</th>{comparison.products.map(p => <th key={p.id}>{p.image}</th>)}</tr></thead><tbody>{requirements.map((r, i) => <tr key={r.id ?? i} className="border-t border-slate-100"><td className="py-3">{r.key} · {PRIORITY_LABELS[r.priority]}</td>{comparison.products.map(p => <td key={p.id} className="p-3 text-center"><span className="font-bold">{comparison.requirementMatches[p.id]?.[i] ?? '?'}</span><p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{comparison.requirementAnalysis?.[i]?.productAssessments.find(a => a.productId === p.id)?.explanation}</p></td>)}</tr>)}</tbody></table></div><div className="rounded-3xl bg-[#172033] p-6 text-white"><h2 className="text-2xl font-semibold">What the evidence is saying.</h2><div className="mt-6 space-y-5 text-sm leading-6 text-slate-300">{comparison.tradeoffs.length ? comparison.tradeoffs.map((text, i) => <p key={i}>{text}</p>) : <p>No supported trade-off narrative available.</p>}</div></div></section>
    <section className="mt-14 rounded-3xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-6"><h2 className="text-2xl font-semibold">What changes if your priorities change?</h2><p className="mt-2 text-sm text-slate-500 dark:text-slate-400">Set a new {budgetCurrency ?? 'explicit currency'} ceiling and regenerate. This starts actual research with updated criteria.</p><label className="mt-5 block text-sm">Budget ceiling<input aria-label="Budget ceiling" type="number" min="0" max="1000000" step="0.01" className={fieldClass + ' mt-2 max-w-xs'} value={budget} onChange={e => setBudget(Number(e.target.value))} /></label><button disabled={demo || !budgetCurrency || !Number.isFinite(budget) || budget < 0} className={primaryClass + ' mt-4'} onClick={() => regenerate([{ key: 'budget', operator: '<=', value: `${budget} ${budgetCurrency}` }])}>Apply budget and regenerate</button></section>
    <ChatPanel comparison={comparison} regenerate={regenerate} records={records} open={openEvidence} /><EvidenceDrawer record={record} close={closeEvidence} /><footer className="py-16 text-center text-xs text-slate-400">{footerNote}</footer></main>
}
function CitationButtons({ ids, records, open }: { ids: string[]; records: Evidence[]; open: (id: string) => void }) { return <div className="mt-2 flex flex-wrap gap-2">{ids.filter(id => records.some(r => r.id === id)).map(id => <button key={id} onClick={() => open(id)} className="rounded-full bg-blue-50 px-2 py-1 text-xs font-semibold text-[#2457d6]">Source {id}</button>)}</div> }
function ChatPanel({ comparison, regenerate, records, open }: { comparison: Comparison; regenerate: (patches: Array<Partial<Requirement>>) => void; records: Evidence[]; open: (id: string) => void }) {
  const [question, setQuestion] = useState(''); const [answer, setAnswer] = useState<FollowUpResponse | null>(null); const [error, setError] = useState(''); const [busy, setBusy] = useState(false)
  async function ask() { setBusy(true); setError(''); setAnswer(null); try { setAnswer(await api.askFollowUp(question.trim(), comparison.id)) } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) } }
  return <section className="mt-10 rounded-3xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-6"><h2 className="flex items-center gap-2 text-xl font-semibold"><MessageCircle size={19} />Ask about these results</h2><form className="mt-4" onSubmit={e => { e.preventDefault(); void ask() }}><label className="text-sm">Follow-up question<input aria-label="Follow-up question" maxLength={500} className={fieldClass + ' mt-2'} value={question} onChange={e => setQuestion(e.target.value)} /></label><button disabled={busy || !question.trim() || comparison.dataMode === 'demo'} className={primaryClass + ' mt-3'}>{busy ? 'Checking stored sources…' : 'Ask question'}</button></form>{error && <Failure message={error} />}{answer && <div className="mt-5 rounded-xl bg-blue-50 p-4 text-sm leading-6"><p>{answer.answer}</p><CitationButtons ids={answer.evidenceIds} records={records} open={open} />{answer.requiresRerun && <p className="mt-3">Changed requirements need a new research run.</p>}{!!answer.suggestedRequirementsPatch?.length && <button className={buttonClass + ' mt-3'} onClick={() => regenerate(answer.suggestedRequirementsPatch ?? [])}>Confirm suggested changes and regenerate</button>}</div>}</section>
}
function ProductDetail({ product, comparison }: { product: Product; comparison: Comparison }) {
  const [tab, setTab] = useState('Specifications'); const [record, setRecord] = useState<Evidence | null>(null)
  const records = product.evidence ?? []
  const open = (id: string) => setRecord(records.find(e => e.id === id) ?? null)
  return <main className="mx-auto max-w-[1200px] px-6 py-12"><Link href={`/results/${comparison.dataMode === 'demo' ? 'demo' : encodeURIComponent(comparison.id)}`} className="text-sm font-semibold text-[#2457d6]">← Back to results</Link><h1 className="mt-8 text-4xl font-semibold">{product.name}</h1><p className="mt-3 text-slate-500 dark:text-slate-400">{product.score} · Must-have status: {product.mustHaveStatus ?? 'uncertain'}</p><Notices items={comparison.notices} /><div className="mt-6"><Price product={product} /></div><div role="tablist" aria-label="Product information" className="mt-8 flex gap-2 overflow-x-auto border-b border-slate-200 dark:border-slate-700">{['Specifications', 'Evidence', 'Reviews summary', 'Warranty', 'Return policy', 'Requirement matching'].map(t => <button role="tab" aria-selected={tab === t} className={cx('whitespace-nowrap border-b-2 p-3 text-sm font-semibold', tab === t ? 'border-[#2457d6] text-[#2457d6]' : 'border-transparent text-slate-500 dark:text-slate-400')} key={t} onClick={() => setTab(t)}>{t}</button>)}</div><section role="tabpanel" className="mt-6 rounded-3xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-6">
    {tab === 'Specifications' && product.specs.map((s, i) => <div key={i} className="border-b border-slate-100 py-4"><p className="text-sm">{s.key}: <strong>{s.value}</strong></p><EvidenceBadge status={s.status} onClick={() => s.evidenceIds[0] && open(s.evidenceIds[0])} />{s.conflictingValues?.map((v, j) => <p key={j} className="mt-2 text-sm text-amber-800">{v.value} · {v.sourceType}</p>)}<CitationButtons ids={s.evidenceIds} records={records} open={open} /></div>)}
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
  useEffect(() => { document.documentElement.style.colorScheme = dark ? "dark" : "light" }, [dark])
  useEffect(() => {
    try { const raw = localStorage.getItem(SESSION_KEY); if (raw) { const saved = JSON.parse(raw); if (typeof saved.rawText === 'string' && Array.isArray(saved.requirements)) setSession(saved) } } catch { /* Corrupt/disabled storage: start with an empty session. */ }
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
    else if (!comparison || comparison.id !== id) content = <Loading />
    else if (pathname.startsWith('/product/')) { const product = comparison.products.find(p => p.id === decodeURIComponent(pathname.split('/')[2])); content = product ? <ProductDetail key={`${comparison.id}:${product.id}`} product={product} comparison={comparison} /> : <Failure message="This product does not belong to this comparison." /> }
    else content = <Results key={comparison.id} comparison={comparison} edit={edit} regenerate={regenerate} navigate={navigate} />
  } else content = <Home start={text => void analyze(text)} />
  return <div className={cx('min-h-screen bg-[#fdfefe] dark:bg-slate-950 text-[#172033] dark:text-slate-100', dark && 'dark')}><a href="#main-content" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:bg-white dark:bg-slate-900 focus:p-3">Skip to main content</a><Header dark={dark} setDark={setDark} />{api.isMockMode && <div className="mx-auto max-w-[1200px] px-6"><Notices items={['UI demo mode: backend calls are disabled and responses are illustrative.']} /></div>}{busy && pathname.startsWith('/results/') && <p role="status" className="mx-auto max-w-[1200px] p-6">Starting updated research…</p>}{error && <div className="mx-auto max-w-[1200px] px-6"><Failure message={error} retry={pathname === '/start' ? () => void analyze(session.rawText) : undefined} /></div>}{<div id="main-content" tabIndex={-1}>{content}</div>}</div>
}
export default function Page() { return <Suspense fallback={<Loading />}><Workspace /></Suspense> }
