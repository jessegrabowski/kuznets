import importlib.util

import narwhals.stable.v2 as nw
import pandas as pd

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


def detach_index(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Move a frame's index into ordinary columns.

    An unnamed datetime-like index is named ``Date``; any other unnamed index is named ``index``;
    unnamed MultiIndex levels get ``level_{position}`` names. The returned names let a pandas
    presenter restore today's index via :func:`attach_index`.

    Parameters
    ----------
    df : DataFrame
        Frame whose index carries meaning (dates, symbols, dimension levels).

    Returns
    -------
    tuple of (DataFrame, list of str)
        The index-free frame and the column names the index became, in level order.
    """
    index = df.index
    if isinstance(index, pd.MultiIndex):
        names = [name if name is not None else f"level_{position}" for position, name in enumerate(index.names)]
        index = index.set_names(names)
    else:
        if index.name is None:
            fallback = "Date" if isinstance(index, pd.DatetimeIndex | pd.PeriodIndex) else "index"
            index = index.rename(fallback)
        names = [index.name]
    return df.set_axis(index, axis=0).reset_index(), names


def attach_index(df: pd.DataFrame, index_cols: list[str]) -> pd.DataFrame:
    """Restore columns produced by :func:`detach_index` as the frame's index.

    Parameters
    ----------
    df : DataFrame
        Tidy frame containing every column named in ``index_cols``.
    index_cols : list of str
        Column names to promote, in level order.

    Returns
    -------
    DataFrame
        Frame indexed by ``index_cols`` (a MultiIndex when more than one name is given).
    """
    return df.set_index(index_cols[0] if len(index_cols) == 1 else index_cols)


def from_pandas(df: pd.DataFrame, output_type: str):
    """Convert a tidy pandas frame to the requested backend.

    The tidy contract is enforced, not repaired: an index that carries data (MultiIndex, named
    index, or datetime-like index) raises, because the narwhals backends disagree on whether to
    keep or drop it -- callers must run :func:`detach_index` first. A leftover positional index
    (e.g. non-contiguous after a boolean filter) is silently discarded. Non-string column labels
    are cast to str, and all-null object columns to float64, since polars and pyarrow accept
    neither.

    Parameters
    ----------
    df : DataFrame
        Tidy frame: data in columns only.
    output_type : str
        Canonical backend name from :func:`validate_output_type`.

    Returns
    -------
    DataFrame or Table
        ``df`` unchanged for 'pandas'; otherwise a native frame of the requested backend
        (``polars.DataFrame``, ``pyarrow.Table``, or a dask collection).
    """
    if output_type == PANDAS:
        return df
    if isinstance(df.index, pd.MultiIndex) or isinstance(df.columns, pd.MultiIndex):
        raise TypeError("from_pandas requires a tidy frame with no MultiIndex; call detach_index first")
    if df.index.name is not None or isinstance(df.index, pd.DatetimeIndex | pd.PeriodIndex):
        raise TypeError(
            f"from_pandas would silently drop the meaningful index {df.index.name!r} "
            f"({type(df.index).__name__}); call detach_index first"
        )
    prepared = df if isinstance(df.index, pd.RangeIndex) else df.reset_index(drop=True)
    if not all(isinstance(label, str) for label in prepared.columns):
        prepared = prepared.set_axis([str(label) for label in prepared.columns], axis=1)
    all_null_object = [
        name for name in prepared.columns if prepared[name].dtype == object and prepared[name].isna().all()
    ]
    if all_null_object:
        prepared = prepared.astype(dict.fromkeys(all_null_object, "float64"))
    frame = nw.from_native(prepared, eager_only=True)
    try:
        if output_type == "polars":
            return frame.to_polars()
        if output_type == "pyarrow":
            return frame.to_arrow()
        return frame.lazy(backend="dask").to_native()
    except ModuleNotFoundError as exc:
        # Catches transitive gaps find_spec cannot see, e.g. polars needing pyarrow for from_pandas.
        _require_backend(output_type)
        raise ImportError(f"output_type={output_type!r} conversion failed: {exc}") from exc
