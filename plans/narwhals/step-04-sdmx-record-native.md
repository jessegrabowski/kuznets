# Step 04 (PR 4) — SDMX family goes record-native

## What and why

OECD and Eurostat are the purest case for the tidy architecture: their wire formats (SDMX-JSON,
JSON-stat) are *already* long-form observation records, and today's code immediately pivots them
wide (`io/util.py::_pivot_observations`). After this PR:

- The record extraction (`_observations_to_records`) becomes the shared tidy source.
- Non-pandas users get frames built natively via `make_frame(records, output_type, schema=...)` —
  no pandas object is ever created on their path ([R]-path; benchmarked fastest in step 00).
- pandas users get the exact same pivot as today: `_pivot_observations` becomes the pandas
  presenter, consuming the same records it consumes today. Byte parity by construction.

Tidy schema for both sources: one column per SDMX dimension (display labels for non-time
dimensions, raw codes for the time dimension — the same labeling the pivot produces today) plus
`value` (float64, matching today's `dtype="float64"` Series). Explicit narwhals `schema=`
(dims `nw.String`, `value` `nw.Float64`) prevents per-backend inference drift.

Date filtering: the tidy path casts the time column via `to_datetime_col` (keep-strings fallback
for non-calendar codes like `"2013-S1"`) and applies `filter_date_range`, which skips
string-typed columns — mirroring today's `isinstance(df.index, DatetimeIndex)` guard before
`truncate`. The pandas presenter keeps today's guarded truncate verbatim.

`read_jsdmx` / `read_jstat` are public helpers; they gain an `output_type="pandas"` parameter.

## Tasks

| # | Commit | Contents | Testing plan |
|---|---|---|---|
| 1 | Split `io/util.py`: records source vs pivot presenter | `_observations_to_records(records, dim_names, label_maps, time_pos) -> list[dict]`; `_pivot_observations` reimplemented as a consumer of those records (pandas-only presenter), byte-identical output | Unit tests on both functions against the recorded OECD/Eurostat fixture JSON in `tests/data/`; untouched oecd/eurostat offline tests = parity oracle |
| 2 | `read_jsdmx` + OECD tidy path | `read_jsdmx(path_or_buf, output_type="pandas")`; `oecd.py`: core returns the record bundle; pandas presenter = verbatim pivot + guarded truncate; tidy presenter = `make_frame` + `to_datetime_col` + `filter_date_range` | Untouched `tests/test_oecd.py` = parity oracle; new backend tests: dimension columns present with display labels, `value` float64, time column datetime dtype, date filter row counts vs pandas result |
| 3 | `read_jstat` + Eurostat tidy path | Same pattern via the shared helpers | Untouched eurostat offline tests = parity oracle; new backend tests incl. a semester-coded fixture (time column stays string; filter skipped) |
| 4 | `io/sdmx.py::read_sdmx` output_type | Same split for the standalone SDMX-XML helper (no reader depends on it; lowest priority — may be dropped from the PR if it balloons) | Unit tests with the existing SDMX fixture; pandas parity + one backend schema test |

## PR review notes

- Commit 1 is the risky one for parity: the pivot must consume records instead of its old inputs
  yet produce identical frames. The untouched offline tests catch any drift; reviewer should
  compare the new `_pivot_observations` body against the old line-by-line.
- Reviewer focus: the tidy schema (label vs code policy per dimension) is a public contract —
  confirm it matches what the pivot's column headers show today.
