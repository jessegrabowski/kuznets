import ftplib
from pathlib import Path

import pytest

from pandas_datareader import data as web, nasdaq_trader
from pandas_datareader._utils import RemoteDataError
from tests._mock import RECORD

pytestmark = pytest.mark.stable

_SAMPLE_SYMBOLS = {"AAPL", "IBM", "MSFT", "SPY"}


class _FakeFTP:
    """Replay a captured ``nasdaqtraded.txt`` over the FTP interface the reader uses."""

    def __init__(self, lines):
        self._lines = lines

    def __call__(self, server, timeout=None):
        return self

    def login(self):
        pass

    def retrlines(self, cmd, callback):
        for line in self._lines:
            callback(line)

    def close(self):
        pass


@pytest.fixture(autouse=True)
def clear_ticker_cache(monkeypatch):
    monkeypatch.setattr(nasdaq_trader, "_ticker_cache", None)
    # Don't actually wait through the retry backoff when a download fails.
    monkeypatch.setattr(nasdaq_trader.time, "sleep", lambda seconds: None)


class TestNasdaqOffline:
    def test_symbols_are_parsed(self, monkeypatch, datapath):
        lines = datapath("data", "nasdaq", "nasdaqtraded.txt")
        with open(lines) as fh:
            text = fh.read().splitlines()
        monkeypatch.setattr(nasdaq_trader, "FTP", _FakeFTP(text))

        symbols = web.DataReader("symbols", "nasdaq")
        assert "IBM" in symbols.index
        assert symbols.loc["SPY", "ETF"]
        assert not symbols.loc["IBM", "ETF"]

    def test_missing_footer_raises(self, monkeypatch):
        monkeypatch.setattr(nasdaq_trader, "FTP", _FakeFTP(["Nasdaq Traded|Symbol", "Y|IBM"]))
        with pytest.raises(RemoteDataError):
            web.DataReader("symbols", "nasdaq")


@pytest.mark.network
class TestNasdaqLive:
    def test_symbols_shape(self, datapath):
        try:
            ftp = ftplib.FTP(nasdaq_trader._NASDAQ_FTP_SERVER, timeout=15)
            ftp.login()
            lines = []
            ftp.retrlines("RETR " + nasdaq_trader._NASDAQ_TICKER_LOC, lines.append)
            ftp.close()
        except ftplib.all_errors as err:
            if RECORD:
                raise
            pytest.skip(f"Nasdaq FTP unreachable: {err}")

        assert lines[0].startswith("Nasdaq Traded|Symbol|")
        assert lines[-1].startswith("File Creation Time:")
        symbols = {line.split("|")[1] for line in lines[1:-1]}
        assert "IBM" in symbols

        if RECORD:
            # Trim the ~12k-row feed to a real sample: header + a few known symbols + footer.
            sample = [lines[0]]
            sample += [line for line in lines[1:-1] if line.split("|")[1] in _SAMPLE_SYMBOLS]
            sample.append(lines[-1])
            Path(datapath("data", "nasdaq", "nasdaqtraded.txt")).write_text("\n".join(sample) + "\n")
