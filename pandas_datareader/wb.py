from functools import reduce
import warnings

import numpy as np
import pandas as pd

from pandas_datareader.base import _BaseReader

# This list of country codes was pulled from wikipedia during October 2014.
# While some exceptions do exist, it is the best proxy for countries supported
# by World Bank.  It is an aggregation of the 2-digit ISO 3166-1 alpha-2, and
# 3-digit ISO 3166-1 alpha-3, codes, with 'all', 'ALL', and 'All' appended ot
# the end.

WB_API_URL = "https://api.worldbank.org/v2"

country_codes = [
    "AD",
    "AE",
    "AF",
    "AG",
    "AI",
    "AL",
    "AM",
    "AO",
    "AQ",
    "AR",
    "AS",
    "AT",
    "AU",
    "AW",
    "AX",
    "AZ",
    "BA",
    "BB",
    "BD",
    "BE",
    "BF",
    "BG",
    "BH",
    "BI",
    "BJ",
    "BL",
    "BM",
    "BN",
    "BO",
    "BQ",
    "BR",
    "BS",
    "BT",
    "BV",
    "BW",
    "BY",
    "BZ",
    "CA",
    "CC",
    "CD",
    "CF",
    "CG",
    "CH",
    "CI",
    "CK",
    "CL",
    "CM",
    "CN",
    "CO",
    "CR",
    "CU",
    "CV",
    "CW",
    "CX",
    "CY",
    "CZ",
    "DE",
    "DJ",
    "DK",
    "DM",
    "DO",
    "DZ",
    "EC",
    "EE",
    "EG",
    "EH",
    "ER",
    "ES",
    "ET",
    "FI",
    "FJ",
    "FK",
    "FM",
    "FO",
    "FR",
    "GA",
    "GB",
    "GD",
    "GE",
    "GF",
    "GG",
    "GH",
    "GI",
    "GL",
    "GM",
    "GN",
    "GP",
    "GQ",
    "GR",
    "GS",
    "GT",
    "GU",
    "GW",
    "GY",
    "HK",
    "HM",
    "HN",
    "HR",
    "HT",
    "HU",
    "ID",
    "IE",
    "IL",
    "IM",
    "IN",
    "IO",
    "IQ",
    "IR",
    "IS",
    "IT",
    "JE",
    "JM",
    "JO",
    "JP",
    "KE",
    "KG",
    "KH",
    "KI",
    "KM",
    "KN",
    "KP",
    "KR",
    "KW",
    "KY",
    "KZ",
    "LA",
    "LB",
    "LC",
    "LI",
    "LK",
    "LR",
    "LS",
    "LT",
    "LU",
    "LV",
    "LY",
    "MA",
    "MC",
    "MD",
    "ME",
    "MF",
    "MG",
    "MH",
    "MK",
    "ML",
    "MM",
    "MN",
    "MO",
    "MP",
    "MQ",
    "MR",
    "MS",
    "MT",
    "MU",
    "MV",
    "MW",
    "MX",
    "MY",
    "MZ",
    "NA",
    "NC",
    "NE",
    "NF",
    "NG",
    "NI",
    "NL",
    "NO",
    "NP",
    "NR",
    "NU",
    "NZ",
    "OM",
    "PA",
    "PE",
    "PF",
    "PG",
    "PH",
    "PK",
    "PL",
    "PM",
    "PN",
    "PR",
    "PS",
    "PT",
    "PW",
    "PY",
    "QA",
    "RE",
    "RO",
    "RS",
    "RU",
    "RW",
    "SA",
    "SB",
    "SC",
    "SD",
    "SE",
    "SG",
    "SH",
    "SI",
    "SJ",
    "SK",
    "SL",
    "SM",
    "SN",
    "SO",
    "SR",
    "SS",
    "ST",
    "SV",
    "SX",
    "SY",
    "SZ",
    "TC",
    "TD",
    "TF",
    "TG",
    "TH",
    "TJ",
    "TK",
    "TL",
    "TM",
    "TN",
    "TO",
    "TR",
    "TT",
    "TV",
    "TW",
    "TZ",
    "UA",
    "UG",
    "UM",
    "US",
    "UY",
    "UZ",
    "VA",
    "VC",
    "VE",
    "VG",
    "VI",
    "VN",
    "VU",
    "WF",
    "WS",
    "YE",
    "YT",
    "ZA",
    "ZM",
    "ZW",
    "ABW",
    "AFG",
    "AGO",
    "AIA",
    "ALA",
    "ALB",
    "AND",
    "ARE",
    "ARG",
    "ARM",
    "ASM",
    "ATA",
    "ATF",
    "ATG",
    "AUS",
    "AUT",
    "AZE",
    "BDI",
    "BEL",
    "BEN",
    "BES",
    "BFA",
    "BGD",
    "BGR",
    "BHR",
    "BHS",
    "BIH",
    "BLM",
    "BLR",
    "BLZ",
    "BMU",
    "BOL",
    "BRA",
    "BRB",
    "BRN",
    "BTN",
    "BVT",
    "BWA",
    "CAF",
    "CAN",
    "CCK",
    "CHE",
    "CHL",
    "CHN",
    "CIV",
    "CMR",
    "COD",
    "COG",
    "COK",
    "COL",
    "COM",
    "CPV",
    "CRI",
    "CUB",
    "CUW",
    "CXR",
    "CYM",
    "CYP",
    "CZE",
    "DEU",
    "DJI",
    "DMA",
    "DNK",
    "DOM",
    "DZA",
    "ECU",
    "EGY",
    "ERI",
    "ESH",
    "ESP",
    "EST",
    "ETH",
    "FIN",
    "FJI",
    "FLK",
    "FRA",
    "FRO",
    "FSM",
    "GAB",
    "GBR",
    "GEO",
    "GGY",
    "GHA",
    "GIB",
    "GIN",
    "GLP",
    "GMB",
    "GNB",
    "GNQ",
    "GRC",
    "GRD",
    "GRL",
    "GTM",
    "GUF",
    "GUM",
    "GUY",
    "HKG",
    "HMD",
    "HND",
    "HRV",
    "HTI",
    "HUN",
    "IDN",
    "IMN",
    "IND",
    "IOT",
    "IRL",
    "IRN",
    "IRQ",
    "ISL",
    "ISR",
    "ITA",
    "JAM",
    "JEY",
    "JOR",
    "JPN",
    "KAZ",
    "KEN",
    "KGZ",
    "KHM",
    "KIR",
    "KNA",
    "KOR",
    "KWT",
    "LAO",
    "LBN",
    "LBR",
    "LBY",
    "LCA",
    "LIE",
    "LKA",
    "LSO",
    "LTU",
    "LUX",
    "LVA",
    "MAC",
    "MAF",
    "MAR",
    "MCO",
    "MDA",
    "MDG",
    "MDV",
    "MEX",
    "MHL",
    "MKD",
    "MLI",
    "MLT",
    "MMR",
    "MNE",
    "MNG",
    "MNP",
    "MOZ",
    "MRT",
    "MSR",
    "MTQ",
    "MUS",
    "MWI",
    "MYS",
    "MYT",
    "NAM",
    "NCL",
    "NER",
    "NFK",
    "NGA",
    "NIC",
    "NIU",
    "NLD",
    "NOR",
    "NPL",
    "NRU",
    "NZL",
    "OMN",
    "PAK",
    "PAN",
    "PCN",
    "PER",
    "PHL",
    "PLW",
    "PNG",
    "POL",
    "PRI",
    "PRK",
    "PRT",
    "PRY",
    "PSE",
    "PYF",
    "QAT",
    "REU",
    "ROU",
    "RUS",
    "RWA",
    "SAU",
    "SDN",
    "SEN",
    "SGP",
    "SGS",
    "SHN",
    "SJM",
    "SLB",
    "SLE",
    "SLV",
    "SMR",
    "SOM",
    "SPM",
    "SRB",
    "SSD",
    "STP",
    "SUR",
    "SVK",
    "SVN",
    "SWE",
    "SWZ",
    "SXM",
    "SYC",
    "SYR",
    "TCA",
    "TCD",
    "TGO",
    "THA",
    "TJK",
    "TKL",
    "TKM",
    "TLS",
    "TON",
    "TTO",
    "TUN",
    "TUR",
    "TUV",
    "TWN",
    "TZA",
    "UGA",
    "UKR",
    "UMI",
    "URY",
    "USA",
    "UZB",
    "VAT",
    "VCT",
    "VEN",
    "VGB",
    "VIR",
    "VNM",
    "VUT",
    "WLF",
    "WSM",
    "YEM",
    "ZAF",
    "ZMB",
    "ZWE",
    "all",
    "ALL",
    "All",
]


