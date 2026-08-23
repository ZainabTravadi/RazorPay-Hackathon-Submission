import { useEffect, useMemo, useRef, useState } from 'react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

const API_URL = `${import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'}/api`

const scenarios = [
  { value: 'provider_outage', label: 'Provider outage', description: 'Simulate a hard failure in a payment provider path.' },
  { value: 'provider_latency_spike', label: 'Latency spike', description: 'Trigger a latency spike without a total outage.' },
  { value: 'merchant_misconfiguration', label: 'Merchant misconfiguration', description: 'Model a merchant-specific integration issue.' },
  { value: 'webhook_failure', label: 'Webhook failure', description: 'Exercise downstream webhook delivery degradation.' },
  { value: 'late_authorization', label: 'Late authorization', description: 'Create delayed authorization conditions.' },
] as const

type Incident = {
  incident_id: string
  incident_type: string
  severity: string
  status: string
  started_at: string | null
  ended_at: string | null
  detected_at: string | null
  anomaly_score: number
  affected_transactions: number
  affected_merchants: number
  revenue_at_risk: number
  primary_provider: string | null
  primary_payment_method: string | null
  primary_region: string | null
  fingerprint: string
  description: string
}

type Summary = {
  payment_success_rate: number
  failure_rate: number
  revenue_at_risk: number
  active_incidents: number
  failed_transactions?: number
}

type HistoricalIncident = {
  incident_id: string
  incident_type: string
  fingerprint: string
  root_cause: string
  resolution: string
  recovery_rate: number
  revenue_impact: number
  timestamp: string | null
}

type RecoveryExecution = {
  recovery_id: string
  incident_id: string
  strategy: string
  approval_status: 'pending' | 'approved' | 'rejected' | 'cancelled'
  execution_status: 'not_started' | 'completed' | 'blocked' | 'failed'
  before_metrics: Record<string, any>
  after_metrics?: Record<string, any> | null
  recovered_transactions: number
  recovered_revenue: number
  recovery_rate: number
  simulated_latency_impact_ms: number
  simulation: boolean
  timestamp: string
}

type Toast = {
  kind: 'success' | 'error' | 'info'
  message: string
} | null

type ChartPoint = {
  label: string
  success: number
  failure: number
}

const currencyFormatter = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 0,
})

const percentFormatter = new Intl.NumberFormat('en-US', {
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
})

async function api(path: string, options?: RequestInit) {
  const response = await fetch(`${API_URL}${path}`, options)
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body.detail ?? `Request failed (${response.status})`)
  return body
}

function formatLabel(value: string) {
  return value
    .replaceAll('_', ' ')
    .replace(/\b\w/g, (match) => match.toUpperCase())
}

function formatMoney(value: number | null | undefined) {
  return currencyFormatter.format(Number(value ?? 0))
}

function formatPercent(value: number | null | undefined, digits = 0) {
  const next = Number(value ?? 0) * 100
  return `${next.toFixed(digits)}%`
}

function formatTime(value?: string | null) {
  if (!value) return 'Pending'
  return new Intl.DateTimeFormat('en-US', { hour: '2-digit', minute: '2-digit' }).format(new Date(value))
}

function formatDateTime(value?: string | null) {
  if (!value) return 'Pending'
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function formatShortDate(value?: string | null) {
  if (!value) return 'Pending'
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }).format(new Date(value))
}

function formatDuration(minutes: number | null | undefined) {
  const next = Number(minutes ?? 0)
  if (next < 60) return `${Math.round(next)}m`
  const hours = Math.floor(next / 60)
  const remaining = Math.round(next % 60)
  return `${hours}h ${remaining}m`
}

function scoreHypothesis(status: string) {
  if (status === 'supported') return 94
  if (status === 'partially_supported') return 63
  return 21
}

function useAnimatedNumber(target: number, enabled = true, duration = 260) {
  const [value, setValue] = useState(0)

  useEffect(() => {
    if (!enabled) {
      setValue(target)
      return
    }

    let raf = 0
    const start = performance.now()
    const initial = value

    const animate = (now: number) => {
      const progress = Math.min(1, (now - start) / duration)
      const next = initial + (target - initial) * (1 - Math.pow(1 - progress, 3))
      setValue(next)
      if (progress < 1) raf = window.requestAnimationFrame(animate)
    }

    raf = window.requestAnimationFrame(animate)
    return () => window.cancelAnimationFrame(raf)
  }, [duration, enabled, target])

  return value
}

function usePrefersReducedMotion() {
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false)

  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    const update = () => setPrefersReducedMotion(media.matches)
    update()
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])

  return prefersReducedMotion
}

