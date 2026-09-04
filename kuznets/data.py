"""
Module contains tools for collecting data from various remote sources.
"""

from typing import Any, Literal, cast, overload

from pandas import DataFrame
import requests

from kuznets.av.forex import AVForexReader
from kuznets.av.time_series import AVTimeSeriesReader
from kuznets.bankofcanada import BankOfCanadaReader
from kuznets.econdb import EcondbReader
from kuznets.eurostat import EurostatReader
from kuznets.famafrench import FamaFrenchReader
from kuznets.fred import FredReader
from kuznets.ilostat import ILOSTATReader
from kuznets.imf import IMFReader, IMTSReader
from kuznets.moex import MoexReader
from kuznets.nasdaq_trader import get_nasdaq_symbols
from kuznets.naver import NaverDailyReader
from kuznets.oecd import OECDReader
from kuznets.output import PANDAS, detach_index, from_pandas, validate_output_type
from kuznets.quandl import QuandlReader
from kuznets.stooq import StooqDailyReader
from kuznets.tiingo import (
    TiingoDailyReader,
    TiingoIEXHistoricalReader,
    TiingoQuoteReader,
)
from kuznets.typing import BackendName, DateLike, Frame, Headers, OutputType, Symbols
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


_DATA_SOURCES = {
    "yahoo",
    "bankofcanada",
    "stooq",
    "fred",
    "famafrench",
    "oecd",
    "eurostat",
    "ilostat",
    "imf",
    "imts",
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
}


def _single_symbol(name: Symbols, data_source: str) -> str:
    """Return *name* as a lone symbol, raising ValueError for the list form."""
    if isinstance(name, str):
        return name
    raise ValueError(f"data_source={data_source!r} reads one symbol at a time, but got {name!r}")


# Each entry point below is declared twice: reading with the default 'pandas' backend yields a
# pandas object, and reading with any other backend yields that backend's native frame. The bodies
# construct their reader with named arguments, so a signature that drifts from its reader is a type
# error rather than a silent lie.


@overload
def get_data_alphavantage(
    symbols: str | None = None,
    function: str = "TIME_SERIES_DAILY",
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    session: requests.Session | None = None,
    chunksize: int = 25,
    api_key: str | None = None,
    output_type: Literal["pandas"] = "pandas",
) -> DataFrame: ...
@overload
def get_data_alphavantage(
    symbols: str | None = None,
    function: str = "TIME_SERIES_DAILY",
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    session: requests.Session | None = None,
    chunksize: int = 25,
    api_key: str | None = None,
    output_type: BackendName = ...,
) -> Frame: ...
def get_data_alphavantage(
    symbols: str | None = None,
    function: str = "TIME_SERIES_DAILY",
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    session: requests.Session | None = None,
    chunksize: int = 25,
    api_key: str | None = None,
    output_type: OutputType = "pandas",
) -> Frame:
    """Read an Alpha Vantage time series. See :class:`~kuznets.av.time_series.AVTimeSeriesReader`."""
    return AVTimeSeriesReader(
        symbols=symbols,
        function=function,
        start=start,
        end=end,
        retry_count=retry_count,
        pause=pause,
        session=session,
        chunksize=chunksize,
        api_key=api_key,
        output_type=output_type,
    ).read()


@overload
def get_data_fred(
    symbols: Symbols,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    timeout: float | None = None,
    session: requests.Session | None = None,
    freq: str | None = None,
    headers: Headers | None = None,
    output_type: Literal["pandas"] = "pandas",
    api_key: str | None = None,
) -> DataFrame: ...
@overload
def get_data_fred(
    symbols: Symbols,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    timeout: float | None = None,
    session: requests.Session | None = None,
    freq: str | None = None,
    headers: Headers | None = None,
    output_type: BackendName = ...,
    api_key: str | None = None,
) -> Frame: ...
def get_data_fred(
    symbols: Symbols,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    timeout: float | None = None,
    session: requests.Session | None = None,
    freq: str | None = None,
    headers: Headers | None = None,
    output_type: OutputType = "pandas",
    api_key: str | None = None,
) -> Frame:
    """Read one or more FRED series. See :class:`~kuznets.fred.FredReader`."""
    return FredReader(
        symbols=symbols,
        start=start,
        end=end,
        retry_count=retry_count,
        pause=pause,
        timeout=timeout,
        session=session,
        freq=freq,
        headers=headers,
        output_type=output_type,
        api_key=api_key,
    ).read()


