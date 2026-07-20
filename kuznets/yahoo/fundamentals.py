import time
import warnings

from pandas import DataFrame, concat, to_datetime

from kuznets._output import from_pandas
from kuznets._utils import RemoteDataError, SymbolWarning
from kuznets.base import _DEFAULT_MAX_WORKERS, _BaseReader, _fetch_symbols_concurrently
from kuznets.yahoo.headers import DEFAULT_HEADERS

# Line items per statement, in presentation order. Yahoo silently omits items a company does not
# report (e.g. Goodwill for Apple), so requesting the full set is safe for every symbol.
BALANCE_SHEET_SERIES = (
    "TotalAssets",
    "CurrentAssets",
    "CashAndCashEquivalents",
    "CashCashEquivalentsAndShortTermInvestments",
    "OtherShortTermInvestments",
    "AccountsReceivable",
    "Receivables",
    "Inventory",
    "OtherCurrentAssets",
    "TotalNonCurrentAssets",
    "NetPPE",
    "GrossPPE",
    "AccumulatedDepreciation",
    "Goodwill",
    "OtherIntangibleAssets",
    "GoodwillAndOtherIntangibleAssets",
    "InvestmentsAndAdvances",
    "OtherNonCurrentAssets",
    "TotalLiabilitiesNetMinorityInterest",
    "CurrentLiabilities",
    "AccountsPayable",
    "Payables",
    "CurrentDebt",
    "CurrentDebtAndCapitalLeaseObligation",
    "CommercialPaper",
    "CurrentDeferredRevenue",
    "OtherCurrentLiabilities",
    "TotalNonCurrentLiabilitiesNetMinorityInterest",
    "LongTermDebt",
    "LongTermDebtAndCapitalLeaseObligation",
    "TradeandOtherPayablesNonCurrent",
    "OtherNonCurrentLiabilities",
    "TotalDebt",
    "NetDebt",
    "StockholdersEquity",
    "CommonStockEquity",
    "CapitalStock",
    "CommonStock",
    "RetainedEarnings",
    "GainsLossesNotAffectingRetainedEarnings",
    "TotalEquityGrossMinorityInterest",
    "MinorityInterest",
    "TotalCapitalization",
    "WorkingCapital",
    "InvestedCapital",
    "TangibleBookValue",
    "ShareIssued",
    "OrdinarySharesNumber",
    "TreasurySharesNumber",
)

INCOME_STATEMENT_SERIES = (
    "TotalRevenue",
    "OperatingRevenue",
    "CostOfRevenue",
    "GrossProfit",
    "OperatingExpense",
    "SellingGeneralAndAdministration",
    "ResearchAndDevelopment",
    "OperatingIncome",
    "NetNonOperatingInterestIncomeExpense",
    "InterestIncome",
    "InterestExpense",
    "InterestIncomeNonOperating",
    "InterestExpenseNonOperating",
    "NetInterestIncome",
    "OtherIncomeExpense",
    "OtherNonOperatingIncomeExpenses",
    "PretaxIncome",
    "TaxProvision",
    "TaxRateForCalcs",
    "TaxEffectOfUnusualItems",
    "NetIncomeContinuousOperations",
    "NetIncome",
    "NetIncomeCommonStockholders",
    "DilutedNIAvailtoComStockholders",
    "BasicEPS",
    "DilutedEPS",
    "BasicAverageShares",
    "DilutedAverageShares",
    "TotalExpenses",
    "TotalOperatingIncomeAsReported",
    "EBIT",
    "EBITDA",
    "NormalizedEBITDA",
    "NormalizedIncome",
    "ReconciledCostOfRevenue",
    "ReconciledDepreciation",
)

