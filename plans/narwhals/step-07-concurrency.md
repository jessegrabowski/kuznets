# Step 07 (PR 7) — concurrent multi-symbol fetching

## What and why

`_dl_mult_symbols` fetches one HTTP request per symbol, sequentially (`base.py`). For a
100-symbol pull that is 100 round-trips of pure network latency — tens of seconds — while the
dataframe work costs milliseconds. A thread pool is the actual large-extraction speedup, and it
is orthogonal to the tidy/backend work (it lands after step 05 so the `stocks`-dict payload
interface is already in place).

Design (settled during planning):

- New helper `base.py::_fetch_symbols_concurrently(symbols, fetch_one, max_workers)` →
  ordered `list[(symbol, DataFrame | Exception)]` via `ThreadPoolExecutor` + `executor.map`
  (order-preserving). Workers catch `(OSError, KeyError)` and *return* the exception; any other
  exception propagates. **Workers never warn** — `SymbolWarning` is emitted from the main thread
  while iterating results, so the warning text, count, and `pytest.warns` behavior are
  byte-identical to today (and safe under Python 3.14 context-local warning filters).
- All tail logic is untouched: all-failed → `RemoteDataError`; failed symbols NaN-filled from the
  first passed frame; ordered `stocks` dict feeds the presenters from step 05. `RemoteDataError`
  subclasses `IOError`, so per-symbol `RemoteDataError`s keep degrading to warnings.
- **One shared `self.session`.** urllib3's connection pooling and `http.cookiejar` are
  thread-safe for the plain GETs issued here; per-thread sessions would silently discard a
  user-supplied `session=` (custom auth, requests-cache). Documented: user-supplied sessions that
  are not thread-safe (requests-cache explicitly is not) should pass `max_workers=1`.
- `max_workers: int = 5` on `_DailyBaseReader.__init__` — polite default, below the mounted
  adapter's `pool_maxsize=10`; `max_workers=1` degrades to sequential through the same code path.
  Threaded through `DataReader(..., max_workers=None)` for the `_DailyBaseReader` family (yahoo,
  yahoo-dividends, stooq, naver, quandl, moex).
- The vestigial `_in_chunks` loop is dropped (it has no inter-chunk pause today); the `chunksize`
  parameter is retained for API compatibility and documented as deprecated/unused.
- `tests/_mock.py` compatibility: the harness patches the *unbound* `requests.Session.get`
  (class-level), so worker threads are intercepted with no harness changes.
- Yahoo caveat to verify during implementation: whether the crumb/cookie handshake in
  `yahoo/daily.py` happens per call. If so, perform it once eagerly before submitting tasks
  (correctness holds either way — it is GETs through a locked cookiejar — but once is politer).

## Tasks

| # | Commit | Contents | Testing plan |
|---|---|---|---|
| 1 | `_fetch_symbols_concurrently` helper | `base.py` helper + docstring stating the ordering and exception contract | New `tests/test_base.py` unit tests with a stub fetch_one: result order equals input order regardless of completion order (stagger via `threading.Event`); caught vs propagated exception classes; `max_workers` clamped to `len(symbols)` |
| 2 | `_dl_mult_symbols` on the helper + `max_workers` plumbing | Rewrite loop body; emit warnings main-thread; drop `_in_chunks` loop; `_DailyBaseReader.__init__(..., max_workers=5)`; `yahoo/daily.py` + `DataReader` threading; crumb verification | Stub `_DailyBaseReader` + `patch_session_get` handler recording `(thread_ident, url)` under a `threading.Lock`, small CSV per symbol: with ~40 symbols, `max_workers=8` result `assert_frame_equal`-identical to `max_workers=1`; all 40 URLs hit exactly once; >1 distinct thread id observed; mixed good/bad symbols → one `SymbolWarning` per bad symbol with exact message, NaN columns; all-bad → `RemoteDataError`; `len(symbols)==1` path; full offline suite green |
| 3 | `yahoo/fx.py::_dl_mult_symbols` onto the helper | Refactor its bespoke loop; warn/NaN/concat tail unchanged | Untouched fx offline tests = parity oracle; extend the thread-recording test pattern to the fx reader |

## PR review notes

- The determinism test (commit 2) is the heart of the PR: identical output at any worker count.
- Reviewer focus: confirm no code path lets a worker thread call `warnings.warn` or mutate reader
  instance state (payload-as-argument from step 05 makes presenters stateless; workers run only
  `_read_one_data`).
