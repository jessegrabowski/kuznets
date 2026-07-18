import json
import time
import warnings

from pandas import DataFrame, Series, concat, to_datetime

from pandas_datareader._utils import RemoteDataError, SymbolWarning
from pandas_datareader.base import _fetch_symbols_concurrently
from pandas_datareader.yahoo.daily import YahooDailyReader


class YahooFXReader(YahooDailyReader):
    """Get historical prices for currency pairs from Yahoo Finance."""

    def _get_params(self, symbol: str) -> dict:
        """Build query parameters for a given symbol.

        Parameters
        ----------
        symbol : str
            Currency pair symbol.

        Returns
        -------
        params : dict
        """
        unix_start = int(time.mktime(self.start.timetuple()))
        day_end = self.end.replace(hour=23, minute=59, second=59)
        unix_end = int(time.mktime(day_end.timetuple()))

        params = {
            "symbol": symbol + "=X",
            "period1": unix_start,
            "period2": unix_end,
            "interval": self.interval,  # deal with this
            "includePrePost": "true",
            "events": "div|split|earn",
            "corsDomain": "finance.yahoo.com",
        }
        return params

    def _read_core(self) -> DataFrame:
        """Fetch FX data.

        Returns
        -------
        df : DataFrame
        """
        try:
            # If a single symbol, (e.g., 'GOOG')
            if isinstance(self.symbols, str | int):
                df = self._read_one_data(self.symbols)

            # Or multiple symbols, (e.g., ['GOOG', 'AAPL', 'MSFT'])
            elif isinstance(self.symbols, DataFrame):
                df = self._dl_mult_symbols(self.symbols.index)
            else:
                df = self._dl_mult_symbols(self.symbols)

            if "Date" in df:
                df = df.set_index("Date")

            if "Volume" in df:
                df = df.drop("Volume", axis=1)

            return df.sort_index().dropna(how="all")
        finally:
            self.close()

    def _read_one_data(self, symbol: str) -> DataFrame:
        """Read data for a single currency pair.

        Parameters
        ----------
        symbol : str
            Currency pair symbol.

        Returns
        -------
        df : DataFrame
        """
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}=X"
        params = self._get_params(symbol)

        resp = self._get_response(url, params=params)
        jsn = json.loads(resp.text)

        data = jsn["chart"]["result"][0]
        df = DataFrame(data["indicators"]["quote"][0])
        df.insert(0, "date", to_datetime(Series(data["timestamp"]), unit="s").dt.date)
        df.columns = map(str.capitalize, df.columns)
        return df

    def _dl_mult_symbols(self, symbols):
        def fetch_one(sym):
            df = self._read_one_data(sym)
            df["PairCode"] = sym
            return df

        results = _fetch_symbols_concurrently(symbols, fetch_one, self.max_workers, catch=(OSError,))
        stocks = {}
        passed = []
        for sym, outcome in results:
            if isinstance(outcome, Exception):
                msg = "Failed to read symbol: {0!r}, replacing with NaN."
                warnings.warn(msg.format(sym), SymbolWarning, stacklevel=2)
            else:
                stocks[sym] = outcome
                passed.append(sym)

        if len(passed) == 0:
            msg = "No data fetched using {0!r}"
            raise RemoteDataError(msg.format(self.__class__.__name__))
        return concat(stocks).set_index(["PairCode", "Date"])
