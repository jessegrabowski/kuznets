from pandas import DataFrame

from pandas_datareader._output import make_frame
from pandas_datareader._utils import RemoteDataError
from pandas_datareader.base import _BaseReader
from pandas_datareader.yahoo._auth import fetch_crumb
from pandas_datareader.yahoo.headers import DEFAULT_HEADERS

_DEFAULT_PARAMS = {
    "lang": "en-US",
    "corsDomain": "finance.yahoo.com",
    ".tsrc": "finance",
}


class YahooQuotesReader(_BaseReader):
    """Get current Yahoo Finance quote for one or more symbols."""

    def __init__(
        self,
        symbols: str | list[str] | None = None,
        start=None,
        end=None,
        retry_count: int = 3,
        pause: float = 0.1,
        session=None,
        output_type: str = "pandas",
    ) -> None:
        super().__init__(
            symbols=symbols,
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            output_type=output_type,
        )
        self.headers = session.headers if session is not None else DEFAULT_HEADERS

    @property
    def url(self) -> str:
        """API URL."""
        return "https://query1.finance.yahoo.com/v7/finance/quote"

    def _read_core(self) -> list:
        """Fetch quote records for one or more symbols.

        Returns
        -------
        results : list of dict
            One raw quote record per symbol.
        """
        symbols = [self.symbols] if isinstance(self.symbols, str) else list(self.symbols)
        crumb = fetch_crumb(self.session, self.headers, self.timeout)
        params = {"symbols": ",".join(symbols), "crumb": crumb, **_DEFAULT_PARAMS}
        results = self._get_response(self.url, params=params, headers=self.headers).json()
        results = results["quoteResponse"]["result"]
        if not results:
            raise RemoteDataError(f"No quotes fetched for {symbols}")
        return results

    def _present_pandas(self, results: list) -> DataFrame:
        """One row per symbol indexed by ticker, with ``price`` copied from the regular market price."""
        df = DataFrame(results).set_index("symbol")
        df["price"] = df["regularMarketPrice"]
        return df

    def _present_tidy(self, results: list):
        """One row per symbol with ``symbol`` as a plain column, built record-natively."""
        records = [{**record, "price": record.get("regularMarketPrice")} for record in results]
        return make_frame(records, self.output_type)
