# Step 03 (PR 3) — tidy paths for the simple readers

## What and why

Give the simple CSV-parsed ([P]-path) readers real tidy output and lock their non-pandas schemas
with tests. These readers need little or no presenter work — their parse result is already a
single date-indexed frame, so the pandas presenter stays the identity (or a one-line `set_index`)
and the default `_present_tidy` (detach index → convert) does the rest. The work in this PR is
mostly *tests*: pinning each reader's tidy schema (column names and dtypes) per backend so later
refactors can't silently drift.

Schema policy reminders:

- Detached indexes keep their names (`DATE` for FRED, `TRADEDATE` for MOEX); an *unnamed*
  datetime index becomes `"Date"`.
- Tidy output has no indexes, no MultiIndex, plain string column names.
- Readers whose core does date filtering (`fred`'s per-series truncate, naver's boolean mask)
  keep it in core — it is pre-decoration and applies to every backend identically.

## Tasks

| # | Commit | Contents | Testing plan |
|---|---|---|---|
| 1 | Generic CSV base readers: bankofcanada, stooq (single-symbol), tsp, quandl (single-symbol) | No reader-code changes expected beyond what step 02 landed (identity presenters + default tidy); adjust only if a reader's parse result carries surprises (e.g. tsp column drops stay in core) | New offline tests parametrized over `["polars", "pyarrow"]` (skipif-not-installed): fixture-driven read with `output_type=`, assert exact column names, date column dtype is datetime, row count equals the pandas result; pandas tests untouched |
| 2 | fred | Core keeps today's `concat(series, axis=1, join="outer", sort=True)` + per-series truncate, then `detach_index`; pandas presenter = `attach_index` (`set_index("DATE")`) | Untouched `tests/test_fred.py` offline class = parity oracle (asserts `index.name == "DATE"`); new backend tests: `DATE` column present + datetime dtype, one column per requested series, row counts match pandas |
| 3 | wb (World Bank) | Core produces `country, year` + indicator columns (`to_numeric` stays in core); pandas presenter = `set_index(["country", "year"])` | Untouched `tests/test_wb.py` = parity oracle; new backend tests: `country`/`year` are plain columns, indicator dtype float, row count matches |
| 4 | naver + moex | naver: boolean-mask date filter stays in core; moex: `TRADEDATE` detach + `read_all_boards` tidy path | Untouched offline tests = parity oracle; new backend tests for both incl. `read_all_boards(output_type="polars")` |
| 5 | nasdaq_trader | `data.py` nasdaq branch: `from_pandas(detach_index(df)[0], output_type)`; Categorical columns must survive conversion (narwhals Categorical → polars Categorical / arrow dictionary) | Untouched nasdaq offline test = parity oracle; new backend test asserting `Symbol` is a plain column and the two categorical fields carry categorical/dictionary dtype |

## PR review notes

- Every commit's diff is dominated by tests; reader diffs should be a handful of lines each.
- Reviewer focus: the asserted tidy schemas *are* the public contract for these readers — check
  the column names read naturally per source (they come from the upstream CSV headers, not
  invented).
