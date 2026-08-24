import { useEffect, useMemo, useRef, useState } from 'react'
import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

const API_URL = `${import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'}/api`

type ReplaySnapshot = {
  phase: 'before_incident' | 'detection' | 'investigation' | 'root_cause' | 'recovery' | 'resolution'
  signal_summary: string
  failure_rate?: number | null
  success_rate?: number | null
  provider_latency_p95_ms?: number | null
  affected_transactions?: number | null
  affected_merchants?: number | null
  revenue_at_risk?: number | null
  confidence?: number | null
  evidence_count?: number
  root_cause?: string | null
  recommendation?: string | null
  approval_status?: string | null
  execution_status?: string | null
  investigation_id?: string | null
  recovery_id?: string | null
  incident_status?: string | null
  metrics?: Record<string, any>
  impact?: Record<string, any>
  evidence?: Array<{
    evidence_id: string
    source: string
    metric: string
    severity: string
    relevance: number
    description: string
    timestamp?: string | null
  }>
  hypotheses?: Array<{
    hypothesis: string
    status: string
    reason: string
  }>
  historical_matches?: Array<{
    incident_id: string
    similarity: number
    root_cause: string
    resolution: string
    recovery_rate: number
  }>
}

type ReplayEvent = {
  event_id: string
  index: number
  type: string
  timestamp: string
  title: string
  description: string
  phase: ReplaySnapshot['phase']
  severity: 'low' | 'medium' | 'high' | 'critical' | 'info'
  incident_id: string
  investigation_id?: string | null
  recovery_id?: string | null
  snapshot: ReplaySnapshot
  metadata: Record<string, any>
}

type ReplayTimeline = {
  incident: {
    incident_id: string
    source_kind: 'incident' | 'historical'
    incident_type?: string | null
    severity?: string | null
    status?: string | null
    started_at: string
    detected_at?: string | null
    ended_at?: string | null
    primary_provider?: string | null
    primary_payment_method?: string | null
    primary_region?: string | null
    description?: string | null
    fingerprint?: string | null
  }
  start_at: string
  end_at: string
  duration_seconds: number
  event_count: number
  replayable: boolean
  deterministic: boolean
  has_investigation: boolean
  has_recovery: boolean
  current_phase: ReplaySnapshot['phase']
  events: ReplayEvent[]
}

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

