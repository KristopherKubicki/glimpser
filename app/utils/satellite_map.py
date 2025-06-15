"""Simple orbital map generator without external dependencies."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Iterable

from PIL import Image, ImageDraw

__all__ = ["generate_satellite_map", "save_satellite_map"]

_MU = 398600.4418  # km^3/s^2
_WGS84_A = 6378.137  # km
_WGS84_F = 1 / 298.257223563


def _jday(
    year: int, month: int, day: int, hour: int, minute: int, second: float
) -> tuple[float, float]:
    if month <= 2:
        year -= 1
        month += 12
    a = year // 100
    b = 2 - a + a // 4
    jd = int(365.25 * (year + 4716)) + int(30.6001 * (month + 1)) + day + b - 1524.5
    fr = (hour + minute / 60 + second / 3600) / 24
    return jd, fr


def _gmst(dt: datetime) -> float:
    jd, fr = _jday(
        dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second + dt.microsecond / 1e6
    )
    t = (jd - 2451545.0 + fr) / 36525.0
    gmst = (
        280.46061837
        + 360.98564736629 * (jd - 2451545.0 + fr)
        + 0.000387933 * t * t
        - t * t * t / 38710000.0
    )
    return math.radians(gmst % 360)


def _ecef_to_geodetic(x: float, y: float, z: float) -> tuple[float, float]:
    a = _WGS84_A
    f = _WGS84_F
    b = a * (1 - f)
    e2 = 1 - (b * b) / (a * a)
    lon = math.atan2(y, x)
    r = math.hypot(x, y)
    lat = math.atan2(z, r)
    for _ in range(5):
        sin_lat = math.sin(lat)
        n = a / math.sqrt(1 - e2 * sin_lat * sin_lat)
        alt = r / math.cos(lat) - n
        lat = math.atan2(z, r * (1 - e2 * n / (n + alt)))
    return math.degrees(lat), math.degrees(lon)


def _teme_to_ecef(r: Iterable[float], dt: datetime) -> tuple[float, float, float]:
    theta = _gmst(dt)
    c, s = math.cos(theta), math.sin(theta)
    x = r[0] * c - r[1] * s
    y = r[0] * s + r[1] * c
    z = r[2]
    return x, y, z


def _parse_tle(line1: str, line2: str):
    epoch_year = int(line1[18:20])
    epoch_year += 2000 if epoch_year < 57 else 1900
    epoch_day = float(line1[20:32])
    epoch = datetime(epoch_year, 1, 1, tzinfo=timezone.utc) + timedelta(
        days=epoch_day - 1
    )
    inc = math.radians(float(line2[8:16]))
    raan = math.radians(float(line2[17:25]))
    ecc = float("0." + line2[26:33].strip())
    argp = math.radians(float(line2[34:42]))
    mean_anom = math.radians(float(line2[43:51]))
    mean_motion = float(line2[52:63])
    return {
        "epoch": epoch,
        "inc": inc,
        "raan": raan,
        "ecc": ecc,
        "argp": argp,
        "M0": mean_anom,
        "n": mean_motion * 2 * math.pi / 86400.0,
    }


def _kepler_to_eci(params: dict, dt: datetime) -> tuple[float, float, float]:
    a = (_MU / (params["n"] ** 2)) ** (1 / 3)
    M = params["M0"] + params["n"] * (dt - params["epoch"]).total_seconds()
    E = M  # assume circular
    nu = E
    r_orb = a * (1 - params["ecc"] * math.cos(E))
    x = r_orb * math.cos(nu)
    y = r_orb * math.sin(nu)
    z = 0.0
    cosw, sinw = math.cos(params["argp"]), math.sin(params["argp"])
    x, y = x * cosw - y * sinw, x * sinw + y * cosw
    cosi, sini = math.cos(params["inc"]), math.sin(params["inc"])
    x, z = x, y * sini
    y = y * cosi
    cosO, sinO = math.cos(params["raan"]), math.sin(params["raan"])
    x, y = x * cosO - y * sinO, x * sinO + y * cosO
    return x, y, z


def _sat_lat_lon(params: dict, dt: datetime) -> tuple[float, float]:
    r = _kepler_to_eci(params, dt)
    x, y, z = _teme_to_ecef(r, dt)
    return _ecef_to_geodetic(x, y, z)


def generate_satellite_map(
    line1: str,
    line2: str,
    width: int = 720,
    height: int = 360,
    minutes: int = 90,
) -> Image.Image:
    """Return a world map with the predicted ground track."""
    params = _parse_tle(line1, line2)
    start = datetime.now(timezone.utc)
    points = []
    for m in range(minutes):
        t = start + timedelta(minutes=m)
        lat, lon = _sat_lat_lon(params, t)
        points.append((lon, lat))

    img = Image.new("RGB", (width, height), (0, 0, 0))
    draw = ImageDraw.Draw(img)

    for lat in range(-60, 61, 30):
        y = height * (0.5 - lat / 180)
        draw.line([(0, y), (width, y)], fill=(64, 64, 64))
    for lon in range(-150, 151, 30):
        x = width * (0.5 + lon / 360)
        draw.line([(x, 0), (x, height)], fill=(64, 64, 64))

    def to_xy(lon: float, lat: float) -> tuple[float, float]:
        return width * (0.5 + lon / 360), height * (0.5 - lat / 180)

    path = [to_xy(lon, lat) for lon, lat in points]
    draw.line(path, fill=(255, 0, 0), width=2)

    return img


def save_satellite_map(
    path: str,
    line1: str,
    line2: str,
    width: int = 720,
    height: int = 360,
    minutes: int = 90,
) -> None:
    """Generate and save a satellite map image."""
    img = generate_satellite_map(line1, line2, width, height, minutes)
    img.save(path)
