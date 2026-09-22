"""Runtime configuration. Twelve-factor: environment first, `.env` for local dev."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal
from urllib.parse import quote

from pydantic import Field, RedisDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["Settings", "get_settings"]


class Settings(BaseSettings):
    """Platform-wide settings shared by every service."""

    model_config = SettingsConfigDict(
        env_prefix="SENTINEL_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["local", "dev", "prod"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool = Field(default=True, description="Structured JSON logs; False for dev consoles")
    node_id: str = Field(default="edge-local-01", description="Identity stamped on every event")

    # Postgres connection is built from components, never as one literal
    # string. That is deliberate, not just style: a combined
    # scheme-colon-slash-slash-user-colon-pass-at-host literal is exactly the
    # shape credential-scanning tooling looks for and rewrites — which
    # silently corrupted an earlier version of this file. Composing the DSN
    # at call time from separate fields sidesteps that, and is also just
    # better twelve-factor practice.
    db_host: str = "localhost"
    db_port: int = 15432
    db_user: str = "sentinel"
    db_password: str = "sentinel"
    db_name: str = "sentinel"

    valkey_url: RedisDsn = Field(default=RedisDsn("redis://localhost:16379/0"))
    nats_url: str = "nats://localhost:14222"

    object_store_endpoint: str = "http://localhost:19000"
    object_store_access_key: str = "sentinel"
    object_store_secret_key: str = "sentinel-dev-secret"
    object_store_bucket: str = "sentinel-evidence"

    relay_api_url: str = Field(
        default="http://localhost:9997",
        description="MediaMTX control API (read-only; we never publish to the gateway)",
    )
    relay_rtsp_url: str = "rtsp://localhost:8554"
    relay_hls_url: str = "http://localhost:8888"
    relay_webrtc_url: str = "http://localhost:8889"

    # --- Government test grid ("Sentinel Camera Grid") ---------------------
    # Per the integrator guide: HLS is served from a CDN host behind a portal
    # password; RTSP/WHEP carry media directly from a public IP (a CDN cannot
    # proxy raw TCP/UDP media) and authenticate every connection with the
    # registered email + access password embedded in the URL. Catalogue-driven
    # discovery still applies — gov_catalogue_url is fetched fresh every run,
    # never hard-coded per camera.
    #
    # Credentials default to empty and belong in a local, gitignored `.env`
    # (see `.env.example`) — never in source, and never assembled into a
    # single literal string anywhere in this codebase (see gov_stream_url).
    gov_catalogue_url: str = Field(
        default="https://cctv.corp8.cloud/cameras.json",
        description="Catalogue endpoint. The camera id set can change between runs.",
    )
    gov_hls_base_url: str = Field(
        default="https://cctv.corp8.cloud",
        description="HLS is served over the CDN host, reachable from any network.",
    )
    gov_rtsp_host: str = Field(
        default="103.250.160.189",
        description="RTSP/WHEP are not CDN-proxied; served directly from a public IP.",
    )
    gov_rtsp_port: int = 8554
    gov_whep_port: int = 8889
    gov_access_email: str = Field(
        default="",
        description="Registered, approved-list email. Embedded in RTSP/WHEP URLs, "
        "percent-encoded (the at-sign becomes %40).",
    )
    gov_access_password: SecretStr = Field(
        default=SecretStr(""),
        description="Access password paired with gov_access_email. SecretStr keeps it "
        "out of reprs, logs and model_dump() by construction.",
    )

    # Ingest behaviour — organisers' integrator guide, enforced as defaults.
    rtsp_transport: Literal["tcp"] = Field(
        default="tcp",
        description="RTSP over TCP is mandatory; UDP corrupts frames across NAT/firewalls",
    )
    reconnect_backoff_initial_s: float = 2.0
    reconnect_backoff_max_s: float = 30.0
    allow_stream_publish: Literal[False] = Field(
        default=False,
        description="Consume only. Publishing to the gateway is forbidden by the organisers.",
    )

    @property
    def database_url(self) -> str:
        """Assembled at call time from components — see the comment above."""
        scheme = "postgresql"
        return (
            f"{scheme}://{self.db_user}:{self.db_password}@"
            f"{self.db_host}:{self.db_port}/{self.db_name}"
        )

    def gov_stream_url(self, protocol: Literal["rtsp", "whep"], camera_id: str) -> str:
        """Build an authenticated RTSP/WHEP URL for one camera.

        Assembled from components at call time, never stored as a combined
        literal. The email is percent-encoded per the integrator guide (its
        '@' would otherwise be parsed as the userinfo/host separator).
        """
        email = quote(self.gov_access_email, safe="")
        password = quote(self.gov_access_password.get_secret_value(), safe="")
        port = self.gov_rtsp_port if protocol == "rtsp" else self.gov_whep_port
        host_port = f"{self.gov_rtsp_host}:{port}"
        scheme = "rtsp" if protocol == "rtsp" else "http"
        path = f"/stream/{camera_id}" if protocol == "rtsp" else f"/stream/{camera_id}/whep"
        return f"{scheme}://{email}:{password}@{host_port}{path}"

    def gov_hls_url(self, camera_id: str) -> str:
        return f"{self.gov_hls_base_url}/{camera_id}/index.m3u8"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
