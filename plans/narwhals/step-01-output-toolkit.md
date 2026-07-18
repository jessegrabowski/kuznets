# Step 01 (PR 1) — `_output.py` toolkit + narwhals dependency

## What and why

Land the entire backend-conversion/construction toolkit as a fully unit-tested module *before* any
reader touches it. Nothing in the package calls it yet by the end of this PR, so the PR is
reviewable in isolation and the offline reader suite is untouched. All narwhals usage in the
project funnels through this one module, so a future narwhals upgrade failure localizes here.

Module: `pandas_datareader/_output.py`, importing `narwhals.stable.v2 as nw` (never-break
guarantee; pin `narwhals>=2.0`).

Public surface (consumed by later steps):

- `validate_output_type(name) -> str` — canonicalize (case-insensitive, `"arrow"` → `"pyarrow"`),
  `ValueError` on unknown values, and fail-fast `ImportError` with a pip-extra hint when the
  backend module is missing (`importlib.util.find_spec`). Called from `_BaseReader.__init__` so
  bad values fail before any HTTP.
- `make_frame(records, output_type, schema=None)` — record-native construction: pure-Python
  records→columns pivot, then `nw.from_dict(columns, backend=output_type).to_native()`
  (column-oriented; see [step 00](step-00-benchmark.md)). Explicit `schema=` to prevent
  per-backend dtype-inference drift.
- `from_pandas(df, output_type)` — tidy pandas → backend. Guards: raise on MultiIndex rows/columns
  (tidy-contract violation, a bug in the caller); str-cast non-string column labels; cast all-null
  object columns to float64 (the yahoo `_empty_history` payload). Then
  `nw.from_native(df, eager_only=True)` → `.to_polars()` / `.to_arrow()` /
  `.lazy(backend="dask").to_native()`.
- `detach_index(df) -> (tidy_df, index_cols)` / `attach_index(df, index_cols)` — reset_index with
  an unnamed datetime-like index falling back to the name `"Date"`; presenters round-trip through
  these, and the round-trip must preserve index name and dtype exactly.
- `filter_date_range(native_frame, column, start, end)` — narwhals
  `nw.col(column).is_between(start, end, closed="both")` (matches `truncate`/label-slice
  inclusivity); pandas `Timestamp`s converted via `.to_pydatetime()`; skips columns that are not
  datetime-typed (OECD/Eurostat semester codes like `"2013-S1"` keep today's
  isinstance-DatetimeIndex-guard semantics).
- `to_datetime_col(native_frame, column)` — narwhals str→datetime cast with a keep-strings
  fallback on failure.
- `concat_frames(frames)` — `nw.concat` wrapper; the backend is inferred from the frames.

There are deliberately **no un-decorators** (no melt-the-panel, no de-period-ize): under the tidy
architecture nothing decorated ever needs converting.

## Tasks

| # | Commit | Contents | Testing plan |
|---|---|---|---|
| 1 | Add narwhals dependency and backend extras | `pyproject.toml`: `dependencies` += `narwhals>=2.0`; `[project.optional-dependencies]`: `polars = ["polars", "pyarrow"]`, `pyarrow = ["pyarrow"]`, `dask = ["dask[dataframe]"]`, `backends = [union]`; `dev` += `polars`, `pyarrow` | `pip install -e ".[dev]"` succeeds; `python -c "import narwhals.stable.v2"`; full `pytest` green (no code change) |
| 2 | `validate_output_type` + backend registry | `_output.py` with the registry (canonical names, module names, extra names) and `validate_output_type`; new `tests/test_output.py` | Unit tests: canonicalization incl. `"arrow"`→`"pyarrow"` and case-insensitivity; `ValueError` message lists valid values; `ImportError` path via monkeypatched `importlib.util.find_spec` (no uninstall gymnastics); `output_type="pandas"` never imports narwhals backends |
| 3 | Conversion path: `from_pandas`, `detach_index`, `attach_index` | Same module; guards for MultiIndex (raise), non-str column labels (cast), all-null object columns (cast float64) | Unit tests: detach/attach round-trip preserves index name+dtype (named `DATE`, unnamed DatetimeIndex → `"Date"`, MultiIndex rows); polars/pyarrow conversions (`pytest.importorskip`); dask single test (skipif-not-installed); the empty/all-NaN-object frame; MultiIndex input raises |
| 4 | Construction and wrangling: `make_frame`, `filter_date_range`, `to_datetime_col`, `concat_frames` | Same module; records→columns pivot + `nw.from_dict` + `schema=`; is_between filter; str→datetime cast with fallback | Unit tests: per-backend construction with and without explicit schema (dtype assertions vs inference); filter inclusivity at both endpoints; non-datetime column skips filtering (semester strings); to_datetime_col fallback keeps strings; concat across ≥3 frames per backend |

## PR review notes

- The PR adds one module + one test file + pyproject changes; no reader behavior can change.
- Reviewer focus: the normalization policies in `from_pandas`/`detach_index` are the public
  contract for every later step — bikeshed them here, not in step 03+.
