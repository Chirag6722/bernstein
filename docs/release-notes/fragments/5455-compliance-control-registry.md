## Central compliance control registry and suite control declaration enforcement

Bernstein now features a central compliance control registry (`bernstein.compliance.controls`) containing standard controls mapped across EU AI Act, OWASP ASI, OWASP Skills, NIST AI RMF, ISO/IEC 42001, and FINOS AIGF.

Every benchmark task suite (`BenchSuite`) must declare the control IDs it measures. Unmapped suites or suites declaring unregistered control IDs fail build validation (`validate_controls`).

Operators and auditors can inspect controls and benchmark coverage using `bernstein compliance controls [--coverage] [--framework <name>] [--format text|json|markdown]`.

The declaration is enforced where every `bench` subcommand resolves its
suite, so a suite that maps to no control cannot run, score, or publish a
bundle — built-in and `.json` suites alike. Both built-in suites now declare
controls: `golden-v1` (`CTL-ROB-01`, `CTL-EVAL-01`, `CTL-EVAL-02`,
`CTL-QUAL-02`) and `tool-surface-v1` (`CTL-SEC-02`, `CTL-SEC-05`,
`CTL-EVAL-01`).

A declared control set is part of suite identity, so **`golden-v1`'s
`suite_hash` changes** in this release. A bundle produced against the
previous `golden-v1` will report a suite-hash mismatch under `bench verify`
and needs re-running. A suite that declares no controls hashes exactly as
before, so nothing else published moves.

The control table in `docs/compliance/regulator-mapped-packs.md` is now
generated from the registry and pinned by a test, so it cannot drift from
what the code declares.
