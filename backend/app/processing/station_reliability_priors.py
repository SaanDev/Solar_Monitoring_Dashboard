"""Built-in station evidence for the burst confirmation, per model.

Measured offline (2026-10-08) from 140 days of BnB v1.0 detections — 696k
files from 72 stations, 2026-05-21..10-07 — with the same procedure the live
service runs (``burst_confirmation.measure_reliability``).

Each entry is ``(score, null, anchor)``:

* ``score`` — how much the station's bursts agree with other sites beyond
  chance, shrunk toward 0 by ``judged / (judged + 20)``. Stations at
  ``score >= radio_burst_min_reliability`` pick the *anchor* minutes below.
* ``null`` — its sun-up observing minutes in each reading category: (silent,
  low, mid, high) = (no burst, model minimum..0.8, 0.8..0.9, >= 0.9). What its
  readings look like when nothing in particular is happening — its chance rates
  (``null[3] / sum(null)`` is its high-confidence duty cycle).
* ``anchor`` — minutes in each category during *anchor* bursts: ones other
  reliable sites confirm on their own with a chance probability <= 0.001. What
  its readings look like when a real burst is on.

The evidence a reading carries is ``log(P(category | burst) / P(category | null))``.
These are the starting point only: the service re-measures every station daily
from the deployment's own trailing window and blends that in by sample size
(``station_reliability_service``), so a fresh install — the desktop app on first
launch — confirms bursts from day one.
"""

# Category distributions pooled over every station — observing minutes and anchor
# minutes: the fallback shapes for a station with little record of its own.
POOLED_NULL = (0.8552, 0.0511, 0.0269, 0.0668)
POOLED_ANCHOR = (0.5700, 0.0602, 0.0460, 0.3238)

