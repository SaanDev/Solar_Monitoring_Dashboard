"""Where the e-CALLISTO stations are, and when each one can see the Sun.

Pure helpers (no DB, no I/O) for the multi-station burst confirmation
(``app.processing.burst_confirmation``):

* ``STATION_LOCATIONS`` — latitude/longitude per station, read from the
  ``OBS_LAT``/``OBS_LAC``/``OBS_LON``/``OBS_LOC`` cards of each station's FITS
  headers (2026-10). Stations missing here are simply treated as "location
  unknown": always sun-up, and a site of their own.
* ``sun_elevation`` — solar elevation at a place and time (low-precision
  almanac, ~0.01°; plenty for a sunrise/sunset cut).
* ``site_map`` — groups stations closer than a radius into one *site*, so
  co-located instruments (several antennas at one observatory) count once: their
  local interference must not be able to confirm itself.
"""
from __future__ import annotations

import math
from collections.abc import Iterable

import numpy as np

# (latitude, longitude) in degrees, east and north positive.
STATION_LOCATIONS: dict[str, tuple[float, float]] = {
    "ALASKA-ANCHORAGE": (61.200, -149.960),
    "ALASKA-COHOE": (60.370, -151.320),
    "ALASKA-HAARP": (62.400, -145.170),
    "ALGERIA-CRAAG": (36.460, 3.280),
    "ALMATY": (43.030, 76.580),
    "Australia-ASSA": (-34.662, 139.637),
    "AUSTRIA-Krumbach": (47.290, 9.550),
    # The header says 25.4 E (Ukraine); Michelbach, Lower Austria, is ~15.4 E.
    "AUSTRIA-MICHELBACH": (48.000, 15.400),
    "AUSTRIA-OE3FLB": (48.010, 15.350),
    "AUSTRIA-UNIGRAZ": (47.100, 15.500),
    "BIR": (53.094, -7.920),
    "BRAZIL": (-22.410, -45.000),
    "Croatia-Visnjan": (45.276, 13.721),
    "EGYPT-Alexandria": (30.800, 29.500),
    "EGYPT-SpaceAgency": (30.033, 31.233),
    "Finland-Kempele": (64.900, 25.500),
    "FINLAND-RUISSALO": (60.440, 22.170),
    "FINLAND-Siuntio": (60.100, 24.200),
    "GERMANY-DLR": (53.141, 12.546),
    "GERMANY-ESSEN": (51.394, 6.979),
    "GLASGOW": (55.900, -4.300),
    "GREENLAND": (66.970, -50.950),
    "HUMAIN": (50.192, 5.255),
    "HURBANOVO": (47.900, 18.200),
    "INDIA-GAURI": (13.600, 77.440),
    "INDIA-OOTY": (11.382, 76.667),
    "INDIA-UDAIPUR": (24.590, 73.210),
    "INDONESIA": (-9.595, 123.946),
    "ITALY-Strassolt": (45.840, 13.600),
    "Malaysia-Banting": (2.780, 101.510),
    "MEXART": (19.600, -101.200),
    "MEXICO-ENSENADA-UNAM": (30.439, -115.464),
    "MEXICO-FCFM-UNACH": (16.690, -93.190),
    "MEXICO-LANCE": (19.600, -101.200),
    "MEXICO-UANL-INFIERNILLO": (25.750, -100.310),
    "MONGOLIA-UB": (47.870, 107.050),
    "MRO": (60.200, 24.400),
    "MRT1": (-20.144, 57.721),
    "NORWAY-EGERSUND": (58.420, 5.970),
    "NORWAY-NY-AALESUND": (78.930, 11.870),
    "NORWAY-RANDABERG": (58.850, 5.600),
    "NZ-WAIRAKEI-DLR": (-38.633, 176.094),
    "PANAMA": (8.490, -80.330),
    "PANAMA-DINACE-UTP": (8.489, -80.329),
    "PARAGUAY": (-25.612, -57.237),
    "POLAND-BALDY": (53.590, 20.590),
    "POLAND-Grotniki": (51.890, 19.310),
    "PRT-FLR-HOT": (39.460, -31.130),
    "PRT-SMA-MAIA": (36.980, -25.120),
    "ROMANIA": (44.410, 26.090),
    "RWANDA": (-1.940, 30.400),
    "S-AFRICA-POTCHEFSTROOM": (-26.700, 27.100),
    "S-AFRICA-POTCHEFSTROOM-MWA": (-26.700, 27.100),
    "S-AFRICA-POTCHEFSTROOM-MWA-NS": (-26.700, 27.100),
    "SOUTHAFRICA-SANSA": (-32.370, 20.800),
    "SPAIN-PERALEJOS": (40.580, -1.920),
    "SPAIN-SIGUENZA": (41.300, -2.380),
    "SRI-Lanka": (7.900, 80.500),
    "SSRT": (51.750, 102.217),
    "SWISS-FM": (47.200, 8.750),
    "SWISS-HB9SCT": (47.200, 8.760),
    "SWISS-HEITERSWIL": (47.300, 9.130),
    "SWISS-IRSOL": (46.177, 8.789),
    "SWISS-Landschlacht": (47.630, 9.240),
    "SWISS-MUHEN": (47.328, 8.059),
    "SWISS-PHLWA": (47.000, 8.000),
    "TAIWAN-NCU": (24.970, 121.100),
    "TRIEST": (45.630, 13.875),
    "UK-GLASGOW": (55.782, -4.317),
    "UNAM": (19.123, -99.123),
    "URUGUAY": (-34.900, -56.200),
    "UZBEKISTAN": (39.600, 66.900),
}

