"""Settings that build credential-bearing URLs.

These are always assembled at call time from separate fields, never stored as
a single literal string — partly for twelve-factor hygiene, and partly because
a combined `scheme://user:pass@host` literal is exactly the shape
credential-scanning tooling rewrites (it corrupted an earlier version of this
file; see the comment in config.py). Assertions here check structure/
components, not full-string equality against a value that might itself get
mangled if ever printed or logged.
"""

from __future__ import annotations

from urllib.parse import quote

from pydantic import SecretStr

from sentinel_core.config import Settings


def test_database_url_is_well_formed() -> None:
    settings = Settings(
        db_host="db.internal", db_port=5433, db_user="u", db_password="p", db_name="n"
    )
    url = settings.database_url

    assert url.startswith("postgresql://")
    assert url.endswith("@db.internal:5433/n")


def test_gov_rtsp_url_embeds_percent_encoded_email_and_password() -> None:
    settings = Settings(
        gov_access_email="alice@example.com", gov_access_password=SecretStr("s3cret!")
    )
    url = settings.gov_stream_url("rtsp", "cam04")

    assert url.startswith("rtsp://")
    assert quote("alice@example.com", safe="") in url
    assert quote("s3cret!", safe="") in url
    assert url.endswith(f"{settings.gov_rtsp_host}:{settings.gov_rtsp_port}/stream/cam04")
    # The literal '@' must never appear before the host — it would be parsed
    # as an early userinfo/host separator and break the URL.
    host_marker = f"@{settings.gov_rtsp_host}"
    assert url.count("@") == 1
    assert url.endswith(host_marker + f":{settings.gov_rtsp_port}/stream/cam04")


def test_gov_whep_url_uses_http_scheme_and_whep_path() -> None:
    settings = Settings(
        gov_access_email="alice@example.com", gov_access_password=SecretStr("s3cret!")
    )
    url = settings.gov_stream_url("whep", "cam04")

    assert url.startswith("http://")
    assert url.endswith(f"{settings.gov_rtsp_host}:{settings.gov_whep_port}/stream/cam04/whep")


def test_gov_hls_url_has_no_embedded_credentials() -> None:
    """HLS is served from the CDN behind a portal password, not per-request
    embedded credentials — so no email/password belongs in this URL at all."""
    settings = Settings(
        gov_access_email="alice@example.com", gov_access_password=SecretStr("s3cret!")
    )
    url = settings.gov_hls_url("cam04")

    assert url == f"{settings.gov_hls_base_url}/cam04/index.m3u8"
    assert "@" not in url


def test_gov_access_password_never_appears_in_repr_or_str() -> None:
    """SecretStr must keep the password out of logs, reprs and model_dump()."""
    settings = Settings(gov_access_password=SecretStr("s3cret!"))

    assert "s3cret!" not in repr(settings.gov_access_password)
    assert "s3cret!" not in str(settings.gov_access_password)
    dumped = settings.model_dump()
    assert "s3cret!" not in repr(dumped)


def test_gov_catalogue_url_defaults_to_the_real_endpoint() -> None:
    """Catalogue-driven discovery: this is fetched fresh every run, never
    used to hard-code a camera id."""
    settings = Settings()
    assert settings.gov_catalogue_url == "https://cctv.corp8.cloud/cameras.json"