CASH_FLOW_SERIES = (
    "OperatingCashFlow",
    "CashFlowFromContinuingOperatingActivities",
    "NetIncomeFromContinuingOperations",
    "DepreciationAndAmortization",
    "DepreciationAmortizationDepletion",
    "DeferredIncomeTax",
    "DeferredTax",
    "StockBasedCompensation",
    "OtherNonCashItems",
    "ChangeInWorkingCapital",
    "ChangesInAccountReceivables",
    "ChangeInInventory",
    "ChangeInPayable",
    "ChangeInOtherCurrentAssets",
    "ChangeInOtherCurrentLiabilities",
    "InvestingCashFlow",
    "CashFlowFromContinuingInvestingActivities",
    "NetPPEPurchaseAndSale",
    "PurchaseOfPPE",
    "CapitalExpenditure",
    "NetBusinessPurchaseAndSale",
    "PurchaseOfBusiness",
    "NetInvestmentPurchaseAndSale",
    "PurchaseOfInvestment",
    "SaleOfInvestment",
    "NetOtherInvestingChanges",
    "FinancingCashFlow",
    "CashFlowFromContinuingFinancingActivities",
    "NetIssuancePaymentsOfDebt",
    "NetLongTermDebtIssuance",
    "LongTermDebtIssuance",
    "LongTermDebtPayments",
    "NetShortTermDebtIssuance",
    "NetCommonStockIssuance",
    "CommonStockIssuance",
    "CommonStockPayments",
    "RepurchaseOfCapitalStock",
    "CashDividendsPaid",
    "CommonStockDividendPaid",
    "NetOtherFinancingCharges",
    "EffectOfExchangeRateChanges",
    "ChangesInCash",
    "BeginningCashPosition",
    "EndCashPosition",
    "FreeCashFlow",
    "IssuanceOfCapitalStock",
    "IssuanceOfDebt",
    "RepaymentOfDebt",
)

_STATEMENT_SERIES = {
    "balance-sheet": BALANCE_SHEET_SERIES,
    "income": INCOME_STATEMENT_SERIES,
    "cash-flow": CASH_FLOW_SERIES,
}
_FREQS = ("annual", "quarterly", "trailing")


