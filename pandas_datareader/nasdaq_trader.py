from ftplib import FTP, all_errors
import time
import warnings

from pandas import DataFrame, read_csv

from pandas_datareader._utils import RemoteDataError
from pandas_datareader.compat import StringIO

_NASDAQ_TICKER_LOC = "/SymbolDirectory/nasdaqtraded.txt"
_NASDAQ_FTP_SERVER = "ftp.nasdaqtrader.com"
_TICKER_DTYPE = [
    ("Nasdaq Traded", bool),
    ("Symbol", str),
    ("Security Name", str),
    ("Listing Exchange", str),
    ("Market Category", str),
    ("ETF", bool),
    ("Round Lot Size", float),
    ("Test Issue", bool),
    ("Financial Status", str),
    ("CQS Symbol", str),
    ("NASDAQ Symbol", str),
    ("NextShares", bool),
]
_CATEGORICAL = ("Listing Exchange", "Financial Status")

_DELIMITER = "|"
_ticker_cache = None


def _bool_converter(item: str) -> bool:
    return item == "Y"


def _download_nasdaq_symbols(timeout: float) -> DataFrame:
    """
    Download Nasdaq symbol data via FTP.

    Parameters
    ----------
    timeout : float
        The time to wait for the FTP connection.

    Returns
    -------
    df : DataFrame
    """
    try:
        ftp_session = FTP(_NASDAQ_FTP_SERVER, timeout=timeout)
        ftp_session.login()
    except all_errors as err:
        raise RemoteDataError(f"Error connecting to {_NASDAQ_FTP_SERVER!r}: {err}") from err

    lines = []
    try:
        ftp_session.retrlines("RETR " + _NASDAQ_TICKER_LOC, lines.append)
    except all_errors as err:
        raise RemoteDataError(f"Error downloading from {_NASDAQ_FTP_SERVER!r}: {err}") from err
    finally:
        ftp_session.close()

    # Sanity Checking
    if not lines[-1].startswith("File Creation Time:"):
        raise RemoteDataError(f"Missing expected footer. Found {lines[-1]!r}")

    # Convert Y/N to True/False.
    converter_map = {col: _bool_converter for col, t in _TICKER_DTYPE if t is bool}

    # For pandas >= 0.20.0, the Python parser issues a warning if
    # both a converter and dtype are specified for the same column.
    # However, this measure is probably temporary until the read_csv
    # behavior is better formalized.
    with warnings.catch_warnings(record=True):
        data = read_csv(
            StringIO("\n".join(lines[:-1])),
            sep="|",
            dtype=_TICKER_DTYPE,
            converters=converter_map,
            index_col=1,
        )

    # Properly cast enumerations
    for cat in _CATEGORICAL:
        data[cat] = data[cat].astype("category")

    return data


def get_nasdaq_symbols(
    retry_count: int = 3,
    timeout: float = 30,
    pause: float | None = None,
) -> DataFrame:
    """
    Get the list of all available equity symbols from Nasdaq.

    Parameters
    ----------
    retry_count : int, default 3
        Number of times to retry query request.
    timeout : float, default 30
        Time, in seconds, to wait for the FTP connection.
    pause : float, optional
        Time, in seconds, to pause between retries. Defaults to timeout / 3.

    Returns
    -------
    df : DataFrame
        DataFrame with company tickers, names, and other properties.
    """
    global _ticker_cache

    if timeout < 0:
        raise ValueError(f"timeout must be >= 0, not {timeout!r}")

    if pause is None:
        pause = timeout / 3
    elif pause < 0:
        raise ValueError(f"pause must be >= 0, not {pause!r}")

    if _ticker_cache is None:
        while retry_count > 0:
            try:
                _ticker_cache = _download_nasdaq_symbols(timeout=timeout)
                retry_count = -1
            except RemoteDataError:
                # retry on any exception
                retry_count -= 1
                if retry_count <= 0:
                    raise
                else:
                    time.sleep(pause)

    return _ticker_cache
