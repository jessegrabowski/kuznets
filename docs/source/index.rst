.. kuznets documentation master file, created by
   sphinx-quickstart on Mon Jan 26 20:32:50 2015.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.


kuznets
=================

.. include:: _version.txt

Remote data access for economic and financial data, returned as pandas, polars, pyarrow, or
dask frames. kuznets is a fork of pandas-datareader that went dataframe-agnostic.


Quick Start
-----------

Install using ``pip``

.. code-block:: shell

   pip install kuznets

and then import and use one of the data readers. This example reads 5-years
of 10-year constant maturity yields on U.S. government bonds.

.. code-block:: python

   import kuznets as kz
   kz.get_data_fred('GS10')


Contents
--------

Contents:

.. toctree::
   :maxdepth: 1

   remote_data.rst
   configuration.rst
   cache.rst
   see-also.rst
   readers/index

Release notes
-------------

Release notes are generated from merged pull requests and published with each
`GitHub release <https://github.com/jessegrabowski/kuznets/releases>`__.

Documentation
-------------

`Stable documentation <https://pydata.github.io/kuznets/>`__
is available on
`github.io <https://pydata.github.io/kuznets/>`__.
A second copy of the stable documentation is hosted on
`read the docs <https://kuznets.readthedocs.io/>`_ for more details.

Recent developments
-------------------
You can install the latest development version using

.. code-block:: shell

   pip install git+https://github.com/jessegrabowski/kuznets.git

or

.. code-block:: shell

   git clone https://github.com/jessegrabowski/kuznets.git
   cd kuznets
   python setup.py install

`Development documentation <https://pydata.github.io/kuznets/devel/>`__
is available for the latest changes in master.

Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
