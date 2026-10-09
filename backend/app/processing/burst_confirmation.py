"""Multi-station confirmation of ML radio-burst detections.

The burst model scores each ~15-minute e-CALLISTO file on its own, and on its own
it is not enough: a handful of stations flag a large share of everything they
record (local interference), so at any daytime minute two or more stations are
usually "seeing a burst" by chance. A burst is only believed when **different
stations see it at the same time, and the combined evidence of every station
observing says it is far likelier a burst than chance**.

``confirm_bursts`` is that rule, on minute resolution:

1. *Sun up.* A file only counts while the Sun is above the station's horizon —
   a night-time "burst" is interference by definition.
2. *Same time.* Readings agree when their files overlap in time (no fixed
   quarter-hour windows, so a burst at a window edge is not split).
3. *Independent views.* Stations closer than ``site_radius_km`` are one site and
   count once, so one observatory's interference cannot confirm itself.
4. *Evidence, weighted by each station's track record.* Every observing station
   has a reading: silent, or a burst at low (model minimum..0.8), mid (0.8..0.9)
   or high (>= 0.9) confidence. Each reading carries
   ``log(P(reading | burst) / P(reading | chance))`` — learned per station
   (``measure_reliability``): a flag from a station that rarely flags and is
   usually right weighs a lot; one from a station that flags half its day
   weighs next to nothing; a clean station staying silent counts *against* a
   burst (scaled by ``silence_weight``, as a narrow-band receiver can miss a
   real burst). Per site the most informative station speaks.
5. *Confirmed* when the site evidence adds up to ``min_evidence`` (nats; 4.0 =
   the readings are ~55x likelier under a burst than by chance) **and** at
   least ``min_sites`` different sites flag it at high confidence, with at
   least ``min_observing_sites`` observing.

Confirmed minutes merge into events (gaps up to ``merge_gap_minutes`` bridged).
The tuning behind the defaults is in docs/radio-burst-confirmation.md.

Pure (no DB, no I/O); numpy only.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import numpy as np
from scipy.special import pdtrc

from app.processing.callisto_stations import STATION_LOCATIONS, site_map, sun_elevation

SEGMENT = timedelta(minutes=15)

# Reading categories.
SILENT, LOW, MID, HIGH = 0, 1, 2, 3
N_CATEGORIES = 4

# Chance-rate bounds: a station that never flagged still has *some* chance of
# doing so, and one that always flags must not blow the expectation up.
DUTY_FLOOR = 0.002
DUTY_CEIL = 0.95
# Chance rate assumed for a voter whose rate is unknown.
DEFAULT_DUTY = 0.1
# A reading counts as supporting a burst ("confirms") above this evidence.
SUPPORT_MIN_LLR = 0.5


@dataclass(frozen=True)
class ConfirmationParams:
    high_conf: float = 0.9            # a "high" reading: p >= this
    mid_conf: float = 0.8             # a "mid" reading: mid_conf <= p < high_conf
    min_evidence: float = 4.0         # nats of combined site evidence
    silence_weight: float = 0.8       # how much a silent station counts against
    min_sites: int = 2                # sites that must flag at high confidence
    min_observing_sites: int = 3      # sites observing (sun up) for a verdict
    site_radius_km: float = 30.0      # stations closer than this are one site
    sun_min_elevation: float = 0.0    # degrees; below it a file does not count
    merge_gap_minutes: int = 5        # confirmed minutes this close are one event
    anchor_alpha: float = 1e-3        # measurement: what counts as a sure burst


@dataclass(frozen=True)
class StationEvidence:
    """Evidence per reading category (silent, low, mid, high), in nats."""
    llr: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    excluded: bool = False            # ignored entirely (operator override)


class EvidenceTable:
    """Per-station evidence with a fallback for stations it does not know."""

    def __init__(
        self,
        stations: Mapping[str, StationEvidence] | None = None,
        default: StationEvidence = StationEvidence(),
    ):
        self.stations = dict(stations or {})
        self.default = default

    def get(self, station: str) -> StationEvidence:
        return self.stations.get(station, self.default)


@dataclass
class ConfirmedBurst:
    start: datetime
    end: datetime
    evidence: float                   # peak combined evidence (nats) in the span
    sites: list[str]                  # distinct sites whose readings support it
    confirming: list[dict]            # detections whose readings support it
    also_flagged: list[dict] = field(default_factory=list)  # other sun-up Burst files overlapping it

    @property
    def likelihood_ratio(self) -> float:
        return float(np.exp(min(self.evidence, 700.0)))

    @property
    def confirming_stations(self) -> list[str]:
        return sorted({d["station"] for d in self.confirming})

    @property
    def also_flagged_stations(self) -> list[str]:
        confirming = set(self.confirming_stations)
        return sorted({d["station"] for d in self.also_flagged} - confirming)


@dataclass
class ConfirmationResult:
    events: list[ConfirmedBurst]
    unconfirmed: list[dict]           # Burst detections that overlap no confirmed burst


# ── Preparation ──────────────────────────────────────────────────────────────


def _utc(dt: datetime) -> datetime:
    """Naive datetimes (SQLite) are UTC."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