@overload
def get_data_famafrench(
    symbols: Symbols | DataFrame | None,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    timeout: float | None = None,
    session: requests.Session | None = None,
    freq: str | None = None,
    headers: Headers | None = None,
    output_type: Literal["pandas"] = "pandas",
) -> dict[int | str, DataFrame | str]: ...
@overload
def get_data_famafrench(
    symbols: Symbols | DataFrame | None,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    timeout: float | None = None,
    session: requests.Session | None = None,
    freq: str | None = None,
    headers: Headers | None = None,
    output_type: BackendName = ...,
) -> dict[int | str, Frame | str]: ...
def get_data_famafrench(
    symbols: Symbols | DataFrame | None,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    timeout: float | None = None,
    session: requests.Session | None = None,
    freq: str | None = None,
    headers: Headers | None = None,
    output_type: OutputType = "pandas",
) -> dict[int | str, Any]:
    """Read a Fama/French dataset. See :class:`~kuznets.famafrench.FamaFrenchReader`.

    Returns one entry per table in the dataset, keyed by table number, plus a ``'DESCR'`` entry
    holding the dataset's text description.
    """
    # Alone among the readers, FamaFrench yields a dict of tables rather than a single frame.
    return cast(
        "dict[int | str, Any]",
        FamaFrenchReader(
            symbols=symbols,
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            timeout=timeout,
            session=session,
            freq=freq,
            headers=headers,
            output_type=output_type,
        ).read(),
    )


@overload
def get_data_yahoo(
    symbols: Symbols | DataFrame | None = None,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    session: requests.Session | None = None,
    adjust_price: bool = False,
    ret_index: bool = False,
    chunksize: int = 1,
    interval: str = "d",
    get_actions: bool = False,
    adjust_dividends: bool = True,
    output_type: Literal["pandas"] = "pandas",
    max_workers: int | None = None,
) -> DataFrame: ...
@overload
def get_data_yahoo(
    symbols: Symbols | DataFrame | None = None,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    session: requests.Session | None = None,
    adjust_price: bool = False,
    ret_index: bool = False,
    chunksize: int = 1,
    interval: str = "d",
    get_actions: bool = False,
    adjust_dividends: bool = True,
    output_type: BackendName = ...,
    max_workers: int | None = None,
) -> Frame: ...
def get_data_yahoo(
    symbols: Symbols | DataFrame | None = None,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    session: requests.Session | None = None,
    adjust_price: bool = False,
    ret_index: bool = False,
    chunksize: int = 1,
    interval: str = "d",
    get_actions: bool = False,
    adjust_dividends: bool = True,
    output_type: OutputType = "pandas",
    max_workers: int | None = None,
) -> Frame:
    """Read daily Yahoo Finance prices. See :class:`~kuznets.yahoo.daily.YahooDailyReader`."""
    return YahooDailyReader(
        symbols=symbols,
        start=start,
        end=end,
        retry_count=retry_count,
        pause=pause,
        session=session,
        adjust_price=adjust_price,
        ret_index=ret_index,
        chunksize=chunksize,
        interval=interval,
        get_actions=get_actions,
        adjust_dividends=adjust_dividends,
        output_type=output_type,
        max_workers=max_workers,
    ).read()


@overload
def get_data_econdb(
    symbols: str,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    session: requests.Session | None = None,
    freq: str | None = None,
    output_type: Literal["pandas"] = "pandas",
) -> DataFrame: ...
@overload
def get_data_econdb(
    symbols: str,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    session: requests.Session | None = None,
    freq: str | None = None,
    output_type: BackendName = ...,
) -> Frame: ...
def get_data_econdb(
    symbols: str,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    session: requests.Session | None = None,
    freq: str | None = None,
    output_type: OutputType = "pandas",
) -> Frame:
    """Read an Econdb series or dataset. See :class:`~kuznets.econdb.EcondbReader`."""
    return EcondbReader(
        symbols=symbols,
        start=start,
        end=end,
        retry_count=retry_count,
        pause=pause,
        session=session,
        freq=freq,
        output_type=output_type,
    ).read()


