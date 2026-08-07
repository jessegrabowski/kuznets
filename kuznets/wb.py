from functools import reduce
import time
from typing import Literal, overload
import warnings

import numpy as np
import pandas as pd

from kuznets.base import _BaseReader
from kuznets.typing import BackendName, Frame, OutputType

# ISO 3166-1 alpha-2 and alpha-3 codes, plus the codes the World Bank API serves that have no ISO
# equivalent: its regional and income aggregates, Kosovo, and the Channel Islands. 'all', 'ALL' and
# 'All' are the API's own wildcards. Codes the API stops serving are kept, since accepting a code it
# rejects only defers the error to the response.

WB_API_URL = "https://api.worldbank.org/v2"

country_codes = [
    "1A",
    "1W",
    "4E",
    "6F",
    "6N",
    "6X",
    "7E",
    "8S",
    "A4",
    "A5",
    "A9",
    "ABW",
    "AD",
    "AE",
    "AF",
    "AFE",
    "AFG",
    "AFR",
    "AFW",
    "AG",
    "AGO",
    "AI",
    "AIA",
    "AL",
    "ALA",
    "ALB",
    "AM",
    "AND",
    "AO",
    "AQ",
    "AR",
    "ARB",
    "ARE",
    "ARG",
    "ARM",
    "AS",
    "ASM",
    "AT",
    "ATA",
    "ATF",
    "ATG",
    "AU",
    "AUS",
    "AUT",
    "AW",
    "AX",
    "AZ",
    "AZE",
    "B1",
    "B2",
    "B3",
    "B4",
    "B6",
    "B7",
    "B8",
    "BA",
    "BB",
    "BD",
    "BDI",
    "BE",
    "BEA",
    "BEC",
    "BEL",
    "BEN",
    "BES",
    "BF",
    "BFA",
    "BG",
    "BGD",
    "BGR",
    "BH",
    "BHI",
    "BHR",
    "BHS",
    "BI",
    "BIH",
    "BJ",
    "BL",
    "BLA",
    "BLM",
    "BLR",
    "BLZ",
    "BM",
    "BMN",
    "BMU",
    "BN",
    "BO",
    "BOL",
    "BQ",
    "BR",
    "BRA",
    "BRB",
    "BRN",
    "BS",
    "BSS",
    "BT",
    "BTN",
    "BV",
    "BVT",
    "BW",
    "BWA",
    "BY",
    "BZ",
    "C4",
    "C5",
    "C6",
    "C7",
    "C8",
    "C9",
    "CA",
    "CAA",
    "CAF",
    "CAN",
    "CC",
    "CCK",
    "CD",
    "CEA",
    "CEB",
    "CEU",
    "CF",
    "CG",
    "CH",
    "CHE",
    "CHI",
    "CHL",
    "CHN",
    "CI",
    "CIV",
    "CK",
    "CL",
    "CLA",
    "CM",
    "CME",
    "CMR",
    "CN",
    "CO",
    "COD",
    "COG",
    "COK",
    "COL",
    "COM",
    "CPV",
    "CR",
    "CRI",
    "CSA",
    "CSS",
    "CU",
    "CUB",
    "CUW",
    "CV",
    "CW",
    "CX",
    "CXR",
    "CY",
    "CYM",
    "CYP",
    "CZ",
    "CZE",
    "D2",
    "D3",
    "D4",
    "D5",
    "D6",
    "D7",
    "DE",
    "DEA",
    "DEC",
    "DEU",
    "DJ",
    "DJI",
    "DK",
    "DLA",
    "DM",
    "DMA",
    "DMN",
    "DNK",
    "DNS",
    "DO",
    "DOM",
    "DSA",
    "DSF",
    "DSS",
    "DZ",
    "DZA",
    "EAP",
    "EAR",
    "EAS",
    "EC",
    "ECA",
    "ECS",
    "ECU",
    "EE",
    "EG",
    "EGY",
    "EH",
    "EMU",
    "ER",
    "ERI",
    "ES",
    "ESH",
    "ESP",
    "EST",
    "ET",
    "ETH",
    "EU",
    "EUU",
    "F6",
    "FI",
    "FIN",
    "FJ",
    "FJI",
    "FK",
    "FLK",
    "FM",
    "FO",
    "FR",
    "FRA",
    "FRO",
    "FSM",
    "FXS",
    "GA",
    "GAB",
    "GB",
    "GBR",
    "GD",
    "GE",
    "GEO",
    "GF",
    "GG",
    "GGY",
    "GH",
    "GHA",
    "GI",
    "GIB",
    "GIN",
    "GL",
    "GLP",
    "GM",
    "GMB",
    "GN",
    "GNB",
    "GNQ",
    "GP",
    "GQ",
    "GR",
    "GRC",
    "GRD",
    "GRL",
    "GS",
    "GT",
    "GTM",
    "GU",
    "GUF",
    "GUM",
    "GUY",
    "GW",
    "GY",
    "HIC",
    "HK",
    "HKG",
    "HM",
    "HMD",
    "HN",
    "HND",
    "HPC",
    "HR",
    "HRV",
    "HT",
    "HTI",
    "HU",
    "HUN",
    "IBB",
    "IBD",
    "IBT",
    "ID",
    "IDA",
    "IDB",
    "IDN",
    "IDX",
    "IE",
    "IL",
    "IM",
    "IMN",
    "IN",
    "IND",
    "INX",
    "IO",
    "IOT",
    "IQ",
    "IR",
    "IRL",
    "IRN",
    "IRQ",
    "IS",
    "ISL",
    "ISR",
    "IT",
    "ITA",
    "JAM",
    "JE",
    "JEY",
    "JG",
    "JM",
    "JO",
    "JOR",
    "JP",
    "JPN",
    "KAZ",
    "KE",
    "KEN",
    "KG",
    "KGZ",
    "KH",
    "KHM",
    "KI",
    "KIR",
    "KM",
    "KN",
    "KNA",
    "KOR",
    "KP",
    "KR",
    "KW",
    "KWT",
    "KY",
    "KZ",
    "LA",
    "LAC",
    "LAO",
    "LB",
    "LBN",
    "LBR",
    "LBY",
    "LC",
    "LCA",
    "LCN",
    "LDC",
    "LI",
    "LIC",
    "LIE",
    "LK",
    "LKA",
    "LMC",
    "LMY",
    "LR",
    "LS",
    "LSO",
    "LT",
    "LTE",
    "LTU",
    "LU",
    "LUX",
    "LV",
    "LVA",
    "LY",
    "M1",
    "M2",
    "MA",
    "MAC",
    "MAF",
    "MAR",
    "MC",
    "MCO",
    "MD",
    "MDA",
    "MDE",
    "MDG",
    "MDV",
    "ME",
    "MEA",
    "MEX",
    "MF",
    "MG",
    "MH",
    "MHL",
    "MIC",
    "MK",
    "MKD",
    "ML",
    "MLI",
    "MLT",
    "MM",
    "MMR",
    "MN",
    "MNA",
    "MNE",
    "MNG",
    "MNP",
    "MO",
    "MOZ",
    "MP",
    "MQ",
    "MR",
    "MRT",
    "MS",
    "MSR",
    "MT",
    "MTQ",
    "MU",
    "MUS",
    "MV",
    "MW",
    "MWI",
    "MX",
    "MY",
    "MYS",
    "MYT",
    "MZ",
    "N6",
    "NA",
    "NAC",
    "NAF",
    "NAM",
    "NC",
    "NCL",
    "NE",
    "NER",
    "NF",
    "NFK",
    "NG",
    "NGA",
    "NI",
    "NIC",
    "NIU",
    "NL",
    "NLD",
    "NO",
    "NOR",
    "NP",
    "NPL",
    "NR",
    "NRS",
    "NRU",
    "NU",
    "NXS",
    "NZ",
    "NZL",
    "OE",
    "OED",
    "OM",
    "OMN",
    "OSS",
    "PA",
    "PAK",
    "PAN",
    "PCN",
    "PE",
    "PER",
    "PF",
    "PG",
    "PH",
    "PHL",
    "PK",
    "PL",
    "PLW",
    "PM",
    "PN",
    "PNG",
    "POL",
    "PR",
    "PRE",
    "PRI",
    "PRK",
    "PRT",
    "PRY",
    "PS",
    "PSE",
    "PSS",
    "PST",
    "PT",
    "PW",
    "PY",
    "PYF",
    "QA",
    "QAT",
    "R6",
    "RE",
    "REU",
    "RO",
    "ROU",
    "RRS",
    "RS",
    "RU",
    "RUS",
    "RW",
    "RWA",
    "S1",
    "S2",
    "S3",
    "S4",
    "SA",
    "SAS",
    "SAU",
    "SB",
    "SC",
    "SD",
    "SDN",
    "SE",
    "SEN",
    "SG",
    "SGP",
    "SGS",
    "SH",
    "SHN",
    "SI",
    "SJ",
    "SJM",
    "SK",
    "SL",
    "SLB",
    "SLE",
    "SLV",
    "SM",
    "SMR",
    "SN",
    "SO",
    "SOM",
    "SPM",
    "SR",
    "SRB",
    "SS",
    "SSA",
    "SSD",
    "SSF",
    "SST",
    "ST",
    "STP",
    "SUR",
    "SV",
    "SVK",
    "SVN",
    "SWE",
    "SWZ",
    "SX",
    "SXM",
    "SXZ",
    "SY",
    "SYC",
    "SYR",
    "SZ",
    "T2",
    "T3",
    "T4",
    "T5",
    "T6",
    "T7",
    "TC",
    "TCA",
    "TCD",
    "TD",
    "TEA",
    "TEC",
    "TF",
    "TG",
    "TGO",
    "TH",
    "THA",
    "TJ",
    "TJK",
    "TK",
    "TKL",
    "TKM",
    "TL",
    "TLA",
    "TLS",
    "TM",
    "TMN",
    "TN",
    "TO",
    "TON",
    "TR",
    "TSA",
    "TSS",
    "TT",
    "TTO",
    "TUN",
    "TUR",
    "TUV",
    "TV",
    "TW",
    "TWN",
    "TZ",
    "TZA",
    "UA",
    "UG",
    "UGA",
    "UKR",
    "UM",
    "UMC",
    "UMI",
    "URY",
    "US",
    "USA",
    "UY",
    "UZ",
    "UZB",
    "V1",
    "V2",
    "V3",
    "V4",
    "VA",
    "VAT",
    "VC",
    "VCT",
    "VE",
    "VEN",
    "VG",
    "VGB",
    "VI",
    "VIR",
    "VN",
    "VNM",
    "VU",
    "VUT",
    "WF",
    "WLD",
    "WLF",
    "WS",
    "WSM",
    "XC",
    "XD",
    "XE",
    "XF",
    "XG",
    "XH",
    "XI",
    "XJ",
    "XK",
    "XKX",
    "XL",
    "XM",
    "XN",
    "XO",
    "XP",
    "XQ",
    "XT",
    "XU",
    "XY",
    "XZN",
    "YE",
    "YEM",
    "YT",
    "Z4",
    "Z7",
    "ZA",
    "ZAF",
    "ZB",
    "ZF",
    "ZG",
    "ZH",
    "ZI",
    "ZJ",
    "ZM",
    "ZMB",
    "ZQ",
    "ZT",
    "ZW",
    "ZWE",
    "all",
    "ALL",
    "All",
]

