from kuznets.sdmx import _SdmxDataflowReader

ILO_SDMX = "https://sdmx.ilo.org/rest"


class ILOSTATReader(_SdmxDataflowReader):
    """Read a dataflow from the ILO's SDMX service, the source for earnings, employment and hours.

    Dataflow identifiers encode the indicator and its breakdowns, so they are looked up rather than
    guessed: ``DF_EAR_CMTA_SEX_CUR_NB`` is mean monthly earnings by sex and currency, and the
    ``DF_EAR_*`` family covers earnings generally. The full list is served at
    https://sdmx.ilo.org/rest/dataflow/ILO.

    Dimensions carry the ILO's own names: ``REF_AREA`` for the country, ``FREQ`` for the frequency.

    Data is served under the ILO's terms, https://www.ilo.org/disclaimer-privacy-policy, and asks to
    be cited as "International Labour Organization. ILOSTAT database, https://ilostat.ilo.org".

    Examples
    --------
    >>> ILOSTATReader(  # doctest: +SKIP
    ...     "DF_EAR_CMTA_SEX_CUR_NB", {"REF_AREA": "ZMB"}, start=2015, end=2019
    ... ).read()
    """

    _SERVICE = ILO_SDMX
