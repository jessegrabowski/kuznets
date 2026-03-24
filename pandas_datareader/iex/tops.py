from pandas_datareader.iex import IEX

# Data provided for free by IEX
# Data is furnished in compliance with the guidelines promulgated in the IEX
# API terms of service and manual
# See https://iextrading.com/api-exhibit-a/ for additional information
# and conditions of use


class TopsReader(IEX):
    """
    Near-real time aggregated bid and offer positions from IEX.

    Notes
    -----
    IEX's aggregated best quoted bid and offer position for all securities on IEX's displayed limit
    order book.
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
        return "tops"


class LastReader(IEX):
    """
    Last sale information from IEX.

    Notes
    -----
    Last provides trade data for executions on IEX. Provides last sale price, size and time.
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
        return "tops/last"
