import pytest

from pandas_datareader import data as web
from pandas_datareader.moex import MoexReader
from tests._backends import BACKENDS, as_narwhals, skip_unless_installed
from tests._mock import from_fixtures, patch_session_get, service_up, tolerate_outage

pytestmark = pytest.mark.stable

# The history URL is checked before the metadata URL because both end in ``securities/<SEC>.csv``.
_META_URL = "https://iss.moex.com/iss/securities/SBER.csv"


def _moex_fixtures(datapath):
    # The reader walks one history URL per (market, engine) the metadata lists; all are served the
    # same captured shares-market response, and read() then filters to the primary board. That
    # many-URLs-to-one-file shape is why the live test below doesn't record.
    return from_fixtures(
        {
            "/history/": datapath("data", "moex", "sber_history.csv"),
            "securities/SBER.csv": datapath("data", "moex", "sber_meta.csv"),
        }
    )


class TestMoexOffline:
    def test_single_symbol_primary_board(self, monkeypatch, datapath):
        patch_session_get(monkeypatch, _moex_fixtures(datapath))
        df = web.DataReader("SBER", "moex", start="2020-07-14", end="2020-07-14")

        assert "SECID" in df.columns
        assert len(df) == 1
        # read() keeps only the primary board (TQBR), dropping the SMAL row in the fixture.
        assert set(df["BOARDID"]) == {"TQBR"}


@pytest.mark.network
class TestMoexLive:
    def test_single_symbol_shape(self):
        if not service_up(_META_URL):
            pytest.skip("MOEX endpoint unreachable")
        with tolerate_outage():
            df = web.DataReader("SBER", "moex", start="2020-07-14", end="2020-07-14")
            assert "SECID" in df.columns
            assert "BOARDID" in df.columns
            assert len(df) > 0


class TestMoexBackends:
    @pytest.mark.parametrize("output_type", BACKENDS)
    def test_primary_board_tidy_schema(self, monkeypatch, datapath, output_type):
        skip_unless_installed(output_type)
        patch_session_get(monkeypatch, _moex_fixtures(datapath))

        as_pandas = web.DataReader("SBER", "moex", start="2020-07-14", end="2020-07-14")
        tidy = as_narwhals(
            web.DataReader("SBER", "moex", start="2020-07-14", end="2020-07-14", output_type=output_type)
        )

        assert tidy.columns[0] == "TRADEDATE"
        assert {"SECID", "BOARDID"} <= set(tidy.columns)
        assert len(tidy) == len(as_pandas)
        assert tidy["BOARDID"].to_list() == as_pandas["BOARDID"].tolist()

    @pytest.mark.parametrize("output_type", BACKENDS)
    def test_read_all_boards_honors_output_type(self, monkeypatch, datapath, output_type):
        skip_unless_installed(output_type)
        patch_session_get(monkeypatch, _moex_fixtures(datapath))

        as_pandas = MoexReader("SBER", start="2020-07-14", end="2020-07-14").read_all_boards()
        reader = MoexReader("SBER", start="2020-07-14", end="2020-07-14", output_type=output_type)
        tidy = as_narwhals(reader.read_all_boards())

        assert tidy.columns[0] == "TRADEDATE"
        assert len(tidy) == len(as_pandas)
        assert sorted(set(tidy["BOARDID"].to_list())) == sorted(set(as_pandas["BOARDID"]))
