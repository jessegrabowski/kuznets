"""
Module contains tools for collecting data from various remote sources.
"""

import datetime

from pandas import Timestamp
import requests

from kuznets._output import PANDAS, detach_index, from_pandas, validate_output_type
from kuznets.av.forex import AVForexReader
from kuznets.av.time_series import AVTimeSeriesReader
from kuznets.bankofcanada import BankOfCanadaReader
from kuznets.econdb import EcondbReader
from kuznets.eurostat import EurostatReader
from kuznets.famafrench import FamaFrenchReader
from kuznets.fred import FredReader
from kuznets.moex import MoexReader
from kuznets.nasdaq_trader import get_nasdaq_symbols
from kuznets.naver import NaverDailyReader
from kuznets.oecd import OECDReader
from kuznets.quandl import QuandlReader
from kuznets.stooq import StooqDailyReader
from kuznets.tiingo import (
    TiingoDailyReader,
    TiingoIEXHistoricalReader,
    TiingoQuoteReader,
)
from kuznets.yahoo.actions import YahooActionReader, YahooDivReader
from kuznets.yahoo.daily import YahooDailyReader
from kuznets.yahoo.fundamentals import YahooFundamentalsReader
from kuznets.yahoo.options import Options
from kuznets.yahoo.quotes import YahooQuotesReader

__all__ = [
    "get_data_econdb",
    "get_data_famafrench",
    "get_data_fred",
    "get_data_moex",
    "get_data_quandl",
    "get_data_yahoo",
    "get_data_yahoo_actions",
    "get_data_yahoo_fundamentals",
    "get_nasdaq_symbols",
    "get_quote_yahoo",
    "get_data_stooq",
    "DataReader",
    "Options",
]


def get_data_alphavantage(*args, **kwargs):
    return AVTimeSeriesReader(*args, **kwargs).read()


def get_data_fred(*args, **kwargs):
    return FredReader(*args, **kwargs).read()


def get_data_famafrench(*args, **kwargs):
    return FamaFrenchReader(*args, **kwargs).read()


def get_data_yahoo(*args, **kwargs):
    return YahooDailyReader(*args, **kwargs).read()


def get_data_econdb(*args, **kwargs):
    return EcondbReader(*args, **kwargs).read()


def get_data_yahoo_actions(*args, **kwargs):
    return YahooActionReader(*args, **kwargs).read()


def get_data_yahoo_fundamentals(*args, **kwargs):
    return YahooFundamentalsReader(*args, **kwargs).read()


def get_quote_yahoo(*args, **kwargs):
    return YahooQuotesReader(*args, **kwargs).read()


def get_data_quandl(*args, **kwargs):
    return QuandlReader(*args, **kwargs).read()


def get_data_moex(*args, **kwargs):
    return MoexReader(*args, **kwargs).read()


def get_data_stooq(*args, **kwargs):
    return StooqDailyReader(*args, **kwargs).read()


def get_data_tiingo(*args, **kwargs):
    return TiingoDailyReader(*args, **kwargs).read()


def get_iex_data_tiingo(*args, **kwargs):
    return TiingoIEXHistoricalReader(*args, **kwargs).read()


def get_quotes_tiingo(*args, **kwargs):
    return TiingoQuoteReader(*args, **kwargs).read()


def get_exchange_rate_av(*args, **kwargs):
    return AVForexReader(*args, **kwargs).read()


