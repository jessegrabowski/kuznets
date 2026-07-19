# Release procedure

Versions come from git tags via hatch-vcs; publishing uses PyPI trusted publishing (no tokens).
The build-and-inspect job also runs on every PR and push to main, so packaging problems surface
before release time.

1. Update `docs/source/whatsnew/` for the release and merge to `main`.
2. Tag: `git tag -a vX.Y.Z -m "Version X.Y.Z"` and `git push origin vX.Y.Z`.
3. Create a GitHub Release from the tag. Publishing fires on release publication, gated by the
   `release` environment's required review.

One-time setup: a PyPI trusted publisher for `kuznets` pointing at `jessegrabowski/kuznets`,
workflow `release.yml`, environment `release`; the `release` environment in repo settings with
required reviewers.