_COUNTRY_CODES = frozenset(country_codes)


class WorldBankReader(_BaseReader):
    """Download data series from the World Bank's World Development Indicators."""

    symbols: list[str]

    _format = "json"

    def __init__(
        self,
        symbols: str | list[str] | None = None,
        countries: str | list[str] | None = None,
        start=None,
        end=None,
        freq: str | None = None,
        retry_count: int | None = None,
        pause: float | None = None,
        session=None,
        errors: str = "warn",
        output_type: str = "pandas",
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
        retry_count : int, optional
            Number of times to retry query request. Falls back to the configured default.
        pause : float, optional
            Time, in seconds, of the pause between retries. Falls back to the configured default.
        session : Session, optional
            ``requests.sessions.Session`` instance to be used.
        errors : str, default "warn"
            One of ``{'ignore', 'warn', 'raise'}``. Controls validation of country codes against a
            hardcoded list. ``'raise'`` will raise a ``ValueError`` on a bad country code.
        output_type : str, optional
            Backend of the returned data: 'pandas', 'polars', 'pyarrow' (alias 'arrow'), or 'dask'.
            Backends other than pandas must be installed separately. Default 'pandas'.
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
            output_type=output_type,
        )

        if countries is None:
            countries = ["MX", "CA", "US"]
        elif isinstance(countries, str):
            countries = [countries]

        bad_countries = sorted({str(country) for country in countries} - _COUNTRY_CODES)
        if bad_countries:
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

    def _read_core(self) -> pd.DataFrame:
        """Fetch all requested indicators from the World Bank API.

        Returns
        -------
        df : DataFrame
        """
        try:
            data = []
            for i, indicator in enumerate(self.symbols):
                if i:
                    # Space out requests so a batch of indicators doesn't slam the API.
                    time.sleep(self.pause)
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
        finally:
            self.close()

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
        data["adminregion"] = [x["value"] for x in data["adminregion"]]
        data["incomeLevel"] = [x["value"] for x in data["incomeLevel"]]
        data["lendingType"] = [x["value"] for x in data["lendingType"]]
        data["region"] = [x["value"] for x in data["region"]]
        data["latitude"] = [float(x) if x != "" else np.nan for x in data["latitude"]]
        data["longitude"] = [float(x) if x != "" else np.nan for x in data["longitude"]]
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
        data["source"] = [x["value"] for x in data["source"]]

        def encode_ascii(x):
            return x.encode("ascii", "ignore")

        data["sourceOrganization"] = data["sourceOrganization"].apply(encode_ascii)
        # Clean topic field

        def get_value(x):
            try:
                return x["value"]
            except Exception:
                return ""

        def get_list_of_values(x):
            return [get_value(y) for y in x]

        data["topics"] = data["topics"].apply(get_list_of_values)
        data["topics"] = data["topics"].apply(lambda x: " ; ".join(x))

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