@dataclass
class _Prepared:
    rows: list[dict]
    station: list[str]
    t0: np.ndarray
    t1: np.ndarray
    prob: np.ndarray
    burst: np.ndarray                 # labelled Burst and above its model's minimum
    sun_up: np.ndarray
    level: np.ndarray                 # reading category of the file

    def subset(self, keep: np.ndarray) -> "_Prepared":
        return _Prepared(
            rows=[self.rows[i] for i in keep], station=[self.station[i] for i in keep],
            t0=self.t0[keep], t1=self.t1[keep], prob=self.prob[keep], burst=self.burst[keep],
            sun_up=self.sun_up[keep], level=self.level[keep],
        )


def _prepare(
    detections: Iterable[dict],
    params: ConfirmationParams,
    burst_minimum: Callable[[str | None], float] | None,
    locations: Mapping[str, tuple[float, float]],
) -> _Prepared:
    rows = list(detections)
    minimums: dict[str | None, float] = {}

    def _minimum(model_id: str | None) -> float:
        if burst_minimum is None:
            return 0.0
        if model_id not in minimums:
            minimums[model_id] = burst_minimum(model_id)
        return minimums[model_id]

    n = len(rows)
    t0 = np.empty(n)
    t1 = np.empty(n)
    prob = np.empty(n)
    burst = np.zeros(n, dtype=bool)
    lat = np.full(n, np.nan)
    lon = np.full(n, np.nan)
    stations: list[str] = []
    for i, r in enumerate(rows):
        start = _utc(r["start_time"])
        end = r.get("end_time")
        end = _utc(end) if end is not None else None
        # A segment is ~15 min; a missing or degenerate end means "one segment".
        if end is None or end <= start:
            end = start + SEGMENT
        t0[i], t1[i] = start.timestamp(), end.timestamp()
        prob[i] = float(r["probability"])
        burst[i] = r.get("predicted_label") == "Burst" and prob[i] >= _minimum(r.get("model_id"))
        st = r["station"]
        stations.append(st)
        if st in locations:
            lat[i], lon[i] = locations[st]
    known = ~np.isnan(lat)
    sun_up = np.ones(n, dtype=bool)  # unknown location: cannot tell, so assume up
    if known.any():
        elev = np.maximum.reduce(
            [
                sun_elevation(t0[known], lat[known], lon[known]),
                sun_elevation((t0[known] + t1[known]) / 2, lat[known], lon[known]),
                sun_elevation(t1[known], lat[known], lon[known]),
            ]
        )
        sun_up[known] = elev >= params.sun_min_elevation
    level = np.where(
        ~burst, SILENT,
        np.where(prob >= params.high_conf, HIGH, np.where(prob >= params.mid_conf, MID, LOW)),
    ).astype(np.int8)
    return _Prepared(rows, stations, t0, t1, prob, burst, sun_up, level)


def _minutes(p: _Prepared) -> tuple[float, np.ndarray, np.ndarray, int]:
    """Minute grid: origin (epoch s), per-row [m0, m1) and the grid length."""
    origin = np.floor(p.t0.min() / 60.0) * 60.0
    m0 = np.rint((p.t0 - origin) / 60.0).astype(np.int64)
    m1 = np.maximum(np.rint((p.t1 - origin) / 60.0).astype(np.int64), m0 + 1)
    return origin, m0, m1, int(m1.max())


