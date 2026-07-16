"""Tests for the natural-language briefing service + route.

Hermetic: the autouse ``fake_cache`` fixture backs Redis in memory, ``_gather_inputs``
is stubbed to a fixed snapshot (no live feeds), and the Anthropic client is a mock
(``_get_client`` patched), so nothing hits the network."""
import copy
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

import app.services.briefing_service as bs
from app.config import settings
from app.main import app

# A fixed conditions snapshot in the shape _gather_inputs returns.
_INPUTS = {
    "as_of": "2026-07-16T06:00",
    "xray": {"class": "C3.4", "flux_wm2": 3.4e-6},
    "proton": {"flux_gt10_pfu": 1.0, "storm": None, "in_progress": False},
    "kp": 3.0,
    "kp_g_scale": None,
    "dst_nt": -20.0,
    "dst_level": None,
    "solar_wind": {"speed_km_s": 450.0, "bz_nt": -3.0, "bt_nt": 5.0},
    "sunspot_number": 120.0,
    "kp_forecast": {"kp": 4.0, "g_scale": None},
    "noaa_outlook": {"today": {"r": "0", "s": "0", "g": "1"}, "forecast_g": ["1", "0", "0"]},
    "inbound_cmes": [{"id": "cme-1", "arrival": "2026-07-18T06:00"}],
    "alerts": [{"id": "alert:xray_flare:1", "severity": "warning"}],
    "storylines": [{"chain_id": "xray_flare:1", "severity": "warning"}],
}


class _Block:
    type = "text"

    def __init__(self, text: str):
        self.text = text


class _Resp:
    def __init__(self, text: str, stop_reason: str = "end_turn"):
        self.content = [_Block(text)]
        self.stop_reason = stop_reason


def _mock_client(text: str = "Quiet. Nothing notable.", stop_reason: str = "end_turn") -> MagicMock:
    client = MagicMock()
    client.messages.create = AsyncMock(return_value=_Resp(text, stop_reason))
    return client


@pytest.fixture
def enabled(monkeypatch):
    """Feature enabled with a fake key + a stubbed input snapshot."""
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    monkeypatch.setattr(settings, "briefing_enabled", True)
    monkeypatch.setattr(bs, "_gather_inputs", AsyncMock(return_value=copy.deepcopy(_INPUTS)))


# ── Change-gate signature (pure) ─────────────────────────────────────────────


def test_signature_stable_under_subbucket_jitter():
    a = copy.deepcopy(_INPUTS)
    b = copy.deepcopy(_INPUTS)
    b["kp"] = 3.2                      # < 0.5 bucket
    b["solar_wind"]["speed_km_s"] = 470.0   # < 50 km/s bucket
    b["solar_wind"]["bz_nt"] = -3.4         # < 2 nT bucket
    b["sunspot_number"] = 124.0             # < 10 bucket
    b["xray"]["flux_wm2"] = 3.9e-6          # not part of the signature
    assert bs._conditions_signature(a) == bs._conditions_signature(b)


def test_signature_changes_on_material_shift():
    base = bs._conditions_signature(_INPUTS)
    flare = copy.deepcopy(_INPUTS)
    flare["xray"]["class"] = "M1.0"         # class transition
    assert bs._conditions_signature(flare) != base

    new_alert = copy.deepcopy(_INPUTS)
    new_alert["alerts"].append({"id": "alert:proton_event:9", "severity": "critical"})
    assert bs._conditions_signature(new_alert) != base

    new_cme = copy.deepcopy(_INPUTS)
    new_cme["inbound_cmes"].append({"id": "cme-2", "arrival": "2026-07-19T00:00"})
    assert bs._conditions_signature(new_cme) != base


# ── generate_briefing ────────────────────────────────────────────────────────


async def test_generate_calls_model_and_is_change_gated(db_session, monkeypatch, enabled):
    client = _mock_client("Unsettled. C-class flaring; G1 watch.")
    monkeypatch.setattr(bs, "_get_client", lambda: client)

    first = await bs.generate_briefing(db_session)
    assert first.available is True
    assert first.text == "Unsettled. C-class flaring; G1 watch."
    assert first.generated_at is not None
    assert first.model == settings.briefing_model
    assert client.messages.create.await_count == 1

    # Same conditions -> served from cache, model NOT called again.
    second = await bs.generate_briefing(db_session)
    assert second.text == first.text
    assert client.messages.create.await_count == 1

    # force bypasses the gate.
    await bs.generate_briefing(db_session, force=True)
    assert client.messages.create.await_count == 2


async def test_material_change_triggers_regeneration(db_session, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    client = _mock_client("first")
    monkeypatch.setattr(bs, "_get_client", lambda: client)

    monkeypatch.setattr(bs, "_gather_inputs", AsyncMock(return_value=copy.deepcopy(_INPUTS)))
    await bs.generate_briefing(db_session)
    assert client.messages.create.await_count == 1

    changed = copy.deepcopy(_INPUTS)
    changed["xray"]["class"] = "X1.0"
    monkeypatch.setattr(bs, "_gather_inputs", AsyncMock(return_value=changed))
    await bs.generate_briefing(db_session)
    assert client.messages.create.await_count == 2   # conditions moved -> regenerated


async def test_no_key_is_unavailable(db_session, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    client = _mock_client()
    monkeypatch.setattr(bs, "_get_client", lambda: client)

    res = await bs.generate_briefing(db_session)
    assert res.available is False
    assert res.text is None
    client.messages.create.assert_not_called()


async def test_api_error_falls_back_to_last_good_brief(db_session, monkeypatch, enabled):
    good = _mock_client("Good brief.")
    monkeypatch.setattr(bs, "_get_client", lambda: good)
    await bs.generate_briefing(db_session)   # seeds cache

    # Conditions change so the gate opens, but the model call now errors.
    changed = copy.deepcopy(_INPUTS)
    changed["xray"]["class"] = "M5.0"
    monkeypatch.setattr(bs, "_gather_inputs", AsyncMock(return_value=changed))
    broken = MagicMock()
    broken.messages.create = AsyncMock(side_effect=RuntimeError("API down"))
    monkeypatch.setattr(bs, "_get_client", lambda: broken)

    res = await bs.generate_briefing(db_session)   # must not raise
    assert res.text == "Good brief."               # served the last good brief
    assert res.available is True


async def test_refusal_keeps_last_good_brief(db_session, monkeypatch, enabled):
    good = _mock_client("Good brief.")
    monkeypatch.setattr(bs, "_get_client", lambda: good)
    await bs.generate_briefing(db_session)

    changed = copy.deepcopy(_INPUTS)
    changed["xray"]["class"] = "M5.0"
    monkeypatch.setattr(bs, "_gather_inputs", AsyncMock(return_value=changed))
    monkeypatch.setattr(bs, "_get_client", lambda: _mock_client("ignored", stop_reason="refusal"))

    res = await bs.generate_briefing(db_session)
    assert res.text == "Good brief."


# ── Route ────────────────────────────────────────────────────────────────────


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_briefing_route_serves_cache(client, db_session, monkeypatch, enabled):
    monkeypatch.setattr(bs, "_get_client", lambda: _mock_client("Active. M-flare in progress."))
    await bs.generate_briefing(db_session)   # populate the cache

    r = await client.get("/api/summary/briefing")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is True
    assert body["text"] == "Active. M-flare in progress."
    assert body["model"] == settings.briefing_model


async def test_briefing_route_unavailable_without_key(client, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    r = await client.get("/api/summary/briefing")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is False
    assert body["text"] is None
