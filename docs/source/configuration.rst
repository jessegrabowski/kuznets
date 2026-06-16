.. _configuration:

*************
Configuration
*************

API keys and global request settings (default headers, retry count, pause, timeout) resolve through
a layered configuration. From highest to lowest precedence:

#. an explicit argument to the reader (``api_key=``, ``headers=``, ``retry_count=``, …);
#. the runtime ``pandas_datareader.options`` object;
#. an environment variable (API keys only, e.g. ``FRED_API_KEY``);
#. the config file ``~/.config/pandas-datareader/config.toml``;
#. the built-in default.

A higher layer only overrides a lower one when it actually supplies a value, so you can set a global
default in the config file and still override it per call.

Runtime options
===============

Set attributes on the module-level ``options`` object to influence every reader in the current
session::

    import pandas_datareader as pdr

    pdr.options.api_keys["fred"] = "my-fred-key"
    pdr.options.headers = {"User-Agent": "my-app/1.0"}
    pdr.options.timeout = 60

    pdr.options.reset()  # restore everything to unset

Config file
===========

For settings that should persist across sessions, create
``~/.config/pandas-datareader/config.toml`` (or point ``PANDAS_DATAREADER_CONFIG`` at a file of your
choosing; ``XDG_CONFIG_HOME`` is honored as well):

.. code-block:: toml

    [api_keys]
    fred = "my-fred-key"
    tiingo = "my-tiingo-key"

    [headers]
    User-Agent = "my-app/1.0"

    [defaults]
    timeout = 60
    pause = 0.5
    retry_count = 5

The file is read once and cached; call ``pandas_datareader.config.reload_config()`` after editing it
within a running session. Keep this file readable only by you, since it may contain secrets.

Environment variables
=====================

Each keyed reader also reads its API key from an environment variable, which sits below the runtime
options but above the config file:

============  ==========================
Source        Environment variable
============  ==========================
FRED          ``FRED_API_KEY``
Alpha Vantage ``ALPHAVANTAGE_API_KEY``
Quandl        ``QUANDL_API_KEY``
Tiingo        ``TIINGO_API_KEY``
============  ==========================
