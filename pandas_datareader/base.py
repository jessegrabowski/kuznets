from collections.abc import Generator
import datetime
from io import StringIO
from urllib.parse import urlencode
import warnings

import numpy as np
from pandas import DataFrame, Timestamp, concat, read_csv
import requests

from pandas_datareader._utils import (
    RemoteDataError,
    SymbolWarning,
    _init_session,
    _sanitize_dates,
)


class _BaseReader:
    """Base class for all data readers."""

    _chunk_size = 1024 * 1024
    _format = "string"

    def __init__(
        self,
        symbols: str | list[str],
        start: str | int | datetime.date | datetime.datetime | Timestamp | None = None,
        end: str | int | datetime.date | datetime.datetime | Timestamp | None = None,
        retry_count: int = 3,
        pause: float = 0.1,
        timeout: float = 30,
        session: requests.Session | None = None,
        freq: str | None = None,
        headers: dict | None = None,
    ) -> None:
        """
        Initialize the reader.

        Parameters
        ----------
        symbols : str or list of str
            String symbol or list of symbols.
        start : str, int, date, datetime, or Timestamp, optional
            Starting date. Parses many different kind of date representations (e.g.,
            ``'JAN-01-2010'``, ``'1/1/10'``, ``'Jan, 1, 1980'``).
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
            Frequency to use in select readers.
        headers : dict, optional
            Headers applied to every request, overriding the defaults. Pass a ``User-Agent`` here to
            identify as something other than ``pandas-datareader`` when a host blocks the default
            agent.
        """
        self.symbols = symbols

        start, end = _sanitize_dates(start or self.default_start_date, end)
        self.start = start
        self.end = end

        if not isinstance(retry_count, int) or retry_count < 0:
            raise ValueError("'retry_count' must be integer larger than 0")
        self.retry_count = retry_count
        self.pause = pause
        self.timeout = timeout
        self.session = _init_session(session, retry_count, pause, headers)
        self.freq = freq
        self.headers = None

    def close(self) -> None:
        """Close network session."""
        self.session.close()

    @property
    def default_start_date(self) -> datetime.date:
        """Default start date for reader. Defaults to 5 years before current date."""
        today = datetime.date.today()
        return today - datetime.timedelta(days=365 * 5)

    @property
    def url(self) -> str:
        """API URL. Must be overridden in subclass."""
        # must be overridden in subclass
        raise NotImplementedError

    @property
    def params(self) -> dict | None:
        """Parameters to use in API calls."""
        return None

    def read(self) -> DataFrame:
        """Read data from connector.

        Returns
        -------
        df : DataFrame
            Data retrieved from the remote source.
        """
        try:
            return self._read_one_data(self.url, self.params)
        finally:
            self.close()

    def _read_one_data(self, url: str, params: dict | None) -> DataFrame:
        """Read one data from specified URL.

        Parameters
        ----------
        url : str
            Target URL.
        params : dict, optional
            Parameters passed to the URL.

        Returns
        -------
        df : DataFrame
            Parsed data.
        """
        if self._format == "string":
            out = self._read_url_as_StringIO(url, params=params)
        elif self._format == "json":
            out = self._get_response(url, params=params).json()
        else:
            raise NotImplementedError(self._format)
        return self._read_lines(out)

    def _read_url_as_StringIO(self, url: str, params: dict | None = None) -> StringIO:
        """Open URL and return contents as StringIO (retries on failure).

        Parameters
        ----------
        url : str
            Target URL.
        params : dict, optional
            Parameters passed to the URL.

        Returns
        -------
        out : StringIO
            Response body ready for parsing.
        """
        response = self._get_response(url, params=params)
        text = self._sanitize_response(response)
        out = StringIO()
        if len(text) == 0:
            service = self.__class__.__name__
            raise OSError(f"{service} request returned no data; check URL for invalid inputs: {self.url}")
        if isinstance(text, bytes):
            out.write(text.decode("utf-8"))
        else:
            out.write(text)
        out.seek(0)
        return out

    @staticmethod
    def _sanitize_response(response: requests.Response) -> str | bytes:
        """Hook to allow subclasses to clean up response data.

        Parameters
        ----------
        response : Response
            The raw response from an HTTP request.

        Returns
        -------
        content : str or bytes
            Cleaned response body.
        """
        return response.content

    def _get_response(
        self,
        url: str,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> requests.Response:
        """Send raw HTTP request to get requests.Response from the
        specified URL.

        Parameters
        ----------
        url : str
            Target URL.
        params : dict, optional
            Parameters passed to the URL.
        headers : dict, optional
            Headers passed to the request.

        Returns
        -------
        response : Response
            Server response.

        Raises
        ------
        RemoteDataError
            If the request fails after all retries.
        """
        headers = headers or self.headers
        # The session's Retry adapter handles retry counting, backoff, and Retry-After; a non-ok
        # status here means urllib3 already exhausted its retries (or the status isn't retryable).
        response = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
        if response.status_code == requests.codes.ok:
            return response

        # Let a subclass surface a response-specific error (e.g. an error payload) before falling
        # back to a generic one.
        self._output_error(response)

        if params is not None and len(params) > 0:
            url = url + "?" + urlencode(params)
        msg = f"Unable to read URL: {url}"
        if response.encoding:
            msg += f"\nResponse Text:\n{response.text.encode(response.encoding)}"

        raise RemoteDataError(msg)

    def _output_error(self, out: requests.Response) -> None:
        """Inspect a non-ok response and raise a source-specific error if recognized.

        The base implementation does nothing; subclasses override to translate an error payload
        into a meaningful exception.

        Parameters
        ----------
        out : Response
            The raw output from a failed HTTP request.
        """

    def _read_lines(self, out: StringIO) -> DataFrame:
        """Parse CSV content from a StringIO into a DataFrame.

        Parameters
        ----------
        out : StringIO
            CSV content.

        Returns
        -------
        rs : DataFrame
            Parsed tabular data.
        """
        rs = read_csv(out, index_col=0, parse_dates=True, na_values=("-", "null"))[::-1]
        # Needed to remove blank space character in header names
        rs.columns = [x.strip() for x in rs.columns.values.tolist()]

        # Yahoo! Finance sometimes does this awesome thing where they
        # return 2 rows for the most recent business day
        if len(rs) > 2 and rs.index[-1] == rs.index[-2]:  # pragma: no cover
            rs = rs[:-1]
        # Get rid of unicode characters in index name.
        try:
            rs.index.name = rs.index.name.decode("unicode_escape").encode("ascii", "ignore")
        except AttributeError:
            # Python 3 string has no decode method.
            rs.index.name = rs.index.name.encode("ascii", "ignore").decode()

        return rs


class _DailyBaseReader(_BaseReader):
    """Base class for daily-frequency readers."""

    def __init__(
        self,
        symbols: str | list[str] | DataFrame | None = None,
        start: str | int | datetime.date | datetime.datetime | Timestamp | None = None,
        end: str | int | datetime.date | datetime.datetime | Timestamp | None = None,
        retry_count: int = 3,
        pause: float = 0.1,
        session: requests.Session | None = None,
        chunksize: int = 25,
    ) -> None:
        """
        Initialize the daily reader.

        Parameters
        ----------
        symbols : str, list of str, or DataFrame, optional
            String symbol, list of symbols, or DataFrame with index containing stock symbols.
        start : str, int, date, datetime, or Timestamp, optional
            Starting date.
        end : str, int, date, datetime, or Timestamp, optional
            Ending date.
        retry_count : int, default 3
            Number of times to retry query request.
        pause : float, default 0.1
            Time, in seconds, of the pause between retries.
        session : Session, optional
            ``requests.sessions.Session`` instance to be used.
        chunksize : int, default 25
            Number of symbols to download consecutively before initiating pause.
        """
        super().__init__(
            symbols=symbols,
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
        )
        self.chunksize = chunksize

    def _get_params(self, *args, **kwargs) -> dict:
        """Return parameters for an API call. Must be overridden in subclass."""
        raise NotImplementedError

    def read(self) -> DataFrame:
        """Read data for one or more symbols.

        Returns
        -------
        df : DataFrame
            Price or volume data for the requested symbols.
        """
        # If a single symbol, (e.g., 'GOOG')
        if isinstance(self.symbols, str | int):
            df = self._read_one_data(self.url, params=self._get_params(self.symbols))
        # Or multiple symbols, (e.g., ['GOOG', 'AAPL', 'MSFT'])
        elif isinstance(self.symbols, DataFrame):
            df = self._dl_mult_symbols(self.symbols.index)
        else:
            df = self._dl_mult_symbols(self.symbols)
        return df

    def _dl_mult_symbols(self, symbols: list[str]) -> DataFrame:
        """Download data for multiple symbols.

        Parameters
        ----------
        symbols : list of str
            List of ticker symbols.

        Returns
        -------
        result : DataFrame
            Combined data for all symbols.

        Raises
        ------
        RemoteDataError
            If no data is fetched for any symbol.
        """
        stocks = {}
        failed = []
        passed = []
        for sym_group in _in_chunks(symbols, self.chunksize):
            for sym in sym_group:
                try:
                    stocks[sym] = self._read_one_data(self.url, self._get_params(sym))
                    passed.append(sym)
                except (OSError, KeyError):
                    msg = "Failed to read symbol: {0!r}, replacing with NaN."
                    warnings.warn(msg.format(sym), SymbolWarning, stacklevel=2)
                    failed.append(sym)

        if len(passed) == 0:
            msg = "No data fetched using {0!r}"
            raise RemoteDataError(msg.format(self.__class__.__name__))
        try:
            if len(stocks) > 0 and len(failed) > 0 and len(passed) > 0:
                df_na = stocks[passed[0]].copy()
                df_na[:] = np.nan
                for sym in failed:
                    stocks[sym] = df_na
                result = concat(stocks, sort=True).unstack(level=0)
                result.columns.names = ["Attributes", "Symbols"]
            return result
        except AttributeError as exc:
            # cannot construct a panel with just 1D nans indicating no data
            msg = "No data fetched using {0!r}"
            raise RemoteDataError(msg.format(self.__class__.__name__)) from exc


def _in_chunks(seq, size: int) -> Generator:
    """
    Return sequence in 'chunks' of size defined by *size*.

    Parameters
    ----------
    seq : sequence
        Input sequence.
    size : int
        Chunk size.

    Yields
    ------
    sequence
        A slice of *seq* of length *size* (or less for the final chunk).
    """
    return (seq[pos : pos + size] for pos in range(0, len(seq), size))


class _OptionBaseReader(_BaseReader):
    """Base class for options data readers."""

    def __init__(self, symbol: str, session: requests.Session | None = None) -> None:
        """
        Instantiate options reader with a ticker saved as *symbol*.

        Parameters
        ----------
        symbol : str
            Ticker symbol (will be upper-cased).
        session : Session, optional
            ``requests.sessions.Session`` instance to be used.
        """
        self.symbol = symbol.upper()
        super().__init__(symbols=symbol, session=session)

    def get_options_data(
        self,
        month: int | None = None,
        year: int | None = None,
        expiry: datetime.date | None = None,
    ) -> DataFrame:
        """
        Get call and put data for the given expiry.

        Parameters
        ----------
        month : int, optional
            Expiry month.
        year : int, optional
            Expiry year.
        expiry : date, optional
            Exact expiry date.

        Returns
        -------
        df : DataFrame
            Options data.
        """
        raise NotImplementedError

    def get_call_data(
        self,
        month: int | None = None,
        year: int | None = None,
        expiry: datetime.date | None = None,
    ) -> DataFrame:
        """
        Get call data for the given expiry.

        Parameters
        ----------
        month : int, optional
            Expiry month.
        year : int, optional
            Expiry year.
        expiry : date, optional
            Exact expiry date.

        Returns
        -------
        df : DataFrame
            Call options data.
        """
        raise NotImplementedError

    def get_put_data(
        self,
        month: int | None = None,
        year: int | None = None,
        expiry: datetime.date | None = None,
    ) -> DataFrame:
        """
        Get put data for the given expiry.

        Parameters
        ----------
        month : int, optional
            Expiry month.
        year : int, optional
            Expiry year.
        expiry : date, optional
            Exact expiry date.

        Returns
        -------
        df : DataFrame
            Put options data.
        """
        raise NotImplementedError

    def get_near_stock_price(
        self,
        above_below: int = 2,
        call: bool = True,
        put: bool = False,
        month: int | None = None,
        year: int | None = None,
        expiry: datetime.date | None = None,
    ) -> DataFrame:
        """
        Get options data near the current stock price.

        Parameters
        ----------
        above_below : int, default 2
            Number of strike prices above and below the current stock price.
        call : bool, default True
            Include call data.
        put : bool, default False
            Include put data.
        month : int, optional
            Expiry month.
        year : int, optional
            Expiry year.
        expiry : date, optional
            Exact expiry date.

        Returns
        -------
        df : DataFrame
            Nearby options data.
        """
        raise NotImplementedError

    def get_forward_data(
        self,
        months: int,
        call: bool = True,
        put: bool = False,
        near: bool = False,
        above_below: int = 2,
    ) -> DataFrame:  # pragma: no cover
        """
        Get call/put data for future months.

        Parameters
        ----------
        months : int
            Number of months forward.
        call : bool, default True
            Include call data.
        put : bool, default False
            Include put data.
        near : bool, default False
            Only include options near the current stock price.
        above_below : int, default 2
            Number of strike prices above and below the current stock price.

        Returns
        -------
        df : DataFrame
            Forward options data.
        """
        raise NotImplementedError

    def get_all_data(self, call: bool = True, put: bool = True) -> DataFrame:
        """
        Get call and/or put data for all available expiry months.

        Parameters
        ----------
        call : bool, default True
            Include call data.
        put : bool, default True
            Include put data.

        Returns
        -------
        df : DataFrame
            All available options data.
        """
        raise NotImplementedError
