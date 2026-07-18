# Step 05 (PR 5) — daily multi-symbol panel, yahoo family, AlphaVantage

## What and why

The multi-symbol daily panel is the most visible schema decision in the project. Today
`_dl_mult_symbols` builds `stocks: dict[symbol, frame]`, then
`concat(stocks, sort=True).unstack(level=0)` with MultiIndex columns `(Attributes, Symbols)`.
Under tidy core:

- **Payload** = the ordered `stocks` dict (plus the failed-symbol NaN fill, unchanged).
- **pandas presenter** = today's `concat().unstack()` + `columns.names` assignment, verbatim.
- **tidy presenter** = `concat(stocks, names=["Symbol"]).reset_index()` → columns
  `Date, Symbol, <attributes>`, sorted by `(Date, Symbol)`. Failed symbols appear as NaN-valued
  rows (dates borrowed from the first passed symbol) — information parity with the pandas panel's
  NaN columns. `SymbolWarning` is emitted either way.

This PR also migrates the rest of the yahoo family and AlphaVantage, including the **one
deliberate breaking change** in the whole project: AV date strings are parsed to real datetimes
*for pandas output too* (the string index was never intentional; the `.loc` lexicographic string
slice becomes a real datetime filter). Everything else in this PR is byte-parity for pandas.

Shape policies (user-approved):

- yahoo actions multi-symbol: pandas keeps today's `dict[symbol, frame]`; non-pandas returns
  **one long frame** `Date, Symbol, action, value`. Single symbol: `Date, action, value`.
- yahoo quotes: [R]-path — one row per symbol, `symbol` + quote fields, built via `make_frame`.
- yahoo fx: `Date` keeps its date (not datetime) type; multi-pair pandas presenter re-imposes
  `set_index(["PairCode", "Date"])` verbatim.

## Tasks

| # | Commit | Contents | Testing plan |
|---|---|---|---|
| 1 | `_dl_mult_symbols` payload + panel presenters | `base.py::_DailyBaseReader`: core returns the ordered `stocks` dict (NaN-fill logic unchanged); pandas presenter verbatim; tidy presenter as above | Untouched multi-symbol offline tests (stooq) = parity oracle; new backend tests: long schema `Date, Symbol, Open…`, row count = Σ per-symbol rows, NaN rows for a failed symbol, `SymbolWarning` still raised, deterministic sort; unit test pinning pandas>=3 `concat`/`unstack` semantics |
| 2 | yahoo daily (single) + yahoo quotes | daily: identity presenters (adjust/return math stays in core, `Date` + OHLCV tidy via detach); quotes: [R]-path via `make_frame`, pandas presenter = verbatim `set_index("symbol")` | Yahoo offline tests (where fixtures exist) = parity oracle; new backend tests incl. the `_empty_history` all-NaN payload through `from_pandas` |
| 3 | yahoo actions/div/split | Core produces long `Date, Symbol, action, value`; pandas presenter = verbatim per-symbol frame/dict logic; non-pandas multi-symbol = one long frame | Untouched actions tests = parity oracle (dict container, per-symbol frames); new backend tests: single-symbol long frame; multi-symbol single long frame with `Symbol` column |
| 4 | yahoo fx | Tidy `Date (date), PairCode?, Open, High, Low, Close`; presenters verbatim | Untouched fx tests = parity oracle; new backend tests: `Date` maps to narwhals `Date` dtype in polars/arrow |
| 5 | AV: datetime dates (breaking) + forex | `av/time_series.py`: parse dates to datetime in core; pandas presenter `set_index("Date")` (now DatetimeIndex); `.loc` string slice → real datetime filter; `av/forex.py`: tidy = one row per pair, presenter = verbatim concat(axis=1) | **AV offline tests updated deliberately** (the one place fixture-derived expectations change): assert DatetimeIndex for pandas output; date-range filtering equivalence vs the old string slice on fixture data; new backend tests; whatsnew entry stub added in step 08 |

## PR review notes

- Commit 1 defines the long panel schema — the headline user-facing contract of the feature.
- Commit 5 is the only intentional pandas behavior change in the whole migration; its test diff
  is the reviewable evidence of exactly what changed.
