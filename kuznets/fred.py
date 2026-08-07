import time

from numpy import nan
from pandas import DataFrame, Series, concat, read_csv, to_datetime
import requests

from kuznets.base import _BaseReader
from kuznets.config import get_api_key
from kuznets.typing import DateLike, Headers, Symbols

FRED_API_URL = "https://api.stlouisfed.org/fred/series/observations"
FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


class FredReader(_BaseReader):
    """Get data for the given name from the St. Louis FED (FRED).

    When an API key is configured (see ``__init__`` for how it is resolved) the official,
    rate-limited JSON API is used. Otherwise the public ``fredgraph.csv`` download endpoint is used,
    which is throttled more aggressively and may fail intermittently under load.
    """

    symbols: Symbols

    def __init__(
        self,
        symbols: Symbols,
        start: DateLike | None = None,
        end: DateLike | None = None,
        retry_count: int | None = None,
        pause: float | None = None,
        timeout: float | None = None,
        session: requests.Session | None = None,
        freq: str | None = None,
        headers: Headers | None = None,
        output_type: str = "pandas",
        api_key: str | None = None,
    ) -> None:
        """Initialize the reader.

        Parameters
        ----------
        symbols : str or list of str
            One or more FRED series IDs.
        start : str, int, date, datetime, or Timestamp, optional
            Starting date.
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
            Frequency to use in select readers.
        headers : dict, optional
            Headers applied to every request, merged over ``options.headers`` and the config file.
        output_type : str, optional
            Backend of the returned data: 'pandas', 'polars', 'pyarrow' (alias 'arrow'), or 'dask'.
            Backends other than pandas must be installed separately. Default 'pandas'.
        api_key : str, optional
            FRED API key. Resolved through :func:`kuznets.config.get_api_key` (argument,
            ``options.api_keys['fred']``, ``FRED_API_KEY``, then the config file). When present, the
            keyed JSON API is queried instead of the public CSV endpoint.
        """
        super().__init__(
            symbols=symbols,
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            timeout=timeout,
            session=session,
            freq=freq,
            headers=headers,
            output_type=output_type,
        )
        self.api_key = get_api_key("fred", api_key, required=False)

    @property
    def url(self) -> str:
        """API URL."""
        return FRED_API_URL if self.api_key else FRED_CSV_URL

    def _read_core(self) -> DataFrame:
        """Fetch all requested series from FRED.

        Returns
        -------
        df : DataFrame
            If multiple series names are passed in ``symbols``, the index is the outer join of the
            individual series indices.
        """
        try:
            names = [self.symbols] if isinstance(self.symbols, str) else list(self.symbols)
            fetch = self._fetch_api if self.api_key else self._fetch_csv

            series = []
            for i, name in enumerate(names):
                if i:
                    # Space out requests so a batch of series doesn't slam FRED.
                    time.sleep(self.pause)
                series.append(fetch(name))

            return concat(series, axis=1, join="outer", sort=True)
        finally:
            self.close()

    def _fetch_csv(self, name: str) -> DataFrame:
        """Fetch a single series from the public ``fredgraph.csv`` endpoint."""
        resp = self._read_url_as_StringIO(f"{self.url}?id={name}")
        data = read_csv(
            resp,
            index_col=0,
            parse_dates=True,
            header=None,
            skiprows=1,
            names=["DATE", name],
            na_values=".",
        )
        try:
            return data.truncate(self.start, self.end)
        except KeyError as exc:  # pragma: no cover
            if str(data.iloc[3].name)[7:12] == "Error":
                raise OSError(f"Failed to get the data. Check that {name!r} is a valid FRED series.") from exc
            raise

    def _fetch_api(self, name: str) -> DataFrame:
        """Fetch a single series from the keyed JSON API."""
        params = {
            "series_id": name,
            "api_key": self.api_key,
            "file_type": "json",
            "observation_start": self.start.strftime("%Y-%m-%d"),
            "observation_end": self.end.strftime("%Y-%m-%d"),
        }
        observations = self._get_response(self.url, params=params).json()["observations"]
        index = to_datetime([obs["date"] for obs in observations])
        index.name = "DATE"
        values = [nan if obs["value"] == "." else float(obs["value"]) for obs in observations]
        return Series(values, index=index, name=name).to_frame()