@overload
def download(
    country: str | list[str] | None = None,
    indicator: str | list[str] | None = None,
    start: int = 2003,
    end: int = 2005,
    freq: str | None = None,
    errors: str = "warn",
    output_type: Literal["pandas"] = "pandas",
    **kwargs,
) -> pd.DataFrame: ...
@overload
def download(
    country: str | list[str] | None = None,
    indicator: str | list[str] | None = None,
    start: int = 2003,
    end: int = 2005,
    freq: str | None = None,
    errors: str = "warn",
    output_type: BackendName = ...,
    **kwargs,
) -> Frame: ...
def download(
    country: str | list[str] | None = None,
    indicator: str | list[str] | None = None,
    start: int = 2003,
    end: int = 2005,
    freq: str | None = None,
    errors: str = "warn",
    output_type: OutputType = "pandas",
    **kwargs,
) -> Frame:
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
    output_type : str, optional
        Backend of the returned data: 'pandas', 'polars', 'pyarrow' (alias 'arrow'), or 'dask'.
        Backends other than pandas must be installed separately. Default 'pandas'.
    **kwargs
        Additional keywords passed to ``WorldBankReader``.

    Returns
    -------
    df : DataFrame or native frame
        Columns country, year, and indicator value, as a pandas DataFrame by default or as a native
        frame of the backend selected with ``output_type``.
    """
    return WorldBankReader(
        symbols=indicator,
        countries=country,
        start=start,
        end=end,
        freq=freq,
        errors=errors,
        output_type=output_type,
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


_cached_series: pd.DataFrame | None = None


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
