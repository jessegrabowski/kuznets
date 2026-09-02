from pandas import DataFrame, DatetimeIndex
import requests

from kuznets.base import _BaseReader
from kuznets.io import build_sdmx_key, read_structure_specific
from kuznets.output import PANDAS, filter_date_range, is_empty
from kuznets.typing import DateLike, Headers, Symbols
from kuznets.utils import RemoteDataError, _year_bounds

# The dataflow's dimensions, in key order, mapped to the names this reader presents them under.
IMTS_DIMENSIONS = {
    "COUNTRY": "country",
    "INDICATOR": "indicator",
    "COUNTERPART_COUNTRY": "counterpart",
    "FREQUENCY": "frequency",
}

_COLUMNS = IMTS_DIMENSIONS | {"TIME_PERIOD": "period"}


class IMTSReader(_BaseReader):
    """Bilateral merchandise trade from the IMF's International Trade in Goods dataflow.

    IMTS reports the value of goods traded between a reporting country and each of its partners, and
    is the dataflow formerly published as Direction of Trade Statistics (DOTS). Indicator codes are
    ``XG_FOB_USD`` (exports of goods, FOB), ``MG_FOB_USD`` and ``MG_CIF_USD`` (imports of goods, FOB
    and CIF) and ``TBG_USD`` (trade balance), all in US dollars.

    The counterpart dimension mixes individual partners, identified by ISO 3166-1 alpha-3 code, with
    regional, income and world aggregates whose codes are prefixed ``G``, ``GX`` or ``TX``. Both come
    back, so summing across counterparts double-counts: select the individual partners first, or read
    the world total from the aggregate rather than adding the parts.

    Data is served under the IMF's terms of use: © International Monetary Fund Copyright, all rights
    reserved, https://www.imf.org/external/terms.htm. The IMF asks that it be cited as
    "International Monetary Fund. International Trade in Goods (by partner country),
    https://data.imf.org/en/datasets/IMF.STA:IMTS".
    """

    symbols: list[str]

    _URL = "https://api.imf.org/external/sdmx/2.1/data/IMF.STA,IMTS,1.0.0"

    def __init__(
        self,
        symbols: Symbols,
        counterpart: Symbols | None = None,
        indicator: Symbols = "XG_FOB_USD",
        freq: str = "A",
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
            Reporting country or countries, as ISO 3166-1 alpha-3 codes (e.g. ``'LAO'``).
        counterpart : str or list of str, optional
            Partner country or countries. Individual partners take alpha-3 codes; the aggregates take
            their own codes, such as ``'G001'`` for the world. Default None, every partner the IMF
            reports.
        indicator : str or list of str, optional
            Indicator code or codes. Default ``'XG_FOB_USD'``, exports of goods FOB in US dollars.
        freq : str, optional
            Frequency of the series: ``'A'``, ``'Q'`` or ``'M'``. Default ``'A'``.
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

        Raises
        ------
        ValueError
            If no reporting country or no indicator is given, or if a country code is too short to be
            an alpha-3 code.
        """
        if not symbols:
            raise ValueError("IMTSReader requires at least one reporting country")
        if not indicator:
            raise ValueError(
                "IMTSReader requires an explicit indicator; the IMF answers a wildcarded INDICATOR "
                "with a document of metadata and no observations rather than an error"
            )

        super().__init__(
            symbols=_country_codes(symbols, "symbols"),
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
        self.counterpart = _country_codes(counterpart, "counterpart")
        self.indicator = [indicator] if isinstance(indicator, str) else list(indicator)

    @property
    def key(self) -> str:
        """The SDMX key selecting the requested series, e.g. ``'LAO.XG_FOB_USD..A'``."""
        selections: dict[str, Symbols | None] = {
            "COUNTRY": self.symbols,
            "INDICATOR": self.indicator,
            "COUNTERPART_COUNTRY": self.counterpart,
            "FREQUENCY": self.freq,
        }
        return build_sdmx_key(selections[dimension] for dimension in IMTS_DIMENSIONS)

    @property
    def url(self) -> str:
        """API URL."""
        return f"{self._URL}/{self.key}"

    @property
    def params(self) -> dict:
        """Query parameters bounding the request to the requested year range."""
        return {"startPeriod": self.start.year, "endPeriod": self.end.year}

    def _read_lines(self, out) -> str:
        """Pass the XML response body through as the payload for the presenters."""
        return out.read()

    def _present_pandas(self, payload: str) -> DataFrame:
        """Pivot the observations into the wide time-indexed frame, truncated to the range."""
        df = self._frame(payload, PANDAS)
        if isinstance(df.index, DatetimeIndex):
            df = df.truncate(*_year_bounds(self.start, self.end))
        return df

    def _present_tidy(self, payload: str):
        """Build the long native frame and filter it to the requested range."""
        start, end = _year_bounds(self.start, self.end)
        return filter_date_range(self._frame(payload, self.output_type), "period", start, end)

    def _frame(self, payload: str, output_type: str):
        """Read the payload into a frame, refusing to hand back an empty one.

        The IMF answers a malformed key with a well-formed document carrying no observations, so an
        empty result is far more often a bad key than a country with no recorded trade.
        """
        frame = read_structure_specific(payload, _COLUMNS, output_type)
        if is_empty(frame):
            raise RemoteDataError(
                f"IMTS returned no observations for key {self.key!r} over {self.start.year}-{self.end.year}. "
                "Check the country codes are ISO 3166-1 alpha-3 and the indicator is spelled correctly, "
                "or widen the date range."
            )
        return frame


def _country_codes(value: Symbols | None, argument: str) -> list[str] | None:
    """Normalize a country selection to upper-case codes, raising on the alpha-2 codes the API ignores."""
    if value is None:
        return None
    codes = [value] if isinstance(value, str) else [str(code) for code in value]
    for code in codes:
        if len(code) < 3:
            raise ValueError(
                f"{argument} takes ISO 3166-1 alpha-3 codes; {code!r} is too short. The IMF answers an "
                "alpha-2 code with an empty document rather than an error, so it is rejected here."
            )
    return [code.upper() for code in codes]
