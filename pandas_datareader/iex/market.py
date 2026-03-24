from pandas_datareader.iex import IEX

# Data provided for free by IEX
# Data is furnished in compliance with the guidelines promulgated in the IEX
# API terms of service and manual
# See https://iextrading.com/api-exhibit-a/ for additional information
# and conditions of use


class MarketReader(IEX):
    """
    Near real-time traded volume from IEX.

    Notes
    -----
    Market data is captured by the IEX system between approximately 7:45 a.m. and 5:15 p.m. ET.
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
        return "market"

    def _get_params(self, symbols: str | list[str] | None) -> dict:
        """Market API does not take any parameters.

        Returns
        -------
        params : dict
            Empty dict.
        """
        return {}