def DataReader(
    name: str | list[str],
    data_source: str | None = None,
    start: str | int | datetime.date | datetime.datetime | Timestamp | None = None,
    end: str | int | datetime.date | datetime.datetime | Timestamp | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    session: requests.Session | None = None,
    api_key: str | None = None,
    headers: dict | None = None,
    output_type: str = "pandas",
    max_workers: int | None = None,
):
    """
    Import data from a number of online sources.

    Currently supports Google Finance, St. Louis FED (FRED), and Kenneth French's data library,
    among others.

    Parameters
    ----------
    name : str or list of str
        The name of the dataset. Some data sources (e.g. fred) will accept a list of names.
    data_source : str, optional
        The data source ("fred", "famafrench", "yahoo").
    start : str, int, date, datetime, or Timestamp, optional
        Left boundary for range (defaults to 1/1/2010).
    end : str, int, date, datetime, or Timestamp, optional
        Right boundary for range (defaults to today).
    retry_count : int, optional
        Number of times to retry query request. Falls back to ``options.retry_count``, the config
        file, then 3.
    pause : float, optional
        Time, in seconds, to pause between consecutive queries of chunks. If single value given for
        symbol, represents the pause between retries. Falls back to the configured default.
    session : Session, default None
        ``requests.sessions.Session`` instance to be used.
    api_key : str, optional
        Optional parameter to specify an API key for certain data sources. Each keyed reader also
        resolves keys from ``options.api_keys``, environment variables, and the config file.
    headers : dict, optional
        Headers applied to every request, merged over ``options.headers`` and the config file. Pass
        a ``User-Agent`` here to identify as something other than ``kuznets`` when a host
        blocks the default agent.
    output_type : str, optional
        Backend of the returned data: 'pandas', 'polars', 'pyarrow' (alias 'arrow'), or 'dask'.
        Backends other than pandas must be installed separately. Default 'pandas'.
    max_workers : int, optional
        Number of concurrent requests for multi-symbol reads from the daily-price sources. Keep it
        modest for rate-limited hosts, and pass 1 when supplying a session that is not thread-safe.
        Default 5.

    Returns
    -------
    df : DataFrame or native frame
        Data from the specified source, as a pandas DataFrame by default or as a native frame of
        the backend selected with ``output_type``.

    Examples
    --------
    # Data from Yahoo Finance
    aapl = DataReader("AAPL", "yahoo")

    # Data from FRED
    vix = DataReader("VIXCLS", "fred")

    # Data from Fama/French
    ff = DataReader("F-F_Research_Data_Factors", "famafrench")
    ff = DataReader("F-F_Research_Data_Factors_weekly", "famafrench")
    ff = DataReader("6_Portfolios_2x3", "famafrench")
    ff = DataReader("F-F_ST_Reversal_Factor", "famafrench")
    """
    expected_source = [
        "yahoo",
        "bankofcanada",
        "stooq",
        "fred",
        "famafrench",
        "oecd",
        "eurostat",
        "nasdaq",
        "quandl",
        "moex",
        "tiingo",
        "yahoo-actions",
        "yahoo-dividends",
        "yahoo-fundamentals",
        "av-forex",
        "av-forex-daily",
        "av-daily",
        "av-daily-adjusted",
        "av-weekly",
        "av-weekly-adjusted",
        "av-monthly",
        "av-monthly-adjusted",
        "av-intraday",
        "econdb",
        "naver",
    ]

    if data_source not in expected_source:
        msg = f"data_source={data_source!r} is not implemented"
        raise NotImplementedError(msg)

    output_type = validate_output_type(output_type)

    if data_source == "yahoo":
        return YahooDailyReader(
            symbols=name,
            start=start,
            end=end,
            adjust_price=False,
            chunksize=25,
            retry_count=retry_count,
            pause=pause,
            session=session,
            output_type=output_type,
            max_workers=max_workers,
        ).read()

    elif data_source == "bankofcanada":
        return BankOfCanadaReader(
            symbols=name,
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            output_type=output_type,
        ).read()

    elif data_source == "stooq":
        return StooqDailyReader(
            symbols=name,
            start=start,
            end=end,
            chunksize=25,
            retry_count=retry_count,
            pause=pause,
            session=session,
            output_type=output_type,
            max_workers=max_workers,
        ).read()

    elif data_source == "fred":
        return FredReader(
            symbols=name,
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            api_key=api_key,
            headers=headers,
            output_type=output_type,
        ).read()

    elif data_source == "famafrench":
        return FamaFrenchReader(
            symbols=name,
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            output_type=output_type,
        ).read()

    elif data_source == "oecd":
        return OECDReader(
            symbols=name,
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            output_type=output_type,
        ).read()
    elif data_source == "eurostat":
        return EurostatReader(
            symbols=name,
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            output_type=output_type,
        ).read()
    elif data_source == "nasdaq":
        if name != "symbols":
            raise ValueError(f"Only the string 'symbols' is supported for Nasdaq, not {name!r}")
        nasdaq_symbols = get_nasdaq_symbols(retry_count=retry_count, pause=pause)
        if output_type == PANDAS:
            return nasdaq_symbols
        tidy, _ = detach_index(nasdaq_symbols)
        return from_pandas(tidy, output_type)

    elif data_source == "quandl":
        return QuandlReader(
            symbols=name,
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            api_key=api_key,
            output_type=output_type,
            max_workers=max_workers,
        ).read()
    elif data_source == "moex":
        return MoexReader(
            symbols=name,
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            output_type=output_type,
            max_workers=max_workers,
        ).read()
    elif data_source == "tiingo":
        return TiingoDailyReader(
            symbols=name,
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            api_key=api_key,
            output_type=output_type,
        ).read()

    elif data_source == "yahoo-actions":
        return YahooActionReader(
            symbols=name,
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            output_type=output_type,
            max_workers=max_workers,
        ).read()

    elif data_source == "yahoo-dividends":
        return YahooDivReader(
            symbols=name,
            start=start,
            end=end,
            adjust_price=False,
            chunksize=25,
            retry_count=retry_count,
            pause=pause,
            session=session,
            interval="d",
            output_type=output_type,
            max_workers=max_workers,
        ).read()

    elif data_source == "yahoo-fundamentals":
        return YahooFundamentalsReader(
            symbols=name,
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            output_type=output_type,
            max_workers=max_workers,
        ).read()

    elif data_source == "av-forex":
        return AVForexReader(
            symbols=name,
            retry_count=retry_count,
            pause=pause,
            session=session,
            api_key=api_key,
            output_type=output_type,
        ).read()

    elif data_source == "av-forex-daily":
        return AVTimeSeriesReader(
            symbols=name,
            function="FX_DAILY",
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            api_key=api_key,
            output_type=output_type,
        ).read()

    elif data_source == "av-daily":
        return AVTimeSeriesReader(
            symbols=name,
            function="TIME_SERIES_DAILY",
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            api_key=api_key,
            output_type=output_type,
        ).read()

    elif data_source == "av-daily-adjusted":
        return AVTimeSeriesReader(
            symbols=name,
            function="TIME_SERIES_DAILY_ADJUSTED",
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            api_key=api_key,
            output_type=output_type,
        ).read()

    elif data_source == "av-weekly":
        return AVTimeSeriesReader(
            symbols=name,
            function="TIME_SERIES_WEEKLY",
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            api_key=api_key,
            output_type=output_type,
        ).read()

    elif data_source == "av-weekly-adjusted":
        return AVTimeSeriesReader(
            symbols=name,
            function="TIME_SERIES_WEEKLY_ADJUSTED",
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            api_key=api_key,
            output_type=output_type,
        ).read()

    elif data_source == "av-monthly":
        return AVTimeSeriesReader(
            symbols=name,
            function="TIME_SERIES_MONTHLY",
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            api_key=api_key,
            output_type=output_type,
        ).read()

    elif data_source == "av-monthly-adjusted":
        return AVTimeSeriesReader(
            symbols=name,
            function="TIME_SERIES_MONTHLY_ADJUSTED",
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            api_key=api_key,
            output_type=output_type,
        ).read()

    elif data_source == "av-intraday":
        return AVTimeSeriesReader(
            symbols=name,
            function="TIME_SERIES_INTRADAY",
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            api_key=api_key,
            output_type=output_type,
        ).read()

    elif data_source == "econdb":
        return EcondbReader(
            symbols=name,
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            output_type=output_type,
        ).read()

    elif data_source == "naver":
        return NaverDailyReader(
            symbols=name,
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            output_type=output_type,
            max_workers=max_workers,
        ).read()

    else:
        msg = f"data_source={data_source!r} is not implemented"
        raise NotImplementedError(msg)
