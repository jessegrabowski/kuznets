.. _typing:

Types and errors
================

.. currentmodule:: kuznets.typing

Type aliases
------------

kuznets ships a ``py.typed`` marker, so type checkers read its annotations directly. The aliases
below are the vocabulary those annotations are written in; import them to annotate your own code
that wraps a reader.

.. code-block:: python

   from kuznets.typing import DateLike, Frame, OutputType, Symbols

   def load(tickers: Symbols, since: DateLike, backend: OutputType = "pandas") -> Frame:
       return kz.DataReader(tickers, "stooq", start=since, output_type=backend)

Reading with the default ``'pandas'`` backend is typed as returning a ``pandas.DataFrame``, so
indexing and ``.loc`` check without a cast. Passing any other backend returns :data:`Frame`,
because the concrete class depends on the value of ``output_type``:

.. code-block:: python

   df = kz.get_data_yahoo("AAPL")                          # pandas.DataFrame
   pl = kz.get_data_yahoo("AAPL", output_type="polars")    # native frame

.. data:: DateLike

   Anything accepted as a ``start`` or ``end`` bound: ``str``, ``int`` (read as a year),
   :class:`datetime.date`, :class:`datetime.datetime`, or :class:`pandas.Timestamp`.

.. data:: Symbols

   A single symbol or a list of them.

.. data:: Headers

   Request headers, as a mapping of ``str`` to ``str``.

.. data:: OutputType

   A backend name accepted by ``output_type``: ``'pandas'``, ``'polars'``, ``'pyarrow'``
   (alias ``'arrow'``), or ``'dask'``.

.. data:: BackendName

   The members of :data:`OutputType` other than ``'pandas'``.

.. data:: Frame

   A native frame of whichever backend ``output_type`` selected -- a ``polars.DataFrame``,
   ``pyarrow.Table``, dask collection, or ``pandas.DataFrame``. The optional backends are not
   imported to spell this out, so installing kuznets without them keeps type checking working.

.. data:: Payload

   The parsed response body a reader threads from fetch through parse to presentation. Its shape is
   reader-specific, so subclasses narrow it in their own overrides.

Errors and warnings
-------------------

.. currentmodule:: kuznets.utils

Readers signal failure with these two, so handling an outage means importing them:

.. code-block:: python

   import kuznets as kz
   from kuznets.utils import RemoteDataError

   try:
       df = kz.get_data_yahoo("NOSUCHTICKER")
   except RemoteDataError:
       ...

.. class:: RemoteDataError

   Raised when a source cannot be read: the request failed after its retries, or the response
   carried a source-specific error. Subclasses :class:`OSError`.

.. class:: SymbolWarning

   Warned when one symbol of a multi-symbol read fails. That symbol's rows come back all-null
   rather than failing the whole request. Subclasses :class:`UserWarning`.
