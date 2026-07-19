# Release procedure

Releases are tag-driven; the version comes from the git tag via hatch-vcs and publishing uses
PyPI trusted publishing (no tokens).

1. Update `docs/source/whatsnew/` for the release and merge to `main`.
2. Tag and push:

        git tag -a vX.Y.Z -m "Version X.Y.Z"
        git push origin vX.Y.Z

3. The `Release` workflow builds the sdist and wheel and publishes to PyPI via the `pypi`
   environment's trusted publisher.

One-time setup (already done for future releases): a pending trusted publisher on PyPI for the
`kuznets` project pointing at `jessegrabowski/kuznets`, workflow `release.yml`, environment
`pypi`.
