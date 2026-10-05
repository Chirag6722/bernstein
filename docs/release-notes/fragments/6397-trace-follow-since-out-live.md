## `trace follow` adds resume, file export, and live following

`bernstein trace follow <entity-id>` now supports `--since <entry-id>`, `--out <path>`, and `--live` (`-f`):

- `--since <entry-id>` resumes follow output strictly after the specified journal entry id, matching both trace and ledger identifiers (`trace:<id>`, `<id>`, `ledger:<run>:<seq>`, `<run>:<seq>`, and entry hashes).
- `--out <path>` writes the per-entity trace output to a file as JSON or formatted text table, creating parent directories if absent.
- `--live` streams new trace and ledger entries in real time until the referenced run reaches a terminal state (`run.closed` / terminal task transitions) or is interrupted (#5114, #6397).
