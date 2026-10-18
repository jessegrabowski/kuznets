from itertools import batched
import time

from numpy import nan
from pandas import DataFrame, Timestamp
import requests

from kuznets.base import _BaseReader
from kuznets.config import get_api_key
from kuznets.typing import DateLike, Headers, Symbols
from kuznets.utils import RemoteDataError, _year_bounds

BLS_API_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"

# Per-request limits. The API truncates a longer range or series list and reports it only in the
# response's messages, so requests are split to stay within them.
_YEARS_PER_REQUEST = {False: 10, True: 20}
_SERIES_PER_REQUEST = {False: 25, True: 50}

# The month each period code starts on: months, quarters, half-years and years.
_PERIOD_START_MONTHS = {f"M{month:02d}": month for month in range(1, 13)} | {
    "Q01": 1,
    "Q02": 4,
    "Q03": 7,
    "Q04": 10,
    "S01": 1,
    "S02": 7,
    "A01": 1,
}

# Annual averages that monthly, quarterly and semiannual series append to each year.
_ANNUAL_AVERAGES = frozenset({"M13", "Q05", "S03"})


class BLSReader(_BaseReader):
    """Read time series from the Bureau of Labor Statistics public API, v2.

    Series are named by their BLS identifier, e.g. ``'LES1252881600'`` for median usual weekly
    earnings or ``'CUUR0000SA0'`` for the CPI-U. Without a registration key the API serves 25
    series and 10 years per request and 25 requests a day. A key raises that to 50 series, 20
    years and 500 requests, and is free at https://data.bls.gov/registrationEngine/.

    Each observation is stamped at the start of its period: the month, the quarter, the half-year
    or the year. Annual averages are left out.
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
        headers: Headers | None = None,
        output_type: str = "pandas",
        api_key: str | None = None,
    ) -> None:
        """Initialize the reader.

        Parameters
        ----------
        symbols : str or list of str
            One or more BLS series IDs.
        start : str, int, date, datetime, or Timestamp, optional
            Start of the data series. Only the year is used.
        end : str, int, date, datetime, or Timestamp, optional
            End of the data series, inclusive. Only the year is used.
        retry_count : int, optional
            Number of times to retry query request. Falls back to the configured default.
        pause : float, optional
            Time, in seconds, of the pause between retries and between requests. Falls back to the
            configured default.
        timeout : float, optional
            Time, in seconds, to wait for server response. Falls back to the configured default.
        session : Session, optional
            ``requests.sessions.Session`` instance to be used.
        headers : dict, optional
            Headers applied to every request, merged over ``options.headers`` and the config file.
        output_type : str, optional
            Backend of the returned data: 'pandas', 'polars', 'pyarrow' (alias 'arrow'), or 'dask'.
            Backends other than pandas must be installed separately. Default 'pandas'.
        api_key : str, optional
            BLS registration key. Resolved through :func:`kuznets.config.get_api_key` (argument,
            ``options.api_keys['bls']``, ``BLS_API_KEY``, then the config file). Optional, and
            raises the per-request limits when present.
        """
        super().__init__(
            symbols=symbols,
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            timeout=timeout,
            session=session,
            headers=headers,
            output_type=output_type,
        )
        self.api_key = get_api_key("bls", api_key, required=False)

    @property
    def url(self) -> str:
        """API URL."""
        return BLS_API_URL

    def _read_core(self) -> DataFrame:
        """Fetch every requested series, one request per batch of series and span of years."""
        try:
            names = [self.symbols] if isinstance(self.symbols, str) else list(self.symbols)
            observations: dict[str, dict[Timestamp, float]] = {name: {} for name in names}

            for i, payload in enumerate(self._payloads(names)):
                if i:
                    # Space out requests so a long range doesn't slam the API.
                    time.sleep(self.pause)
                for series in self._post_payload(payload):
                    observations[series["seriesID"]].update(_parse_observations(series["data"]))
        finally:
            self.close()

        empty = [name for name, values in observations.items() if not values]
        if empty:
            raise RemoteDataError(
                f"BLS returned no observations for {', '.join(empty)} over "
                f"{self.start.year}-{self.end.year}; check that each is a valid series ID"
            )

        df = DataFrame(observations).sort_index()
        df.index.name = "DATE"
        return df.truncate(*_year_bounds(self.start, self.end))

    def _payloads(self, names: list[str]) -> list[dict]:
        """Split the request into payloads within the per-request series and year limits."""
        keyed = self.api_key is not None
        years = range(self.start.year, self.end.year + 1)
        spans = [(span[0], span[-1]) for span in batched(years, _YEARS_PER_REQUEST[keyed])]

        payloads = []
        for batch in batched(names, _SERIES_PER_REQUEST[keyed]):
            for first, last in spans:
                payload: dict = {"seriesid": list(batch), "startyear": str(first), "endyear": str(last)}
                if keyed:
                    payload["registrationkey"] = self.api_key
                payloads.append(payload)
        return payloads

    def _post_payload(self, payload: dict) -> list[dict]:
        """Send one payload, returning its series or raising with the API's own explanation."""
        body = self._post_response(self.url, payload).json()
        if body.get("status") != "REQUEST_SUCCEEDED":
            message = " ".join(body.get("message", []))
            # The API quotes a rejected key back in full, and the message ends up in tracebacks and logs.
            if self.api_key:
                message = message.replace(self.api_key, "<redacted>")
            raise RemoteDataError(f"BLS refused the request: {message}")
        return body["Results"]["series"]


def _parse_observations(rows: list[dict]) -> dict[Timestamp, float]:
    """Map each observation's period start to its value, leaving out annual averages."""
    return {
        _period_start(row["year"], row["period"]): _value(row["value"])
        for row in rows
        if row["period"] not in _ANNUAL_AVERAGES
    }


def _period_start(year: str, period: str) -> Timestamp:
    """Convert a BLS year and period code, e.g. ``'2024'`` and ``'Q03'``, to the period's start."""
    month = _PERIOD_START_MONTHS.get(period)
    if month is None:
        raise ValueError(f"unrecognized BLS period code {period!r}")
    return Timestamp(year=int(year), month=month, day=1)


def _value(value: str) -> float:
    """Read an observation's value, which the API writes as ``'-'`` when it is missing."""
    try:
        return float(value)
    except ValueError:
        return nan
