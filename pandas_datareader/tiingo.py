import os

import pandas as pd

from pandas_datareader.base import _BaseReader


def get_tiingo_symbols() -> pd.DataFrame:
    """
    Get the set of stock symbols supported by Tiingo.

    Returns
    -------
    df : DataFrame
        DataFrame with symbols (ticker), exchange, asset type, currency and start and end dates.

    Notes
    -----
    Reads https://apimedia.tiingo.com/docs/tiingo/daily/supported_tickers.zip
    """
    url = "https://apimedia.tiingo.com/docs/tiingo/daily/supported_tickers.zip"
    return pd.read_csv(url)


class TiingoIEXHistoricalReader(_BaseReader):
    """Historical IEX data from Tiingo on equities, ETFs and mutual funds."""

    def __init__(
        self,
        symbols: str | list[str],
        start=None,
        end=None,
        retry_count: int = 3,
        pause: float = 0.1,
        timeout: float = 30,
        session=None,
        freq: str | None = None,
        api_key: str | None = None,
    ) -> None:
        """
        Initialize the reader.

        Parameters
        ----------
        symbols : str or list of str
            String symbol or list of symbols.
        start : str, int, date, datetime, or Timestamp, optional
            Starting date. Defaults to 5 years before current date.
        end : str, int, date, datetime, or Timestamp, optional
            Ending date.
        retry_count : int, default 3
            Number of times to retry query request.
        pause : float, default 0.1
            Time, in seconds, of the pause between retries.
        timeout : float, default 30
            Time, in seconds, to wait for server response.
        session : Session, optional
            ``requests.sessions.Session`` instance to be used.
        freq : str, optional
            Re-sample frequency. Format is ``#`` + ``min`` or ``hour``; e.g. ``"15min"`` or
            ``"4hour"``. Defaults to ``"5min"``. Minimum is ``"1min"``.
        api_key : str, optional
            Tiingo API key. If not provided the environmental variable ``TIINGO_API_KEY`` is read.
            The API key is *required*.
        """
        super().__init__(symbols, start, end, retry_count, pause, timeout, session, freq)

        if isinstance(self.symbols, str):
            self.symbols = [self.symbols]
        self._symbol = ""
        if api_key is None:
            api_key = os.getenv("TIINGO_API_KEY")
        if not api_key or not isinstance(api_key, str):
            raise ValueError(
                "The tiingo API key must be provided either "
                "through the api_key variable or through the "
                "environmental variable TIINGO_API_KEY."
            )
        self.api_key = api_key
        self._concat_axis = 0

    @property
    def url(self) -> str:
        """API URL."""
        _url = "https://api.tiingo.com/iex/{ticker}/prices"
        return _url.format(ticker=self._symbol)

    @property
    def params(self) -> dict:
        """Parameters to use in API calls."""
        return {
            "startDate": self.start.strftime("%Y-%m-%d"),
            "endDate": self.end.strftime("%Y-%m-%d"),
            "resampleFreq": self.freq,
            "format": "json",
        }

    def _get_crumb(self, *args) -> None:
        """Not used for Tiingo."""
        pass

    def _read_one_data(self, url: str, params: dict | None) -> pd.DataFrame:
        """Read one data from specified URL.

        Parameters
        ----------
        url : str
            Target URL.
        params : dict, optional
            Query parameters.

        Returns
        -------
        df : DataFrame
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Token " + self.api_key,
        }
        out = self._get_response(url, params=params, headers=headers).json()
        return self._read_lines(out)

    def _read_lines(self, out: list[dict]) -> pd.DataFrame:
        """Parse JSON response into a DataFrame.

        Parameters
        ----------
        out : list of dict
            Parsed JSON response.

        Returns
        -------
        df : DataFrame
        """
        df = pd.DataFrame(out)
        df["symbol"] = self._symbol
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index(["symbol", "date"])
        return df

    def read(self) -> pd.DataFrame:
        """Read data from connector.

        Returns
        -------
        df : DataFrame
        """
        dfs = []
        for symbol in self.symbols:
            self._symbol = symbol
            try:
                dfs.append(self._read_one_data(self.url, self.params))
            finally:
                self.close()
        return pd.concat(dfs, axis=self._concat_axis)


class TiingoDailyReader(_BaseReader):
    """Historical daily data from Tiingo on equities, ETFs and mutual funds."""

    def __init__(
        self,
        symbols: str | list[str],
        start=None,
        end=None,
        retry_count: int = 3,
        pause: float = 0.1,
        timeout: float = 30,
        session=None,
        freq: str | None = None,
        api_key: str | None = None,
    ) -> None:
        """
        Initialize the reader.

        Parameters
        ----------
        symbols : str or list of str
            String symbol or list of symbols.
        start : str, int, date, datetime, or Timestamp, optional
            Starting date. Default is 5 years before current date.
        end : str, int, date, datetime, or Timestamp, optional
            Ending date.
        retry_count : int, default 3
            Number of times to retry query request.
        pause : float, default 0.1
            Time, in seconds, of the pause between retries.
        timeout : float, default 30
            Time, in seconds, to wait for server response.
        session : Session, optional
            ``requests.sessions.Session`` instance to be used.
        freq : str, optional
            Not used.
        api_key : str, optional
            Tiingo API key. If not provided the environmental variable ``TIINGO_API_KEY`` is read.
            The API key is *required*.
        """
        super().__init__(symbols, start, end, retry_count, pause, timeout, session, freq)
        if isinstance(self.symbols, str):
            self.symbols = [self.symbols]
        self._symbol = ""
        if api_key is None:
            api_key = os.getenv("TIINGO_API_KEY")
        if not api_key or not isinstance(api_key, str):
            raise ValueError(
                "The tiingo API key must be provided either "
                "through the api_key variable or through the "
                "environmental variable TIINGO_API_KEY."
            )
        self.api_key = api_key
        self._concat_axis = 0

    @property
    def url(self) -> str:
        """API URL."""
        _url = "https://api.tiingo.com/tiingo/daily/{ticker}/prices"
        return _url.format(ticker=self._symbol)

    @property
    def params(self) -> dict:
        """Parameters to use in API calls."""
        return {
            "startDate": self.start.strftime("%Y-%m-%d"),
            "endDate": self.end.strftime("%Y-%m-%d"),
            "format": "json",
        }

    def _get_crumb(self, *args) -> None:
        """Not used for Tiingo."""
        pass

    def _read_one_data(self, url: str, params: dict | None) -> pd.DataFrame:
        """Read one data from specified URL.

        Parameters
        ----------
        url : str
            Target URL.
        params : dict, optional
            Query parameters.

        Returns
        -------
        df : DataFrame
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Token " + self.api_key,
        }
        out = self._get_response(url, params=params, headers=headers).json()
        return self._read_lines(out)

    def _read_lines(self, out: list[dict]) -> pd.DataFrame:
        """Parse JSON response into a DataFrame.

        Parameters
        ----------
        out : list of dict
            Parsed JSON response.

        Returns
        -------
        df : DataFrame
        """
        df = pd.DataFrame(out)
        df["symbol"] = self._symbol
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index(["symbol", "date"])
        return df

    def read(self) -> pd.DataFrame:
        """Read data from connector.

        Returns
        -------
        df : DataFrame
        """
        dfs = []
        for symbol in self.symbols:
            self._symbol = symbol
            try:
                dfs.append(self._read_one_data(self.url, self.params))
            finally:
                self.close()
        return pd.concat(dfs, axis=self._concat_axis)


