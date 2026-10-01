"""Tests for the solar image catalog and live SDO frame resolution (network-free)."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest

import app.services.sdo_latest as sl
import app.services.solar_image_service as si
from app.services.solar_image_service import CATALOG, _with_cache_bust


@pytest.fixture(autouse=True)
def _fresh_frame_cache():
    sl._cache = None
    yield
    sl._cache = None


def test_catalog_has_core_channels():
    ids = {s.id for s in CATALOG}
    assert {"aia171", "aia193", "aia211", "aia304", "hmiic", "hmib", "suvi195"} <= ids


def test_catalog_sources_resolvable():
    for s in CATALOG:
        assert s.label  # human-readable label present
        # Each entry is either a live SDO channel or a fixed-name image, never both.
        assert (s.sdo_code is None) != (s.url is None)
        assert s.sdo_code is None or s.sdo_code in sl.SDO_CODES
        assert s.url is None or s.url.startswith("https://")


def test_cache_bust_appends_timestamp():
    ts = datetime(2026, 6, 15, 17, 42, tzinfo=timezone.utc)
    out = _with_cache_bust("https://x/y.jpg", ts)
    assert out == f"https://x/y.jpg?ts={int(ts.timestamp())}"


# ── Live SDO frames: SDO dated browse archive / JSOC HMI / SDO latest/ ──

_TODAY = datetime.now(timezone.utc).date()
_YESTERDAY = _TODAY - timedelta(days=1)
_STALE_LM = "Mon, 21 Sep 2026 15:42:27 GMT"  # when SDO's latest/ folder froze


def _stamp(day, hhmmss: str) -> str:
    return f"{day:%Y%m%d}_{hhmmss}"


def _at(day, hhmmss: str) -> datetime:
    return datetime.strptime(_stamp(day, hhmmss), "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)


def _listing(*frames: tuple[str, str]) -> str:
    """Apache autoindex page, newest first; every frame at all four sizes."""
    rows = "".join(
        f'<img src="/icons/image2.gif" alt="[IMG]"> <a href="{n}">{n}</a>  2026-10-01 12:00  500K\n'
        for stamp, code in frames
        for n in (f"{stamp}_{res}_{code}.jpg" for res in (512, 4096, 2048, 1024))
    )
    return f"<html><body><pre>{rows}</pre></body></html>\n"


def _jsoc_times(**stamps: str) -> str:
    return "".join(f"{k}:\t{v}\n" for k, v in stamps.items())


def _client(*, today=None, yesterday=None, jsoc=None, latest_lm=None, log=None):
    """Mock upstream: a missing listing/manifest 404s; ``latest_lm`` is the
    Last-Modified served by SDO's latest/ folder (None = 404)."""

    def handler(request: httpx.Request) -> httpx.Response:
        if log is not None:
            log.append(str(request.url))
        url = str(request.url)
        for day, body in ((_TODAY, today), (_YESTERDAY, yesterday)):
            if url.startswith(sl.SDO_BROWSE_DIR.format(d=day)):
                return httpx.Response(200, text=body) if body else httpx.Response(404)
        if url.startswith(sl.JSOC_HMI_LATEST):
            return httpx.Response(200, text=jsoc) if jsoc else httpx.Response(404)
        if url.startswith(sl.SDO_LATEST) and latest_lm:
            return httpx.Response(200, headers={"last-modified": latest_lm})
        return httpx.Response(404)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_browse_picks_newest_frame_per_code():
    today = _listing(
        (_stamp(_TODAY, "121000"), "HMIBC"),
        (_stamp(_TODAY, "120500"), "0171"),
        (_stamp(_TODAY, "115500"), "0171"),
        (_stamp(_TODAY, "115000"), "HMIB"),
    )
    async with _client(today=today) as c:
        frames = await sl.latest_sdo_frames(c)

    f = frames["0171"]
    assert f.time == _at(_TODAY, "120500")  # the newer of the two
    assert f.thumb_url == f"{sl.SDO_BROWSE_DIR.format(d=_TODAY)}{_stamp(_TODAY, '120500')}_512_0171.jpg"
    assert f.full_url.endswith(f"{_stamp(_TODAY, '120500')}_2048_0171.jpg")
    # Exact code match: HMIB must not pick up the newer HMIBC row.
    assert frames["HMIB"].time == _at(_TODAY, "115000")
    # Nothing anywhere for the other channels -> left out, not faked.
    assert "0193" not in frames


async def test_live_browse_frame_used_over_frozen_latest_folder():
    # The reported bug: latest/ stuck on 2026-09-21 while the dated archive is live.
    today = _listing((_stamp(_TODAY, "120000"), "0171"))
    async with _client(today=today, latest_lm=_STALE_LM) as c:
        frames = await sl.latest_sdo_frames(c)
    assert frames["0171"].time == _at(_TODAY, "120000")
    assert "/browse/" in frames["0171"].full_url
    # Channels absent from the archive still get latest/ as a last resort.
    assert frames["0193"].full_url == f"{sl.SDO_LATEST}/latest_2048_0193.jpg"


async def test_rows_beyond_scan_window_are_not_used():
    # 0193's newest row is 4 h older than the archive's newest frame: not live.
    today = _listing(
        (_stamp(_TODAY, "120000"), "0171"),
        (_stamp(_TODAY, "080000"), "0193"),
    )
    async with _client(today=today) as c:
        frames = await sl.latest_sdo_frames(c)
    assert "0171" in frames
    assert "0193" not in frames


