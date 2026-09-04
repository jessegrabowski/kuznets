import requests

from kuznets.io import DataStructure, StructureRef
from kuznets.sdmx import ResolvedDataflow, _SdmxDataflowReader
from kuznets.typing import DateLike, Headers, Symbols

IMF_SDMX = "https://api.imf.org/external/sdmx/2.1"

# The IMTS dimensions, in key order, mapped to the names this reader presents them under.
IMTS_DIMENSIONS = {
    "COUNTRY": "country",
    "INDICATOR": "indicator",
    "COUNTERPART_COUNTRY": "counterpart",
    "FREQUENCY": "frequency",
}

_COLUMNS = IMTS_DIMENSIONS | {"TIME_PERIOD": "period"}


class IMFReader(_SdmxDataflowReader):
    """Read any dataflow from the IMF's SDMX 2.1 service, discovering its shape per request.

    The service publishes over two hundred dataflows -- ``CPI`` for consumer prices, ``MFS_IR`` for
    interest rates, ``QGFS`` for government finance, ``BOP`` for the balance of payments -- and their
    dimensions differ in name, number and order. Name the dataflow and the codes to restrict it to,
    and the reader resolves the rest.

    Data is served under the IMF's terms of use: © International Monetary Fund Copyright, all rights
    reserved, https://www.imf.org/external/terms.htm. The IMF asks that a dataflow be cited by name,
    as at https://data.imf.org.

    Examples
    --------
    >>> IMFReader("CPI", {"COUNTRY": "ZMB", "FREQUENCY": "M"}, start=2020).read()  # doctest: +SKIP
    """

    _SERVICE = IMF_SDMX


class IMTSReader(IMFReader):
    """Bilateral merchandise trade from the IMF's International Trade in Goods dataflow.

    IMTS reports the value of goods traded between a reporting country and each of its partners, and
    is the dataflow formerly published as Direction of Trade Statistics (DOTS). Indicator codes are
    ``XG_FOB_USD`` (exports of goods, FOB), ``MG_FOB_USD`` and ``MG_CIF_USD`` (imports of goods, FOB
    and CIF) and ``TBG_USD`` (trade balance), all in US dollars.

    The counterpart dimension mixes individual partners, identified by ISO 3166-1 alpha-3 code, with
    regional, income and world aggregates whose codes are prefixed ``G``, ``GX`` or ``TX``. Both come
    back, so summing across counterparts double-counts: select the individual partners first, or read
    the world total from the aggregate rather than adding the parts.

    IMTS's shape is fixed here rather than discovered, so a key is built without touching the network
    and a bad country code is rejected on construction. :class:`IMFReader` reads the same dataflow
    with its codes checked against the service's codelists instead.

    The selection is fixed at construction: ``symbols``, ``counterpart``, ``indicator`` and ``freq``
    record what was asked for, and reassigning one does not change what a later read returns.
    """

    symbols: list[str]

    _URL = f"{IMF_SDMX}/data/IMF.STA,IMTS,1.0.0"

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
        """
        if not symbols:
            raise ValueError("IMTSReader requires at least one reporting country")
        if not indicator:
            raise ValueError(
                "IMTSReader requires an explicit indicator; the IMF answers a wildcarded INDICATOR "
                "with a document of metadata and no observations rather than an error"
            )

        countries = _country_codes(symbols, "symbols") or []
        self.counterpart = _country_codes(counterpart, "counterpart")
        self.indicator = [indicator] if isinstance(indicator, str) else list(indicator)
        super().__init__(
            dataflow="IMTS",
            selections={
                "COUNTRY": countries,
                "INDICATOR": self.indicator,
                "COUNTERPART_COUNTRY": self.counterpart,
                "FREQUENCY": freq,
            },
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            timeout=timeout,
            session=session,
            headers=headers,
            output_type=output_type,
        )
        self.symbols = countries
        self.freq = freq

    def _static_structure(self) -> ResolvedDataflow:
        """IMTS's dimensions, which are fixed and so need no structure request."""
        return ResolvedDataflow(
            flow=StructureRef("IMF.STA", "IMTS", "1.0.0"),
            structure_ref=StructureRef("IMF.STA", "DSD_IMTS", "1.0.0"),
            structure=DataStructure(list(IMTS_DIMENSIONS), "TIME_PERIOD", {}),
        )

    def _column_names(self) -> dict[str, str]:
        """Present the dimensions under the names this reader has always used."""
        return dict(_COLUMNS)


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
