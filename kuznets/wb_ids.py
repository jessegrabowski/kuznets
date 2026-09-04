from xml.etree import ElementTree as ET

from pandas import DataFrame
import requests

from kuznets.base import _BaseReader
from kuznets.io.util import LabelMaps, _pivot_observations, _present_observations
from kuznets.output import filter_date_range
from kuznets.typing import DateLike, Frame, Headers, Symbols
from kuznets.utils import RemoteDataError, _year_bounds
from kuznets.wb import WB_API_URL

IDS_SOURCE = 6

# The creditor every series is also reported against in aggregate. Left unrestricted the service
# answers with one row per creditor, which is nineteen thousand rows for a single country and series.
ALL_CREDITORS = "WLD"

_DIMENSIONS = ("country", "series", "counterpart", "period")

_TIME_POSITION = _DIMENSIONS.index("period")
_NO_LABELS: LabelMaps = [{} for _ in _DIMENSIONS]
_CONCEPTS = {"Country": "country", "Series": "series", "Counterpart-Area": "counterpart", "Time": "period"}

# The service answers a request it cannot serve with an error document rather than a status, and
# does so for a country outside the database exactly as for a code that does not exist.
_ERROR_MESSAGE = ".//{http://www.worldbank.org}message"


class WorldBankIDSReader(_BaseReader):
    """Read external debt terms from the World Bank's International Debt Statistics.

    IDS is a separate database from the World Development Indicators that :class:`WorldBankReader`
    covers, and adds a creditor dimension the WDI has no equivalent for. ``DT.INR.DPPG`` is the average interest rate on new public and publicly guaranteed external debt
    commitments, and ``DT.INR.OFFT`` and ``DT.INR.PRVT`` split the same rate by official and private
    creditor. ``DT.MAT.DPPG`` reports average maturity.

    Series are reported per creditor and in aggregate. The default reads the aggregate, because a
    single country and series across every creditor runs to five figures of rows.

    Data is served under the World Bank's terms of use, https://www.worldbank.org/en/about/legal,
    and asks to be cited as "World Bank. International Debt Statistics".
    """

    symbols: list[str]

    _format = "json"

    def __init__(
        self,
        symbols: Symbols,
        countries: Symbols,
        counterpart: Symbols = ALL_CREDITORS,
        start: DateLike | None = None,
        end: DateLike | None = None,
        retry_count: int | None = None,
        pause: float | None = None,
        timeout: float | None = None,
        session: requests.Session | None = None,
        headers: Headers | None = None,
        output_type: str = "pandas",
    ) -> None:
        """
        Initialize the reader.

        Parameters
        ----------
        symbols : str or list of str
            Series code or codes, e.g. ``'DT.INR.DPPG'``.
        countries : str or list of str
            Borrowing country or countries, as ISO 3166-1 alpha-3 codes.
        counterpart : str or list of str, optional
            Creditor or creditors, by the numeric codes IDS uses for individual lenders. Default
            ``'WLD'``, every creditor in aggregate.
        start : str, int, date, datetime, or Timestamp, optional
            Start of the data series. Only the year is used.
        end : str, int, date, datetime, or Timestamp, optional
            End of the data series, inclusive. Only the year is used.
        retry_count : int, optional
            Number of times to retry query request. Falls back to the configured default.
        pause : float, optional
            Time, in seconds, of the pause between retries. Falls back to the configured default.
        timeout : float, optional
            Time, in seconds, to wait for server response. Falls back to the configured default.
        session : Session, optional
            ``requests.sessions.Session`` instance to be used.
        headers : dict, optional
            Headers applied to every request, merged over ``options.headers`` and the config file.
        output_type : str, optional
            Backend of the returned data: 'pandas', 'polars', 'pyarrow' (alias 'arrow'), or 'dask'.
            Backends other than pandas must be installed separately. Default 'pandas'.
        """
        if not symbols:
            raise ValueError("WorldBankIDSReader requires at least one series")
        if not countries:
            raise ValueError("WorldBankIDSReader requires at least one country")

        super().__init__(
            symbols=_codes(symbols),
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            timeout=timeout,
            session=session,
            headers=headers,
            output_type=output_type,
        )
        self.countries = _codes(countries)
        self.counterpart = _codes(counterpart)

    @property
    def url(self) -> str:
        """API URL selecting the requested country, series and creditor."""
        return (
            f"{WB_API_URL}/sources/{IDS_SOURCE}"
            f"/country/{';'.join(self.countries)}"
            f"/series/{';'.join(self.symbols)}"
            f"/counterpart-area/{';'.join(self.counterpart)}"
            "/time/all/data"
        )

    @property
    def params(self) -> dict:
        """Query parameters requesting JSON a page at a time."""
        return {"format": "json", "per_page": 10000}

    def _read_core(self) -> list[dict]:
        """Follow the paging to the end, so a caller never silently receives the first page."""
        try:
            rows: list[dict] = []
            page = 1
            while True:
                payload = self._read_page(page)
                rows.extend(payload["source"]["data"])
                if page >= payload["pages"]:
                    return rows
                page += 1
        finally:
            self.close()

    def _read_page(self, page: int) -> dict:
        """Fetch one page, refusing the error document the service returns under HTTP 200."""
        response = self._get_response(self.url, params=self.params | {"page": page})
        if response.text.lstrip().startswith("<"):
            raise RemoteDataError(f"{_error_text(response.text)} Requested: {self.url}")
        return response.json()

    def _present_pandas(self, payload: list[dict]) -> DataFrame:
        """Pivot the observations into the wide time-indexed frame, truncated to the range."""
        frame = _pivot_observations(_records(payload), list(_DIMENSIONS), _NO_LABELS, _TIME_POSITION)
        return frame.truncate(*_year_bounds(self.start, self.end))

    def _present_tidy(self, payload: list[dict]) -> Frame:
        """Build the long native frame and filter it to the requested range."""
        frame = _present_observations(
            _records(payload), list(_DIMENSIONS), _NO_LABELS, _TIME_POSITION, self.output_type
        )
        start, end = _year_bounds(self.start, self.end)
        return filter_date_range(frame, "period", start, end)


def _codes(value: Symbols) -> list[str]:
    """Normalize a selection to the list of upper-case codes it names."""
    codes = [value] if isinstance(value, str) else list(value)
    return [str(code).upper() for code in codes]


def _records(rows: list[dict]) -> list[tuple[tuple[str, ...], float]]:
    """Turn the service's concept/variable rows into the observations the presenters take.

    A row carries its dimensions as a list of named concepts rather than as fields, and reports a
    year as ``'YR1970'``. Rows without a value are dropped, as they are for every other reader.
    """
    records = []
    for row in rows:
        if row.get("value") is None:
            continue
        coded = {_CONCEPTS[entry["concept"]]: entry["id"] for entry in row["variable"] if entry["concept"] in _CONCEPTS}
        coded["period"] = coded["period"].removeprefix("YR")
        records.append((tuple(coded[dimension] for dimension in _DIMENSIONS), float(row["value"])))
    return records


def _error_text(body: str) -> str:
    """Read the message out of the error document the service answers a bad request with."""
    try:
        message = ET.fromstring(body).find(_ERROR_MESSAGE)
    except ET.ParseError:
        return "The World Bank returned an unreadable response."
    return (message.text or "").strip() if message is not None else "The World Bank returned an error."
