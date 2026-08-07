import requests

_CRUMB_URL = "https://query1.finance.yahoo.com/v1/test/getcrumb"
_COOKIE_URL = "https://fc.yahoo.com"


def fetch_crumb(session: requests.Session, headers: dict, timeout: float) -> str:
    """Prime the session cookie and return a Yahoo API crumb.

    The v7 quote and options endpoints reject requests without a cookie/crumb pair. Fetch a cookie
    from Yahoo, then exchange it for a crumb that authorizes the request.

    Parameters
    ----------
    session : Session
        ``requests.sessions.Session`` whose cookie jar is primed in place.
    headers : dict
        Request headers (a browser ``User-Agent`` is required).
    timeout : float
        Per-request timeout, in seconds.

    Returns
    -------
    crumb : str
        Token to pass as the ``crumb`` query parameter.
    """
    session.get(_COOKIE_URL, headers=headers, timeout=timeout)
    return session.get(_CRUMB_URL, headers=headers, timeout=timeout).text
