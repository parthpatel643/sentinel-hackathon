from urllib.parse import unquote, urlsplit

from sentinel_core.stream_urls import (
    REDACTED,
    has_credentials,
    redact_credentials,
    rtsp_host,
    with_credentials,
)


def test_special_characters_in_password_do_not_change_the_host() -> None:
    url = with_credentials("rtsp://10.0.0.5:554/Streaming/Channels/101", "admin", "p@ss:w/rd#1?")

    parts = urlsplit(url)
    assert parts.hostname == "10.0.0.5"
    assert parts.port == 554
    assert parts.path == "/Streaming/Channels/101"
    assert unquote(parts.username or "") == "admin"
    assert unquote(parts.password or "") == "p@ss:w/rd#1?"


def test_email_username_is_encoded() -> None:
    url = with_credentials("rtsp://grid.example:8554/stream/1", "team@example.com", "x")

    assert urlsplit(url).hostname == "grid.example"
    assert unquote(urlsplit(url).username or "") == "team@example.com"


def test_existing_credentials_are_kept() -> None:
    url = "rtsp://viewer:secret@cam.local/live"

    assert with_credentials(url, "admin", "other") == url


def test_no_username_leaves_url_untouched() -> None:
    assert with_credentials("rtsp://cam.local/live", None, "pw") == "rtsp://cam.local/live"


def test_username_without_password() -> None:
    assert with_credentials("rtsp://cam.local/live", "admin", "") == "rtsp://admin@cam.local/live"


def test_redaction_hides_userinfo_but_keeps_the_endpoint() -> None:
    url = with_credentials("rtsp://103.0.0.1:8554/stream/cam06", "team@example.com", "p@ss")

    redacted = redact_credentials(url)

    assert redacted == f"rtsp://{REDACTED}@103.0.0.1:8554/stream/cam06"
    assert "p%40ss" not in redacted and "team" not in redacted


def test_redaction_is_a_no_op_without_credentials() -> None:
    url = "http://relay.local:8888/cam06/index.m3u8"

    assert redact_credentials(url) == url
    assert not has_credentials(url)


def test_redaction_survives_unencoded_reserved_characters_in_the_password() -> None:
    for url in (
        "rtsp://admin:pa#ss@10.0.0.5:554/ch1",
        "rtsp://admin:pa?ss@10.0.0.5:554/ch1",
        "rtsp://admin:p/ss@10.0.0.5:554/ch1",
    ):
        redacted = redact_credentials(url)
        assert "pa" not in redacted.split("@")[0]
        assert redacted == f"rtsp://{REDACTED}@10.0.0.5:554/ch1"


def test_rtsp_host_drops_a_management_port() -> None:
    assert rtsp_host("10.20.1.15:8080") == "10.20.1.15"
    assert rtsp_host("10.20.1.15") == "10.20.1.15"
    assert rtsp_host("nvr.depot.local:80") == "nvr.depot.local"
    assert rtsp_host("[fe80::1]:8080") == "[fe80::1]"