export default function App() {
  const prefersReducedMotion = usePrefersReducedMotion()
  const workspaceRef = useRef<HTMLElement | null>(null)
  const toastTimer = useRef<number | null>(null)

  const [summary, setSummary] = useState<Summary | null>(null)
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [historicalIncidents, setHistoricalIncidents] = useState<HistoricalIncident[]>([])
  const [chartPoints, setChartPoints] = useState<ChartPoint[]>([])
  const [selectedIncident, setSelectedIncident] = useState<Incident | null>(null)
  const [investigation, setInvestigation] = useState<any>(null)
  const [impact, setImpact] = useState<any>(null)
  const [timeline, setTimeline] = useState<any[]>([])
  const [clusters, setClusters] = useState<any[]>([])
  const [recommendation, setRecommendation] = useState<any>(null)
  const [policy, setPolicy] = useState<any>(null)
  const [recovery, setRecovery] = useState<RecoveryExecution | null>(null)
  const [scenario, setScenario] = useState<(typeof scenarios)[number]['value']>(scenarios[0].value)
  const [busy, setBusy] = useState<'inject' | 'reset' | 'prepare' | 'approve' | 'execute' | ''>('')
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<Toast>(null)
  const [pageReady, setPageReady] = useState(false)
  const [workspaceLoading, setWorkspaceLoading] = useState(false)
  const [investigating, setInvestigating] = useState(false)

  const showToast = (message: string, kind: NonNullable<Toast>['kind'] = 'info') => {
    setToast({ kind, message })
    if (toastTimer.current) window.clearTimeout(toastTimer.current)
    toastTimer.current = window.setTimeout(() => setToast(null), 2600)
  }

  useEffect(() => () => {
    if (toastTimer.current) window.clearTimeout(toastTimer.current)
  }, [])

  const refreshOverview = async () => {
    const [nextSummary, nextIncidents, payments, nextHistorical] = await Promise.all([
      api('/dashboard/summary'),
      api('/incidents'),
      api('/payments?limit=12'),
      api('/historical-incidents'),
    ])

    const orderedPayments = [...(payments.items ?? [])].reverse()
    setSummary(nextSummary)
    setIncidents(nextIncidents)
    setHistoricalIncidents(nextHistorical)
    setChartPoints(
      orderedPayments.map((item: any, index: number) => ({
        label: formatTime(item.timestamp) || `T${index + 1}`,
        success: item.status === 'captured' || item.status === 'authorized' ? 1 : 0,
        failure: item.status === 'failed' ? 1 : 0,
      })),
    )

    return nextIncidents as Incident[]
  }

  useEffect(() => {
    let mounted = true
    ;(async () => {
      try {
        await refreshOverview()
      } catch (reason: any) {
        if (mounted) setError(reason.message)
      } finally {
        if (mounted) setPageReady(true)
      }
    })()
    return () => {
      mounted = false
    }
  }, [])

  const copyToClipboard = async (value: string, label: string) => {
    try {
      await navigator.clipboard.writeText(value)
      showToast(`${label} copied`, 'success')
    } catch {
      showToast(`Could not copy ${label.toLowerCase()}`, 'error')
    }
  }

  const syncSelectedIncident = (nextIncidents: Incident[]) => {
    if (!selectedIncident) return
    const refreshed = nextIncidents.find((item) => item.incident_id === selectedIncident.incident_id)
    if (refreshed) setSelectedIncident(refreshed)
  }

  const loadIncidentWorkspace = async (nextIncident: Incident) => {
    setSelectedIncident(nextIncident)
    setWorkspaceLoading(true)
    setError(null)
    setInvestigation(null)
    setImpact(null)
    setTimeline([])
    setClusters([])
    setRecommendation(null)
    setPolicy(null)
    setRecovery(null)
    setInvestigating(false)

    try {
      const [nextImpact, nextTimeline, nextClusters, nextRecommendation, nextPolicy, existingInvestigations] = await Promise.all([
        api(`/incidents/${nextIncident.incident_id}/impact`),
        api(`/incidents/${nextIncident.incident_id}/timeline`),
        api(`/incidents/${nextIncident.incident_id}/clusters`),
        api(`/incidents/${nextIncident.incident_id}/recovery-recommendation`),
        api(`/incidents/${nextIncident.incident_id}/recovery-policy`),
        api('/investigations'),
      ])

      const existing = [...existingInvestigations]
        .filter((item: any) => item.incident_id === nextIncident.incident_id)
        .sort((a: any, b: any) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime())[0]

      const nextInvestigation = existing ? await api(`/investigations/${existing.investigation_id}`) : null

      setImpact(nextImpact)
      setTimeline(nextTimeline)
      setClusters(nextClusters)
      setRecommendation(nextRecommendation)
      setPolicy(nextPolicy)
      setInvestigation(nextInvestigation)
    } catch (reason: any) {
      setError(reason.message)
    } finally {
      setWorkspaceLoading(false)
      requestAnimationFrame(() => {
        if (!prefersReducedMotion) workspaceRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
        else workspaceRef.current?.scrollIntoView({ behavior: 'auto', block: 'start' })
      })
    }
  }

  const selectIncident = async (nextIncident: Incident) => {
    await loadIncidentWorkspace(nextIncident)
  }

  const investigate = async () => {
    if (!selectedIncident) return
    setInvestigating(true)
    setError(null)
    try {
      const nextInvestigation = await api(`/investigate/${selectedIncident.incident_id}`, { method: 'POST' })
      setInvestigation(nextInvestigation)
      showToast('Investigation completed', 'success')
      const nextIncidents = await refreshOverview()
      syncSelectedIncident(nextIncidents)
    } catch (reason: any) {
      setError(reason.message)
    } finally {
      setInvestigating(false)
    }
  }

  const reset = async () => {
    setBusy('reset')
    setError(null)
    try {
      await api('/simulator/reset', { method: 'POST' })
      setSelectedIncident(null)
      setInvestigation(null)
      setImpact(null)
      setTimeline([])
      setClusters([])
      setRecommendation(null)
      setPolicy(null)
      setRecovery(null)
      showToast('Simulator reset', 'success')
      await refreshOverview()
    } catch (reason: any) {
      setError(reason.message)
    } finally {
      setBusy('')
    }
  }

  const inject = async () => {
    setBusy('inject')
    setError(null)
    try {
      const result = await api(`/simulator/inject/${scenario}`, { method: 'POST' })
      showToast('Incident injected', 'success')
      const nextIncidents = await refreshOverview()
      const nextIncident = nextIncidents.find((item: Incident) => item.incident_id === result.incident_id)
      if (nextIncident) await loadIncidentWorkspace(nextIncident)
    } catch (reason: any) {
      setError(reason.message)
    } finally {
      setBusy('')
    }
  }

  const runRecoveryAction = async (stage: 'prepare' | 'approve' | 'execute', path: string) => {
    setBusy(stage)
    setError(null)
    try {
      const nextRecovery = await api(path, { method: 'POST' })
      setRecovery(nextRecovery)
      showToast(
        stage === 'execute'
          ? 'Recovery completed'
          : stage === 'approve'
            ? 'Recovery approved'
            : 'Recovery prepared',
        'success',
      )
      const nextIncidents = await refreshOverview()
      syncSelectedIncident(nextIncidents)
    } catch (reason: any) {
      setError(reason.message)
    } finally {
      setBusy('')
    }
  }

  const investigationResult = investigation?.final_result ?? null

  const rankedHypotheses = useMemo(() => {
    if (!investigationResult?.alternative_hypotheses) return []
    return [...investigationResult.alternative_hypotheses].sort((left: any, right: any) => scoreHypothesis(right.status) - scoreHypothesis(left.status))
  }, [investigationResult])

  const similarIncidents = useMemo(() => {
    if (!investigationResult?.historical_matches) return []
    const lookup = new Map(historicalIncidents.map((item) => [item.incident_id, item]))
    return investigationResult.historical_matches.map((match: any) => ({
      ...match,
      history: lookup.get(match.incident_id),
    }))
  }, [historicalIncidents, investigationResult])

  const chronology = useMemo(() => {
    if (!selectedIncident) return []
    return buildChronology(selectedIncident, investigation, recovery, timeline)
  }, [investigation, recovery, selectedIncident, timeline])

  const incidentProgress = useMemo(() => {
    if (!selectedIncident) return []
    const hasInvestigation = Boolean(investigationResult)
    const hasRecovery = Boolean(recovery)
    const approved = recovery?.approval_status === 'approved'
    const completed = recovery?.execution_status === 'completed'

    const stages = [
      {
        label: 'Detected',
        note: selectedIncident.detected_at ? formatDateTime(selectedIncident.detected_at) : 'Recorded',
        status: 'complete',
      },
      {
        label: 'Investigating',
        note: hasInvestigation ? `RCA prepared by ${investigation?.agent ?? 'investigation agent'}` : 'In progress',
        status: hasInvestigation ? 'complete' : 'active',
      },
      {
        label: 'RCA ready',
        note: investigationResult ? `${Math.round(investigationResult.confidence * 100)}% confidence` : 'Pending',
        status: investigationResult ? 'complete' : hasInvestigation ? 'active' : 'pending',
      },
      {
        label: 'Recovery prepared',
        note: recovery?.timestamp ? formatDateTime(recovery.timestamp) : 'Awaiting preparation',
        status: hasRecovery ? 'complete' : investigationResult ? 'active' : 'pending',
      },
      {
        label: 'Approved',
        note: recovery ? recovery.approval_status.replaceAll('_', ' ') : 'Human approval required',
        status: approved ? 'complete' : hasRecovery ? 'active' : 'pending',
      },
      {
        label: 'Completed',
        note: completed ? 'Simulation finished' : 'Awaiting execution',
        status: completed ? 'complete' : approved ? 'active' : 'pending',
      },
    ]

    return stages
  }, [investigation?.agent, investigationResult, recovery, selectedIncident])

  const lifecyclePhase = selectedIncident
    ? recovery?.execution_status === 'completed'
      ? 5
      : recovery?.approval_status === 'approved'
        ? 4
        : recovery?.approval_status === 'pending'
          ? 3
          : investigationResult
            ? 2
            : 1
    : 0

  return (
    <div className="app-shell">
      <div className="app-frame">
        <header className="topbar">
          <div className="brand">
            <div className="brand-mark">F</div>
            <div>
              <strong>FluxPay</strong>
              <small>Incident response and payment reliability</small>
            </div>
          </div>

          <nav className="topbar-nav" aria-label="Primary navigation">
            <span className="nav-item active">Incidents</span>
            <span className="nav-item">Investigations</span>
            <span className="nav-item">Recovery</span>
          </nav>

          <div className={`system-badge ${summary?.active_incidents ? 'attention' : 'healthy'}`}>
            <span className="status-dot" />
            <div>
              <strong>{summary?.active_incidents ? `${summary.active_incidents} active incidents` : 'System nominal'}</strong>
              <small>{pageReady ? 'Live operational view' : 'Loading workspace'}</small>
            </div>
          </div>
        </header>

        <main className="page">
          <section className="hero">
            <div className="hero-copy">
              <p className="eyebrow">Production incident command center</p>
              <h1>Detect, investigate, prove, and recover with confidence.</h1>
              <p>
                A calm operational workspace for payment reliability teams. The backend intelligence is surfaced as a
                controlled incident narrative, not a raw telemetry dump.
              </p>
            </div>

            <div className="hero-status-card">
              <div className="hero-status-row">
                <span className="status-pill neutral">Live monitoring</span>
                <span className="hero-time">{summary ? `Updated ${new Intl.DateTimeFormat('en-US', { hour: '2-digit', minute: '2-digit' }).format(new Date())}` : 'Awaiting data'}</span>
              </div>

              <div className="hero-stat-grid">
              <HeroStat
                label="Success rate"
                  value={summary?.payment_success_rate ?? 0}
                  formatValue={(value) => formatPercent(value, 1)}
                  tone="success"
                  animated={Boolean(summary)}
                />
                <HeroStat
                label="Failure rate"
                  value={summary?.failure_rate ?? 0}
                  formatValue={(value) => formatPercent(value, 1)}
                  tone="danger"
                  animated={Boolean(summary)}
                />
                <HeroStat
                label="Revenue at risk"
                  value={summary?.revenue_at_risk ?? 0}
                  formatValue={(value) => formatMoney(value)}
                  tone="warning"
                  animated={Boolean(summary)}
                />
              </div>
            </div>
          </section>

          <section className="simulator-panel panel">
            <div className="panel-head">
              <div>
                <p className="section-kicker">Incident simulator</p>
                <h2>Generate a controlled incident to evaluate investigation and recovery behavior.</h2>
              </div>
              <div className="panel-head-actions">
                <button className="button secondary" type="button" onClick={reset} disabled={busy !== ''}>
                  {busy === 'reset' ? 'Resetting...' : 'Reset simulator'}
                </button>
                <button className="button primary" type="button" onClick={inject} disabled={busy !== ''}>
                  {busy === 'inject' ? 'Injecting...' : 'Inject incident'}
                </button>
              </div>
            </div>

            <div className="scenario-grid" role="radiogroup" aria-label="Incident scenario">
              {scenarios.map((option) => {
                const selected = scenario === option.value
                return (
                  <button
                    key={option.value}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    className={`scenario-card ${selected ? 'selected' : ''}`}
                    onClick={() => setScenario(option.value)}
                    disabled={busy !== ''}
                  >
                    <span className="scenario-card-top">
                      <strong>{option.label}</strong>
                      <span className="scenario-radio" />
                    </span>
                    <p>{option.description}</p>
                  </button>
                )
              })}
            </div>

            <div className="simulator-footer">
              <span>Simulation only</span>
              <span>Payment records are not mutated</span>
            </div>
          </section>

          {error && (
            <section className="message-banner error" role="alert">
              <div>
                <strong>Something needs attention.</strong>
                <p>{error}</p>
              </div>
            </section>
          )}

          {toast && (
            <div className={`toast ${toast.kind}`} role="status" aria-live="polite">
              <span className="toast-dot" />
              <span>{toast.message}</span>
            </div>
          )}

          <section className="overview-grid">
            <div className="panel chart-panel">
              <div className="panel-head compact">
                <div>
                  <p className="section-kicker">Operational signal</p>
                  <h2>Payment health</h2>
                </div>
                <span className="panel-meta">Recent transaction sample</span>
              </div>

              <div className="chart-wrap">
                {!pageReady || !chartPoints.length ? (
                  <div className="skeleton chart-skeleton" />
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={chartPoints}>
                      <defs>
                        <linearGradient id="successFill" x1="0" x2="0" y1="0" y2="1">
                          <stop offset="5%" stopColor="var(--success)" stopOpacity={0.25} />
                          <stop offset="95%" stopColor="var(--success)" stopOpacity={0.02} />
                        </linearGradient>
                        <linearGradient id="failureFill" x1="0" x2="0" y1="0" y2="1">
                          <stop offset="5%" stopColor="var(--danger)" stopOpacity={0.2} />
                          <stop offset="95%" stopColor="var(--danger)" stopOpacity={0.02} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid stroke="var(--border)" strokeDasharray="4 4" vertical={false} />
                      <XAxis dataKey="label" stroke="var(--muted)" tickLine={false} axisLine={false} />
                      <YAxis stroke="var(--muted)" tickLine={false} axisLine={false} width={28} />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: 'var(--surface-elevated)',
                          border: '1px solid var(--border-strong)',
                          borderRadius: 14,
                          boxShadow: 'var(--shadow-md)',
                        }}
                        labelStyle={{ color: 'var(--text)', fontWeight: 700 }}
                        itemStyle={{ color: 'var(--muted-strong)' }}
                      />
                      <Area type="monotone" dataKey="success" stroke="var(--success)" strokeWidth={2} fill="url(#successFill)" />
                      <Area type="monotone" dataKey="failure" stroke="var(--danger)" strokeWidth={2} fill="url(#failureFill)" />
                    </AreaChart>
                  </ResponsiveContainer>
                )}
              </div>
            </div>

            <div className="panel incident-list-panel">
              <div className="panel-head compact">
                <div>
                  <p className="section-kicker">Active incidents</p>
                  <h2>Open investigations</h2>
                </div>
                <span className="panel-meta">{incidents.length} detected</span>
              </div>

              {incidents.length === 0 ? (
                <div className="empty-state">
                  <div className="empty-mark" />
                  <strong>All systems are currently operating normally.</strong>
                  <p>No active incidents are waiting for investigation.</p>
                </div>
              ) : (
                <div className="incident-list">
                  {incidents.slice(0, 6).map((item) => {
                    const selected = selectedIncident?.incident_id === item.incident_id
                    return (
                      <button
                        key={item.incident_id}
                        type="button"
                        className={`incident-row ${selected ? 'selected' : ''}`}
                        onClick={() => selectIncident(item)}
                        disabled={workspaceLoading}
                      >
                        <div className={`severity-rail ${item.severity}`} />
                        <div className="incident-row-main">
                          <div className="incident-row-title">
                            <strong>{formatLabel(item.incident_type)}</strong>
                            <span>{item.incident_id}</span>
                          </div>
                          <div className="incident-row-meta">
                            <span>{item.primary_provider ?? 'Multi-provider'}</span>
                            <span>{item.primary_region ?? 'Multi-region'}</span>
                          </div>
                        </div>
                        <div className="incident-row-side">
                          <StatusChip value={item.severity} />
                          <small>{formatDateTime(item.detected_at)}</small>
                        </div>
                      </button>
                    )
                  })}
                </div>
              )}
            </div>
          </section>

          {selectedIncident && (
            <section className="workspace" ref={workspaceRef}>
              <div className="workspace-header">
                <div className="incident-identity">
                  <div className="identity-topline">
                    <span className={`live-dot ${selectedIncident.status === 'completed' ? 'inactive' : ''}`} />
                    <span>{selectedIncident.status === 'completed' ? 'Completed incident' : 'Active incident'}</span>
                  </div>
                  <h2>{formatLabel(selectedIncident.incident_type)}</h2>
                  <p>{selectedIncident.description || 'Detailed incident context from the backend investigation system.'}</p>

                  <div className="identity-meta">
                    <button
                      type="button"
                      className="copy-chip"
                      onClick={() => copyToClipboard(selectedIncident.incident_id, 'Incident ID')}
                    >
                      <span>Incident ID</span>
                      <strong>{selectedIncident.incident_id}</strong>
                    </button>
                    <span className="meta-pill">
                      <strong>Severity</strong>
                      <StatusChip value={selectedIncident.severity} />
                    </span>
                    <span className="meta-pill">
                      <strong>Status</strong>
                      <StatusChip value={selectedIncident.status} />
                    </span>
                    <span className="meta-pill">
                      <strong>Detected</strong>
                      <span>{formatDateTime(selectedIncident.detected_at)}</span>
                    </span>
                    <span className="meta-pill">
                      <strong>Provider</strong>
                      <span>{selectedIncident.primary_provider ?? 'Multi-provider'}</span>
                    </span>
                    <span className="meta-pill">
                      <strong>Scope</strong>
                      <span>{selectedIncident.primary_region ?? 'Multi-region'}</span>
                    </span>
                  </div>
                </div>

                <div className="workspace-header-side">
                  <div className="confidence-ring">
                    <div>
                      <strong>{selectedIncident.anomaly_score.toFixed(1)}</strong>
                      <span>anomaly</span>
                    </div>
                  </div>
                  <div className="header-side-card">
                    <strong>{selectedIncident.affected_transactions.toLocaleString()} affected payments</strong>
                    <span>{selectedIncident.affected_merchants.toLocaleString()} merchants touched</span>
                    <span>{formatMoney(selectedIncident.revenue_at_risk)} estimated revenue at risk</span>
                  </div>
                </div>
              </div>

              <LifecycleRail stages={incidentProgress} activeIndex={lifecyclePhase} />

              <div className="workspace-grid">
                <div className="workspace-main">
                  <section className="section-card rca-card">
                    <SectionHeading eyebrow="Root cause analysis" title="What happened, and why do we believe it?" />
                    {workspaceLoading || (!investigationResult && !investigation) ? (
                      <div className="rca-empty">
                        <div>
                          <h3>Run the investigation to synthesize the evidence.</h3>
                          <p>
                            The backend will compare payment signals, provider health, regional behavior, and historical
                            incidents before producing a ranked explanation.
                          </p>
                        </div>
                        <button type="button" className="button primary" onClick={investigate} disabled={investigating || busy !== ''}>
                          {investigating ? 'Investigating...' : 'Investigate incident'}
                        </button>
                      </div>
                    ) : (
                      <div className="rca-result">
                        <div className="rca-mark">
                          <span>RCA</span>
                        </div>
                        <div className="rca-body">
                          <div className="rca-headline">
                            <div>
                              <p className="section-kicker">Primary root cause</p>
                              <h3>{investigationResult.root_cause}</h3>
                            </div>
                            <div className="rca-confidence">
                              <strong>{Math.round(investigationResult.confidence * 100)}%</strong>
                              <span>confidence</span>
                            </div>
                          </div>

                          <p className="rca-explanation">{investigationResult.incident_summary}</p>

                          <div className="rca-meta-grid">
                            <div>
                              <span>Component</span>
                              <strong>{formatLabel(investigationResult.root_cause_category)}</strong>
                            </div>
                            <div>
                              <span>Supporting signals</span>
                              <strong>{investigationResult.evidence.length} evidence items</strong>
                            </div>
                            <div>
                              <span>Recommended next step</span>
                              <strong>{investigationResult.recommended_next_step}</strong>
                            </div>
                          </div>
                        </div>
                      </div>
                    )}
                  </section>

                  {investigationResult && (
                    <>
                      <details className="analysis-panel" open>
                        <summary>
                          <div>
                            <p className="section-kicker">Evidence</p>
                            <strong>Investigative evidence stream</strong>
                          </div>
                          <span>{investigationResult.evidence.length} signals</span>
                        </summary>
                        <div className="evidence-stream">
                          {investigationResult.evidence.map((item: any, index: number) => (
                            <article
                              key={item.evidence_id}
                              className="evidence-item"
                              style={{ animationDelay: `${index * 42}ms` }}
                            >
                              <div className={`evidence-node ${item.severity}`} />
                              <div className="evidence-content">
                                <div className="evidence-topline">
                                  <div>
                                    <strong>{formatLabel(item.metric)}</strong>
                                    <span>{item.source}</span>
                                  </div>
                                  <StatusChip value={item.severity} />
                                </div>
                                <p>{item.description}</p>
                                <div className="evidence-meta">
                                  <span>Relevance {Math.round(item.relevance * 100)}%</span>
                                  <span>{item.timestamp ? formatDateTime(item.timestamp) : 'Observed in analysis'}</span>
                                  {item.delta !== null && item.delta !== undefined && <span>Delta {Number(item.delta).toFixed(2)}</span>}
                                </div>
                              </div>
                            </article>
                          ))}
                        </div>
                      </details>

                      <details className="analysis-panel" open>
                        <summary>
                          <div>
                            <p className="section-kicker">Hypotheses</p>
                            <strong>Ranked analytical view</strong>
                          </div>
                          <span>{rankedHypotheses.length} considered</span>
                        </summary>
                        <div className="hypothesis-list">
                          {rankedHypotheses.map((item: any, index: number) => {
                            const score = scoreHypothesis(item.status)
                            return (
                              <div
                                key={item.hypothesis}
                                className="hypothesis-row"
                                style={{ animationDelay: `${index * 40}ms` }}
                              >
                                <div className="hypothesis-name">
                                  <span className={`hypothesis-index ${item.status}`}>{index + 1}</span>
                                  <div>
                                    <strong>{item.hypothesis}</strong>
                                    <p>{item.reason}</p>
                                  </div>
                                </div>
                                <div className="hypothesis-score">
                                  <strong>{score}%</strong>
                                  <span className={item.status}>{formatLabel(item.status)}</span>
                                  <div className="hypothesis-track">
                                    <span className={item.status} style={{ width: `${score}%` }} />
                                  </div>
                                </div>
                              </div>
                            )
                          })}
                        </div>
                      </details>

                      <details className="analysis-panel">
                        <summary>
                          <div>
                            <p className="section-kicker">Similar incidents</p>
                            <strong>Historical context and outcome</strong>
                          </div>
                          <span>{similarIncidents.length} matches</span>
                        </summary>
                        <div className="similar-list">
                          {similarIncidents.length === 0 ? (
                            <div className="empty-inline">
                              <strong>No similar incidents available.</strong>
                              <p>The investigation did not surface a strong historical match.</p>
                            </div>
                          ) : (
                            similarIncidents.map((item: any) => (
                              <article key={item.incident_id} className="similar-row">
                                <div className="similar-main">
                                  <strong>{item.history?.incident_type ? formatLabel(item.history.incident_type) : 'Historical match'}</strong>
                                  <span>{item.history?.timestamp ? formatShortDate(item.history.timestamp) : 'Date unavailable'}</span>
                                </div>
                                <div className="similar-side">
                                  <strong>{Math.round(item.similarity * 100)}%</strong>
                                  <span>similarity</span>
                                </div>
                                <div className="similar-outcome">
                                  <span>{item.resolution}</span>
                                  <small>{formatMoney(item.history?.revenue_impact)}</small>
                                </div>
                              </article>
                            ))
                          )}
                        </div>
                      </details>

                      <details className="analysis-panel">
                        <summary>
                          <div>
                            <p className="section-kicker">Incident timeline</p>
                            <strong>Persisted chronology</strong>
                          </div>
                          <span>{chronology.length} records</span>
                        </summary>
                        <div className="timeline-stream">
                          {chronology.map((item, index) => (
                            <article key={`${item.label}-${index}`} className={`timeline-item ${item.kind}`}>
                              <div className="timeline-node" />
                              <div className="timeline-content">
                                <div>
                                  <strong>{item.label}</strong>
                                  <span>{item.note}</span>
                                </div>
                                <small>{item.time ?? 'State recorded'}</small>
                              </div>
                            </article>
                          ))}
                        </div>
                      </details>
                    </>
                  )}
                </div>

                <aside className="workspace-side">
                  <section className="section-card impact-card">
                    <SectionHeading eyebrow="Impact" title="What was affected?" />
                    <div className="impact-lead">
                      <span>Estimated revenue at risk</span>
                      <strong>{formatMoney(impact?.revenue_at_risk ?? selectedIncident.revenue_at_risk)}</strong>
                    </div>

                    <div className="impact-grid">
                      <MetricPill label="Affected payments" value={impact?.affected_transactions ?? selectedIncident.affected_transactions} animated={Boolean(impact)} />
                      <MetricPill label="Failed payments" value={impact?.failed_transactions ?? 0} animated={Boolean(impact)} />
                      <MetricPill label="Merchants affected" value={impact?.affected_merchants ?? selectedIncident.affected_merchants} animated={Boolean(impact)} />
                      <MetricPill label="Duration" value={formatDuration(impact?.incident_duration_minutes ?? 0)} animated={Boolean(impact)} />
                      <MetricPill
                        label="Recoverable revenue"
                        value={formatMoney(impact?.estimated_recoverable_revenue ?? 0)}
                        animated={Boolean(impact)}
                      />
                      <MetricPill
                        label="Success rate delta"
                        value={`${percentFormatter.format(Math.abs((impact?.success_rate_delta ?? 0) * 100))}%`}
                        animated={Boolean(impact)}
                      />
                    </div>

                    <div className="impact-meta">
                      <div>
                        <span>Provider</span>
                        <strong>{(impact?.affected_providers ?? [selectedIncident.primary_provider ?? 'Multi-provider']).join(', ')}</strong>
                      </div>
                      <div>
                        <span>Payment methods</span>
                        <strong>{(impact?.affected_payment_methods ?? [selectedIncident.primary_payment_method ?? 'Mixed']).join(', ')}</strong>
                      </div>
                    </div>
                  </section>

                  <section className="section-card recovery-card">
                    <SectionHeading eyebrow="Controlled recovery" title="Recommended recovery" />
                    <div className="recommendation-block">
                      <div className="recommendation-head">
                        <p>{recommendation ? formatLabel(recommendation.strategy) : 'Awaiting analysis'}</p>
                        {policy && <StatusChip value={policy.risk_level} />}
                      </div>
                      <strong>{recommendation?.expected_benefit ?? 'Run the investigation to generate a recovery recommendation.'}</strong>
                      <span>{recommendation?.reason ?? 'The recovery workflow becomes available after the incident is understood.'}</span>
                    </div>

                    <RecoveryLadder recovery={recovery} policy={policy} />

                    {selectedIncident && !recovery && (
                      <button
                        type="button"
                        className="button primary full-width"
                        onClick={() => runRecoveryAction('prepare', `/incidents/${selectedIncident.incident_id}/recovery`)}
                        disabled={busy !== '' || policy?.allowed === false}
                      >
                        {busy === 'prepare' ? 'Preparing...' : 'Prepare recovery'}
                      </button>
                    )}

                    {recovery?.approval_status === 'pending' && (
                      <button
                        type="button"
                        className="button primary full-width"
                        onClick={() => runRecoveryAction('approve', `/recoveries/${recovery.recovery_id}/approve`)}
                        disabled={busy !== ''}
                      >
                        {busy === 'approve' ? 'Approving...' : 'Approve recovery'}
                      </button>
                    )}

                    {recovery?.approval_status === 'approved' && recovery.execution_status === 'not_started' && (
                      <button
                        type="button"
                        className="button primary full-width"
                        onClick={() => runRecoveryAction('execute', `/recoveries/${recovery.recovery_id}/execute`)}
                        disabled={busy !== ''}
                      >
                        {busy === 'execute' ? 'Executing...' : 'Execute simulation'}
                      </button>
                    )}

                    {policy && !policy.allowed && (
                      <div className="policy-note">
                        <strong>Policy blocked automation</strong>
                        <p>{policy.reasons?.join(' ') ?? 'Human approval is required before recovery can proceed.'}</p>
                      </div>
                    )}

                    {recovery && (
                      <div className="recovery-summary">
                        <div>
                          <span>Recovery ID</span>
                          <button type="button" className="inline-copy" onClick={() => copyToClipboard(recovery.recovery_id, 'Recovery ID')}>
                            {recovery.recovery_id}
                          </button>
                        </div>
                        <div>
                          <span>Prepared at</span>
                          <strong>{formatDateTime(recovery.timestamp)}</strong>
                        </div>
                        <div>
                          <span>Approval state</span>
                          <StatusChip value={recovery.approval_status} />
                        </div>
                        <div>
                          <span>Execution state</span>
                          <StatusChip value={recovery.execution_status} />
                        </div>
                      </div>
                    )}

                    {recovery?.execution_status === 'completed' && (
                      <div className="completion-card">
                        <div className="completion-mark" />
                        <div>
                          <strong>Recovery completed</strong>
                          <p>
                            {recovery.recovered_transactions} transactions recovered for {formatMoney(recovery.recovered_revenue)}.
                          </p>
                        </div>
                      </div>
                    )}

                    <p className="simulation-note">Simulation only. Recovery actions are controlled by backend policy checks.</p>
                  </section>
                </aside>
              </div>
            </section>
          )}
        </main>
      </div>
    </div>
  )
}

