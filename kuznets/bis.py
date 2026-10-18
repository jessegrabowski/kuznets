import requests

from kuznets.sdmx import _SdmxDataflowReader

BIS_SDMX = "https://stats.bis.org/api/v1"


class BISReader(_SdmxDataflowReader):
    """Read a dataflow from the BIS SDMX service, the source for effective exchange rates and policy rates.

    Dataflows are named ``WS_*``: ``WS_EER`` for effective exchange rates, ``WS_CBPOL`` for central
    bank policy rates, ``WS_XRU`` for US dollar exchange rates, ``WS_SPP`` for residential property
    prices and ``WS_TC`` for total credit. The full list is served at
    https://stats.bis.org/api/v1/dataflow/BIS.

    Dimensions carry the BIS's own names, and countries take ISO 3166-1 alpha-2 codes under
    ``REF_AREA``. ``WS_EER``, for instance, is keyed by ``FREQ``, ``EER_TYPE`` (``'R'`` real,
    ``'N'`` nominal), ``EER_BASKET`` (``'B'`` broad, ``'N'`` narrow) and ``REF_AREA``.

    Data is served under the BIS's terms of use for statistics,
    https://www.bis.org/about/legal/permitted-use-statistics.

    Examples
    --------
    >>> BISReader(  # doctest: +SKIP
    ...     "WS_EER", {"FREQ": "M", "EER_TYPE": "R", "EER_BASKET": "B", "REF_AREA": "IN"}, start=2011
    ... ).read()
    """

    _SERVICE = BIS_SDMX

    # The BIS answers the format parameter with HTTP 406, and serves structure-specific data without it.
    _FORMAT = None

    def _output_error(self, out: requests.Response) -> None:
        """Explain an empty selection, which the BIS answers with HTTP 404 instead of an empty document."""
        if out.status_code == requests.codes.not_found and "No data for data query" in out.text:
            raise self._no_observations_error()