_EARTH_RADIUS_KM = 6371.0


def sun_elevation(epoch_s, lat_deg, lon_deg):
    """Solar elevation in degrees at unix time(s) ``epoch_s`` for the given
    latitude/longitude (degrees, east positive). Accepts scalars or numpy arrays."""
    n = np.asarray(epoch_s, dtype=float) / 86400.0 + 2440587.5 - 2451545.0
    mean_lon = np.mod(280.460 + 0.9856474 * n, 360.0)
    anomaly = np.radians(np.mod(357.528 + 0.9856003 * n, 360.0))
    ecl_lon = np.radians(mean_lon + 1.915 * np.sin(anomaly) + 0.020 * np.sin(2 * anomaly))
    obliquity = np.radians(23.439 - 0.0000004 * n)
    ra = np.arctan2(np.cos(obliquity) * np.sin(ecl_lon), np.cos(ecl_lon))
    dec = np.arcsin(np.sin(obliquity) * np.sin(ecl_lon))
    gmst_h = np.mod(18.697374558 + 24.06570982441908 * n, 24.0)
    hour_angle = np.radians(gmst_h * 15.0 + np.asarray(lon_deg, dtype=float)) - ra
    lat = np.radians(np.asarray(lat_deg, dtype=float))
    return np.degrees(
        np.arcsin(np.sin(lat) * np.sin(dec) + np.cos(lat) * np.cos(dec) * np.cos(hour_angle))
    )


def distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance between two (lat, lon) points."""
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def site_map(
    stations: Iterable[str],
    radius_km: float,
    locations: dict[str, tuple[float, float]] = STATION_LOCATIONS,
) -> dict[str, str]:
    """{station: site} — stations within ``radius_km`` of each other (transitively)
    share a site, named after its alphabetically first member. A station with no
    known location is a site of its own."""
    names = sorted(set(stations))
    parent = {n: n for n in names}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    located = [n for n in names if n in locations]
    for i, a in enumerate(located):
        for b in located[i + 1 :]:
            if distance_km(locations[a], locations[b]) <= radius_km:
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[max(ra, rb)] = min(ra, rb)
    return {n: find(n) for n in names}