@overload
def get_data_yahoo_actions(
    symbols: Symbols | DataFrame | None = None,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    session: requests.Session | None = None,
    adjust_price: bool = False,
    ret_index: bool = False,
    chunksize: int = 1,
    interval: str = "d",
    get_actions: bool = False,
    adjust_dividends: bool = True,
    output_type: Literal["pandas"] = "pandas",
    max_workers: int | None = None,
) -> DataFrame: ...
@overload
def get_data_yahoo_actions(
    symbols: Symbols | DataFrame | None = None,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    session: requests.Session | None = None,
    adjust_price: bool = False,
    ret_index: bool = False,
    chunksize: int = 1,
    interval: str = "d",
    get_actions: bool = False,
    adjust_dividends: bool = True,
    output_type: BackendName = ...,
    max_workers: int | None = None,
) -> Frame: ...
def get_data_yahoo_actions(
    symbols: Symbols | DataFrame | None = None,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    session: requests.Session | None = None,
    adjust_price: bool = False,
    ret_index: bool = False,
    chunksize: int = 1,
    interval: str = "d",
    get_actions: bool = False,
    adjust_dividends: bool = True,
    output_type: OutputType = "pandas",
    max_workers: int | None = None,
) -> Frame:
    """Read Yahoo dividend and split actions. See :class:`~kuznets.yahoo.actions.YahooActionReader`."""
    return YahooActionReader(
        symbols=symbols,
        start=start,
        end=end,
        retry_count=retry_count,
        pause=pause,
        session=session,
        adjust_price=adjust_price,
        ret_index=ret_index,
        chunksize=chunksize,
        interval=interval,
        get_actions=get_actions,
        adjust_dividends=adjust_dividends,
        output_type=output_type,
        max_workers=max_workers,
    ).read()


@overload
def get_data_yahoo_fundamentals(
    symbols: Symbols | None = None,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    session: requests.Session | None = None,
    freq: str = "annual",
    statement: str = "balance-sheet",
    series: str | list[str] | None = None,
    output_type: Literal["pandas"] = "pandas",
    max_workers: int | None = None,
) -> DataFrame: ...
@overload
def get_data_yahoo_fundamentals(
    symbols: Symbols | None = None,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    session: requests.Session | None = None,
    freq: str = "annual",
    statement: str = "balance-sheet",
    series: str | list[str] | None = None,
    output_type: BackendName = ...,
    max_workers: int | None = None,
) -> Frame: ...
def get_data_yahoo_fundamentals(
    symbols: Symbols | None = None,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    session: requests.Session | None = None,
    freq: str = "annual",
    statement: str = "balance-sheet",
    series: str | list[str] | None = None,
    output_type: OutputType = "pandas",
    max_workers: int | None = None,
) -> Frame:
    """Read Yahoo fundamentals. See :class:`~kuznets.yahoo.fundamentals.YahooFundamentalsReader`."""
    return YahooFundamentalsReader(
        symbols=symbols,
        start=start,
        end=end,
        retry_count=retry_count,
        pause=pause,
        session=session,
        freq=freq,
        statement=statement,
        series=series,
        output_type=output_type,
        max_workers=max_workers,
    ).read()


@overload
def get_quote_yahoo(
    symbols: Symbols | None = None,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    session: requests.Session | None = None,
    output_type: Literal["pandas"] = "pandas",
) -> DataFrame: ...
@overload
def get_quote_yahoo(
    symbols: Symbols | None = None,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    session: requests.Session | None = None,
    output_type: BackendName = ...,
) -> Frame: ...
def get_quote_yahoo(
    symbols: Symbols | None = None,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    session: requests.Session | None = None,
    output_type: OutputType = "pandas",
) -> Frame:
    """Read Yahoo quotes. See :class:`~kuznets.yahoo.quotes.YahooQuotesReader`."""
    return YahooQuotesReader(
        symbols=symbols,
        start=start,
        end=end,
        retry_count=retry_count,
        pause=pause,
        session=session,
        output_type=output_type,
    ).read()


@overload
def get_data_quandl(
    symbols: Symbols,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    session: requests.Session | None = None,
    chunksize: int = 25,
    api_key: str | None = None,
    output_type: Literal["pandas"] = "pandas",
    max_workers: int | None = None,
) -> DataFrame: ...
@overload
def get_data_quandl(
    symbols: Symbols,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    session: requests.Session | None = None,
    chunksize: int = 25,
    api_key: str | None = None,
    output_type: BackendName = ...,
    max_workers: int | None = None,
) -> Frame: ...
def get_data_quandl(
    symbols: Symbols,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    session: requests.Session | None = None,
    chunksize: int = 25,
    api_key: str | None = None,
    output_type: OutputType = "pandas",
    max_workers: int | None = None,
) -> Frame:
    """Read a Quandl dataset. See :class:`~kuznets.quandl.QuandlReader`."""
    return QuandlReader(
        symbols=symbols,
        start=start,
        end=end,
        retry_count=retry_count,
        pause=pause,
        session=session,
        chunksize=chunksize,
        api_key=api_key,
        output_type=output_type,
        max_workers=max_workers,
    ).read()


