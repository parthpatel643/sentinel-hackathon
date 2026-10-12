"""A street-map background for the Movement Report's route.

Tiles are fetched once, when the report is exported, and stitched into one
image that is embedded in the PDF. The manifest's hashes therefore cover the
map exactly as it was printed: the evidence never depends on a tile server
afterwards. When tiles cannot be fetched (no internet at the venue, a
departmental tile server down, tiles disabled), `fetch_basemap` returns None
and the report falls back to the route drawn to scale on a blank frame.

Tiles are cached on disk, so a camera's area is fetched once, and requests
identify themselves as the OpenStreetMap tile usage policy asks. Point
`SENTINEL_REPORT_TILE_URL` at a departmental tile server for production, or
set it empty to never fetch.
"""

from __future__ import annotations

import asyncio
import io
import math
from dataclasses import dataclass
from pathlib import Path

import httpx
from PIL import Image

from core_api.registry.schemas import GeoPointOut
from sentinel_core.config import Settings

__all__ = ["Basemap", "fetch_basemap", "plan_view", "world_pixel"]

TILE = 256
MAX_ZOOM = 17
# A single camera has no extent to fit: show its streets, as the console does.
SINGLE_POINT_ZOOM = 16
# Map width in pixels. About 110 dpi across the report's 277 mm frame, so the
# tiles' labels print at a readable size.
WIDTH_PX = 1200
# Fraction of the frame kept clear around the outermost cameras.
MARGIN = 0.12
_MAX_TILES = 40
_USER_AGENT = "Sentinel-Platform/1.0 (Movement Report export)"


@dataclass(frozen=True, slots=True)
class Basemap:
    """A stitched map image and the Web Mercator window it shows."""

    image_png: bytes
    zoom: int
    left: float
    top: float
    width_px: int
    height_px: int
    attribution: str

    def place(self, lat: float, lon: float) -> tuple[float, float]:
        """A coordinate as a 0..1 fraction across and down the image."""
        x, y = world_pixel(lat, lon, self.zoom)
        return (x - self.left) / self.width_px, (y - self.top) / self.height_px

    def metres_per_pixel(self, lat: float) -> float:
        return float(156_543.033_92 * math.cos(math.radians(lat)) / 2**self.zoom)


def world_pixel(lat: float, lon: float, zoom: int) -> tuple[float, float]:
    """Web Mercator pixel coordinates of a point at a zoom level."""
    size = TILE * 2**zoom
    lat = max(min(lat, 85.0511), -85.0511)
    x = (lon + 180.0) / 360.0 * size
    sin = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + sin) / (1 - sin)) / (4 * math.pi)) * size
    return x, y


def plan_view(points: list[GeoPointOut], width_px: int, height_px: int) -> tuple[int, float, float]:
    """(zoom, left, top): the closest zoom that fits every point inside the
    frame's margin, centred on them."""
    usable_w = width_px * (1 - 2 * MARGIN)
    usable_h = height_px * (1 - 2 * MARGIN)
    zoom = SINGLE_POINT_ZOOM
    if len({(p.lat, p.lon) for p in points}) > 1:
        zoom = 0
        for candidate in range(MAX_ZOOM, -1, -1):
            xs, ys = zip(*(world_pixel(p.lat, p.lon, candidate) for p in points), strict=True)
            if max(xs) - min(xs) <= usable_w and max(ys) - min(ys) <= usable_h:
                zoom = candidate
                break
    xs, ys = zip(*(world_pixel(p.lat, p.lon, zoom) for p in points), strict=True)
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    return zoom, cx - width_px / 2, cy - height_px / 2


async def fetch_basemap(
    points: list[GeoPointOut],
    *,
    aspect: float,
    settings: Settings,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Basemap | None:
    """The map behind the route, or None if any tile cannot be had.
    `aspect` is the report frame's width over its height."""
    url = settings.report_tile_url.strip()
    if not points or not url:
        return None
    width_px, height_px = WIDTH_PX, round(WIDTH_PX / aspect)
    zoom, left, top = plan_view(points, width_px, height_px)
    first_x, first_y = math.floor(left / TILE), math.floor(top / TILE)
    last_x = math.floor((left + width_px - 1) / TILE)
    last_y = math.floor((top + height_px - 1) / TILE)
    wanted = [(x, y) for y in range(first_y, last_y + 1) for x in range(first_x, last_x + 1)]
    if len(wanted) > _MAX_TILES:
        return None

    cache = Path(settings.report_tile_cache_dir)
    n = 2**zoom
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(5.0),
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
            transport=transport,
        ) as client:
            tiles = await asyncio.gather(
                *(_tile(client, url, cache, zoom, x % n, y) for x, y in wanted)
            )
    except (httpx.HTTPError, OSError, ValueError, SyntaxError):
        return None

    canvas = Image.new("RGB", ((last_x - first_x + 1) * TILE, (last_y - first_y + 1) * TILE))
    for (x, y), data in zip(wanted, tiles, strict=True):
        with Image.open(io.BytesIO(data)) as tile:
            canvas.paste(tile.convert("RGB"), ((x - first_x) * TILE, (y - first_y) * TILE))
    ox, oy = round(left - first_x * TILE), round(top - first_y * TILE)
    window = canvas.crop((ox, oy, ox + width_px, oy + height_px))
    # Lightened, so the route and its numbered stops stand out from the streets.
    window = Image.blend(window, Image.new("RGB", window.size, (255, 255, 255)), 0.2)
    out = io.BytesIO()
    window.save(out, format="PNG", optimize=True)
    return Basemap(
        image_png=out.getvalue(),
        zoom=zoom,
        left=first_x * TILE + ox,
        top=first_y * TILE + oy,
        width_px=width_px,
        height_px=height_px,
        attribution=settings.report_tile_attribution,
    )


async def _tile(client: httpx.AsyncClient, url: str, cache: Path, z: int, x: int, y: int) -> bytes:
    path = cache / str(z) / str(x) / f"{y}.png"
    if path.is_file():
        return path.read_bytes()
    response = await client.get(url.format(z=z, x=x, y=y))
    response.raise_for_status()
    data = response.content
    with Image.open(io.BytesIO(data)) as check:
        check.verify()  # an error page served as 200 is not a tile
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data