class WorldBankReader(_BaseReader):
    """Download data series from the World Bank's World Development Indicators."""

    _format = "json"

    def __init__(
        self,
        symbols: str | list[str] | None = None,
        countries: str | list[str] | None = None,
        start=None,
        end=None,
        freq: str | None = None,
        retry_count: int = 3,
        pause: float = 0.1,
        session=None,
        errors: str = "warn",
    ) -> None:
        """
        Initialize the reader.

        Parameters
        ----------
        symbols : str or list of str, optional
            World Bank indicator string or list of strings, taken from the ``id`` field in
            ``WDIsearch()``.
        countries : str or list of str, optional
            ``'all'`` downloads data for all countries. 2- or 3-character ISO country codes select
            individual countries (e.g. ``'US'``, ``'CA'`` or ``'USA'``, ``'CAN'``). The codes can be
            mixed.
        start : str, int, date, datetime, or Timestamp, optional
            First year of the data series. Month and day are ignored.
        end : str, int, date, datetime, or Timestamp, optional
            Last year of the data series (inclusive). Month and day are ignored.
        freq : str, optional
            Frequency or periodicity of the data (``'M'`` for monthly, ``'Q'`` for quarterly,
            ``'A'`` for annual). ``None`` defaults to annual.
        retry_count : int, default 3
            Number of times to retry query request.
        pause : float, default 0.1
            Time, in seconds, of the pause between retries.
        session : Session, optional
            ``requests.sessions.Session`` instance to be used.
        errors : str, default "warn"
            One of ``{'ignore', 'warn', 'raise'}``. Controls validation of country codes against a
            hardcoded list. ``'raise'`` will raise a ``ValueError`` on a bad country code.
        """
        if symbols is None:
            symbols = ["NY.GDP.MKTP.CD", "NY.GNS.ICTR.ZS"]
        elif isinstance(symbols, str):
            symbols = [symbols]

        super().__init__(
            symbols=symbols,
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
        )

        if countries is None:
            countries = ["MX", "CA", "US"]
        elif isinstance(countries, str):
            countries = [countries]

        bad_countries = np.setdiff1d(countries, country_codes)
        # Validate the input
        if len(bad_countries) > 0:
            tmp = ", ".join(bad_countries)
            if errors == "raise":
                raise ValueError(f"Invalid Country Code(s): {tmp}")
            if errors == "warn":
                warnings.warn(
                    f"Non-standard ISO country codes: {tmp}",
                    UserWarning,
                    stacklevel=2,
                )

        freq_symbols = ["M", "Q", "A", None]

        if freq not in freq_symbols:
            msg = f"The frequency `{freq}` is not in the accepted list."
            raise ValueError(msg)

        self.freq = freq
        self.countries = countries
        self.errors = errors

    @property
    def url(self) -> str:
        """API URL."""
        countries = ";".join(self.countries)
        return WB_API_URL + "/countries/" + countries + "/indicators/"

    @property
    def params(self) -> dict:
        """Parameters to use in API calls."""
        if self.freq == "M":
            return {
                "date": f"{self.start.year}M{self.start.month:02d}:{self.end.year}M{self.end.month:02d}",
                "per_page": 25000,
                "format": "json",
            }
        elif self.freq == "Q":
            return {
                "date": f"{self.start.year}Q{self.start.quarter}:{self.end.year}Q{self.end.quarter}",
                "per_page": 25000,
                "format": "json",
            }
        else:
            return {
                "date": f"{self.start.year}:{self.end.year}",
                "per_page": 25000,
                "format": "json",
            }

    def read(self) -> pd.DataFrame:
        """Read data from the World Bank API.

        Returns
        -------
        df : DataFrame
        """
        try:
            return self._read()
        finally:
            self.close()

    def _read(self) -> pd.DataFrame:
        data = []
        for indicator in self.symbols:
            # Build URL for api call
            try:
                df = self._read_one_data(self.url + indicator, self.params)
                df.columns = ["country", "iso_code", "year", indicator]
                data.append(df)

            except ValueError as e:
                msg = str(e) + " Indicator: " + indicator
                if self.errors == "raise":
                    raise ValueError(msg) from e
                elif self.errors == "warn":
                    warnings.warn(msg, stacklevel=2)

        # Confirm we actually got some data, and build Dataframe
        if len(data) > 0:
            out = reduce(lambda x, y: x.merge(y, how="outer"), data)
            out = out.drop("iso_code", axis=1)
            out = out.set_index(["country", "year"])
            out = out.apply(pd.to_numeric, errors="coerce")

            return out
        else:
            msg = "No indicators returned data."
            raise ValueError(msg)

    def _read_lines(self, out: list) -> pd.DataFrame:
        # Check to see if there is a possible problem
        possible_message = out[0]

        if "message" in possible_message.keys():
            msg = possible_message["message"][0]
            try:
                msg = msg["key"].split() + ["\n "] + msg["value"].split()
                wb_err = " ".join(msg)
            except Exception:
                wb_err = ""
                if "key" in msg.keys():
                    wb_err = msg["key"] + "\n "
                if "value" in msg.keys():
                    wb_err += msg["value"]

            msg = f"Problem with a World Bank Query \n {wb_err}."
            raise ValueError(msg)

        if "total" in possible_message.keys():
            if possible_message["total"] == 0:
                msg = "No results found from world bank."
                raise ValueError(msg)

        # Parse JSON file
        data = out[1]
        country = [x["country"]["value"] for x in data]
        iso_code = [x["country"]["id"] for x in data]
        year = [x["date"] for x in data]
        value = [x["value"] for x in data]
        # Prepare output
        df = pd.DataFrame({"country": country, "iso_code": iso_code, "year": year, "value": value})
        return df

    def get_countries(self) -> pd.DataFrame:
        """Query information about countries.

        Returns
        -------
        df : DataFrame
            Includes country code, region, income level, capital city, latitude, and longitude.

        """
        url = WB_API_URL + "/countries/?per_page=1000&format=json"

        resp = self._get_response(url)
        data = resp.json()[1]

        data = pd.DataFrame(data)
        data.adminregion = [x["value"] for x in data.adminregion]
        data.incomeLevel = [x["value"] for x in data.incomeLevel]
        data.lendingType = [x["value"] for x in data.lendingType]
        data.region = [x["value"] for x in data.region]
        data.latitude = [float(x) if x != "" else np.nan for x in data.latitude]
        data.longitude = [float(x) if x != "" else np.nan for x in data.longitude]
        data = data.rename(columns={"id": "iso3c", "iso2Code": "iso2c"})
        return data

    def get_indicators(self) -> pd.DataFrame:
        """Download information about all World Bank data series.

        Returns
        -------
        df : DataFrame
        """
        global _cached_series
        if isinstance(_cached_series, pd.DataFrame):
            return _cached_series.copy()

        url = WB_API_URL + "/indicators?per_page=50000&format=json"

        resp = self._get_response(url)
        data = resp.json()[1]

        data = pd.DataFrame(data)
        # Clean fields
        data.source = [x["value"] for x in data.source]

        def encode_ascii(x):
            return x.encode("ascii", "ignore")

        data.sourceOrganization = data.sourceOrganization.apply(encode_ascii)
        # Clean topic field

        def get_value(x):
            try:
                return x["value"]
            except Exception:
                return ""

        def get_list_of_values(x):
            return [get_value(y) for y in x]

        data.topics = data.topics.apply(get_list_of_values)
        data.topics = data.topics.apply(lambda x: " ; ".join(x))

        # Clean output
        data = data.sort_values(by="id")
        data.index = pd.Index(list(range(data.shape[0])))

        # cache
        _cached_series = data.copy()

        return data

    def search(self, string: str = "gdp.*capi", field: str = "name", case: bool = False) -> pd.DataFrame:
        """
        Search available data series from the World Bank.

        Parameters
        ----------
        string : str, default "gdp.*capi"
            Regular expression to search for.
        field : str, default "name"
            Field to search in. One of ``'id'``, ``'name'``, ``'source'``, ``'sourceNote'``,
            ``'sourceOrganization'``, or ``'topics'``.
        case : bool, default False
            Whether to perform case-sensitive search.

        Returns
        -------
        df : DataFrame

        Notes
        -----
        The first time this method is called it will download and cache the full list of available
        series. Subsequent searches will use the cached copy.
        """
        indicators = self.get_indicators()
        data = indicators[field]
        idx = data.str.contains(string, case=case)
        out = indicators.loc[idx].dropna()
        return out