class YahooFundamentalsReader(_BaseReader):
    """Get financial-statement fundamentals from the Yahoo Finance timeseries API.

    Fetch balance-sheet, income-statement, or cash-flow line items as reported per fiscal period.
    Pick a whole statement with ``statement`` or exact line items with ``series``; the module-level
    tuples ``BALANCE_SHEET_SERIES``, ``INCOME_STATEMENT_SERIES``, and ``CASH_FLOW_SERIES`` list the
    known items.

    Examples
    --------
    >>> YahooFundamentalsReader("AAPL").read()  # annual balance sheet
    >>> YahooFundamentalsReader(["AAPL", "MSFT"], statement="income", freq="quarterly").read()
    >>> YahooFundamentalsReader("AAPL", series=["TotalAssets", "NetDebt"]).read()
    """

    def __init__(
        self,
        symbols: str | list[str] | None = None,
        start=None,
        end=None,
        retry_count: int | None = None,
        pause: float | None = None,
        session=None,
        freq: str = "annual",
        statement: str = "balance-sheet",
        series: list[str] | None = None,
        output_type: str = "pandas",
        max_workers: int | None = None,
    ) -> None:
        """
        Initialize the reader.

        Parameters
        ----------
        symbols : str or list of str
            Single stock symbol (ticker) or list of symbols. A list — even of one symbol — returns
            the multi-symbol shape.
        start : str, int, date, datetime, or Timestamp, optional
            Earliest fiscal period end to include. Defaults to 5 years before the current date.
        end : str, int, date, datetime, or Timestamp, optional
            Latest fiscal period end to include. Defaults to today.
        retry_count : int, optional
            Number of times to retry query request. Falls back to the configured default.
        pause : float, optional
            Time, in seconds, of the pause between retries. Falls back to the configured default.
        session : Session, optional
            ``requests.sessions.Session`` instance to be used.
        freq : str, optional
            Reporting period: 'annual', 'quarterly', or 'trailing' (trailing twelve months;
            populated only for flow items such as revenue and cash flow, not balance-sheet stocks).
            Default 'annual'.
        statement : str, optional
            Statement preset to fetch: 'balance-sheet', 'income', or 'cash-flow'. Ignored when
            ``series`` is given. Default 'balance-sheet'.
        series : list of str, optional
            Exact line items to fetch, named without the frequency prefix (e.g. ``'TotalAssets'``,
            not ``'annualTotalAssets'``). When omitted, the ``statement`` preset is fetched.
        output_type : str, optional
            Backend of the returned data: 'pandas', 'polars', 'pyarrow' (alias 'arrow'), or 'dask'.
            Backends other than pandas must be installed separately. Default 'pandas'.
        max_workers : int, optional
            Number of concurrent requests for multi-symbol reads. Keep it modest for rate-limited
            hosts, and pass 1 when supplying a session that is not thread-safe. Default 5.
        """
        super().__init__(
            symbols=symbols,
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            freq=freq,
            output_type=output_type,
        )
        if freq not in _FREQS:
            raise ValueError(f"freq={freq!r} is not supported; choose one of {', '.join(map(repr, _FREQS))}")
        if series is None:
            if statement not in _STATEMENT_SERIES:
                valid = ", ".join(map(repr, _STATEMENT_SERIES))
                raise ValueError(f"statement={statement!r} is not supported; choose one of {valid}")
            series = _STATEMENT_SERIES[statement]
        elif isinstance(series, str):
            series = [series]
        self.series = tuple(series)
        self.max_workers = _DEFAULT_MAX_WORKERS if max_workers is None else max_workers
        self.headers = session.headers if session is not None else DEFAULT_HEADERS

    @property
    def url(self) -> str:
        """API URL, with a placeholder for the symbol."""
        return "https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{}"

    @property
    def params(self) -> dict:
        """Query parameters: the prefixed series names and the Unix-timestamp period bounds."""
        day_end = self.end.replace(hour=23, minute=59, second=59)
        return {
            "type": ",".join(f"{self.freq}{item}" for item in self.series),
            "period1": int(time.mktime(self.start.timetuple())),
            "period2": int(time.mktime(day_end.timetuple())),
        }

    def _read_core(self):
        """Fetch fundamentals for one or more symbols.

        Returns
        -------
        DataFrame or dict
            A single wide frame for a str symbol; a dict of one frame per symbol for a list.
            Symbols that fail or return no data are dropped from the dict with a
            :class:`SymbolWarning`.
        """
        try:
            if isinstance(self.symbols, str):
                return self._fetch_one(self.symbols)
            results = _fetch_symbols_concurrently(self.symbols, self._fetch_one, self.max_workers)
        finally:
            self.close()

        frames = {}
        for symbol, outcome in results:
            if isinstance(outcome, Exception):
                warnings.warn(f"Failed to read symbol: {symbol!r}, skipping.", SymbolWarning, stacklevel=2)
            else:
                frames[symbol] = outcome
        if not frames:
            raise RemoteDataError(f"No fundamentals data fetched for {list(self.symbols)}")
        return frames

    def _fetch_one(self, symbol: str) -> DataFrame:
        """Fetch and pivot one symbol's series into a wide frame indexed by fiscal period end."""
        response = self._get_response(self.url.format(symbol), params=self.params, headers=self.headers)
        payload = response.json().get("timeseries", {}).get("result") or []

        columns = {}
        for series in payload:
            name = series["meta"]["type"][0]
            item = name.removeprefix(self.freq)
            # Missing reports arrive as explicit nulls, either as a null entry or as a null
            # reportedValue; skipping both keeps never-reported items out of the frame entirely.
            values = {}
            for entry in series.get(name, []):
                raw = (entry.get("reportedValue") or {}).get("raw") if entry else None
                if raw is not None:
                    values[entry["asOfDate"]] = raw
            if values:
                columns[item] = values
        if not columns:
            raise RemoteDataError(f"No fundamentals data fetched for {symbol!r}")

        frame = DataFrame({item: columns[item] for item in self.series if item in columns}, dtype="float64")
        frame.index = to_datetime(frame.index)
        frame.index.name = "Date"
        return frame.sort_index()

    def _present_pandas(self, payload):
        """Wide frame indexed by period end; multi-symbol payloads stack under a (Symbol, Date) MultiIndex."""
        if isinstance(payload, dict):
            return concat(payload, names=["Symbol"])
        return payload

    def _present_tidy(self, payload):
        """Convert to the requested backend; multi-symbol payloads become one row per (date, symbol)."""
        if not isinstance(payload, dict):
            return super()._present_tidy(payload)
        long = concat(payload, names=["Symbol"]).reset_index()
        long = long.sort_values(["Date", "Symbol"], kind="stable").reset_index(drop=True)
        ordered = ["Date", "Symbol", *(column for column in long.columns if column not in ("Date", "Symbol"))]
        return from_pandas(long[ordered], self.output_type)
