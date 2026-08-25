# Submission Checklist

- [ ] Public repository ready
- [x] README complete and aligned with implementation
- [x] Architecture documented
- [x] Setup instructions documented and locally verified
- [x] Backend tests passing
- [x] Frontend production build passing
- [x] No secrets or API keys committed
- [x] No fake production, payment-provider, or money-movement claims
- [x] Demo flow documented
- [x] Five-minute pitch structure documented in README demo flow
- [ ] Screenshots/assets identified or added if required by the Buildathon submission form
- [x] Known limitations documented

## Repository Hygiene

- Local `fluxpay.db`, Python caches, pytest caches, `node_modules`, dashboard builds, and temporary reports are ignored by `.gitignore`.
- Generated verification scripts, benchmark output, and historical reports were removed from the submission; reproducible coverage remains in the evaluation runner and pytest suites.
- Browser E2E pass completed against the local stack: inject -> investigate -> RCA -> prepare -> approve -> execute -> measured recovery -> reload -> replay. A forced primary/fallback failure reached terminal `escalated` with two attempts and nine persisted events.

## Verified Commands

```text
.venv\Scripts\python.exe -m pytest tests/ -q
cd apps/dashboard
npm.cmd run build
cd ../..
git diff --check
```

Latest results: 56 backend tests passed; dashboard production build passed. Vite emitted only its existing bundle-size warning, and `git diff --check` is clean.
