"""NOAA radiation-storm (S-scale) classification from >=10 MeV integral proton flux.

NOAA S-scale thresholds in particle flux units (pfu, particles / cm^2 s sr):
    S1: >= 1e1     S2: >= 1e2     S3: >= 1e3     S4: >= 1e4     S5: >= 1e5
Below 10 pfu there is no radiation storm.
"""

# Proton event threshold (NOAA declares an SEP/S1 event at >=10 MeV >= 10 pfu).
PROTON_EVENT_THRESHOLD_PFU = 10.0


def storm_scale(flux_gt10: float | None) -> str | None:
    if flux_gt10 is None or flux_gt10 < 10.0:
        return None
    if flux_gt10 >= 1e5:
        return "S5"
    if flux_gt10 >= 1e4:
        return "S4"
    if flux_gt10 >= 1e3:
        return "S3"
    if flux_gt10 >= 1e2:
        return "S2"
    return "S1"