class TiingoMetaDataReader(TiingoDailyReader):
    """Read metadata about symbols from Tiingo."""

    def __init__(
        self,
        symbols: str | list[str],
        start=None,
        end=None,
        retry_count: int = 3,
        pause: float = 0.1,
        timeout: float = 30,
        session=None,
        freq: str | None = None,
        api_key: str | None = None,
    ) -> None:
        """
        Initialize the reader.

        Parameters
        ----------
        symbols : str or list of str
            String symbol or list of symbols.
        start : str, int, date, datetime, or Timestamp, optional
            Not used.
        end : str, int, date, datetime, or Timestamp, optional
            Not used.
        retry_count : int, default 3
            Number of times to retry query request.
        pause : float, default 0.1
            Time, in seconds, of the pause between retries.
        timeout : float, default 30
            Time, in seconds, to wait for server response.
        session : Session, optional
            ``requests.sessions.Session`` instance to be used.
        freq : str, optional
            Not used.
        api_key : str, optional
            Tiingo API key. If not provided the environmental variable ``TIINGO_API_KEY`` is read.
            The API key is *required*.
        """
        super().__init__(symbols, start, end, retry_count, pause, timeout, session, freq, api_key)
        self._concat_axis = 1

    @property
    def url(self) -> str:
        """API URL."""
        _url = "https://api.tiingo.com/tiingo/daily/{ticker}"
        return _url.format(ticker=self._symbol)

    @property
    def params(self) -> None:
        """Not used."""
        return None

    def _read_lines(self, out: dict) -> pd.Series:
        """Parse JSON response into a Series.

        Parameters
        ----------
        out : dict
            Parsed JSON response.

        Returns
        -------
        df : Series
        """
        s = pd.Series(out)
        s.name = self._symbol
        return s


class TiingoQuoteReader(TiingoDailyReader):
    """Read quotes (latest prices) from Tiingo."""

    @property
    def params(self) -> None:
        """Not used."""
        return None
