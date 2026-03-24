from pandas_datareader.base import _DailyBaseReader


class StooqDailyReader(_DailyBaseReader):
    """Get historical stock prices from Stooq."""

    @property
    def url(self) -> str:
        """API URL."""
        return "https://stooq.com/q/d/l/"

    def _get_params(self, symbol: str, country: str = "US") -> dict:
        """Build query parameters for a given symbol.

        Parameters
        ----------
        symbol : str
            Ticker symbol.
        country : str, default "US"
            Country suffix to append if not already present.

        Returns
        -------
        params : dict
        """
        symbol_parts = symbol.split(".")
        if not symbol.startswith("^"):
            if len(symbol_parts) == 1:
                symbol = ".".join([symbol, country])
            elif symbol_parts[1].lower() == "pl":
                symbol = symbol_parts[0]
            else:
                if symbol_parts[1].lower() not in [
                    "de",
                    "hk",
                    "hu",
                    "jp",
                    "uk",
                    "us",
                    "f",
                    "b",
                ]:
                    symbol = ".".join([symbol, "US"])

        params = {
            "s": symbol,
            "i": self.freq or "d",
            "d1": self.start.strftime("%Y%m%d"),
            "d2": self.end.strftime("%Y%m%d"),
        }

        return params
