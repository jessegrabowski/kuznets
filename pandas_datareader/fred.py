import time

from numpy import nan
from pandas import DataFrame, Series, concat, read_csv, to_datetime

from pandas_datareader.base import _BaseReader
from pandas_datareader.compat import is_list_like
from pandas_datareader.config import get_api_key

FRED_API_URL = "https://api.stlouisfed.org/fred/series/observations"
FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


class FredReader(_BaseReader):
    """Get data for the given name from the St. Louis FED (FRED).

    When an API key is configured (see ``__init__`` for how it is resolved) the official,
    rate-limited JSON API is used. Otherwise the public ``fredgraph.csv`` download endpoint is used,
    which is throttled more aggressively and may fail intermittently under load.
    """

    def __init__(self, *args, api_key: str | None = None, **kwargs) -> None:
        """Initialize the reader.

        Parameters
        ----------
        api_key : str, optional
            FRED API key. Resolved through :func:`pandas_datareader.config.get_api_key` (argument,
            ``options.api_keys['fred']``, ``FRED_API_KEY``, then the config file). When present, the
            keyed JSON API is queried instead of the public CSV endpoint.

        Notes
        -----
        See :class:`pandas_datareader.base._BaseReader` for the remaining parameters.
        """
        super().__init__(*args, **kwargs)
        self.api_key = get_api_key("fred", api_key, required=False)

    @property
    def url(self) -> str:
        """API URL."""
        return FRED_API_URL if self.api_key else FRED_CSV_URL

    def read(self) -> DataFrame:
        """Read data from FRED.

        Returns
        -------
        df : DataFrame
            If multiple names are passed for "series" then the index of the DataFrame is the outer
            join of the indices of each series.
        """
        try:
            return self._read()
        finally:
            self.close()

    def _read(self) -> DataFrame:
        names = self.symbols if is_list_like(self.symbols) else [self.symbols]
        fetch = self._fetch_api if self.api_key else self._fetch_csv

        series = []
        for i, name in enumerate(names):
            if i:
                # Space out requests so a batch of series doesn't slam FRED.
                time.sleep(self.pause)
            series.append(fetch(name))

        return concat(series, axis=1, join="outer", sort=True)

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
            if data.iloc[3].name[7:12] == "Error":
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
