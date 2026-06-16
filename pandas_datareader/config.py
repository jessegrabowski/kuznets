import os
from pathlib import Path
import tomllib
import warnings

# Map a reader's short source name to the environment variable holding its API key.
API_KEY_ENV_VARS = {
    "fred": "FRED_API_KEY",
    "alphavantage": "ALPHAVANTAGE_API_KEY",
    "quandl": "QUANDL_API_KEY",
    "tiingo": "TIINGO_API_KEY",
}

# Built-in fallbacks for scalar settings, used when no layer supplies a value.
_SETTING_DEFAULTS = {"retry_count": 3, "pause": 0.1, "timeout": 30.0}


class _Options:
    """Runtime configuration for pandas-datareader.

    Set attributes on the module-level :data:`options` instance to influence every reader without
    threading arguments through each call. Each attribute sits between an explicit call argument
    (which always wins) and the environment / config-file layers. A ``None`` scalar or empty
    container means "unset", so lower-precedence layers and the built-in defaults still apply.

    Attributes
    ----------
    api_keys : dict mapping str to str
        Source name (e.g. ``'fred'``) to API key. Overrides the matching environment variable.
    headers : dict mapping str to str
        Default request headers merged into every session. Pass a ``User-Agent`` here to identify
        as something other than ``pandas-datareader``.
    retry_count : int or None
        Default retry count for transient request failures.
    pause : float or None
        Default backoff factor, in seconds, between retries.
    timeout : float or None
        Default per-request timeout, in seconds.
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        """Restore every option to its unset state."""
        self.api_keys: dict[str, str] = {}
        self.headers: dict[str, str] = {}
        self.retry_count: int | None = None
        self.pause: float | None = None
        self.timeout: float | None = None


options = _Options()

_UNLOADED = object()
_config_cache = _UNLOADED


def config_path() -> Path:
    """Return the config file path.

    Honor ``PANDAS_DATAREADER_CONFIG`` if set, otherwise fall back to
    ``$XDG_CONFIG_HOME/pandas-datareader/config.toml`` (and ``~/.config`` when ``XDG_CONFIG_HOME``
    is unset).

    Returns
    -------
    path : Path
        Location the config file is read from. The file need not exist.
    """
    override = os.getenv("PANDAS_DATAREADER_CONFIG")
    if override:
        return Path(override).expanduser()
    base = os.getenv("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "pandas-datareader" / "config.toml"


def _file_config() -> dict:
    """Return the parsed config file, caching the result.

    A missing file yields an empty mapping. An unreadable or malformed file warns and is treated as
    empty so a bad config never hard-fails a request.
    """
    global _config_cache
    if _config_cache is not _UNLOADED:
        return _config_cache
    path = config_path()
    data: dict = {}
    if path.is_file():
        try:
            with open(path, "rb") as fh:
                data = tomllib.load(fh)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            warnings.warn(f"Ignoring unreadable pandas-datareader config at {path}: {exc}", stacklevel=2)
    _config_cache = data
    return data


def reload_config() -> dict:
    """Drop the cached config file and re-read it from disk.

    Returns
    -------
    config : dict
        The freshly parsed config.
    """
    global _config_cache
    _config_cache = _UNLOADED
    return _file_config()


def get_api_key(source: str, api_key: str | None = None, required: bool = True) -> str | None:
    """Resolve an API key for *source* across the configuration layers.

    Precedence, highest first: the *api_key* argument, ``options.api_keys[source]``, the source's
    environment variable, then the ``[api_keys]`` table of the config file.

    Parameters
    ----------
    source : str
        Short source name, e.g. ``'fred'`` or ``'tiingo'``.
    api_key : str, optional
        Explicit key supplied at the call site, taking precedence over every other layer.
    required : bool, optional
        Raise ``ValueError`` when no key is found. Pass False for sources where the key is optional
        (e.g. FRED, which falls back to a keyless endpoint). Default True.

    Returns
    -------
    api_key : str or None
        The resolved key, or ``None`` when none is found and *required* is False.

    Raises
    ------
    ValueError
        If no key is found and *required* is True.
    TypeError
        If a resolved key is not a string.
    """
    for candidate in (
        api_key,
        options.api_keys.get(source),
        os.getenv(API_KEY_ENV_VARS.get(source, "")),
        _file_config().get("api_keys", {}).get(source),
    ):
        if candidate:
            if not isinstance(candidate, str):
                raise TypeError(f"API key for {source!r} must be a string, got {type(candidate).__name__}.")
            return candidate
    if required:
        env = API_KEY_ENV_VARS.get(source, f"{source.upper()}_API_KEY")
        raise ValueError(
            f"No API key found for {source!r}. Provide it via the api_key argument, "
            f"pandas_datareader.options.api_keys[{source!r}], the {env} environment variable, "
            f"or an [api_keys] entry in {config_path()}."
        )
    return None


def get_headers(headers: dict | None = None) -> dict | None:
    """Merge default request headers across the configuration layers.

    Layers are merged low precedence to high: the config file's ``[headers]`` table, then
    ``options.headers``, then the *headers* argument. Later layers override individual keys.

    Parameters
    ----------
    headers : dict, optional
        Explicit headers supplied at the call site, taking precedence over every other layer.

    Returns
    -------
    headers : dict or None
        The merged headers, or ``None`` when no layer supplies any.
    """
    merged: dict = {}
    merged.update(_file_config().get("headers", {}))
    if options.headers:
        merged.update(options.headers)
    if headers:
        merged.update(headers)
    return merged or None


def get_setting(name: str, value: int | float | None = None) -> int | float:
    """Resolve a scalar setting (``retry_count``, ``pause``, ``timeout``) across the layers.

    Precedence, highest first: the *value* argument, the matching ``options`` attribute, the
    ``[defaults]`` table of the config file, then the built-in default.

    Parameters
    ----------
    name : str
        Setting name; one of the keys in ``[defaults]``.
    value : int or float, optional
        Explicit value supplied at the call site. ``None`` means "unset".

    Returns
    -------
    setting : int or float
        The resolved setting.
    """
    if value is not None:
        return value
    runtime = getattr(options, name)
    if runtime is not None:
        return runtime
    file_value = _file_config().get("defaults", {}).get(name)
    if file_value is not None:
        return file_value
    return _SETTING_DEFAULTS[name]
