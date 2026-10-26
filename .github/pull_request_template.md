## What and why

<!-- What changes, and the reason. One change per pull request. -->

## Checked

- [ ] `ruff check` and `ruff format --check` pass
- [ ] `python -m pytest -q` passes; new behaviour has a test, and I broke the rule on purpose to see the test fail
- [ ] Dashboard: `npm run lint`, `npm test`, `npm run build` pass (if `dashboard/` changed)
- [ ] The two contracts are unchanged, or only extended (stage record, output line)
- [ ] Results changed? I regenerated the snapshots (`python -m pipeline.refresh_snapshots`) and `docs/FINAL_NUMBERS.md`; none was edited by hand
- [ ] No personal data, secrets or local paths are committed

## Not checked, and known limits

<!-- Be plain about what this does not cover or could not be verified. -->
