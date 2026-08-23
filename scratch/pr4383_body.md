Fixes #4383

### Problem
When the PyPI index propagation takes longer than expected, the install smoke job fails with a generic timeout error that does not clearly distinguish between upload failure and PyPI CDN index delay.

### Changes
1. Updated timeout message in `scripts/wait_for_pypi_visibility.py` to explicitly name PyPI index propagation.
2. Added `copr-skipped-notice` job to `.github/workflows/publish.yml` to clearly alert operators when downstream builds are skipped.
3. Updated unit tests in `tests/unit/test_wait_for_pypi_visibility.py` (10 passing tests).