PRIORS: dict[str, dict[str, tuple[float, tuple[int, int, int, int], tuple[int, int, int, int]]]] = {
    "bnb-1.0.0": {
        "ALASKA-ANCHORAGE": (0.16, (126629, 3435, 1680, 2070), (2879, 130, 70, 519)),
        "ALASKA-COHOE": (0.52, (112981, 4178, 2531, 16013), (971, 160, 185, 2278)),
        "ALASKA-HAARP": (0.33, (106117, 4950, 3870, 21180), (857, 89, 146, 2684)),
        "ALGERIA-CRAAG": (-0.06, (59272, 3947, 1650, 1440), (1900, 268, 165, 328)),
        "ALMATY": (0.06, (69536, 6690, 3359, 4515), (2054, 403, 225, 859)),
        "Australia-ASSA": (0.48, (71940, 4710, 2595, 10020), (120, 60, 27, 1351)),
        "AUSTRIA-Krumbach": (-0.16, (50608, 90, 45, 75), (3077, 26, 15, 0)),
        "AUSTRIA-MICHELBACH": (0.10, (100590, 2040, 690, 750), (4187, 210, 89, 60)),
        "AUSTRIA-OE3FLB": (-0.01, (22806, 14354, 13399, 62967), (608, 420, 673, 3962)),
        "AUSTRIA-UNIGRAZ": (0.45, (110192, 3812, 1609, 3181), (2626, 538, 545, 2009)),
        "BIR": (0.50, (109800, 3510, 1965, 11115), (520, 135, 90, 4264)),
        "BRAZIL": (0.37, (28125, 120, 120, 90), (2173, 90, 60, 26)),
        "Croatia-Visnjan": (0.17, (13066, 135, 45, 75), (312, 0, 15, 45)),
        "EGYPT-Alexandria": (0.09, (48376, 9845, 4859, 8006), (1366, 469, 450, 2098)),
        "EGYPT-SpaceAgency": (0.20, (84430, 465, 300, 465), (4238, 90, 30, 210)),
        "Finland-Kempele": (0.04, (120801, 4800, 2310, 4290), (4332, 469, 182, 1028)),
        "FINLAND-RUISSALO": (0.43, (98043, 3669, 1898, 5444), (1562, 323, 419, 3158)),
        "FINLAND-Siuntio": (0.15, (115230, 3585, 2130, 2190), (5366, 255, 108, 288)),
        "GERMANY-DLR": (0.31, (94875, 12705, 4575, 13410), (351, 196, 90, 4421)),
        "GERMANY-ESSEN": (0.19, (119760, 2325, 990, 2145), (4376, 345, 285, 960)),
        "GLASGOW": (0.39, (87750, 5895, 3015, 9315), (1277, 479, 405, 3162)),
        "GREENLAND": (0.04, (6715, 150, 45, 137), (15, 0, 0, 30)),
        "HUMAIN": (0.72, (92879, 2265, 1635, 3555), (1532, 393, 741, 2383)),
        "HURBANOVO": (0.14, (79827, 1110, 555, 510), (4396, 94, 120, 210)),
        "INDIA-GAURI": (0.43, (79578, 7334, 3798, 14405), (404, 177, 243, 2806)),
        "INDIA-OOTY": (0.06, (43225, 18374, 12718, 28349), (757, 334, 272, 2758)),
        "INDIA-UDAIPUR": (0.33, (87923, 7133, 3492, 9481), (820, 316, 211, 2652)),
        "INDONESIA": (0.36, (82110, 1615, 646, 2335), (1319, 71, 35, 525)),
        "ITALY-Strassolt": (0.12, (76393, 1560, 540, 915), (4162, 113, 86, 125)),
        "Malaysia-Banting": (0.03, (38997, 120, 15, 15), (967, 15, 0, 15)),
        "MEXART": (0.13, (88078, 7485, 2745, 3315), (1221, 301, 165, 1259)),
        "MEXICO-ENSENADA-UNAM": (0.28, (10935, 2490, 1140, 2220), (120, 120, 75, 530)),
        "MEXICO-FCFM-UNACH": (0.22, (69577, 6762, 3888, 11171), (243, 199, 120, 1653)),
        "MEXICO-LANCE": (0.19, (73105, 10658, 6183, 14558), (499, 146, 225, 2091)),
        "MEXICO-UANL-INFIERNILLO": (0.11, (18502, 3059, 1916, 4875), (150, 65, 54, 316)),
        "MONGOLIA-UB": (0.09, (67136, 1995, 669, 1080), (1901, 135, 67, 105)),
        "MRO": (0.07, (92124, 24465, 9240, 9765), (2473, 1119, 621, 2054)),
        "MRT1": (0.22, (83781, 344, 120, 120), (3554, 135, 60, 105)),
        "NORWAY-EGERSUND": (-0.04, (83220, 12300, 6915, 10845), (3344, 536, 361, 1046)),
        "NORWAY-NY-AALESUND": (-0.12, (173713, 405, 510, 675), (6798, 0, 15, 30)),
        "NORWAY-RANDABERG": (0.05, (132735, 75, 60, 30), (6184, 0, 0, 0)),
        "NZ-WAIRAKEI-DLR": (0.14, (62399, 8191, 5490, 11655), (280, 30, 65, 1075)),
        "PANAMA": (-0.04, (13525, 496, 375, 599), (323, 10, 0, 15)),
        "PANAMA-DINACE-UTP": (0.02, (12002, 300, 135, 225), (44, 0, 0, 0)),
        "PARAGUAY": (0.35, (72958, 135, 0, 30), (3469, 0, 0, 15)),
        "POLAND-BALDY": (0.52, (105937, 5115, 2430, 11385), (709, 148, 150, 4319)),
        "POLAND-Grotniki": (0.09, (59670, 3945, 1230, 1020), (2699, 240, 90, 240)),
        "PRT-FLR-HOT": (0.00, (765, 0, 0, 0), (0, 0, 0, 0)),
        "PRT-SMA-MAIA": (-0.52, (26060, 45, 45, 105), (837, 15, 0, 3)),
        "ROMANIA": (0.00, (83248, 11325, 6523, 13965), (3795, 754, 253, 866)),
        "RWANDA": (0.19, (7743, 150, 30, 75), (136, 30, 0, 45)),
        "S-AFRICA-POTCHEFSTROOM": (-0.06, (59093, 195, 75, 49), (1980, 57, 15, 15)),
        "S-AFRICA-POTCHEFSTROOM-MWA": (0.16, (14234, 165, 45, 0), (230, 60, 0, 0)),
        "S-AFRICA-POTCHEFSTROOM-MWA-NS": (0.38, (3822, 45, 45, 90), (190, 15, 15, 45)),
        "SOUTHAFRICA-SANSA": (0.01, (87130, 1485, 1005, 1110), (4387, 60, 15, 45)),
        "SPAIN-PERALEJOS": (0.21, (112067, 1020, 315, 525), (5087, 163, 60, 284)),
        "SPAIN-SIGUENZA": (0.10, (90921, 4200, 1995, 2685), (3247, 468, 436, 965)),
        "SRI-Lanka": (0.06, (51303, 6091, 3076, 5037), (1499, 359, 151, 564)),
        "SSRT": (0.39, (75658, 3434, 2011, 2927), (834, 365, 277, 1139)),
        "SWISS-FM": (0.07, (22327, 60, 15, 15), (642, 0, 0, 0)),
        "SWISS-HB9SCT": (0.03, (108370, 686, 270, 150), (5598, 11, 0, 15)),
        "SWISS-HEITERSWIL": (0.33, (79853, 6225, 2415, 8565), (575, 272, 137, 3931)),
        "SWISS-IRSOL": (0.12, (101130, 5895, 2595, 3795), (3037, 485, 448, 1739)),
        "SWISS-Landschlacht": (0.35, (84891, 6549, 3360, 7879), (505, 164, 194, 3457)),
        "SWISS-MUHEN": (0.20, (100587, 9645, 3495, 4035), (2933, 630, 405, 1905)),
        "SWISS-PHLWA": (-0.01, (8436, 5715, 4264, 7920), (465, 206, 244, 1081)),
        "TAIWAN-NCU": (0.14, (83674, 7560, 3330, 6510), (1110, 282, 237, 1292)),
        "TRIEST": (0.08, (79875, 6645, 2880, 5940), (2362, 360, 299, 1889)),
        "UK-GLASGOW": (0.01, (18300, 390, 180, 120), (516, 15, 15, 0)),
        "UNAM": (0.07, (35040, 360, 120, 180), (737, 12, 0, 0)),
        "URUGUAY": (-0.16, (69118, 90, 15, 30), (3216, 0, 0, 0)),
        "UZBEKISTAN": (0.22, (92778, 1065, 480, 1365), (3159, 225, 103, 525)),
    },
}

# BnB v1.1 (2026-10-09) has no offline measurement of its own yet, so it starts
# from v1.0's tables: the same network and the same reading bands, and on
# held-out Trainer files the two read alike overall — >= 0.9 on 49.8% of 3,255
# labelled bursts for both, and on 4.6% of 6,909 quiet files (v1.0: 3.2%). Per
# station they differ more (GLASGOW, TAIWAN-NCU and SWISS-CalU read high far more
# often on quiet files under v1.1), which is what the live measurement corrects:
# a station's chance rates switch to v1.1's own after a day of its detections
# whenever they are higher, and its score and burst readings blend in as they
# accumulate. Where v1.1 is quieter than v1.0 the v1.0 rate stays as the floor,
# so its flags are, if anything, under-weighted. Replace this with a v1.1
# measurement once the backfill has re-scored enough history.
PRIORS["bnb-1.1.0"] = PRIORS["bnb-1.0.0"]