@overload
def get_data_moex(
    symbols: Symbols | DataFrame | None = None,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    session: requests.Session | None = None,
    chunksize: int = 25,
    output_type: Literal["pandas"] = "pandas",
    max_workers: int | None = None,
) -> DataFrame: ...
@overload
def get_data_moex(
    symbols: Symbols | DataFrame | None = None,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    session: requests.Session | None = None,
    chunksize: int = 25,
    output_type: BackendName = ...,
    max_workers: int | None = None,
) -> Frame: ...
def get_data_moex(
    symbols: Symbols | DataFrame | None = None,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    session: requests.Session | None = None,
    chunksize: int = 25,
    output_type: OutputType = "pandas",
    max_workers: int | None = None,
) -> Frame:
    """Read Moscow Exchange prices. See :class:`~kuznets.moex.MoexReader`."""
    return MoexReader(
        symbols=symbols,
        start=start,
        end=end,
        retry_count=retry_count,
        pause=pause,
        session=session,
        chunksize=chunksize,
        output_type=output_type,
        max_workers=max_workers,
    ).read()


@overload
def get_data_stooq(
    symbols: Symbols | DataFrame | None = None,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    session: requests.Session | None = None,
    chunksize: int = 25,
    output_type: Literal["pandas"] = "pandas",
    max_workers: int | None = None,
) -> DataFrame: ...
@overload
def get_data_stooq(
    symbols: Symbols | DataFrame | None = None,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    session: requests.Session | None = None,
    chunksize: int = 25,
    output_type: BackendName = ...,
    max_workers: int | None = None,
) -> Frame: ...
def get_data_stooq(
    symbols: Symbols | DataFrame | None = None,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    session: requests.Session | None = None,
    chunksize: int = 25,
    output_type: OutputType = "pandas",
    max_workers: int | None = None,
) -> Frame:
    """Read Stooq daily prices. See :class:`~kuznets.stooq.StooqDailyReader`."""
    return StooqDailyReader(
        symbols=symbols,
        start=start,
        end=end,
        retry_count=retry_count,
        pause=pause,
        session=session,
        chunksize=chunksize,
        output_type=output_type,
        max_workers=max_workers,
    ).read()


@overload
def get_data_tiingo(
    symbols: Symbols,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    timeout: float | None = None,
    session: requests.Session | None = None,
    freq: str | None = None,
    api_key: str | None = None,
    output_type: Literal["pandas"] = "pandas",
) -> DataFrame: ...
@overload
def get_data_tiingo(
    symbols: Symbols,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    timeout: float | None = None,
    session: requests.Session | None = None,
    freq: str | None = None,
    api_key: str | None = None,
    output_type: BackendName = ...,
) -> Frame: ...
def get_data_tiingo(
    symbols: Symbols,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    timeout: float | None = None,
    session: requests.Session | None = None,
    freq: str | None = None,
    api_key: str | None = None,
    output_type: OutputType = "pandas",
) -> Frame:
    """Read Tiingo daily prices. See :class:`~kuznets.tiingo.TiingoDailyReader`."""
    return TiingoDailyReader(
        symbols=symbols,
        start=start,
        end=end,
        retry_count=retry_count,
        pause=pause,
        timeout=timeout,
        session=session,
        freq=freq,
        api_key=api_key,
        output_type=output_type,
    ).read()


@overload
def get_iex_data_tiingo(
    symbols: Symbols,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    timeout: float | None = None,
    session: requests.Session | None = None,
    freq: str | None = None,
    api_key: str | None = None,
    output_type: Literal["pandas"] = "pandas",
) -> DataFrame: ...
@overload
def get_iex_data_tiingo(
    symbols: Symbols,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    timeout: float | None = None,
    session: requests.Session | None = None,
    freq: str | None = None,
    api_key: str | None = None,
    output_type: BackendName = ...,
) -> Frame: ...
def get_iex_data_tiingo(
    symbols: Symbols,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    timeout: float | None = None,
    session: requests.Session | None = None,
    freq: str | None = None,
    api_key: str | None = None,
    output_type: OutputType = "pandas",
) -> Frame:
    """Read Tiingo IEX intraday history. See :class:`~kuznets.tiingo.TiingoIEXHistoricalReader`."""
    return TiingoIEXHistoricalReader(
        symbols=symbols,
        start=start,
        end=end,
        retry_count=retry_count,
        pause=pause,
        timeout=timeout,
        session=session,
        freq=freq,
        api_key=api_key,
        output_type=output_type,
    ).read()