def download(
    country: str | list[str] | None = None,
    indicator: str | list[str] | None = None,
    start: int = 2003,
    end: int = 2005,
    freq: str | None = None,
    errors: str = "warn",
    **kwargs,
) -> pd.DataFrame:
    """
    Download data series from the World Bank's World Development Indicators.

    Parameters
    ----------
    country : str or list of str, optional
        ``'all'`` downloads data for all countries. 2- or 3-character ISO country codes select
        individual countries (e.g. ``'US'``, ``'CA'``).
    indicator : str or list of str, optional
        Indicator code(s) taken from the ``id`` field in ``WDIsearch()``.
    start : int, default 2003
        First year of the data series.
    end : int, default 2005
        Last year of the data series (inclusive).
    freq : str, optional
        Frequency of the data (``'M'`` for monthly, ``'Q'`` for quarterly, ``'A'`` for annual).
        ``None`` defaults to annual.
    errors : str, default "warn"
        One of ``{'ignore', 'warn', 'raise'}``. Controls validation of country codes.
    **kwargs
        Additional keywords passed to ``WorldBankReader``.

    Returns
    -------
    df : DataFrame
        DataFrame with columns country, year, and indicator value.
    """
    return WorldBankReader(
        symbols=indicator,
        countries=country,
        start=start,
        end=end,
        freq=freq,
        errors=errors,
        **kwargs,
    ).read()


