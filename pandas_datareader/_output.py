import importlib.util

PANDAS = "pandas"

# Canonical backend name -> (module probed for availability, pip extra that installs it). pandas is
# absent here because it is a hard dependency and needs no availability check.
_OPTIONAL_BACKENDS = {
    "polars": ("polars", "polars"),
    "pyarrow": ("pyarrow", "pyarrow"),
    "dask": ("dask.dataframe", "dask"),
}
_ALIASES = {"arrow": "pyarrow"}


def validate_output_type(output_type: str) -> str:
    """Canonicalize an ``output_type`` value and verify its backend is importable.

    Call before issuing any network request so an invalid value or missing backend fails fast.

    Parameters
    ----------
    output_type : str
        Requested output backend, case-insensitive. One of 'pandas', 'polars', 'pyarrow' (alias
        'arrow'), or 'dask'.

    Returns
    -------
    str
        The canonical backend name.

    Raises
    ------
    TypeError
        If ``output_type`` is not a str.
    ValueError
        If ``output_type`` does not name a recognized backend.
    ImportError
        If the backend is recognized but its package is not installed.
    """
    if not isinstance(output_type, str):
        raise TypeError(f"output_type must be a str, got {type(output_type).__name__}")
    lowered = output_type.lower()
    canonical = _ALIASES.get(lowered, lowered)
    if canonical == PANDAS:
        return canonical
    if canonical not in _OPTIONAL_BACKENDS:
        valid = ", ".join(repr(name) for name in sorted([PANDAS, *_OPTIONAL_BACKENDS, *_ALIASES]))
        raise ValueError(f"output_type={output_type!r} is not supported; choose one of {valid}")
    _require_backend(canonical)
    return canonical


def _require_backend(canonical: str) -> None:
    """Raise a helpful ImportError if the package backing *canonical* is not installed."""
    module, extra = _OPTIONAL_BACKENDS[canonical]
    package = module.partition(".")[0]
    try:
        missing = importlib.util.find_spec(module) is None
    except ModuleNotFoundError:
        # find_spec on a dotted name (dask.dataframe) raises when the parent package is absent.
        missing = True
    if missing:
        raise ImportError(
            f"output_type={canonical!r} requires the optional dependency {package!r}. "
            f"Install it with 'pip install {package}' or 'pip install pandas-datareader[{extra}]'."
        )