@overload
def get_quotes_tiingo(
    symbols: Symbols,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    timeout: float | None = None,
    session: requests.Session | None = None,
    freq: str | None = None,
    api_key: str | None = None,
    output_type: Literal["pandas"] = "pandas",
) -> DataFrame: ...
@overload
def get_quotes_tiingo(
    symbols: Symbols,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    timeout: float | None = None,
    session: requests.Session | None = None,
    freq: str | None = None,
    api_key: str | None = None,
    output_type: BackendName = ...,
) -> Frame: ...
def get_quotes_tiingo(
    symbols: Symbols,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    timeout: float | None = None,
    session: requests.Session | None = None,
    freq: str | None = None,
    api_key: str | None = None,
    output_type: OutputType = "pandas",
) -> Frame:
    """Read Tiingo symbol metadata. See :class:`~kuznets.tiingo.TiingoQuoteReader`."""
    return TiingoQuoteReader(
        symbols=symbols,
        start=start,
        end=end,
        retry_count=retry_count,
        pause=pause,
        timeout=timeout,
        session=session,
        freq=freq,
        api_key=api_key,
        output_type=output_type,
    ).read()


@overload
def get_exchange_rate_av(
    symbols: Symbols | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    session: requests.Session | None = None,
    api_key: str | None = None,
    output_type: Literal["pandas"] = "pandas",
) -> DataFrame: ...
@overload
def get_exchange_rate_av(
    symbols: Symbols | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    session: requests.Session | None = None,
    api_key: str | None = None,
    output_type: BackendName = ...,
) -> Frame: ...
def get_exchange_rate_av(
    symbols: Symbols | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    session: requests.Session | None = None,
    api_key: str | None = None,
    output_type: OutputType = "pandas",
) -> Frame:
    """Read an Alpha Vantage exchange rate. See :class:`~kuznets.av.forex.AVForexReader`."""
    return AVForexReader(
        symbols=symbols,
        retry_count=retry_count,
        pause=pause,
        session=session,
        api_key=api_key,
        output_type=output_type,
    ).read()


