import pytest

from kuznets import config

pytestmark = pytest.mark.stable


@pytest.fixture(autouse=True)
def clear_api_key_env(monkeypatch):
    """Clear API-key env vars so precedence tests control the environment layer explicitly."""
    for env in config.API_KEY_ENV_VARS.values():
        monkeypatch.delenv(env, raising=False)


def _write_config(tmp_path, monkeypatch, body):
    path = tmp_path / "config.toml"
    path.write_text(body)
    monkeypatch.setenv("KUZNETS_CONFIG", str(path))
    config.reload_config()
    return path


class TestApiKeyResolution:
    def test_explicit_wins(self, monkeypatch):
        monkeypatch.setenv("FRED_API_KEY", "env")
        config.options.api_keys["fred"] = "opt"
        assert config.get_api_key("fred", "explicit") == "explicit"

    def test_options_beat_env(self, monkeypatch):
        monkeypatch.setenv("FRED_API_KEY", "env")
        config.options.api_keys["fred"] = "opt"
        assert config.get_api_key("fred") == "opt"

    def test_env_beats_file(self, tmp_path, monkeypatch):
        _write_config(tmp_path, monkeypatch, '[api_keys]\nfred = "file"\n')
        monkeypatch.setenv("FRED_API_KEY", "env")
        assert config.get_api_key("fred") == "env"

    def test_file_is_lowest(self, tmp_path, monkeypatch):
        _write_config(tmp_path, monkeypatch, '[api_keys]\nfred = "file"\n')
        assert config.get_api_key("fred") == "file"

    def test_optional_returns_none(self):
        assert config.get_api_key("fred", required=False) is None

    def test_required_raises_with_guidance(self):
        with pytest.raises(ValueError, match="TIINGO_API_KEY"):
            config.get_api_key("tiingo")

    def test_non_string_key_raises(self):
        config.options.api_keys["fred"] = 1234
        with pytest.raises(TypeError):
            config.get_api_key("fred")


class TestHeaderResolution:
    def test_empty_by_default(self):
        assert config.get_headers() is None

    def test_merge_precedence(self, tmp_path, monkeypatch):
        _write_config(tmp_path, monkeypatch, '[headers]\nUser-Agent = "file"\nX-File = "1"\n')
        config.options.headers = {"User-Agent": "opt"}
        merged = config.get_headers({"Accept": "json"})
        assert merged == {"User-Agent": "opt", "X-File": "1", "Accept": "json"}


class TestSettingResolution:
    def test_default_when_unset(self):
        assert config.get_setting("retry_count") == 3
        assert config.get_setting("pause") == 0.1
        assert config.get_setting("timeout") == 30.0

    def test_explicit_wins(self):
        config.options.timeout = 50
        assert config.get_setting("timeout", 5) == 5

    def test_options_beat_file(self, tmp_path, monkeypatch):
        _write_config(tmp_path, monkeypatch, "[defaults]\ntimeout = 10\n")
        config.options.timeout = 50
        assert config.get_setting("timeout") == 50

    def test_file_beats_default(self, tmp_path, monkeypatch):
        _write_config(tmp_path, monkeypatch, "[defaults]\ntimeout = 10\n")
        assert config.get_setting("timeout") == 10


class TestConfigFile:
    def test_missing_file_is_empty(self):
        assert config.reload_config() == {}

    def test_malformed_file_warns_and_is_empty(self, tmp_path, monkeypatch):
        path = tmp_path / "config.toml"
        path.write_text("this is = = not toml")
        monkeypatch.setenv("KUZNETS_CONFIG", str(path))
        with pytest.warns(UserWarning, match="unreadable"):
            assert config.reload_config() == {}

    def test_path_override_env(self, monkeypatch):
        monkeypatch.setenv("KUZNETS_CONFIG", "/some/where/x.toml")
        # as_posix() normalizes separators so the assertion holds on Windows too.
        assert config.config_path().as_posix() == "/some/where/x.toml"

    def test_path_default_xdg(self, monkeypatch):
        monkeypatch.delenv("KUZNETS_CONFIG", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", "/cfg")
        assert config.config_path().as_posix() == "/cfg/kuznets/config.toml"

    def test_path_default_home(self, monkeypatch):
        monkeypatch.delenv("KUZNETS_CONFIG", raising=False)
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        monkeypatch.setattr(config.Path, "home", classmethod(lambda cls: config.Path("/home/me")))
        assert config.config_path().as_posix() == "/home/me/.config/kuznets/config.toml"
