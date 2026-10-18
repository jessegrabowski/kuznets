import requests

from kuznets.config import get_headers
from kuznets.typing import Headers

DEFAULT_HEADERS = {
    "Connection": "keep-alive",
    "Expires": str(-1),
    "Upgrade-Insecure-Requests": str(1),
    # Google Chrome:
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    ),
}


def session_headers(session: requests.Session) -> dict[str, str]:
    """Return a session's headers as a plain string mapping."""
    # requests allows bytes header values; dropping them beats stringifying them into b'...'.
    return {key: value for key, value in session.headers.items() if isinstance(value, str)}


def request_headers(session: requests.Session | None, headers: Headers | None) -> dict[str, str]:
    """Return the headers for a Yahoo request.

    Parameters
    ----------
    session : Session or None
        The session the caller supplied, which already carries the caller's headers.
    headers : dict, optional
        Headers the caller passed. Without a session, they override the browser defaults per key.

    Returns
    -------
    headers : dict of str to str
        The supplied session's headers, or the browser defaults with the caller's headers over them.
    """
    if session is None:
        return DEFAULT_HEADERS | (get_headers(headers) or {})
    return session_headers(session)
