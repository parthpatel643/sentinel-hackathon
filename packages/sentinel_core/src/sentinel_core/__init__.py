"""Shared domain model and infrastructure ports for the Sentinel Platform.

Everything here is imported by both the edge plane and the core plane, so it must
stay free of heavy dependencies (no OpenCV, no torch, no FastAPI).
"""

from sentinel_core.clock import Frame, StreamClock
from sentinel_core.config import Settings, get_settings
from sentinel_core.logging import configure_logging, get_logger

__all__ = [
    "Frame",
    "Settings",
    "StreamClock",
    "configure_logging",
    "get_logger",
    "get_settings",
]
