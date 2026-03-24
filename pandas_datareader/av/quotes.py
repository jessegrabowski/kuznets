import numpy as np
import pandas as pd

from pandas_datareader.av import AlphaVantage
from pandas_datareader.exceptions import DEP_ERROR_MSG, ImmediateDeprecationError


class AVQuotesReader(AlphaVantage):
    """Get Alpha Vantage realtime stock quotes. **Immediately deprecated.**"""

    def __init__(
        self,
        symbols: str | list[str] | None = None,
        retry_count: int = 3,
        pause: float = 0.1,
        session=None,
        api_key: str | None = None,
    ) -> None:
        """
        Initialize the reader.

        Parameters
        ----------
        symbols : str, list of str, or DataFrame, optional
            Single stock symbol (ticker), list of symbols, or DataFrame with index containing stock
            symbols.
        retry_count : int, default 3
            Number of times to retry query request.
        pause : float, default 0.1
            Time, in seconds, to pause between consecutive queries.
        session : Session, optional
            ``requests.sessions.Session`` instance to be used.
        api_key : str, optional
            Alpha Vantage API key.
        """
        raise ImmediateDeprecationError(DEP_ERROR_MSG.format("AVQuotesReader"))

        if isinstance(symbols, str):
            syms = [symbols]
        elif isinstance(symbols, list):
            if len(symbols) > 100:
                raise ValueError("Up to 100 symbols at once are allowed.")
            else:
                syms = symbols
        super().__init__(
            symbols=syms,
            start=None,
            end=None,
            retry_count=retry_count,
            pause=pause,
            session=session,
            api_key=api_key,
        )

    @property
    def function(self) -> str:
        """Alpha Vantage endpoint function."""
        return "BATCH_STOCK_QUOTES"

    @property
    def data_key(self) -> str:
        """Key of data returned from Alpha Vantage."""
        return "Stock Quotes"

    @property
    def params(self) -> dict:
        """Parameters to use in API calls."""
        return {
            "symbols": ",".join(self.symbols),
            "function": self.function,
            "apikey": self.api_key,
        }

    def _read_lines(self, out: dict) -> pd.DataFrame:
        """Parse Alpha Vantage quotes JSON response.

        Parameters
        ----------
        out : dict
            Parsed JSON response.

        Returns
        -------
        df : DataFrame
        """
        result = []
        quotes = out[self.data_key]
        for quote in quotes:
            df = pd.DataFrame(quote, index=[0])
            df.columns = [col[3:] for col in df.columns]
            df.set_index("symbol", inplace=True)
            df["price"] = df["price"].astype("float64")
            try:
                df["volume"] = df["volume"].astype("int64")
            except ValueError:
                df["volume"] = [np.nan * len(self.symbols)]
            result.append(df)
        if len(result) != len(self.symbols):
            raise ValueError("Not all symbols downloaded. Check valid ticker(s).")
        else:
            return pd.concat(result)
