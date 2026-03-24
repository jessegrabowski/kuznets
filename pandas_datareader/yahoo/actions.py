import pandas as pd
from pandas import DataFrame, MultiIndex

from pandas_datareader.yahoo.daily import YahooDailyReader


class YahooActionReader(YahooDailyReader):
    """
    Get historical corporate actions (dividends and stock splits) from Yahoo Finance. All dates
    correspond with dividend and stock split ex-dates.
    """

    def read(self) -> DataFrame | dict[str, DataFrame]:
        """Read action data.

        Returns
        -------
        DataFrame or dict of str to DataFrame
            If multiple symbols, returns a dict keyed by symbol.
        """
        data = super().read()
        actions = {}
        if isinstance(data.columns, MultiIndex):
            data = data.swaplevel(0, 1, axis=1)
            for s in data.columns.levels[0]:
                actions[s] = _get_one_action(data[s])
            return actions
        else:
            return _get_one_action(data)

    @property
    def get_actions(self) -> bool:
        """Always True for action reader."""
        return True


def _get_one_action(data: DataFrame) -> DataFrame:
    """Extract actions (dividends and splits) from a single-symbol DataFrame.

    Parameters
    ----------
    data : DataFrame
        DataFrame with optional ``'Dividends'`` and ``'Splits'`` columns.

    Returns
    -------
    df : DataFrame
    """
    actions = DataFrame(columns=["action", "value"])

    if "Dividends" in data.columns:
        # Add a label column so we can combine our two DFs
        dividends = DataFrame(data["Dividends"]).dropna()
        dividends["action"] = "DIVIDEND"
        dividends = dividends.rename(columns={"Dividends": "value"})
        actions = pd.concat([actions, dividends], sort=True, axis=1)
        actions = actions.sort_index(ascending=False)

    if "Splits" in data.columns:
        # Add a label column so we can combine our two DFs
        splits = DataFrame(data["Splits"]).dropna()
        splits["action"] = "SPLIT"
        splits = splits.rename(columns={"Splits": "value"})
        actions = pd.concat([actions, splits], sort=True, axis=1)
        actions = actions.sort_index(ascending=False)

    return actions


class YahooDivReader(YahooActionReader):
    """Get historical dividend data from Yahoo Finance."""

    def read(self) -> DataFrame:
        """Read dividend data only.

        Returns
        -------
        df : DataFrame
        """
        data = super().read()
        return data[data["action"] == "DIVIDEND"]


class YahooSplitReader(YahooActionReader):
    """Get historical stock split data from Yahoo Finance."""

    def read(self) -> DataFrame:
        """Read split data only.

        Returns
        -------
        df : DataFrame
        """
        data = super().read()
        return data[data["action"] == "SPLIT"]
