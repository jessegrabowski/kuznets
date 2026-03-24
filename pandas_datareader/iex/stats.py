from datetime import datetime, timedelta

import pandas as pd

from pandas_datareader.exceptions import UnstableAPIWarning
from pandas_datareader.iex import IEX

# Data provided for free by IEX
# Data is furnished in compliance with the guidelines promulgated in the IEX
# API terms of service and manual
# See https://iextrading.com/api-exhibit-a/ for additional information
# and conditions of use


class DailySummaryReader(IEX):
    """Daily statistics from IEX for a day or month.

    .. warning::
       Daily statistics is not working due to issues with the IEX API.
    """

    def __init__(
        self,
        symbols: str | list[str] | None = None,
        start=None,
        end=None,
        retry_count: int = 3,
        pause: float = 0.1,
        session=None,
    ) -> None:
        import warnings

        warnings.warn(
            "Daily statistics is not working due to issues with the IEX API",
            UnstableAPIWarning,
            stacklevel=2,
        )
        self.curr_date = start
        super().__init__(
            symbols=symbols,
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
        )

    @property
    def service(self) -> str:
        """Service endpoint."""
        return "stats/historical/daily"

    def _get_params(self, symbols: str | list[str] | None) -> dict:
        """Build query parameters.

        Returns
        -------
        params : dict
        """
        p = {}
        if self.curr_date is not None:
            p["date"] = self.curr_date.strftime("%Y%m%d")
        return p

    def read(self) -> pd.DataFrame:
        """Read daily statistics for each date in the range.

        Returns
        -------
        df : DataFrame
        """
        tlen = self.end - self.start
        dfs = []
        for date in (self.start + timedelta(n) for n in range(tlen.days)):
            self.curr_date = date
            tdf = super().read()
            dfs.append(tdf)
        return pd.concat(dfs)


class MonthlySummaryReader(IEX):
    """Monthly statistics from IEX."""

    def __init__(
        self,
        symbols: str | list[str] | None = None,
        start=None,
        end=None,
        retry_count: int = 3,
        pause: float = 0.1,
        session=None,
    ) -> None:
        self.curr_date = start
        self.date_format = "%Y%m"
        super().__init__(
            symbols=symbols,
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
        )

    @property
    def service(self) -> str:
        """Service endpoint."""
        return "stats/historical"

    def _get_params(self, symbols: str | list[str] | None) -> dict:
        """Build query parameters.

        Returns
        -------
        params : dict
        """
        p = {}
        if self.curr_date is not None:
            p["date"] = self.curr_date.strftime(self.date_format)
        return p

    def read(self) -> pd.DataFrame:
        """Read monthly statistics for each month in the range.

        Returns
        -------
        df : DataFrame
        """
        tlen = self.end - self.start
        dfs = []

        # Build list of all dates within the given range
        lrange = [self.start + timedelta(n) for n in range(tlen.days)]

        mrange = []
        for dt in lrange:
            if datetime(dt.year, dt.month, 1) not in mrange:
                mrange.append(datetime(dt.year, dt.month, 1))
        lrange = mrange

        for date in lrange:
            self.curr_date = date
            tdf = super().read()

            # We may not return data if this was a weekend/holiday:
            if not tdf.empty:
                tdf["date"] = date.strftime(self.date_format)
                dfs.append(tdf)

        # We may not return any data if we failed to specify useful parameters:
        return pd.concat(dfs) if len(dfs) > 0 else pd.DataFrame()


class RecordsReader(IEX):
    """Total matched volume information from IEX."""

    def __init__(
        self,
        symbols: str | list[str] | None = None,
        start=None,
        end=None,
        retry_count: int = 3,
        pause: float = 0.1,
        session=None,
    ) -> None:
        super().__init__(
            symbols=symbols,
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
        )

    @property
    def service(self) -> str:
        """Service endpoint."""
        return "stats/records"

    def _get_params(self, symbols: str | list[str] | None) -> dict:
        """Record Stats API does not take any parameters.

        Returns
        -------
        params : dict
            Empty dict.
        """
        return {}


class RecentReader(IEX):
    """Recent trading volume from IEX.

    Notes
    -----
    Returns 6 fields for each day:

      * date: refers to the trading day.
      * volume: refers to executions received from order routed to away
        trading centers.
      * routedVolume: refers to single counted shares matched from executions
        on IEX.
      * marketShare: refers to IEX's percentage of total US Equity market
        volume.
      * isHalfday: will be true if the trading day is a half day.
      * litVolume: refers to the number of lit shares traded on IEX
        (single-counted).
    """

    def __init__(
        self,
        symbols: str | list[str] | None = None,
        start=None,
        end=None,
        retry_count: int = 3,
        pause: float = 0.1,
        session=None,
    ) -> None:
        super().__init__(
            symbols=symbols,
            start=start,
            end=end,
            retry_count=retry_count,
            pause=pause,
            session=session,
        )

    @property
    def service(self) -> str:
        """Service endpoint."""
        return "stats/recent"

    def _get_params(self, symbols: str | list[str] | None) -> dict:
        """Recent Stats API does not take any parameters.

        Returns
        -------
        params : dict
            Empty dict.
        """
        return {}
