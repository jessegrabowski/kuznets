import datetime
from typing import Any, Literal

from narwhals.stable.v2.typing import IntoFrame
from pandas import Timestamp

__all__ = [
    "BackendName",
    "DateLike",
    "Frame",
    "Headers",
    "OutputType",
    "Payload",
    "Symbols",
]

type DateLike = str | int | datetime.date | datetime.datetime | Timestamp

type Symbols = str | list[str]

type Headers = dict[str, str]

# Backends other than pandas. Kept separate from OutputType so the two overloads of a reader entry
# point -- pandas in, DataFrame out; anything else in, native frame out -- do not overlap.
type BackendName = Literal["polars", "pyarrow", "arrow", "dask"]

type OutputType = Literal["pandas"] | BackendName

# A native frame of whichever backend ``output_type`` selected: pandas.DataFrame, polars.DataFrame,
# pyarrow.Table, or a dask collection. Readers that return a pandas frame say so precisely; this
# alias is for the paths where the backend is only known at runtime.
type Frame = IntoFrame

# The parsed response body a reader threads from fetch to parse to presentation. Its shape is
# reader-specific -- a StringIO of CSV, decoded JSON, a DataFrame, or a dict of frames per symbol --
# so each reader narrows it in its own overrides.
type Payload = Any
