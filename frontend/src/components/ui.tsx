import type { ReactNode } from 'react'

export function Panel({
  children,
  className = '',
}: {
  children: ReactNode
  className?: string
}) {
  return <section className={`panel p-5 sm:p-6 ${className}`}>{children}</section>
}

export function PageTitle({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string
  title: string
  description: string
  action?: ReactNode
}) {
  return (
    <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-cyan-300/80">{eyebrow}</p>
        <h2 className="mt-2 text-2xl font-semibold tracking-tight text-white sm:text-3xl">{title}</h2>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">{description}</p>
      </div>
      {action}
    </div>
  )
}

export function EmptyState({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-700 bg-slate-950/35 px-5 py-10 text-center">
      <p className="text-sm font-medium text-slate-200">{title}</p>
      <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-slate-500">{detail}</p>
    </div>
  )
}

export function ErrorNotice({ children }: { children: ReactNode }) {
  return (
    <div role="alert" className="rounded-xl border border-rose-500/25 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
      {children}
    </div>
  )
}

export function StatCard({
  label,
  value,
  detail,
  tone = 'cyan',
}: {
  label: string
  value: string | number
  detail?: string
  tone?: 'cyan' | 'blue' | 'green' | 'amber' | 'rose'
}) {
  const tones = {
    cyan: 'border-cyan-500/20 bg-cyan-500/[0.04] text-cyan-200',
    blue: 'border-blue-500/20 bg-blue-500/[0.04] text-blue-200',
    green: 'border-emerald-500/20 bg-emerald-500/[0.04] text-emerald-200',
    amber: 'border-amber-500/20 bg-amber-500/[0.04] text-amber-200',
    rose: 'border-rose-500/20 bg-rose-500/[0.04] text-rose-200',
  }
  return (
    <div className={`rounded-2xl border p-4 ${tones[tone]}`}>
      <p className="text-[10px] font-semibold uppercase tracking-[0.17em] text-slate-400">{label}</p>
      <p className="mt-3 break-words text-2xl font-semibold text-white">{value}</p>
      {detail ? <p className="mt-1 text-xs text-slate-500">{detail}</p> : null}
    </div>
  )
}

export function formatDate(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

export function formatFactorName(value: string) {
  return value
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

export function policyTone(action: string) {
  if (action === 'QUARANTINE') return 'border-rose-500/30 bg-rose-500/10 text-rose-200'
  if (action === 'RESTRICT' || action === 'MONITOR') return 'border-amber-500/30 bg-amber-500/10 text-amber-200'
  return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'
}