def get_countries(**kwargs) -> pd.DataFrame:
    """Query information about countries.

    Returns
    -------
    df : DataFrame
        Includes country code, region, income level, capital city, latitude, and longitude.

    Parameters
    ----------
    **kwargs
        Keywords passed to ``WorldBankReader``.
    """
    return WorldBankReader(**kwargs).get_countries()


def get_indicators(**kwargs) -> pd.DataFrame:
    """Download information about all World Bank data series.

    Returns
    -------
    df : DataFrame

    Parameters
    ----------
    **kwargs
        Keywords passed to ``WorldBankReader``.
    """
    return WorldBankReader(**kwargs).get_indicators()


_cached_series = None


def search(
    string: str = "gdp.*capi",
    field: str = "name",
    case: bool = False,
    **kwargs,
) -> pd.DataFrame:
    """
    Search available data series from the World Bank.

    Parameters
    ----------
    string : str, default "gdp.*capi"
        Regular expression to search for.
    field : str, default "name"
        Field to search in. One of ``'id'``, ``'name'``, ``'source'``, ``'sourceNote'``,
        ``'sourceOrganization'``, or ``'topics'``.
    case : bool, default False
        Whether to perform case-sensitive search.
    **kwargs
        Keywords passed to ``WorldBankReader``.

    Returns
    -------
    df : DataFrame

    Notes
    -----
    The first time this function is called it will download and cache the full list of available
    series. Subsequent searches will use the cached copy.
    """

    return WorldBankReader(**kwargs).search(string=string, field=field, case=case)
