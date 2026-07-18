import datetime as dt

import pandas as pd

from pandas_datareader.av import AlphaVantage


class AVTimeSeriesReader(AlphaVantage):
    """Get data from Alpha Vantage Stock Time Series endpoints."""

    _FUNC_TO_DATA_KEY = {
        "TIME_SERIES_DAILY": "Time Series (Daily)",
        "TIME_SERIES_DAILY_ADJUSTED": "Time Series (Daily)",
        "TIME_SERIES_WEEKLY": "Weekly Time Series",
        "TIME_SERIES_WEEKLY_ADJUSTED": "Weekly Adjusted Time Series",
        "TIME_SERIES_MONTHLY": "Monthly Time Series",
        "TIME_SERIES_MONTHLY_ADJUSTED": "Monthly Adjusted Time Series",
        "TIME_SERIES_INTRADAY": "Time Series (1min)",
        "FX_DAILY": "Time Series FX (Daily)",
    }

    def __init__(
        self,
        symbols: str | None = None,
        function: str = "TIME_SERIES_DAILY",
        start=None,
        end=None,
        retry_count: int = 3,
        pause: float = 0.1,
        session=None,
        chunksize: int = 25,
        api_key: str | None = None,
        output_type: str = "pandas",
    ) -> None:
        """
        Initialize the reader.

        Parameters
        ----------
        symbols : str, optional
            Single stock symbol (ticker).
        function : str, default "TIME_SERIES_DAILY"
            Alpha Vantage time series function name.
        start : str, int, date, datetime, or Timestamp, optional
            Starting date. Defaults to 20 years before current date (3 days for intraday).
        end : str, int, date, datetime, or Timestamp, optional
            Ending date.
        retry_count : int, default 3
            Number of times to retry query request.
        pause : float, default 0.1
            Time, in seconds, to pause between consecutive queries of chunks.
        session : Session, optional
            ``requests.sessions.Session`` instance to be used.
        chunksize : int, default 25
            Not used.
        api_key : str, optional
            Alpha Vantage API key. If not provided the environmental variable
            ``ALPHAVANTAGE_API_KEY`` is read. The API key is *required*.
        output_type : str, optional
            Backend of the returned data: 'pandas', 'polars', 'pyarrow' (alias 'arrow'), or 'dask'.
            Backends other than pandas must be installed separately. Default 'pandas'.
        """
        self._func = function
        super().__init__(
            symbols=symbols,
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            api_key=api_key,
            output_type=output_type,
        )

    @property
    def default_start_date(self) -> dt.datetime:
        """Default start date (3 days for intraday, 20 years otherwise)."""
        d_days = 3 if self.intraday else 365 * 20
        return dt.datetime.today() - dt.timedelta(days=d_days)

    @property
    def function(self) -> str:
        """Alpha Vantage endpoint function."""
        return self._func

    @property
    def intraday(self) -> bool:
        """Whether the function is intraday."""
        return self.function == "TIME_SERIES_INTRADAY"

    @property
    def forex(self) -> bool:
        """Whether the function is forex daily."""
        return self.function == "FX_DAILY"

    @property
    def output_size(self) -> str:
        """Compact or full output size based on date range.

        Returns
        -------
        size : str
            ``"compact"`` if the date range is less than 80 days and not intraday, otherwise
            ``"full"``.
        """
        delta = dt.datetime.now() - self.start
        return "compact" if delta.days < 80 and not self.intraday else "full"

    @property
    def data_key(self) -> str:
        """Key of data returned from Alpha Vantage."""
        return self._FUNC_TO_DATA_KEY[self.function]

    @property
    def params(self) -> dict:
        """Parameters to use in API calls."""
        p = {
            "function": self.function,
            "apikey": self.api_key,
            "outputsize": self.output_size,
        }
        if self.intraday:
            p.update({"interval": "1min"})
        if self.forex:
            p.update({"from_symbol": self.symbols.split("/")[0]})
            p.update({"to_symbol": self.symbols.split("/")[1]})
        else:
            p.update({"symbol": self.symbols})
        return p

    def _read_lines(self, out: dict) -> pd.DataFrame:
        """Parse Alpha Vantage time series JSON response.

        Parameters
        ----------
        out : dict
            Parsed JSON response.

        Returns
        -------
        df : DataFrame
        """
        data = super()._read_lines(out)
        data.index = pd.to_datetime(data.index)
        data = data.sort_index().loc[self.start : self.end]
        if data.empty:
            raise ValueError("Please input a valid date range")
        else:
            for column in data.columns:
                if column == "volume":
                    data[column] = data[column].astype("int64")
                else:
                    data[column] = data[column].astype("float64")
        return data
