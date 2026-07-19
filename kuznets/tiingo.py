import datetime as dt

import pandas as pd

from kuznets._output import make_frame
from kuznets.base import _BaseReader
from kuznets.config import get_api_key


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


def _records_to_pandas(payload: list, concat_axis: int) -> pd.DataFrame:
    """Replay the per-symbol frame construction and concatenate along ``concat_axis``."""
    frames = []
    for symbol, out in payload:
        df = pd.DataFrame(out)
        df["symbol"] = symbol
        df["date"] = pd.to_datetime(df["date"])
        frames.append(df.set_index(["symbol", "date"]))
    return pd.concat(frames, axis=concat_axis)


def _records_to_tidy(payload: list, output_type: str):
    """One row per record with ``symbol`` first; ISO dates parse in Python so every backend agrees."""
    records = [{"symbol": symbol, **record} for symbol, out in payload for record in out]
    parsed = []
    for record in records:
        try:
            parsed.append(dt.datetime.fromisoformat(record["date"]))
        except (KeyError, TypeError, ValueError):
            parsed = None
            break
    if parsed is not None:
        for record, timestamp in zip(records, parsed, strict=True):
            record["date"] = timestamp
    return make_frame(records, output_type)


class TiingoIEXHistoricalReader(_BaseReader):
    """Historical IEX data from Tiingo on equities, ETFs and mutual funds."""

    def __init__(
        self,
        symbols: str | list[str],
        start=None,
        end=None,
        retry_count: int | None = None,
        pause: float | None = None,
        timeout: float | None = None,
        session=None,
        freq: str | None = None,
        api_key: str | None = None,
        output_type: str = "pandas",
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
        retry_count : int, optional
            Number of times to retry query request. Falls back to the configured default.
        pause : float, optional
            Time, in seconds, of the pause between retries. Falls back to the configured default.
        timeout : float, optional
            Time, in seconds, to wait for server response. Falls back to the configured default.
        session : Session, optional
            ``requests.sessions.Session`` instance to be used.
        freq : str, optional
            Re-sample frequency. Format is ``#`` + ``min`` or ``hour``; e.g. ``"15min"`` or
            ``"4hour"``. Defaults to ``"5min"``. Minimum is ``"1min"``.
        api_key : str, optional
            Tiingo API key. Resolved through :func:`kuznets.config.get_api_key` (argument,
            ``options.api_keys['tiingo']``, ``TIINGO_API_KEY``, then the config file). The API key
            is *required*.
        output_type : str, optional
            Backend of the returned data: 'pandas', 'polars', 'pyarrow' (alias 'arrow'), or 'dask'.
            Backends other than pandas must be installed separately. Default 'pandas'.
        """
        super().__init__(symbols, start, end, retry_count, pause, timeout, session, freq, output_type=output_type)

        if isinstance(self.symbols, str):
            self.symbols = [self.symbols]
        self._symbol = ""
        self.api_key = get_api_key("tiingo", api_key)
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

    def _read_lines(self, out: list[dict]) -> list[dict]:
        """Pass the parsed JSON records through as the payload for the presenters."""
        return out

    def _read_core(self) -> list:
        """Fetch raw records for every requested symbol.

        Returns
        -------
        payload : list of tuple
            One ``(symbol, records)`` pair per requested symbol.
        """
        payload = []
        for symbol in self.symbols:
            self._symbol = symbol
            try:
                payload.append((symbol, self._read_one_data(self.url, self.params)))
            finally:
                self.close()
        return payload

    def _present_pandas(self, payload: list) -> pd.DataFrame:
        """(symbol, date)-indexed frame concatenated across symbols."""
        return _records_to_pandas(payload, self._concat_axis)

    def _present_tidy(self, payload: list):
        """One row per (symbol, date) with plain columns."""
        return _records_to_tidy(payload, self.output_type)


class TiingoDailyReader(_BaseReader):
    """Historical daily data from Tiingo on equities, ETFs and mutual funds."""

    def __init__(
        self,
        symbols: str | list[str],
        start=None,
        end=None,
        retry_count: int | None = None,
        pause: float | None = None,
        timeout: float | None = None,
        session=None,
        freq: str | None = None,
        api_key: str | None = None,
        output_type: str = "pandas",
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
        retry_count : int, optional
            Number of times to retry query request. Falls back to the configured default.
        pause : float, optional
            Time, in seconds, of the pause between retries. Falls back to the configured default.
        timeout : float, optional
            Time, in seconds, to wait for server response. Falls back to the configured default.
        session : Session, optional
            ``requests.sessions.Session`` instance to be used.
        freq : str, optional
            Not used.
        api_key : str, optional
            Tiingo API key. Resolved through :func:`kuznets.config.get_api_key` (argument,
            ``options.api_keys['tiingo']``, ``TIINGO_API_KEY``, then the config file). The API key
            is *required*.
        output_type : str, optional
            Backend of the returned data: 'pandas', 'polars', 'pyarrow' (alias 'arrow'), or 'dask'.
            Backends other than pandas must be installed separately. Default 'pandas'.
        """
        super().__init__(symbols, start, end, retry_count, pause, timeout, session, freq, output_type=output_type)
        if isinstance(self.symbols, str):
            self.symbols = [self.symbols]
        self._symbol = ""
        self.api_key = get_api_key("tiingo", api_key)
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

    def _read_lines(self, out: list[dict]) -> list[dict]:
        """Pass the parsed JSON records through as the payload for the presenters."""
        return out

    def _read_core(self) -> list:
        """Fetch raw records for every requested symbol.

        Returns
        -------
        payload : list of tuple
            One ``(symbol, records)`` pair per requested symbol.
        """
        payload = []
        for symbol in self.symbols:
            self._symbol = symbol
            try:
                payload.append((symbol, self._read_one_data(self.url, self.params)))
            finally:
                self.close()
        return payload

    def _present_pandas(self, payload: list) -> pd.DataFrame:
        """(symbol, date)-indexed frame concatenated across symbols."""
        return _records_to_pandas(payload, self._concat_axis)

    def _present_tidy(self, payload: list):
        """One row per (symbol, date) with plain columns."""
        return _records_to_tidy(payload, self.output_type)


class TiingoMetaDataReader(TiingoDailyReader):
    """Read metadata about symbols from Tiingo."""

    def __init__(
        self,
        symbols: str | list[str],
        start=None,
        end=None,
        retry_count: int | None = None,
        pause: float | None = None,
        timeout: float | None = None,
        session=None,
        freq: str | None = None,
        api_key: str | None = None,
        output_type: str = "pandas",
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
        retry_count : int, optional
            Number of times to retry query request. Falls back to the configured default.
        pause : float, optional
            Time, in seconds, of the pause between retries. Falls back to the configured default.
        timeout : float, optional
            Time, in seconds, to wait for server response. Falls back to the configured default.
        session : Session, optional
            ``requests.sessions.Session`` instance to be used.
        freq : str, optional
            Not used.
        api_key : str, optional
            Tiingo API key. Resolved through :func:`kuznets.config.get_api_key` (argument,
            ``options.api_keys['tiingo']``, ``TIINGO_API_KEY``, then the config file). The API key
            is *required*.
        output_type : str, optional
            Backend of the returned data: 'pandas', 'polars', 'pyarrow' (alias 'arrow'), or 'dask'.
            Backends other than pandas must be installed separately. Default 'pandas'.
        """
        super().__init__(
            symbols, start, end, retry_count, pause, timeout, session, freq, api_key, output_type=output_type
        )
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

    def _read_lines(self, out: dict) -> dict:
        """Pass the parsed metadata mapping through as the payload for the presenters."""
        return out

    def _present_pandas(self, payload: list) -> pd.DataFrame:
        """Metadata fields as rows, one column per symbol."""
        series = []
        for symbol, out in payload:
            s = pd.Series(out)
            s.name = symbol
            series.append(s)
        return pd.concat(series, axis=self._concat_axis)

    def _present_tidy(self, payload: list):
        """One row per symbol with the metadata fields as columns."""
        records = [{"symbol": symbol, **out} for symbol, out in payload]
        return make_frame(records, self.output_type)


class TiingoQuoteReader(TiingoDailyReader):
    """Read quotes (latest prices) from Tiingo."""

    @property
    def params(self) -> None:
        """Not used."""
        return None
