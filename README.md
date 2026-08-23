# FluxPay

FluxPay is an intelligent payment incident-response, investigation, and revenue-recovery platform. It helps an operations team move from a detected payment degradation to an evidence-backed root-cause analysis, an impact estimate, and a controlled recovery simulation.

The project uses synthetic payment data and a simulated recovery environment. It does not connect to or execute transactions against real Razorpay infrastructure.

## Project Overview

FluxPay addresses a common payment-operations problem: an incident can be detected quickly, but understanding its cause, scope, and safest response requires evidence from several systems. FluxPay assembles that evidence into a bounded investigation and keeps recovery actions behind an explicit operator approval step.

The main lifecycle is:

```text
Seed
  -> Detect or inject incident
  -> Incident
  -> Investigation
  -> RCA
  -> Evidence / hypotheses / similar incidents
  -> Impact analysis
  -> Recovery recommendation / policy
  -> Recovery preparation
  -> Approval
  -> Execution
  -> Completed simulation
```

## Architecture

```mermaid
flowchart TD
    S[Synthetic seed data] --> D[Anomaly detector]
    D --> I[Incident management]
    X[Simulator injection] --> D
    I --> B[FastAPI backend]
    B --> R[Investigator and RCA pipeline]
    R --> M[MCP read-only tools]
    M --> DB[(SQLite or configured database)]
    R --> E[Evidence, hypotheses, history, and trace]
    B --> A[Impact, metrics, fingerprint, clusters, and timeline]
    B --> P[Recovery recommendation and policy]
    P --> Q[Prepare -> Approve -> Execute]
    Q --> C[Completed sandbox simulation]
    B --> F[React/Vite dashboard]
    V[Evaluation benchmark] --> R
```

The major components are:

- **FastAPI backend:** exposes dashboard, incident, investigation, simulator, metrics, payment, provider, historical-incident, and recovery APIs.
- **Database layer:** SQLAlchemy models and sessions use SQLite by default when `DATABASE_URL` is absent, or the configured database URL when supplied.
- **Synthetic data:** deterministic payment events, merchants, providers, and 30 historical incidents are created by the seed utilities.
- **Detection and incident management:** anomaly detection evaluates generated or injected payment data and persists qualifying `INC-*` incidents.
- **Investigation/RCA pipeline:** the investigator calls bounded deterministic read-only tools, compares evidence and hypotheses, retrieves similar historical incidents, and persists an `INV-*` trace and result.
- **Recovery state machine:** impact and policy services recommend a constrained strategy and persist preparation, approval, rejection, and simulated execution state.
- **React/Vite dashboard:** provides the demo workflow and displays investigation intelligence and recovery state transitions.
- **MCP server:** registers ten read-only investigation tools; the tools do not refund, retry, route, mutate configuration, or call payment providers.
- **Evaluation:** the deterministic benchmark measures classification and recovery recommendation accuracy across 20 scenarios.

## Data Model and Resource Lifecycle

FluxPay keeps incident and investigation resources separate:

| Resource | Meaning | Created by |
|---|---|---|
| `INC-*` | Persisted payment incident | `POST /api/simulator/inject/{scenario}` when detection qualifies the scenario |
| `INV-*` | Persisted investigation and RCA trace | `POST /api/investigate/{incident_id}` |
| `REC-*` | Persisted recovery execution record | `POST /api/incidents/{incident_id}/recovery` |

The investigation endpoints require an `INV-*` identifier. Therefore, `GET /api/investigations/{INC-*}` returning `404` is expected: an incident is not an investigation.

## API and Features

All endpoints use the `/api` prefix.

