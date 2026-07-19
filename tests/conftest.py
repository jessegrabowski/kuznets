from pathlib import Path

import pytest

from kuznets import config


@pytest.fixture(autouse=True)
def isolate_config(monkeypatch):
    """Reset global config state so tests never read the developer's ``~/.config`` or leak options.

    Resets ``options`` and points the config file at a nonexistent path. API-key environment
    variables are deliberately left intact so live API tests can still read keys from the
    environment; tests that need a clean environment clear specific vars themselves.
    """
    config.options.reset()
    monkeypatch.setenv("KUZNETS_CONFIG", "/nonexistent/kuznets.toml")
    config.reload_config()
    yield
    config.options.reset()
    monkeypatch.setenv("KUZNETS_CONFIG", "/nonexistent/kuznets.toml")
    config.reload_config()


def pytest_addoption(parser):
    parser.addoption("--only-stable", action="store_true", help="run only stable tests")
    parser.addoption(
        "--skip-requires-api-key",
        action="store_true",
        help="skip tests that require an API key",
    )
    parser.addoption(
        "--strict-data-files",
        action="store_true",
        help="Fail if a test is skipped for missing data file.",
    )


def pytest_runtest_setup(item):
    if "stable" not in item.keywords and item.config.getoption("--only-stable"):
        pytest.skip("skipping due to --only-stable")

    if "requires_api_key" in item.keywords and item.config.getoption("--skip-requires-api-key"):
        pytest.skip("skipping due to --skip-requires-api-key")


@pytest.fixture
def datapath(request):
    """Get the path to a data file.

    Parameters
    ----------
    path : str
        Path to the file, relative to ``tests/``

    Returns
    -------
    path : Path
        Path including ``tests/``.

    Raises
    ------
    ValueError
        If the path doesn't exist and the --strict-data-files option is set.
    """
    base_path = Path(__file__).parent

    def deco(*args):
        path = base_path.joinpath(*args)
        if not path.exists():
            if request.config.getoption("--strict-data-files"):
                msg = "Could not find file {} and --strict-data-files is set."
                raise ValueError(msg.format(path))
            else:
                msg = "Could not find {}."
                pytest.skip(msg.format(path))
        return path

    return deco