function formatDateTime(value?: string | null) {
  if (!value) return 'Pending'
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function formatDuration(value: number) {
  if (value < 60) return `${Math.round(value)}s`
  const minutes = Math.floor(value / 60)
  const seconds = Math.round(value % 60)
  return `${minutes}m ${seconds}s`
}

function formatPercent(value: number | null | undefined, digits = 0) {
  return `${((value ?? 0) * 100).toFixed(digits)}%`
}

const playbackSpeeds = [0.5, 1, 2, 5, 10] as const
const phases: Array<{ label: string; value: ReplaySnapshot['phase'] }> = [
  { label: 'Before incident', value: 'before_incident' },
  { label: 'Detection', value: 'detection' },
  { label: 'Investigation', value: 'investigation' },
  { label: 'Root cause', value: 'root_cause' },
  { label: 'Recovery', value: 'recovery' },
  { label: 'Resolution', value: 'resolution' },
]

export default function ReplayPanel({
  incidentId,
  onExit,
}: {
  incidentId: string
  onExit: () => void
}) {
  const reduceMotionRef = useRef(false)
  const [timeline, setTimeline] = useState<ReplayTimeline | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState<(typeof playbackSpeeds)[number]>(1)
  const [activeIndex, setActiveIndex] = useState(0)

  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    const update = () => {
      reduceMotionRef.current = media.matches
      if (media.matches) setPlaying(false)
    }
    update()
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])

  useEffect(() => {
    let mounted = true
    setLoading(true)
    setError(null)
    setPlaying(false)
    setActiveIndex(0)

    ;(async () => {
      try {
        const payload = await api(`/incidents/${incidentId}/replay`)
        if (!mounted) return
        setTimeline(payload)
      } catch (reason: any) {
        if (mounted) setError(reason.message)
      } finally {
        if (mounted) setLoading(false)
      }
    })()

    return () => {
      mounted = false
    }
  }, [incidentId])

  const events = timeline?.events ?? []
  const activeEvent = events[activeIndex] ?? events[0] ?? null
  const progress = events.length > 1 ? (activeIndex / (events.length - 1)) * 100 : 0

  useEffect(() => {
    if (!playing || events.length === 0) return
    const delay = Math.max(120, 900 / speed)
    const timer = window.setInterval(() => {
      setActiveIndex((current) => {
        if (current >= events.length - 1) {
          window.clearInterval(timer)
          setPlaying(false)
          return current
        }
        return current + 1
      })
    }, delay)
    return () => window.clearInterval(timer)
  }, [events.length, playing, speed])

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.code === 'Space') {
        event.preventDefault()
        setPlaying((current) => !current)
      }
      if (event.key === 'ArrowLeft') {
        event.preventDefault()
        setPlaying(false)
        setActiveIndex((current) => Math.max(0, current - 1))
      }
      if (event.key === 'ArrowRight') {
        event.preventDefault()
        setPlaying(false)
        setActiveIndex((current) => Math.min(events.length - 1, current + 1))
      }
      if (event.key.toLowerCase() === 'r') {
        event.preventDefault()
        setPlaying(false)
        setActiveIndex(0)
      }
    }

    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [events.length])

  useEffect(() => {
    if (reduceMotionRef.current) setPlaying(false)
  }, [activeIndex])

  const chartData = useMemo(
    () =>
      events.map((event, index) => ({
        label: `${index + 1}`,
        event_id: event.event_id,
        failure_rate: event.snapshot.failure_rate ?? event.snapshot.metrics?.current_failure_rate ?? 0,
        success_rate: event.snapshot.success_rate ?? event.snapshot.metrics?.current_success_rate ?? 0,
        latency: event.snapshot.provider_latency_p95_ms ?? event.snapshot.metrics?.current_latency_p95_ms ?? 0,
      })),
    [events],
  )

  const currentPhaseIndex = Math.max(
    0,
    phases.findIndex((phase) => phase.value === activeEvent?.phase),
  )

  if (loading) {
    return (
      <div className="replay-shell">
        <div className="replay-loading">
          <div className="skeleton replay-skeleton" />
          <div className="skeleton replay-skeleton" />
        </div>
      </div>
    )
  }

  if (error || !timeline || !activeEvent) {
    return (
      <div className="replay-shell">
        <div className="replay-empty">
          <div>
            <p className="section-kicker">Replay mode</p>
            <h3>Replay data is unavailable.</h3>
            <p>{error ?? 'This incident does not currently have replayable data.'}</p>
          </div>
          <button type="button" className="button secondary" onClick={onExit}>
            Exit replay
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="replay-shell">
      <div className="replay-header">
        <div>
          <p className="section-kicker">Incident replay engine</p>
          <h3>{formatLabel(timeline.incident.incident_type ?? 'Historical incident')}</h3>
          <p>
            {timeline.incident.incident_id} | {timeline.incident.primary_provider ?? 'Multi-provider'} |{' '}
            {timeline.incident.primary_region ?? 'Multi-region'}
          </p>
        </div>
        <div className="replay-header-actions">
          <button type="button" className="button secondary" onClick={onExit}>
            Exit replay
          </button>
          <button type="button" className="button secondary" onClick={() => { setPlaying(false); setActiveIndex(0) }}>
            Restart
          </button>
        </div>
      </div>

      <div className="replay-meta-grid">
        <Meta label="Severity" value={timeline.incident.severity ?? 'unknown'} />
        <Meta label="Status" value={timeline.incident.status ?? 'resolved'} />
        <Meta label="Start" value={formatDateTime(timeline.start_at)} />
        <Meta label="End" value={formatDateTime(timeline.end_at)} />
        <Meta label="Duration" value={formatDuration(timeline.duration_seconds)} />
        <Meta label="Progress" value={`${Math.round(progress)}%`} />
      </div>

      <div className="replay-controls">
        <div className="replay-buttons">
          <button type="button" className="button secondary" onClick={() => {
            setPlaying(false)
            setActiveIndex((current) => Math.max(0, current - 1))
          }}>
            Previous
          </button>
          <button type="button" className="button primary" onClick={() => setPlaying((current) => !current)}>
            {playing ? 'Pause' : 'Play'}
          </button>
          <button type="button" className="button secondary" onClick={() => {
            setPlaying(false)
            setActiveIndex((current) => Math.min(events.length - 1, current + 1))
          }}>
            Next
          </button>
        </div>

        <div className="replay-speeds">
          {playbackSpeeds.map((item) => (
            <button
              key={item}
              type="button"
              className={`speed-chip ${speed === item ? 'active' : ''}`}
              onClick={() => setSpeed(item)}
            >
              {item}x
            </button>
          ))}
        </div>
      </div>

      <div className="replay-timeline-panel">
        <div className="replay-timeline-header">
          <span>Timeline</span>
          <strong>
            {activeIndex + 1} of {events.length}
          </strong>
        </div>
        <div className="replay-track-wrap">
          <div className="replay-track">
            <div className="replay-track-fill" style={{ width: `${progress}%` }} />
            <div className="replay-track-cursor" style={{ left: `${progress}%` }} />
            {events.map((event, index) => {
              const position = events.length > 1 ? (index / (events.length - 1)) * 100 : 0
              const active = index === activeIndex
              return (
                <button
                  key={event.event_id}
                  type="button"
                  className={`replay-marker ${active ? 'active' : ''} ${event.severity}`}
                  style={{ left: `${position}%`, transform: `translateX(-50%) translateY(${index % 2 === 0 ? -8 : 8}px)` }}
                  onClick={() => {
                    setPlaying(false)
                    setActiveIndex(index)
                  }}
                  aria-label={`${event.title} at ${formatDateTime(event.timestamp)}`}
                >
                  <span />
                </button>
              )
            })}
          </div>
          <input
            className="replay-scrubber"
            type="range"
            min={0}
            max={Math.max(events.length - 1, 0)}
            step={1}
            value={activeIndex}
            onChange={(event) => {
              setPlaying(false)
              setActiveIndex(Number(event.target.value))
            }}
            aria-label="Replay scrubber"
          />
        </div>
      </div>

      <div className="replay-phase-rail">
        {phases.map((phase, index) => (
          <div key={phase.value} className={`replay-phase ${index < currentPhaseIndex ? 'complete' : ''} ${index === currentPhaseIndex ? 'active' : ''}`}>
            <span>{index + 1}</span>
            <strong>{phase.label}</strong>
          </div>
        ))}
      </div>

      <div className="replay-grid">
        <section className="section-card replay-moment-card">
          <div className="panel-head compact">
            <div>
              <p className="section-kicker">Current replay moment</p>
              <h2>{activeEvent.title}</h2>
            </div>
            <span className="panel-meta">{formatDateTime(activeEvent.timestamp)}</span>
          </div>
          <p className="replay-description">{activeEvent.description}</p>
          <div className="replay-moment-summary">
            <Metric label="Failure rate" value={activeEvent.snapshot.failure_rate ?? activeEvent.snapshot.metrics?.current_failure_rate ?? 0} tone="danger" />
            <Metric label="Success rate" value={activeEvent.snapshot.success_rate ?? activeEvent.snapshot.metrics?.current_success_rate ?? 0} tone="success" />
            <Metric label="Latency p95" value={activeEvent.snapshot.provider_latency_p95_ms ?? activeEvent.snapshot.metrics?.current_latency_p95_ms ?? 0} tone="warning" />
          </div>
          <div className="replay-snapshot-line">
            <strong>{activeEvent.snapshot.signal_summary}</strong>
            <span>{activeEvent.snapshot.phase.replaceAll('_', ' ')}</span>
          </div>
        </section>

        <section className="section-card replay-chart-card">
          <div className="panel-head compact">
            <div>
              <p className="section-kicker">Signal evolution</p>
              <h2>Failure rate over time</h2>
            </div>
            <span className="panel-meta">Virtual replay clock</span>
          </div>
          <div className="replay-chart-wrap">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient id="replayFailureFill" x1="0" x2="0" y1="0" y2="1">
                    <stop offset="5%" stopColor="var(--danger)" stopOpacity={0.26} />
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
                />
                <ReferenceLine x={chartData[activeIndex]?.label} stroke="var(--accent)" strokeDasharray="4 4" />
                <Area type="monotone" dataKey="failure_rate" stroke="var(--danger)" strokeWidth={2} fill="url(#replayFailureFill)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </section>

        <section className="section-card replay-analysis-card">
          <div className="panel-head compact">
            <div>
              <p className="section-kicker">Investigation context</p>
              <h2>Why the system believes this</h2>
            </div>
            <span className="panel-meta">
              Confidence {formatPercent(activeEvent.snapshot.confidence ?? 0, 0)}
            </span>
          </div>
          <div className="replay-analysis-stack">
            <div className="replay-root-cause">
              <span>Root cause</span>
              <strong>{activeEvent.snapshot.root_cause ?? 'Not yet confirmed'}</strong>
            </div>
            <div className="replay-evidence-list">
              {(activeEvent.snapshot.evidence ?? []).slice(0, 4).map((item) => (
                <div key={item.evidence_id} className="replay-evidence-row">
                  <div>
                    <strong>{formatLabel(item.metric)}</strong>
                    <span>{item.source}</span>
                  </div>
                  <p>{item.description}</p>
                </div>
              ))}
            </div>
            <div className="replay-hypothesis-list">
              {(activeEvent.snapshot.hypotheses ?? []).slice(0, 3).map((item) => (
                <div key={item.hypothesis} className={`replay-hypothesis ${item.status}`}>
                  <div>
                    <strong>{item.hypothesis}</strong>
                    <span>{item.reason}</span>
                  </div>
                  <em>{item.status.replaceAll('_', ' ')}</em>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="section-card replay-recovery-card">
          <div className="panel-head compact">
            <div>
              <p className="section-kicker">Recovery progression</p>
              <h2>Prepare, approve, execute</h2>
            </div>
            <span className="panel-meta">{activeEvent.snapshot.recovery_id ?? 'No recovery record'}</span>
          </div>
          <div className="replay-recovery-ladder">
            <RecoveryStep label="Prepare" status={activeEvent.snapshot.recovery_id ? 'complete' : 'active'} detail={activeEvent.snapshot.recovery_id ? 'Recovery prepared' : 'Ready to prepare'} />
            <RecoveryStep label="Approval required" status={activeEvent.snapshot.approval_status === 'approved' ? 'complete' : activeEvent.snapshot.approval_status === 'pending' ? 'active' : 'pending'} detail={activeEvent.snapshot.approval_status ?? 'Pending'} />
            <RecoveryStep label="Approved" status={activeEvent.snapshot.approval_status === 'approved' ? 'complete' : 'pending'} detail={activeEvent.snapshot.approval_status === 'approved' ? 'Operator approval captured' : 'Waiting'} />
            <RecoveryStep label="Execute" status={activeEvent.snapshot.execution_status === 'completed' ? 'complete' : activeEvent.snapshot.approval_status === 'approved' ? 'active' : 'pending'} detail={activeEvent.snapshot.execution_status ?? 'Pending'} />
            <RecoveryStep label="Completed" status={activeEvent.snapshot.execution_status === 'completed' ? 'complete' : 'pending'} detail={activeEvent.snapshot.execution_status === 'completed' ? 'Simulation completed' : 'Awaiting execution'} />
          </div>
        </section>
      </div>
    </div>
  )
}

function Metric({
  label,
  value,
  tone,
}: {
  label: string
  value: number
  tone: 'success' | 'warning' | 'danger'
}) {
  return (
    <div className={`replay-metric ${tone}`}>
      <span>{label}</span>
      <strong>{label === 'Latency p95' ? `${Math.round(value)}ms` : formatPercent(value, 0)}</strong>
    </div>
  )
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div className="replay-meta-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function RecoveryStep({ label, status, detail }: { label: string; status: 'pending' | 'active' | 'complete'; detail: string }) {
  return (
    <div className={`replay-recovery-step ${status}`}>
      <div className="replay-recovery-index" />
      <div>
        <strong>{label}</strong>
        <span>{detail}</span>
      </div>
    </div>
  )
}