| Area | Endpoints |
|---|---|
| Health | `GET /health` |
| Dashboard | `GET /dashboard/summary` |
| Simulator | `POST /simulator/reset`, `POST /simulator/inject/{incident_type}` |
| Incidents | `GET /incidents`, `GET /incidents/{incident_id}` |
| Incident intelligence | `GET /incidents/{incident_id}/impact`, `/fingerprint`, `/clusters`, `/timeline` |
| Investigations | `POST /investigate/{incident_id}`, `GET /investigations`, `GET /investigations/{investigation_id}` |
| Investigation detail | `GET /investigations/{investigation_id}/trace`, `/evidence`, `/hypotheses`, `/similar-incidents` |
| Recovery planning | `GET /incidents/{incident_id}/recovery-recommendation`, `GET /incidents/{incident_id}/recovery-policy` |
| Recovery lifecycle | `POST /incidents/{incident_id}/recovery`, `POST /recoveries/{recovery_id}/approve`, `/reject`, `/execute` |
| Payments and metrics | `GET /payments`, `GET /metrics/success-rate`, `GET /metrics/failure-rate`, `GET /metrics/latency` |
| Providers and history | `GET /providers`, `GET /providers/{provider_id}/health`, `GET /historical-incidents` |
| Knowledge | `GET /knowledge/search?q=...` |

The investigation result includes the selected root cause, confidence, evidence, alternative hypotheses, rejected hypotheses, impact, historical matches, recommended next step, duration, and tool-call count. Investigation traces retain tool inputs, structured outputs, purposes, summaries, and timestamps; hidden chain-of-thought is not persisted.

## Recovery State Machine

Recovery is a controlled, simulated workflow. Approval does not execute the recovery.

```text
pending / not_started
        |
      approve
        v
approved / not_started
        |
      execute
        v
completed
```

Rejection moves a prepared recovery to `rejected`. The service enforces these guards:

- Execution before approval is rejected.
- A rejected recovery cannot be approved.
- A completed recovery cannot be executed again.
- A duplicate active recovery preparation for the same incident is rejected.
- Simulation does not mutate payment rows and is marked `simulation=true`.

## Simulator Scenarios

The simulator accepts all ten scenario names below. A `400` result means detection did not produce a qualifying incident, so no `INC-*` resource is created.

| Scenario | Verified result | Interpretation |
|---|---:|---|
| `provider_outage` | 200 | Supported |
| `payment_method_degradation` | 200 | Supported |
| `mixed_incident` | 200 | Supported |
| `regional_degradation` | 200 | Supported |
| `customer_level_failure` | 200 | Supported |
| `provider_latency_spike` | 400 | Detector/data limitation |
| `merchant_misconfiguration` | 400 | Detector/data limitation |
| `webhook_failure` | 400 | Detector/data limitation |
| `late_authorization` | 400 | Detector/data limitation |
| `normal_traffic_spike` | 400 | Expected negative control |

The four detector/data-limited scenarios are not broken API endpoints. Their scenario types are accepted, but the current detection and data conditions do not produce a qualifying detectable incident. Detection thresholds and rules were not weakened to force them to succeed. `normal_traffic_spike` is intentionally retained as a negative control.

## Frontend Demo Flow

1. Click **Reset simulator**.
2. Keep **provider_outage** selected and click **Inject incident**.
3. Select the generated `INC-*` incident.
4. Click **Investigate incident**.
5. View the RCA and confidence.
6. View evidence and reasoning trace summary.
7. View hypotheses and similar incidents.
8. View impact and revenue at risk.
9. View fingerprint, failure clusters, and timeline.
10. Review the recovery recommendation and policy.
11. Click **Prepare recovery** and confirm `pending / not_started`.
12. Click **Approve recovery** and confirm `approved / not_started`.
13. Click **Execute simulation**.
14. View the completed recovery result.

## Running Locally

The default local database is SQLite (`fluxpay.db`) when `DATABASE_URL` is not set. PostgreSQL can be used through the repository's Docker Compose configuration.

Initialize tables:

```bash
python -m database.init_db
```

Seed the clean demo state with 5,000 baseline payments and 30 historical incidents:

```bash
python -m data.seed --reset --events 5000 --seed 42
```

Start the API:

```bash
uvicorn apps.api.main:app --reload --host 0.0.0.0 --port 8000
```

