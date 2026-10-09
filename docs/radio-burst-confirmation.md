# Multi-station radio-burst confirmation

The burst model (BnB v1.1) scores each ~15-minute e-CALLISTO file on its own. On its
own that is not enough to raise an alert: a handful of stations flag a large share
of everything they record (local interference), so at almost any daytime minute
two or more stations are "seeing a burst" by chance. A burst becomes a
`radio_burst` event only when **different stations see it at the same time, and
the readings of every station observing make a burst far likelier than chance**.

Code: `backend/app/processing/burst_confirmation.py` (the rule, pure),
`backend/app/services/station_reliability_service.py` (each station's record),
`backend/app/services/radio_burst_service.py` (events, alerts, history).

## The rule

For every minute:

1. **Sun up.** A file counts only while the Sun is above its station's horizon
   (`RADIO_BURST_SUN_MIN_ELEVATION`, 0°). Station coordinates come from the FITS
   `OBS_LAT`/`OBS_LON` cards (`processing/callisto_stations.py`); a station with no
   known location is assumed up.
2. **Same time.** Readings agree when their files overlap in time. There are no
   fixed quarter-hour windows, so a burst at a window edge is not split, and a
   confirmed event spans only the overlap of the files behind it.
3. **Independent views.** Stations within `RADIO_BURST_SITE_RADIUS_KM` (30 km) are
   one *site* and count once: MEXART/MEXICO-LANCE, MRO/FINLAND-Siuntio, the
   POTCHEFSTROOM instruments, SWISS-FM/HB9SCT, AUSTRIA-MICHELBACH/OE3FLB,
   GLASGOW/UK-GLASGOW, PANAMA/PANAMA-DINACE-UTP. 72 stations make 64 sites.
4. **Evidence, weighted by track record.** Every observing station has a
   reading: *silent*, or a burst at *low* (model minimum–0.8), *mid* (0.8–0.9) or
   *high* (≥ 0.9) confidence. Each reading carries
   `log(P(reading | burst) / P(reading | chance))`, learned per station:
   - A flag from a station that rarely flags and is usually right weighs a lot
     (HUMAIN, BIR: +2.3–2.6).
   - A flag from a station that flags half its day weighs next to nothing
     (AUSTRIA-OE3FLB: +0.25).
   - A clean station staying silent counts *against* a burst, scaled by
     `RADIO_BURST_SILENCE_WEIGHT` (0.8), because a narrow-band receiver can miss
     a real burst.

   Per site, the most informative station speaks.
5. **Confirmed** when the sites' evidence adds up to `RADIO_BURST_MIN_EVIDENCE`
   (4.0 nats: the readings are ~55× likelier under a burst than by chance)
   **and** at least `RADIO_BURST_MIN_SITES` (2) different sites flag it at
   p ≥ `RADIO_BURST_HIGH_CONF_PROBABILITY` (0.9), with at least
   `RADIO_BURST_MIN_OBSERVING_SITES` (3) observing.

Because silent observers count against, the bar adapts by itself. It is strict
at busy hours, when ~35 sites observe, and lenient at 20–23 UTC, when only
~9–12 do.

Confirmed minutes within 5 minutes of each other merge into one event. Its
description lists:
- the stations whose readings support it (evidence ≥ 0.5),
- the stations that also flagged it with little weight,
- the evidence as odds (e.g. "evidence 3,400:1"),
- the peak probability.

`events.stations` lists both groups, so the Timeline offers every spectrogram
that shows the burst.

## Station records

Every day the service measures each station over the trailing
`RADIO_BURST_RELIABILITY_DAYS` (60) of stored detections:

- **Chance spread:** its minutes per reading category while observing. Shrunk
  toward the all-station spread by two days' worth, so a station with a day of
  data is not taken as never flagging.
- **Burst spread:** its minutes per category during *anchor* bursts. These are
  minutes that the reliable stations at *other* sites confirm on their own,
  with a chance probability ≤ 0.001 (a strict count test).
- **Score:** how often its own bursts are also flagged by ≥ 2 other sites,
  compared with the same rate after moving its files by ±1–3 days:
  `score = (rate − chance) / (1 − chance)`. It is ~0 for noise and ~0.7 for the
  cleanest. Stations scoring ≥ `RADIO_BURST_MIN_RELIABILITY` (0.15) pick the
  anchor bursts.

These are blended with built-in priors measured on 140 days
(`processing/station_reliability_priors.py`), so a fresh install, such as the
desktop app, confirms bursts from day one. A station's chance rates never drop
below its long-run rates. In a quiet spell the measured rates fall, and taking
them at face value would lower the bar exactly when coincidences are most of
what there is to see.

**Settings → Burst Confirmation Stations** lists every station's weights and
status. Its overrides survive re-measurement:
- *Boost* gives a station's flags at least a typical reliable station's weight.
- *Ignore* leaves the station out entirely.

It can also re-measure on demand.

## How the defaults were chosen (2026-10-08)

The rules were replayed over 140 days of stored BnB v1.0 detections: 696k files
from 72 stations, 2026-05-21 → 10-07.

The false-alarm rate comes from **time slides**. Each site's detections are moved
by a different whole number of days (within ±32), so their time-of-day pattern
stays but real coincidences vanish; events that still appear are chance.

Recall is measured on the official e-CALLISTO list's **important bursts**: types
II, IV and V, plus III/IIIG/CTM of intensity 2–3 (536 of them). The list is a
reference, not ground truth.

| Rule | Events/day | Chance/day | Real (purity) | Important found | Type II | CTM |
|---|---|---|---|---|---|---|
| Old: ≥ 4 stations, ≥ 2 at p > 0.9, 15-min windows | 38 | ≈ real | ~0% | (flags most of the day) | | |
| v1 count test: reliable sites @ 0.9, Poisson α 0.01 | 3.64 | 0.26 | 92.8% | 74.3% | 83% | 39% |
| Evidence ≥ 3.5 (sensitive) | 4.06 | 0.41 | 89.9% | 81.5% | 89% | 53% |
| **Evidence ≥ 4.0 (default)** | **3.89** | **0.29** | **92.5%** | **80.0%** | **89%** | **51%** |
| Evidence ≥ 4.5 | 3.84 | 0.22 | 94.4% | 79.3% | 89% | 49% |
| Evidence ≥ 5.0 (strict) | 3.72 | 0.14 | 96.3% | 78.0% | 86% | 48% |

At equal purity, the evidence rule finds ~6 points more of the important bursts
than the count test. At high purity it finds ~9 more: the count test at 96%
purity finds 69%.

With the live 60-day records (instead of the priors), purity holds at 94% over
Jun–Jul and 96% over the quieter Aug–Sep.

Why the count test missed bursts: in 115 of its 135 misses of important bursts,
the model *had* flagged them at many stations (often 10–16). But only 3–4 were
reliable sites at p ≥ 0.9, which at busy hours is no better than chance. The
evidence rule uses the other readings too: flags at lower confidence, flags from
middling stations, and silence.

Other findings:

- At p ≥ 0.9, 44% of observed minutes already have ≥ 2 sites flagging, mostly
  from a few stations. AUSTRIA-OE3FLB flags ~55% of its observing time,
  SWISS-PHLWA ~30% and INDIA-OOTY ~28%, and none of them agrees with other
  stations more than chance. NORWAY-EGERSUND flags 33% of its files even at night.
- Night-time files are only 2.4% of all Burst flags, but they are all
  interference.
- Pairwise co-detection barely depends on distance, so a small site radius is
  enough.

**The remaining ceiling is timing.** The model scores whole 15-minute files, so
two readings "agree" if they fall anywhere in an overlap minutes wide, and the
chance background at busy hours is high. In 134 of the 135 misses above, at
least one station had flagged the burst, so the bursts are in the data. Locating
each burst inside its file, for example from the spectrogram's light curve,
would shrink the coincidence window from ~15 to ~2 minutes. That should lift
recall well beyond what any re-weighting of whole-file readings can.

## Under BnB v1.1 (2026-10-09)

The defaults above and the built-in station records were measured on BnB v1.0.
BnB v1.1 is the same network retrained on 2026 recordings, with a higher decision
threshold (0.787 instead of 0.563). The reading bands (low / mid at 0.8 / high at
0.9) are fixed probabilities, so v1.1's low band is narrow (0.787–0.8).

v1.1 starts from v1.0's station records (`station_reliability_priors.py`). On
held-out Trainer files the two models read alike overall: both read ≥ 0.9 on
49.8% of 3,255 labelled bursts. On 6,909 quiet files v1.1 reads ≥ 0.9 more often
(4.6% vs 3.2%). The largest increases are at a few stations (GLASGOW, TAIWAN-NCU,
SWISS-CalU, SRI-Lanka). The daily re-measurement handles this. A station's
chance rates switch to v1.1's own once it has a day of v1.1 detections, if they
are higher. Its score and burst readings blend in by sample size. The catch-up
re-scores the last 30 days with v1.1, so that history is available within days.

The 4.0-nat default has not been re-tuned on v1.1. Replay the study on v1.1's
detections once enough history is re-scored, and then replace the borrowed priors
with v1.1's own.

## History

`RADIO_DERIVATION_VERSION` (in `radio_burst_service.py`) records which rule derived
the stored `radio_burst` events (`app_settings.radio_burst_derivation_version`). At
startup, a database derived by an older version rebuilds every stored day once.
This is silent: the notification ledger is pre-filled, so old events under a new
rule are not announced. Bump the version when a change should reach history too.

Live rebuilds keep an announced burst announced when a late station moves its
start earlier: an event's id is its start time, so the new id inherits the old
ledger entry.
