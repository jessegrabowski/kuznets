# Backend-agnostic loaders: tidy core + `output_type=`

## Why

pandas-datareader hard-codes pandas as its only output format. The Python data ecosystem is going
dataframe-agnostic; every loader should gain an `output_type=` parameter returning pandas / polars /
pyarrow / dask natively, without breaking a single existing pandas user.

The design rests on one verified fact: **every pandas-specific structure in this library
(DatetimeIndex, PeriodIndex, MultiIndex rows/columns, the wide multi-symbol panel) is a final
decoration applied to data that arrives tidy.**

- Fama-French: flat CSV with integer date codes; `to_period()` imposed at `famafrench.py:134-139`.
- SDMX (OECD/Eurostat): the wire format is long-form observation records; `io/util.py:33`
  `_pivot_observations` pivots them wide — the pivot is ours, not the data's.
- Multi-symbol daily: `concat(stocks)` produces a tidy (symbol, date) long frame *before*
  `.unstack(level=0)` widens it (`base.py:383`).

So the architecture is **tidy core + presentation layers**, not "pandas core + convert on exit"
(which would decorate results and then immediately un-decorate them for non-pandas users):

- Each reader's core produces a **payload** — its pre-decoration intermediate (tidy columns, no
  indexes). Presentation context (e.g. Fama-French per-table frequency) travels *inside* the
  payload, never on `self`.
- `output_type="pandas"` (default) runs the **pandas presenter**: today's decorations
  (`set_index`, `to_period`, `unstack`), moved verbatim wherever they are non-trivial, so the
  untouched offline fixture suite is a byte-parity oracle. Zero breaking changes (one deliberate
  exception: AlphaVantage dates become real datetimes, see [step 05](step-05-daily-panel-yahoo-av.md)).
- Any other backend runs the **tidy presenter**: the tidy frame is handed over directly — never
  pivoted, never period-ized. Long/tidy *is* the data model (multi-symbol = one row per
  (Date, Symbol) with plain OHLCV columns).
- **narwhals** (`narwhals.stable.v2`, pinned `>=2.0`) is the required, load-bearing conversion and
  construction layer. JSON/SDMX readers construct natively via `nw.from_dict(backend=output_type)`
  so non-pandas users skip pandas entirely on those paths ([benchmarked](step-00-benchmark.md):
  it is the *fastest* construction path on every backend). CSV readers parse with pandas, then
  convert. Backends stay user-installed, with a fail-fast, helpful `ImportError`.

A second, orthogonal feature rides along: **concurrent multi-symbol fetching**. The per-symbol HTTP
loop in `_dl_mult_symbols` is sequential today; a thread pool is the real large-extraction speedup
(network dominates compute by ~100x in this library).

## Decisions log (user-approved)

| Decision | Choice |
|---|---|
| Architecture | Tidy core + presentation layers (full refactor) |
| Non-pandas panel schema | Long/tidy: `Date, Symbol, <attributes>` |
| Conversion/construction layer | narwhals `stable.v2`, required dependency, `>=2.0` |
| Record construction | Column-oriented `nw.from_dict` after pure-Python records→columns pivot (benchmark step 00) |
| famafrench container | dict in every backend; values native frames with `Date` col; `"DESCR"` stays str |
| yahoo actions multi-symbol | pandas keeps dict; non-pandas = one long frame `Date, Symbol, action, value` |
| tiingo metadata | pandas keeps fields×symbols frame; non-pandas = one row per symbol |
| Failed panel symbols | Kept as NaN rows in tidy output (parity with NaN columns in the pandas panel) |
| AlphaVantage dates | Parsed to datetime **for pandas too** — deliberate breaking change ("the strings were always dumb") |
| PeriodIndex mapping | Period-start timestamps in tidy output; pandas presenter re-imposes periods |
| Concurrency | Shared session, `ThreadPoolExecutor`, `max_workers=5` default, main-thread warnings |
| Out of scope | `yahoo/options.py::Options` stays pandas-only; FRED/WB internal loops stay sequential |

## Steps

Each step is one PR. Each step file explains the work and lists a table of tasks, where every task
is a single logically scoped commit with its own testing plan. The full offline test suite stays
green after every commit.

| PR | Step | Contents |
|---|---|---|
| — | [00 — benchmark gate](step-00-benchmark.md) | `nw.from_dict` benchmark (done; gate passed) |
| 1 | [01 — output toolkit](step-01-output-toolkit.md) | `_output.py` + narwhals dep + unit tests |
| 2 | [02 — template split](step-02-template-split.md) | Mechanical `read()` → core/presenter split; `output_type` threading |
| 3 | [03 — simple readers](step-03-simple-readers.md) | Tidy paths for the simple CSV-parsed readers |
| 4 | [04 — SDMX record-native](step-04-sdmx-record-native.md) | OECD/Eurostat/io layer construct natively from records |
| 5 | [05 — daily panel, yahoo, av](step-05-daily-panel-yahoo-av.md) | Multi-symbol long tidy; yahoo family; AV datetime change |
| 6 | [06 — parity-delicate readers](step-06-parity-delicate.md) | famafrench, econdb, tiingo |
| 7 | [07 — concurrency](step-07-concurrency.md) | Parallel `_dl_mult_symbols` + `max_workers` |
| 8 | [08 — docs and release](step-08-docs-release.md) | remote_data/cache docs, whatsnew, README, extras polish |

## Verification standard (applies to every commit)

```bash
pip install -e ".[dev,polars,pyarrow]"
ruff check . && ruff format --check .
pytest                                    # offline suite — the byte-parity oracle
pytest tests/test_output.py tests/test_base.py -v
```

Per PR, once before merge: `pytest -m network` (API-drift check only). End-to-end sanity:
`get_data_fred('GDP')` must be `assert_frame_equal`-identical to a pre-branch checkout, and
`DataReader("AAPL", "stooq", output_type="polars")` must return a long polars frame.

## Key verified facts (for implementers)

- narwhals index gotcha: `to_polars()` (via `pl.from_pandas`) **drops** a pandas index;
  `to_arrow()` (via `pa.Table.from_pandas`) **keeps** it as a column. The tidy contract (no
  indexes cross the reader→presenter boundary) makes this moot by construction — but it is why
  `from_pandas` in `_output.py` asserts tidiness instead of silently resetting.
- `pl.from_pandas` requires pyarrow → pyarrow belongs in the `polars` extra.
- `RemoteDataError` subclasses `IOError`, so per-symbol failures degrade to `SymbolWarning`
  through the existing `except (OSError, KeyError)` — the concurrent version must preserve this.
- `tests/_mock.py` patches the *unbound* `requests.Session.get`, so worker threads are
  intercepted automatically; warnings must still be emitted from the main thread for
  `pytest.warns` to be reliable.