def _paint(n_rows: int, T: int, row: np.ndarray, m0: np.ndarray, m1: np.ndarray) -> np.ndarray:
    """[n_rows, T] count of intervals covering each minute."""
    diff = np.zeros((n_rows, T + 1), dtype=np.int32)
    np.add.at(diff, (row, m0), 1)
    np.add.at(diff, (row, m1), -1)
    return np.cumsum(diff, axis=1)[:, :T]


def _readings(n_rows: int, T: int, row, m0, m1, level) -> np.ndarray:
    """[n_rows, T] reading category per minute: the strongest covering file's
    level, or -1 where the row has no (sun-up) file."""
    out = np.full((n_rows, T), -1, dtype=np.int8)
    for lv in range(N_CATEGORIES):
        sel = level >= lv
        if sel.any():
            out[_paint(n_rows, T, row[sel], m0[sel], m1[sel]) > 0] = lv
    return out


def _runs(mask: np.ndarray, merge_gap: int) -> list[tuple[int, int]]:
    """Contiguous True runs ``[a, b)``, merged across gaps <= ``merge_gap``."""
    edges = np.diff(np.concatenate([[0], mask.astype(np.int8), [0]]))
    out: list[list[int]] = []
    for a, b in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)):
        if out and a - out[-1][1] <= merge_gap:
            out[-1][1] = int(b)
        else:
            out.append([int(a), int(b)])
    return [(a, b) for a, b in out]


def chance_probability(k: np.ndarray, lam: np.ndarray) -> np.ndarray:
    """P(Poisson(lam) >= k), elementwise (k >= 1)."""
    k = np.asarray(k)
    return pdtrc(k - 1, np.maximum(np.asarray(lam, dtype=float), 1e-9))


# ── Confirmation ─────────────────────────────────────────────────────────────


def confirm_bursts(
    detections: Iterable[dict],
    evidence: EvidenceTable,
    params: ConfirmationParams = ConfirmationParams(),
    burst_minimum: Callable[[str | None], float] | None = None,
    locations: Mapping[str, tuple[float, float]] = STATION_LOCATIONS,
) -> ConfirmationResult:
    """Confirmed bursts among scored files (see the module docstring).

    ``detections`` are scored-file rows — **both** labels, since a silent
    station is evidence too — with ``station``, ``start_time``, optional
    ``end_time``, ``probability``, ``predicted_label`` and optional ``model_id``.
    ``burst_minimum(model_id)`` is the probability a row's own model needs to
    call it a burst (rows of a retired model are judged by that model's threshold).
    """
    p = _prepare(detections, params, burst_minimum, locations)
    if not p.burst.any():
        return ConfirmationResult(events=[], unconfirmed=[])
    excluded = np.array([evidence.get(st).excluded for st in p.station], dtype=bool)
    usable = np.flatnonzero(p.sun_up & ~excluded)
    if usable.size == 0:
        return ConfirmationResult(events=[], unconfirmed=[p.rows[i] for i in np.flatnonzero(p.burst)])

    origin, m0_all, m1_all, T = _minutes(p)
    u = p.subset(usable)
    m0, m1 = m0_all[usable], m1_all[usable]
    names = sorted(set(u.station))
    stidx = {s: i for i, s in enumerate(names)}
    st_row = np.array([stidx[s] for s in u.station])
    site_of = site_map(names, params.site_radius_km, locations)
    site_names = sorted(set(site_of.values()))
    sidx = {s: i for i, s in enumerate(site_names)}
    st_site = np.array([sidx[site_of[s]] for s in names])
    S = len(site_names)

    # Evidence per station-minute, then per site: its most informative station.
    readings = _readings(len(names), T, st_row, m0, m1, u.level)
    site_evidence = np.full((S, T), -np.inf)
    site_high = np.zeros((S, T), dtype=bool)
    for i, st in enumerate(names):
        table = np.array(evidence.get(st).llr, dtype=float)
        table[SILENT] *= params.silence_weight
        r = readings[i]
        vals = np.where(r >= 0, table[np.clip(r, 0, 3)], -np.inf)
        np.maximum(site_evidence[st_site[i]], vals, out=site_evidence[st_site[i]])
        site_high[st_site[i]] |= r == HIGH
    observing = np.isfinite(site_evidence)
    total = np.where(observing, site_evidence, 0.0).sum(axis=0)
    confirmed = (
        (total >= params.min_evidence)
        & (site_high.sum(axis=0) >= params.min_sites)
        & (observing.sum(axis=0) >= params.min_observing_sites)
    )

    row_llr = np.array(
        [evidence.get(st).llr[lv] for st, lv in zip(u.station, u.level)], dtype=float
    )
    supports = u.burst & (row_llr >= SUPPORT_MIN_LLR)

    def _when(minute: int) -> datetime:
        return datetime.fromtimestamp(origin + minute * 60.0, tz=timezone.utc)

    def _ordered(rows: list[dict], t0: np.ndarray, st: list[str], idx: np.ndarray) -> list[dict]:
        return [rows[i] for i in sorted(idx, key=lambda i: (t0[i], st[i]))]

    events: list[ConfirmedBurst] = []
    claimed = np.zeros(len(p.rows), dtype=bool)
    for a, b in _runs(confirmed, params.merge_gap_minutes):
        over_u = (m0 < b) & (m1 > a)
        conf_idx = np.flatnonzero(over_u & supports)
        also_idx = np.flatnonzero(over_u & u.burst & ~supports)
        claimed |= (m0_all < b) & (m1_all > a) & p.burst
        events.append(
            ConfirmedBurst(
                start=_when(a),
                end=_when(b),
                evidence=float(total[a:b].max()),
                sites=sorted({site_of[u.station[i]] for i in conf_idx}),
                confirming=_ordered(u.rows, u.t0, u.station, conf_idx),
                also_flagged=_ordered(u.rows, u.t0, u.station, also_idx),
            )
        )
    unconfirmed = _ordered(p.rows, p.t0, p.station, np.flatnonzero(p.burst & ~claimed))
    return ConfirmationResult(events=events, unconfirmed=unconfirmed)


