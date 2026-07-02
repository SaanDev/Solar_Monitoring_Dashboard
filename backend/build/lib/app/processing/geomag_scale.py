"""Geomagnetic storm classification for Kp and Dst.

Kp -> NOAA G-scale (geomagnetic storm):
    G1: Kp=5   G2: Kp=6   G3: Kp=7   G4: Kp=8   G5: Kp=9
Below Kp 5 there is no storm.

Dst -> storm intensity (common scientific convention, nT):
    weak:   -30 .. -50      moderate: -50 .. -100
    intense: -100 .. -250   super:    <= -250
"""


def kp_storm_scale(kp: float | None) -> str | None:
    if kp is None or kp < 5:
        return None
    if kp >= 9:
        return "G5"
    if kp >= 8:
        return "G4"
    if kp >= 7:
        return "G3"
    if kp >= 6:
        return "G2"
    return "G1"


def dst_storm_level(dst: float | None) -> str | None:
    if dst is None or dst > -30:
        return None
    if dst <= -250:
        return "Super storm"
    if dst <= -100:
        return "Intense storm"
    if dst <= -50:
        return "Moderate storm"
    return "Weak storm"
