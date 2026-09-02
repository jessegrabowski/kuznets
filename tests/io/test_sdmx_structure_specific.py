import pytest

from kuznets.io import build_sdmx_key

pytestmark = pytest.mark.stable


@pytest.mark.parametrize(
    "selections, expected",
    [
        (["LAO", "XG_FOB_USD", "THA", "A"], "LAO.XG_FOB_USD.THA.A"),
        (["LAO", "XG_FOB_USD", None, "A"], "LAO.XG_FOB_USD..A"),
        (["LAO", "XG_FOB_USD", "THA", None], "LAO.XG_FOB_USD.THA."),
        ([["LAO", "THA"], ["XG_FOB_USD", "MG_FOB_USD"], None, "A"], "LAO+THA.XG_FOB_USD+MG_FOB_USD..A"),
        (["LAO", "XG_FOB_USD", [], "A"], "LAO.XG_FOB_USD..A"),
    ],
)
def test_build_sdmx_key(selections, expected):
    assert build_sdmx_key(selections) == expected