If the `uvicorn` executable is not on PATH:

```bash
python -m uvicorn apps.api.main:app --reload --host 0.0.0.0 --port 8000
```

Start the dashboard in another terminal:

```bash
cd apps/dashboard
npm install
npm run dev
```

Open `http://localhost:5173`. The dashboard uses `VITE_API_BASE_URL` when provided and otherwise defaults to `http://localhost:8000`.

## Verification and Audit Results

These are the final verified audit results for the locked implementation:

- Pytest: **18 passed**.
- Benchmark: **20/20 root-cause accuracy**.
- Benchmark: **20/20 recovery recommendation accuracy**.
- MCP: **10 read-only tools registered**.
- Frontend production build: **passed**.
- Browser smoke test: **passed**.
- Browser console errors: **0**.
- Failed browser requests: **0**.
- Final clean database: **5,000 payments, 30 historical incidents, 0 active incidents, 0 investigations, 0 recoveries**.

The measured benchmark can be run with:

```bash
python -m evaluation.runner
```

The machine-readable report is written to `evaluation/report.json`. MCP registration can be inspected with:

```bash
python -m mcp_server
```

## Fixes Found During Audit

The following defects were identified and fixed before the final documentation pass:

| Defect | Symptom | Root cause and fix | Verification |
|---|---|---|---|
| Destructive simulator reset | Reset removed the seeded baseline payments | Reset was narrowed to operational incident-scoped payment rows and operational records | Clean reset preserved 5,000 baseline payments |
| Stale metrics | Dashboard metrics could reflect regenerated data instead of persisted records | Metrics were changed to calculate from persisted payment data | Persisted-data and dashboard checks passed |
| Incorrect synthetic duration | Incident duration depended on the real wall clock | Synthetic duration calculation was corrected to use incident timestamps | Regression tests passed |
| Repeated recovery execution | A completed recovery could be executed again | Execution now rejects any recovery not in `not_started` state | Recovery state-machine tests passed |

## Known Limitations

- `provider_latency_spike`, `merchant_misconfiguration`, `webhook_failure`, and `late_authorization` do not produce detectable incidents under the current detector/data conditions.
- `normal_traffic_spike` is an intentional negative control and does not create an incident.
- Frontend/API coverage is focused on the primary demo workflow and is not necessarily identical for every backend endpoint.
- Vite reports an existing chunk-size warning for the production bundle; the build still passes.
- No lint or typecheck script is configured in the dashboard package.
- The system is synthetic and local; it is not a deployed production payment service.

## Design and Engineering Decisions

- Incidents and investigations use separate identifiers and resources so detection records cannot be confused with investigative traces.
- Recovery preparation, approval, and execution are separate persisted transitions to keep remediation controlled and auditable.
- Metrics read persisted payment records so dashboard values describe the same data used by incident and impact analysis.
- Injected payments use incident-scoped IDs, preserving baseline identity and preventing collisions.
- Simulator reset preserves seeded baseline payments while clearing operational state.
- Negative controls are retained instead of forcing every scenario to become an incident.
- The benchmark measures deterministic investigation and recovery behavior rather than hardcoding a score.
- MCP tools are read-only and bounded, keeping investigation separate from payment mutation.

## Submission-Ready Summary

FluxPay demonstrates an end-to-end payment incident workflow: it seeds deterministic synthetic traffic, detects or injects incidents, investigates them through read-only evidence tools, produces RCA with hypotheses and historical comparisons, quantifies impact, recommends constrained recovery, and requires explicit approval before a sandbox execution. Its FastAPI, database, detection, investigation, recovery, MCP, evaluation, and React/Vite layers are connected through persisted resource lifecycles. The final audit verified 18 passing tests, 20/20 RCA accuracy, 20/20 recovery recommendation accuracy, 10 registered MCP tools, a passing frontend build, and a browser flow with zero console errors and failed requests. Four detector/data-limited scenarios and the intentional negative control remain documented limitations; the primary provider-outage demonstration is verified and submission-ready.