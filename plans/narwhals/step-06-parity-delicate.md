# Step 06 (PR 6) — parity-delicate readers: famafrench, econdb, tiingo

## What and why

These three readers carry the subtlest pandas semantics in the library; they land last among the
readers, each in its own commit, with parity risk isolated.

**famafrench** — the payload is `_Parsed(tables: dict[int, DataFrame], freqs: dict[int, "M"|"Y"|None],
descr: str, titles: list[str])`. The per-table frequency (detected from the integer date-code
width during parsing) travels in the payload, and only the pandas presenter consumes it to
re-impose `to_period(freq)`. Two boundary subtleties:

- Tidy `Date` columns hold **period-start timestamps**; monthly/annual timestamp → period
  round-trips losslessly, so the pandas presenter reconstructs today's PeriodIndex exactly.
- **Truncation must happen in core during the transient period phase**, not via the shared
  `filter_date_range`: today's `truncate` compares *periods* (`Period("1926-07") >= Period(start)`
  keeps a month even when `start` is mid-month), which is not equivalent to filtering
  period-start timestamps. This is the one reader where the shared filter must not be used; both
  presenters then contain identical rows.
- Container parity: `dict[int | "DESCR", ...]` in every backend; `"DESCR"` stays a str.

**econdb** — the tidy side is record-native ([R]): long records `TIME_PERIOD` + one column per
metadata dimension + `value`. The pandas presenter replays today's iterative
`merge(how="outer")` loop + MultiIndex columns + truncate **verbatim on today's per-series
frames** (carried in the payload) — zero parity risk, at the cost of the payload temporarily
carrying both representations. Cleaning the presenter up to pivot-from-records is a possible
follow-up, deliberately not done here.

**tiingo** — daily/IEX/quote go [R]-native: long `symbol, date` (datetime via `to_datetime_col`)
+ payload fields, one frame. The pandas presenter is the verbatim per-symbol
`DataFrame(out)` + `set_index(["symbol", "date"])` + `concat`. Metadata: pandas keeps today's
fields×symbols frame (Series `concat(axis=1)`); non-pandas gets the tidy transpose — one row per
symbol, `symbol` + metadata fields as columns (a fields-as-rows frame has heterogeneous value
types per row, untypeable in arrow/polars).

## Tasks

| # | Commit | Contents | Testing plan |
|---|---|---|---|
| 1 | famafrench payload + presenters | `_Parsed` NamedTuple; in-core period-phase truncate; pandas presenter `set_index("Date")` + `to_period(freqs[i])` + dict/DESCR reassembly; tidy presenter converts each table, dict container preserved | Untouched `tests/test_famafrench.py` = parity oracle (incl. daily-date tables from the recent daily-parse fix); new unit test: timestamp→period round-trip for M/Y at truncation boundaries (mid-month start); new backend tests: dict keys preserved, `DESCR` str, `Date` datetime col, per-table row counts match pandas |
| 2 | econdb records + verbatim presenter | Core returns records + today's per-series frames in the payload; tidy = `make_frame` + `filter_date_range`; pandas presenter = verbatim merge loop | Untouched econdb offline tests = parity oracle; new backend tests: dimension columns + `value` schema, filtered row counts vs pandas |
| 3 | tiingo daily/IEX/quote record-native | [R]-path via `make_frame`; `to_datetime_col` on `date`; pandas presenter verbatim | Untouched tiingo tests = parity oracle (note: tiingo needs an API key, so offline coverage relies on mocked payloads — extend `tests/test_tiingo.py` mocks if thin); new backend tests: `symbol, date` plain columns, datetime dtype |
| 4 | tiingo metadata policy | pandas: verbatim fields×symbols frame; non-pandas: one row per symbol via `make_frame` | Parity oracle as above; new backend tests: one row per requested symbol, metadata fields as typed columns |

## PR review notes

- Reviewer focus commit 1: the truncation-boundary unit test is the proof the period subtlety is
  handled; check its cases (start/end mid-month, annual tables, daily tables).
- Reviewer focus commit 2: the double-representation payload is intentional scaffolding — the
  commit message should say so and name the follow-up.