function buildChronology(
  incident: Incident,
  investigation: any,
  recovery: RecoveryExecution | null,
  timeline: any[],
) {
  const items: Array<{ label: string; note: string; time?: string; kind: 'info' | 'warning' | 'critical' | 'success' }> = []

  if (incident.started_at) {
    items.push({
      label: 'Incident begins',
      note: 'Persisted incident start time',
      time: formatDateTime(incident.started_at),
      kind: 'info',
    })
  }

  timeline.forEach((entry: any) => {
    items.push({
      label: entry.event,
      note: `Timeline signal: ${entry.level}`,
      time: formatDateTime(entry.time),
      kind: entry.level === 'critical' ? 'critical' : entry.level === 'warning' ? 'warning' : 'info',
    })
  })

  if (incident.detected_at) {
    items.push({
      label: 'Incident detected',
      note: 'Backend anomaly detector raised the incident',
      time: formatDateTime(incident.detected_at),
      kind: 'critical',
    })
  }

  if (investigation?.started_at) {
    items.push({
      label: 'Investigation starts',
      note: `Investigation ${investigation.investigation_id}`,
      time: formatDateTime(investigation.started_at),
      kind: 'warning',
    })
  }

  if (investigation?.completed_at) {
    items.push({
      label: 'RCA prepared',
      note: `${Math.round((investigation.final_result?.confidence ?? 0) * 100)}% confidence`,
      time: formatDateTime(investigation.completed_at),
      kind: 'success',
    })
  }

  if (recovery?.timestamp) {
    items.push({
      label: 'Recovery prepared',
      note: `Strategy: ${formatLabel(recovery.strategy)}`,
      time: formatDateTime(recovery.timestamp),
      kind: 'info',
    })
  }

  if (recovery?.approval_status === 'approved') {
    items.push({
      label: 'Approval recorded',
      note: 'Operator approval captured by the backend state machine',
      kind: 'success',
    })
  }

  if (recovery?.execution_status === 'completed') {
    items.push({
      label: 'Recovery executed',
      note: `Recovered ${recovery.recovered_transactions} transactions`,
      kind: 'success',
    })
  }

  return items
}