# ── Station reliability + evidence measurement ───────────────────────────────


@dataclass
class StationMeasure:
    files: int = 0                    # sun-up files scored
    bursts: int = 0                   # of those, labelled Burst
    judged: int = 0                   # bursts with >= 3 other sites observing
    confirmed: int = 0                # judged bursts that >= 2 other sites also flagged
    chance_rate: float | None = None  # the same rate with the station day-shifted
    score: float | None = None        # (rate - chance) / (1 - chance)
    duty: float | None = None         # share of its observing minutes flagged >= high_conf
    observed_minutes: int = 0
    # Minutes per reading category while observing, and during anchor bursts.
    null_counts: tuple[int, int, int, int] = (0, 0, 0, 0)
    anchor_counts: tuple[int, int, int, int] = (0, 0, 0, 0)


def measure_reliability(
    detections: Iterable[dict],
    params: ConfirmationParams = ConfirmationParams(),
    burst_minimum: Callable[[str | None], float] | None = None,
    locations: Mapping[str, tuple[float, float]] = STATION_LOCATIONS,
    voters: Mapping[str, tuple[bool, float]] | None = None,
    shift_days: tuple[int, ...] = (-3, -2, -1, 1, 2, 3),
    min_others_observing: int = 3,
    min_others_flagging: int = 2,
) -> dict[str, StationMeasure]:
    """Each station's track record, from stored detections.

    *Score* — for every sun-up Burst file of a station with at least
    ``min_others_observing`` other sites observing: is it overlapped by
    high-confidence bursts from at least ``min_others_flagging`` other sites?
    That share (``rate``) is compared with the share when the station's files are
    moved by whole days (``chance_rate``): ``score = (rate - chance) / (1 - chance)``
    — ~0 for a station whose flags are noise, up to ~0.7 for the cleanest. "Other"
    means other *sites*, so a co-located twin cannot vouch.

    *Readings* — minutes per category (silent/low/mid/high) while observing
    (``null_counts``), and during *anchor* bursts (``anchor_counts``): minutes the
    other sites' ``voters`` — ``{station: (votes, chance_rate)}``, normally the
    stations that cleared the score bar — confirm on their own with a chance
    probability <= ``anchor_alpha``. Without ``voters`` no anchors are counted.
    """
    p = _prepare(detections, params, burst_minimum, locations)
    keep = np.flatnonzero(p.sun_up)
    out: dict[str, StationMeasure] = {}
    if keep.size == 0:
        return out
    p = p.subset(keep)
    _, m0, m1, T = _minutes(p)
    names = sorted(set(p.station))
    stidx = {s: i for i, s in enumerate(names)}
    st_row = np.array([stidx[s] for s in p.station])
    site_of = site_map(names, params.site_radius_km, locations)
    site_names = sorted(set(site_of.values()))
    sidx = {s: i for i, s in enumerate(site_names)}
    s_row = np.array([sidx[site_of[st]] for st in p.station])
    S = len(site_names)

    high = p.burst & (p.prob >= params.high_conf)
    observing = _paint(S, T, s_row, m0, m1) > 0
    flagging = _paint(S, T, s_row[high], m0[high], m1[high]) > 0
    n_observing = observing.sum(axis=0)
    n_flagging = flagging.sum(axis=0)
    readings = _readings(len(names), T, st_row, m0, m1, p.level)
    stations = np.array(p.station)
    shifts = [d * 1440 for d in shift_days]

    # Anchor minutes per site: what the other sites' voters confirm on their own.
    anchors = np.zeros((S, T), dtype=bool)
    if voters:
        vote_hi = np.zeros((S, T), dtype=bool)
        chance = np.zeros((S, T))
        for i, st in enumerate(names):
            votes, duty = voters.get(st, (False, DEFAULT_DUTY))
            if not votes:
                continue
            s = sidx[site_of[st]]
            vote_hi[s] |= readings[i] == HIGH
            seg = chance[s]
            np.maximum(seg, np.where(readings[i] >= 0, float(np.clip(duty, DUTY_FLOOR, DUTY_CEIL)), 0.0), out=seg)
        k_all, lam_all = vote_hi.sum(axis=0), chance.sum(axis=0)
        for s in range(S):
            k = k_all - vote_hi[s]
            lam = lam_all - chance[s]
            cand = (k >= 3) & (n_observing - observing[s] >= params.min_observing_sites)
            if cand.any():
                anchors[s, cand] = chance_probability(k[cand], lam[cand]) <= params.anchor_alpha

    for st in names:
        mine = stations == st
        si = sidx[site_of[st]]
        others_obs = np.concatenate([[0], np.cumsum(n_observing - observing[si] >= min_others_observing)])
        others_flag = np.concatenate([[0], np.cumsum(n_flagging - flagging[si] >= min_others_flagging)])
        a_all, b_all = m0[mine & p.burst], m1[mine & p.burst]

        def _rate(shift: int) -> tuple[int, int]:
            a, b = a_all + shift, b_all + shift
            ok = (a >= 0) & (b <= T)
            a, b = a[ok], b[ok]
            judged = others_obs[b] - others_obs[a] > 0
            hit = (others_flag[b] - others_flag[a] > 0) & judged
            return int(hit.sum()), int(judged.sum())

        m = StationMeasure(files=int(mine.sum()), bursts=int((mine & p.burst).sum()))
        m.confirmed, m.judged = _rate(0)
        bg = [_rate(s) for s in shifts]
        bg_hits, bg_judged = sum(h for h, _ in bg), sum(n for _, n in bg)
        if bg_judged:
            m.chance_rate = bg_hits / bg_judged
        if m.judged and m.chance_rate is not None and m.chance_rate < 1.0:
            m.score = (m.confirmed / m.judged - m.chance_rate) / (1.0 - m.chance_rate)
        r = readings[stidx[st]]
        seen = r >= 0
        m.observed_minutes = int(seen.sum())
        m.null_counts = tuple(int(x) for x in np.bincount(r[seen], minlength=N_CATEGORIES)[:N_CATEGORIES])
        at_anchor = seen & anchors[si]
        m.anchor_counts = tuple(int(x) for x in np.bincount(r[at_anchor], minlength=N_CATEGORIES)[:N_CATEGORIES])
        if m.observed_minutes:
            m.duty = m.null_counts[HIGH] / m.observed_minutes
        out[st] = m
    return out
