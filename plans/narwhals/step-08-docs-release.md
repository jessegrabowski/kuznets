# Step 08 (PR 8) — docs, whatsnew, README

## What and why

Document the two features and their policies as the current contract (not as a changelog of the
refactor): what `output_type` accepts, what each backend's output looks like, and how concurrent
fetching behaves. Process history (why tidy-core, the benchmark, PR sequencing) lives in
`plans/narwhals/` and the git history — not in user-facing docs.

## Tasks

| # | Commit | Contents | Testing plan |
|---|---|---|---|
| 1 | remote_data.rst + cache.rst | New "Output backends" section: `output_type` values, install extras (`pip install pandas-datareader[polars]` etc.), the tidy data model per backend (indexes are pandas-only presentation; long panel schema `Date, Symbol, …`; famafrench dict with `Date` datetime columns; actions long frame; tiingo metadata row-per-symbol), fail-fast errors. New "Concurrent downloads" section: `max_workers`, politeness guidance for rate-limited hosts, shared-session semantics. `cache.rst`: requests-cache sessions are not thread-safe → use `max_workers=1` | `sphinx-build -W` (docs extra) renders clean; doctest-style snippets execute against fixtures where practical |
| 2 | whatsnew | New version file + `whatsnew.rst` link: `output_type` feature, narwhals>=2.0 required dependency, backend extras, concurrent fetching + `max_workers`, **breaking:** AlphaVantage dates now real datetimes (pandas included), `chunksize` deprecated/unused, note that third-party `_BaseReader` subclasses overriding `read()` bypass conversion and should override `_read_core()` | Docs build clean; entries cross-reference the sections from commit 1 |
| 3 | README + pyproject polish | README: requirements list (+narwhals), install extras, a 3-line `output_type="polars"` example alongside the existing pandas example; verify classifiers/extras consistency in `pyproject.toml` | README renders on GitHub preview; `pip install -e ".[backends]"` resolves; full offline suite green one final time |

## Release checklist (after PR 8 merges)

```bash
pip install -e ".[dev,polars,pyarrow]"
ruff check . && ruff format --check .
pytest                          # offline
pytest -m network               # one live drift check
```

End-to-end sanity, against a pre-branch checkout:

- `get_data_fred('GDP')` → `assert_frame_equal`-identical (pandas default unchanged).
- `DataReader("AAPL", "stooq", output_type="polars")` → long polars frame `Date, Symbol, …`.
- `DataReader(["AAPL", "MSFT"], "stooq")` → today's wide MultiIndex panel, faster wall-clock with
  `max_workers>1`.
