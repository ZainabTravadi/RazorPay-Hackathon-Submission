import { Fragment, useEffect, useMemo, useState } from 'react'

const API_URL = `${import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'}/api`

type RcaNode = {
  id: string
  label: string
  type: string
}

type RcaEdge = {
  source: string
  target: string
  relationship: string
}

type RcaGraph = {
  incident_id: string
  nodes: RcaNode[]
  edges: RcaEdge[]
}

const stageOrder = [
  { key: 'incident', label: 'Incident' },
  { key: 'evidence', label: 'Evidence / Signals' },
  { key: 'hypothesis', label: 'Hypotheses' },
  { key: 'root_cause', label: 'Root Cause' },
  { key: 'recovery_action', label: 'Recovery Action' },
] as const

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

export default function ExplainableRCA({
  incidentId,
  enabled,
}: {
  incidentId: string
  enabled: boolean
}) {
  const [graph, setGraph] = useState<RcaGraph | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!incidentId || !enabled) {
      setGraph(null)
      setError(null)
      setLoading(false)
      return
    }

    let mounted = true
    setLoading(true)
    setError(null)
    setGraph(null)

    ;(async () => {
      try {
        const payload = await api(`/incidents/${incidentId}/rca-graph`)
        if (mounted) setGraph(payload)
      } catch (reason: any) {
        if (mounted) {
          setGraph(null)
          setError(reason.message || 'Unable to load the RCA reasoning chain for this incident.')
        }
      } finally {
        if (mounted) setLoading(false)
      }
    })()

    return () => {
      mounted = false
    }
  }, [enabled, incidentId])

  const stageGroups = useMemo(() => {
    const nodes = graph?.nodes ?? []
    const edges = graph?.edges ?? []

    return stageOrder.map((stage, index) => {
      const stageNodes = nodes.filter((node) => node.type === stage.key)
      const nextStage = stageOrder[index + 1]
      const nextStageNodes = nextStage ? nodes.filter((node) => node.type === nextStage.key) : []
      const relationships =
        nextStage && stageNodes.length > 0 && nextStageNodes.length > 0
          ? Array.from(
              new Set(
                edges
                  .filter((edge) => stageNodes.some((node) => node.id === edge.source) && nextStageNodes.some((node) => node.id === edge.target))
                  .map((edge) => edge.relationship),
              ),
            )
          : []

      return {
        ...stage,
        nodes: stageNodes,
        relationships,
      }
    })
  }, [graph])

  if (loading) {
    return (
      <section className="section-card explainable-rca-card">
        <div className="section-heading">
          <p className="section-kicker">Explainable RCA</p>
          <h3>Why did this happen?</h3>
        </div>
        <div className="explainable-rca-loading" aria-hidden="true">
          <div className="skeleton explainable-rca-skeleton" />
          <div className="skeleton explainable-rca-skeleton" />
          <div className="skeleton explainable-rca-skeleton" />
          <div className="skeleton explainable-rca-skeleton" />
          <div className="skeleton explainable-rca-skeleton" />
        </div>
      </section>
    )
  }

  if (error) {
    return (
      <section className="section-card explainable-rca-card">
        <div className="section-heading">
          <p className="section-kicker">Explainable RCA</p>
          <h3>Why did this happen?</h3>
        </div>
        <div className="rca-empty explainable-rca-empty">
          <div>
            <h3>Unable to load the explainable RCA.</h3>
            <p>{error}</p>
          </div>
        </div>
      </section>
    )
  }

  if (!graph || graph.nodes.length === 0 || graph.edges.length === 0) {
    return (
      <section className="section-card explainable-rca-card">
        <div className="section-heading">
          <p className="section-kicker">Explainable RCA</p>
          <h3>Why did this happen?</h3>
        </div>
        <div className="rca-empty explainable-rca-empty">
          <div>
            <h3>No explainable RCA is available for this incident yet.</h3>
            <p>The backend has not produced a reasoning chain for this incident.</p>
          </div>
        </div>
      </section>
    )
  }

  return (
    <section className="section-card explainable-rca-card">
      <div className="section-heading">
        <p className="section-kicker">Explainable RCA</p>
        <h3>Why did this happen?</h3>
      </div>

      <div className="explainable-rca-flow">
        {stageGroups.map((stage, index) => (
          <Fragment key={stage.key}>
            <StageCard
              label={stage.label}
              nodes={stage.nodes}
              highlighted={stage.key === 'root_cause'}
              tone={stage.key}
            />
            {index < stageGroups.length - 1 && <Connector relationships={stage.relationships} />}
          </Fragment>
        ))}
      </div>
    </section>
  )
}

function StageCard({
  label,
  nodes,
  highlighted,
  tone,
}: {
  label: string
  nodes: RcaNode[]
  highlighted?: boolean
  tone: string
}) {
  return (
    <div className={`explainable-rca-stage ${tone} ${highlighted ? 'highlighted' : ''}`}>
      <div className="explainable-rca-stage-head">
        <span>{label}</span>
        <strong>{nodes.length}</strong>
      </div>
      <div className="explainable-rca-node-list">
        {nodes.map((node) => (
          <article key={node.id} className={`explainable-rca-node ${node.type}`}>
            <div className="explainable-rca-node-dot" />
            <div className="explainable-rca-node-copy">
              <strong>{node.type === 'incident' ? 'Incident' : node.label}</strong>
              <span>{node.type === 'incident' ? node.label : formatLabel(node.type)}</span>
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}

function Connector({ relationships }: { relationships: string[] }) {
  return (
    <div className="explainable-rca-connector" aria-hidden="true">
      <div className="explainable-rca-connector-line" />
      <div className="explainable-rca-connector-arrow">↓</div>
      <div className="explainable-rca-connector-label">{relationships.length > 0 ? relationships.map(formatLabel).join(' · ') : 'Relates to'}</div>
    </div>
  )
}
