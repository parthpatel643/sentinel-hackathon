"""Credential handling for camera stream URLs.

Real CCTV estates put credentials in the RTSP URL's userinfo, and real
passwords contain `@`, `:`, `/`, `#` and `?` — each of which silently
re-parses the URL if interpolated raw (`rtsp://admin:p@ss@host` connects to
host `ss@host`). `with_credentials` is the one way stream URLs are built with
credentials; `redact_credentials` is the one way they are shown to a human.
"""

from __future__ import annotations

from urllib.parse import quote, urlsplit, urlunsplit

__all__ = ["REDACTED", "has_credentials", "redact_credentials", "rtsp_host", "with_credentials"]

REDACTED = "***"


def rtsp_host(management_host: str) -> str:
    """The bare host of a device's management address, for building its RTSP
    URL. An NVR reached as `10.20.1.15:8080` (a forwarded web port) still
    serves RTSP on its own port, so carrying `:8080` into
    `rtsp://host:554/...` would produce a URL with two ports."""
    hostname = urlsplit(f"//{management_host}").hostname or management_host
    return f"[{hostname}]" if ":" in hostname else hostname


def has_credentials(url: str) -> bool:
    return "@" in urlsplit(url).netloc


def with_credentials(url: str, username: str | None, password: str | None) -> str:
    """Put percent-encoded credentials into `url`'s userinfo.

    A URL that already carries credentials is returned unchanged: the device
    (an ONVIF `GetStreamUri` response, an operator's CSV row) is the more
    specific source, and overwriting it would break cameras whose RTSP
    account differs from their management account.
    """
    if not username or has_credentials(url):
        return url
    parts = urlsplit(url)
    userinfo = quote(username, safe="")
    if password:
        userinfo += ":" + quote(password, safe="")
    return urlunsplit(parts._replace(netloc=f"{userinfo}@{parts.netloc}"))


def redact_credentials(url: str) -> str:
    """Replace any userinfo with a fixed marker, keeping scheme, host, port
    and path so an operator can still tell which endpoint a camera uses.

    Works on the raw string rather than the parsed netloc: an operator who
    pasted a password with an unencoded `#`, `?` or `/` produces a URL whose
    parsed netloc ends before the `@`, and parsing would then report "no
    credentials" and hand the password straight back. Masking up to the last
    `@` over-redacts the rare path containing `@`, which is the safe way to
    be wrong."""
    scheme, separator, rest = url.partition("://")
    if not separator or "@" not in rest:
        return url
    return f"{scheme}://{REDACTED}@{rest.rpartition('@')[2]}"
