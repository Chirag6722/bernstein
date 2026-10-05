## Verify workflow_run commit before checkout in coverage ratchet workflow

Updated `.github/workflows/coverage-ratchet.yml` to checkout the trusted `main` ref and perform runtime 40-hex SHA format and `origin/main` ancestry verification before checking out the measured commit. This removes the untrusted `github.event.workflow_run.head_sha` interpolation from `actions/checkout`, satisfying OpenSSF Scorecard's `Dangerous-Workflow` static analyzer while preserving runtime verification.

(#6073)