@overload
def DataReader(
    name: Symbols,
    data_source: str | None = None,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    session: requests.Session | None = None,
    api_key: str | None = None,
    headers: Headers | None = None,
    output_type: Literal["pandas"] = "pandas",
    max_workers: int | None = None,
    dataflow: str | None = None,
) -> DataFrame: ...
@overload
def DataReader(
    name: Symbols,
    data_source: str | None = None,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    session: requests.Session | None = None,
    api_key: str | None = None,
    headers: Headers | None = None,
    output_type: BackendName = ...,
    max_workers: int | None = None,
    dataflow: str | None = None,
) -> Frame: ...
def DataReader(
    name: Symbols,
    data_source: str | None = None,
    start: DateLike | None = None,
    end: DateLike | None = None,
    retry_count: int | None = None,
    pause: float | None = None,
    session: requests.Session | None = None,
    api_key: str | None = None,
    headers: Headers | None = None,
    output_type: OutputType = "pandas",
    max_workers: int | None = None,
    dataflow: str | None = None,
) -> Frame:
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
    dataflow : str, optional
        Dataflow to read, for sources that serve many under one name. Required by ``'imf'`` and
        ``'ilostat'``, where *name* selects the country, e.g.
        ``DataReader('ZMB', 'imf', dataflow='CPI')``. Ignored elsewhere. Default None.

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
    if data_source not in _DATA_SOURCES:
        msg = f"data_source={data_source!r} is not implemented"
        raise NotImplementedError(msg)

    backend = validate_output_type(output_type)

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
            output_type=backend,
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
            output_type=backend,
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
            output_type=backend,
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
            output_type=backend,
        ).read()

    elif data_source == "famafrench":
        return FamaFrenchReader(
            symbols=name,
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            output_type=backend,
        ).read()

    elif data_source == "oecd":
        return OECDReader(
            symbols=name,
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            output_type=backend,
        ).read()
    elif data_source == "eurostat":
        return EurostatReader(
            symbols=name,
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            output_type=backend,
        ).read()
    elif data_source == "ilostat":
        if not dataflow:
            raise ValueError(
                "Reading from 'ilostat' needs a dataflow, e.g. "
                "DataReader('ZMB', 'ilostat', dataflow='DF_EAR_CMTA_SEX_CUR_NB')"
            )
        return ILOSTATReader(
            dataflow=dataflow,
            selections={"REF_AREA": name},
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            headers=headers,
            output_type=backend,
        ).read()
    elif data_source == "imf":
        if not dataflow:
            raise ValueError("Reading from 'imf' needs a dataflow, e.g. DataReader('ZMB', 'imf', dataflow='CPI')")
        return IMFReader(
            dataflow=dataflow,
            selections={"COUNTRY": name},
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            headers=headers,
            output_type=backend,
        ).read()
    elif data_source == "imts":
        return IMTSReader(
            symbols=name,
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            headers=headers,
            output_type=backend,
        ).read()
    elif data_source == "nasdaq":
        if name != "symbols":
            raise ValueError(f"Only the string 'symbols' is supported for Nasdaq, not {name!r}")
        nasdaq_symbols = get_nasdaq_symbols(retry_count=retry_count, pause=pause)
        if backend == PANDAS:
            return nasdaq_symbols
        tidy, _ = detach_index(nasdaq_symbols)
        return from_pandas(tidy, backend)

    elif data_source == "quandl":
        return QuandlReader(
            symbols=name,
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            api_key=api_key,
            output_type=backend,
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
            output_type=backend,
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
            output_type=backend,
        ).read()

    elif data_source == "yahoo-actions":
        return YahooActionReader(
            symbols=name,
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            output_type=backend,
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
            output_type=backend,
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
            output_type=backend,
            max_workers=max_workers,
        ).read()

    elif data_source == "av-forex":
        return AVForexReader(
            symbols=name,
            retry_count=retry_count,
            pause=pause,
            session=session,
            api_key=api_key,
            output_type=backend,
        ).read()

    elif data_source == "av-forex-daily":
        return AVTimeSeriesReader(
            symbols=_single_symbol(name, data_source),
            function="FX_DAILY",
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            api_key=api_key,
            output_type=backend,
        ).read()

    elif data_source == "av-daily":
        return AVTimeSeriesReader(
            symbols=_single_symbol(name, data_source),
            function="TIME_SERIES_DAILY",
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            api_key=api_key,
            output_type=backend,
        ).read()

    elif data_source == "av-daily-adjusted":
        return AVTimeSeriesReader(
            symbols=_single_symbol(name, data_source),
            function="TIME_SERIES_DAILY_ADJUSTED",
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            api_key=api_key,
            output_type=backend,
        ).read()

    elif data_source == "av-weekly":
        return AVTimeSeriesReader(
            symbols=_single_symbol(name, data_source),
            function="TIME_SERIES_WEEKLY",
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            api_key=api_key,
            output_type=backend,
        ).read()

    elif data_source == "av-weekly-adjusted":
        return AVTimeSeriesReader(
            symbols=_single_symbol(name, data_source),
            function="TIME_SERIES_WEEKLY_ADJUSTED",
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            api_key=api_key,
            output_type=backend,
        ).read()

    elif data_source == "av-monthly":
        return AVTimeSeriesReader(
            symbols=_single_symbol(name, data_source),
            function="TIME_SERIES_MONTHLY",
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            api_key=api_key,
            output_type=backend,
        ).read()

    elif data_source == "av-monthly-adjusted":
        return AVTimeSeriesReader(
            symbols=_single_symbol(name, data_source),
            function="TIME_SERIES_MONTHLY_ADJUSTED",
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            api_key=api_key,
            output_type=backend,
        ).read()

    elif data_source == "av-intraday":
        return AVTimeSeriesReader(
            symbols=_single_symbol(name, data_source),
            function="TIME_SERIES_INTRADAY",
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            api_key=api_key,
            output_type=backend,
        ).read()

    elif data_source == "econdb":
        return EcondbReader(
            symbols=_single_symbol(name, data_source),
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            output_type=backend,
        ).read()

    elif data_source == "naver":
        return NaverDailyReader(
            symbols=name,
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
            output_type=backend,
            max_workers=max_workers,
        ).read()

    else:
        msg = f"data_source={data_source!r} is not implemented"
        raise NotImplementedError(msg)
