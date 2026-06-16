import datetime
import json
import os

from dateutil.relativedelta import relativedelta
import pandas as pd

from pandas_datareader.base import _DailyBaseReader
from pandas_datareader.config import get_api_key

# Data provided for free by IEX
# Data is furnished in compliance with the guidelines promulgated in the IEX
# API terms of service and manual
# See https://iextrading.com/api-exhibit-a/ for additional information
# and conditions of use


class IEXDailyReader(_DailyBaseReader):
    """Get historical stock prices from IEX Cloud."""

    def __init__(
        self,
        symbols: str | list[str] | None = None,
        start=None,
        end=None,
        retry_count: int | None = None,
        pause: float | None = None,
        session=None,
        chunksize: int = 25,
        api_key: str | None = None,
    ) -> None:
        """
        Initialize the reader.

        Parameters
        ----------
        symbols : str, list of str, or DataFrame, optional
            Single stock symbol (ticker), list of symbols, or DataFrame with index containing stock
            symbols.
        start : str, int, date, datetime, or Timestamp, optional
            Starting date. Defaults to 15 years before current date.
        end : str, int, date, datetime, or Timestamp, optional
            Ending date.
        retry_count : int, optional
            Number of times to retry query request. Falls back to the configured default.
        pause : float, optional
            Time, in seconds, to pause between consecutive queries. Falls back to the configured
            default.
        session : Session, optional
            ``requests.sessions.Session`` instance to be used.
        chunksize : int, default 25
            Number of symbols to download consecutively before initiating pause.
        api_key : str, optional
            IEX Cloud Secret Token. Resolved through :func:`pandas_datareader.config.get_api_key`
            (argument, ``options.api_keys['iex']``, ``IEX_API_KEY``, then the config file). The API
            key is *required*.
        """
        self.api_key = get_api_key("iex", api_key)
        self.sandbox = os.getenv("IEX_SANDBOX") == "enable"
        super().__init__(
            symbols=symbols,
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            chunksize=chunksize,
        )

    @property
    def default_start_date(self) -> datetime.date:
        """Default start date (15 years before today)."""
        today = datetime.date.today()
        return today - datetime.timedelta(days=365 * 15)

    @property
    def url(self) -> str:
        """API URL."""
        if self.sandbox is True:
            return "https://sandbox.iexapis.com/stable/stock/market/batch"
        else:
            return "https://cloud.iexapis.com/stable/stock/market/batch"

    @property
    def endpoint(self) -> str:
        """API endpoint."""
        return "chart"

    def _get_params(self, symbol: str | list[str]) -> dict:
        """Build query parameters for an API call.

        Parameters
        ----------
        symbol : str or list of str
            Ticker symbol(s).

        Returns
        -------
        params : dict
        """
        chart_range = self._range_string_from_date()
        if isinstance(symbol, list):
            symbolList = ",".join(symbol)
        else:
            symbolList = symbol
        params = {
            "symbols": symbolList,
            "types": self.endpoint,
            "range": chart_range,
            "token": self.api_key,
        }
        return params

    def _range_string_from_date(self) -> str:
        """Convert start date into an IEX-compatible range string.

        Returns
        -------
        range_str : str
            One of ``"5d"``, ``"1m"``, ``"3m"``, ``"6m"``, ``"1y"``, ``"2y"``, ``"5y"``, or
            ``"max"``.
        """
        delta = relativedelta(self.start, datetime.datetime.now())
        years = delta.years * -1
        if 5 <= years <= 15:
            return "max"
        if 2 <= years < 5:
            return "5y"
        elif 1 <= years < 2:
            return "2y"
        elif 0 <= years < 1:
            delta_days = (datetime.datetime.now() - self.start).days
            if 0 <= delta_days < 6:
                return "5d"
            elif 6 <= delta_days < 28:
                return "1m"
            elif 28 <= delta_days < 84:
                return "3m"
            elif 84 <= delta_days < 168:
                return "6m"

            return "1y"
        else:
            raise ValueError("Invalid date specified. Must be within past 15 years.")

    def read(self) -> pd.DataFrame:
        """Read data from IEX Cloud.

        Returns
        -------
        df : DataFrame
        """
        try:
            return self._read_one_data(self.url, self._get_params(self.symbols))
        finally:
            self.close()

    def _read_lines(self, out) -> pd.DataFrame:
        """Parse IEX Cloud JSON response.

        Parameters
        ----------
        out : StringIO
            Raw response content.

        Returns
        -------
        df : DataFrame
        """
        data = out.read()
        json_data = json.loads(data)
        result = {}
        if type(self.symbols) is str:
            syms = [self.symbols]
        else:
            syms = self.symbols
        for symbol in syms:
            d = json_data.pop(symbol)["chart"]
            df = pd.DataFrame(d)
            df.set_index("date", inplace=True)
            values = ["open", "high", "low", "close", "volume"]
            df = df[values]
            sstart = self.start.strftime("%Y-%m-%d")
            send = self.end.strftime("%Y-%m-%d")
            df = df.loc[sstart:send]
            result.update({symbol: df})
        if len(result) > 1:
            result = pd.concat(result).unstack(level=0)
            result.columns.names = ["Attributes", "Symbols"]
            return result
        return result[self.symbols]