function HeroStat({
  label,
  value,
  formatValue,
  tone,
  animated,
}: {
  label: string
  value: number
  formatValue: (value: number) => string
  tone: 'success' | 'danger' | 'warning'
  animated: boolean
}) {
  const animatedValue = useAnimatedNumber(value, animated)
  return (
    <div className={`hero-stat ${tone} ${animated ? 'animated' : ''}`}>
      <span>{label}</span>
      <strong>{formatValue(animatedValue)}</strong>
    </div>
  )
}

function MetricPill({
  label,
  value,
  animated,
}: {
  label: string
  value: string | number
  animated: boolean
}) {
  const numeric = typeof value === 'number' ? value : Number.parseFloat(String(value).replace(/[^0-9.-]/g, '')) || 0
  const animatedValue = useAnimatedNumber(numeric, animated)
  const display = typeof value === 'number' ? Math.round(animatedValue).toLocaleString('en-IN') : value

  return (
    <div className={`metric-pill ${animated ? 'animated' : ''}`}>
      <span>{label}</span>
      <strong>{display}</strong>
    </div>
  )
}

function RecoveryLadder({ recovery, policy }: { recovery: RecoveryExecution | null; policy: any }) {
  const steps = [
    {
      label: 'Prepare',
      note: recovery ? 'Prepared in backend' : policy?.allowed === false ? 'Blocked by policy' : 'Ready to prepare',
      status: recovery ? 'complete' : policy?.allowed === false ? 'blocked' : 'active',
    },
    {
      label: 'Approval required',
      note: recovery?.approval_status === 'pending' ? 'Waiting on human approval' : recovery?.approval_status === 'approved' ? 'Approved' : 'Pending',
      status: recovery
        ? recovery.approval_status === 'approved'
          ? 'complete'
          : recovery.approval_status === 'pending'
            ? 'active'
            : 'pending'
        : 'pending',
    },
    {
      label: 'Approved',
      note: recovery?.approval_status ?? 'Waiting',
      status: recovery?.approval_status === 'approved' ? 'complete' : 'pending',
    },
    {
      label: 'Execute',
      note: recovery?.execution_status === 'completed' ? 'Simulation executed' : recovery?.approval_status === 'approved' ? 'Ready to execute' : 'Pending',
      status: recovery?.execution_status === 'completed' ? 'complete' : recovery?.approval_status === 'approved' ? 'active' : 'pending',
    },
    {
      label: 'Completed',
      note: recovery?.execution_status === 'completed' ? 'Finished' : 'Awaiting execution',
      status: recovery?.execution_status === 'completed' ? 'complete' : 'pending',
    },
  ]

  return (
    <div className="recovery-ladder">
      {steps.map((step, index) => (
        <div key={step.label} className={`ladder-step ${step.status}`} style={{ animationDelay: `${index * 48}ms` }}>
          <div className="ladder-index">{index + 1}</div>
          <div>
            <strong>{step.label}</strong>
            <span>{step.note}</span>
          </div>
        </div>
      ))}
    </div>
  )
}

function LifecycleRail({ stages, activeIndex }: { stages: Array<{ label: string; note: string; status: string }>; activeIndex: number }) {
  return (
    <div className="lifecycle-rail">
      {stages.map((stage, index) => (
        <div key={stage.label} className={`lifecycle-step ${stage.status}`} style={{ animationDelay: `${index * 40}ms` }}>
          <div className="lifecycle-node">
            <span>{index + 1}</span>
          </div>
          <div>
            <strong>{stage.label}</strong>
            <span>{stage.note}</span>
          </div>
        </div>
      ))}
      <div className="lifecycle-marker" style={{ width: `${Math.max(0, Math.min(activeIndex, stages.length - 1)) * 20}%` }} />
    </div>
  )
}

function SectionHeading({ eyebrow, title }: { eyebrow: string; title: string }) {
  return (
    <div className="section-heading">
      <p className="section-kicker">{eyebrow}</p>
      <h3>{title}</h3>
    </div>
  )
}

function StatusChip({ value }: { value: string }) {
  return (
    <span className={`status-chip ${value.toLowerCase()}`}>
      <span className="status-chip-dot" />
      {formatLabel(value)}
    </span>
  )
}
