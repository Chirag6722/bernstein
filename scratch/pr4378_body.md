Fixes #4378

### Problem
When an adapter encounters an HTTP 429 error, it was uniformly treated as a transient rate limit and retried with exponential backoff. However, certain 429 errors represent standing caps (e.g. monthly quota exceeded, credit depleted, organization tier cap) that retrying cannot clear, causing unnecessary backoff loops and delayed run failure.

### Changes
1. Added `StandingCapError`, `STANDING_CAP_PATTERNS`, and `classify_standing_cap(output)` in `src/bernstein/adapters/base.py`.
2. Updated `_probe_fast_exit` to detect standing cap signatures and abort fast instead of backing off.
3. Updated `SpawnAnalyzer.analyze` in `src/bernstein/core/agents/spawn_analyzer.py` to classify standing cap errors as non-transient aborts.
4. Added `tests/unit/adapters/test_standing_cap_classification.py` (8 unit tests).
