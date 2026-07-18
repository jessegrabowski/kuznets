import importlib.util

import narwhals.stable.v2 as nw
import pytest

# Non-pandas backends every reader's tidy schema is pinned against. Extend here and every
# parametrized backend test picks the new backend up.
BACKENDS = ["polars", "pyarrow"]


def skip_unless_installed(backend: str) -> None:
    if backend != "pandas" and importlib.util.find_spec(backend) is None:
        pytest.skip(f"{backend} is not installed")


def as_narwhals(frame) -> nw.DataFrame:
    """Wrap any backend's native frame for backend-agnostic assertions."""
    return nw.from_native(frame, eager_only=True)


def column_values(frame, name: str) -> list:
    return as_narwhals(frame)[name].to_list()