async def test_hmi_takes_newest_of_browse_and_jsoc():
    today = _listing(
        (_stamp(_TODAY, "120000"), "HMIB"),
        (_stamp(_TODAY, "120000"), "HMIIC"),
    )
    jsoc = _jsoc_times(
        continuum=_stamp(_TODAY, "123000"),
        magnetogram=_stamp(_TODAY, "123000"),  # newer than browse HMIB
        colorIc=_stamp(_TODAY, "110000"),      # older than browse HMIIC
    )
    async with _client(today=today, jsoc=jsoc) as c:
        frames = await sl.latest_sdo_frames(c)
    assert frames["HMIB"].time == _at(_TODAY, "123000")
    assert frames["HMIB"].thumb_url == f"{sl.JSOC_HMI_LATEST}/HMI_latest_Mag_256x256.gif"
    assert frames["HMIIC"].time == _at(_TODAY, "120000")
    assert "/browse/" in frames["HMIIC"].thumb_url


async def test_jsoc_supplies_hmi_missing_from_browse():
    # Since 2026-09-24 HMI is absent from SDO's feeds; JSOC still has it.
    today = _listing((_stamp(_TODAY, "120000"), "0171"))
    jsoc = _jsoc_times(magnetogram=_stamp(_TODAY, "115500"), colorIc=_stamp(_TODAY, "114500"))
    async with _client(today=today, jsoc=jsoc, latest_lm=_STALE_LM) as c:
        frames = await sl.latest_sdo_frames(c)
    assert frames["HMIB"].full_url == f"{sl.JSOC_HMI_LATEST}/HMI_latest_Mag_1024x1024.gif"
    assert frames["HMIIC"].full_url == f"{sl.JSOC_HMI_LATEST}/HMI_latest_colInt_1024x1024.jpg"
    assert frames["HMIIC"].time == _at(_TODAY, "114500")


async def test_short_today_listing_reaches_into_yesterday():
    # Just after 00:00 UTC today's folder holds a few frames; yesterday's newest
    # frames are still inside the window, older ones are not.
    today = _listing((_stamp(_TODAY, "000500"), "0171"))
    yesterday = _listing(
        (_stamp(_YESTERDAY, "235500"), "0193"),
        (_stamp(_YESTERDAY, "200000"), "0211"),  # 4 h before today's 00:05
    )
    async with _client(today=today, yesterday=yesterday) as c:
        frames = await sl.latest_sdo_frames(c)
    assert frames["0171"].time == _at(_TODAY, "000500")
    assert frames["0193"].time == _at(_YESTERDAY, "235500")
    assert frames["0193"].full_url.startswith(sl.SDO_BROWSE_DIR.format(d=_YESTERDAY))
    assert "0211" not in frames


async def test_missing_today_folder_uses_yesterday():
    yesterday = _listing((_stamp(_YESTERDAY, "235500"), "0171"))
    async with _client(yesterday=yesterday) as c:
        frames = await sl.latest_sdo_frames(c)
    assert frames["0171"].time == _at(_YESTERDAY, "235500")


async def test_today_window_stops_before_yesterday():
    # Today's listing already spans the window, so yesterday is never fetched.
    log: list[str] = []
    today = _listing(
        (_stamp(_TODAY, "120000"), "0171"),
        (_stamp(_TODAY, "060000"), "0193"),
    )
    async with _client(today=today, log=log) as c:
        await sl.latest_sdo_frames(c)
    assert not any(u.startswith(sl.SDO_BROWSE_DIR.format(d=_YESTERDAY)) for u in log)


async def test_unreachable_feeds_fall_back_to_latest_folder():
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(sl.SDO_LATEST):
            return httpx.Response(200, headers={"last-modified": _STALE_LM})
        raise httpx.ConnectError("down", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        frames = await sl.latest_sdo_frames(c)
    assert set(frames) == set(sl.SDO_CODES)
    assert frames["0171"].time == datetime(2026, 9, 21, 15, 42, 27, tzinfo=timezone.utc)


async def test_lookup_is_cached_briefly():
    log: list[str] = []
    today = _listing((_stamp(_TODAY, "120000"), "0171"))
    async with _client(today=today, log=log) as c:
        first = await sl.latest_sdo_frames(c)
        calls = len(log)
        assert await sl.latest_sdo_frames(c) == first
    assert len(log) == calls


# ── Gallery assembly ──


async def test_gallery_uses_live_frames_and_omits_unavailable_channels():
    t = datetime(2026, 10, 1, 16, 36, 10, tzinfo=timezone.utc)
    frames = {"0171": sl.Frame(t, "https://sdo/thumb_0171.jpg", "https://sdo/full_0171.jpg")}
    suvi_t = datetime(2026, 10, 1, 16, 44, tzinfo=timezone.utc)
    with patch.object(si, "latest_sdo_frames", new=AsyncMock(return_value=frames)), patch.object(
        si, "_observation_time", new=AsyncMock(return_value=suvi_t)
    ):
        out = await si.get_latest_solar_images()

    assert [i.id for i in out] == ["aia171", "suvi195"]  # catalog order, gaps dropped
    aia = out[0]
    assert aia.timestamp == t
    assert aia.thumbnail_url == _with_cache_bust("https://sdo/thumb_0171.jpg", t)
    assert aia.full_url == _with_cache_bust("https://sdo/full_0171.jpg", t)
    assert out[1].timestamp == suvi_t


async def test_filtered_gallery_skips_sdo_lookup_for_suvi_only():
    lookup = AsyncMock(return_value={})
    with patch.object(si, "latest_sdo_frames", new=lookup), patch.object(
        si, "_observation_time", new=AsyncMock(return_value=datetime.now(timezone.utc))
    ):
        out = await si.get_solar_images("GOES", None, None)
    assert [i.id for i in out] == ["suvi195"]
    lookup.assert_not_awaited()
