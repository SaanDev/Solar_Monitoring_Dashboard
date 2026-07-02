"""Convert GOES long-channel (0.1-0.8 nm) X-ray flux to NOAA flare class.

NOAA classifies solar flares from the 1-8 Angstrom (0.1-0.8 nm) long-channel
peak flux in W/m^2:
    A: 1e-8 - 1e-7      B: 1e-7 - 1e-6      C: 1e-6 - 1e-5
    M: 1e-5 - 1e-4      X: >= 1e-4
The subclass is the flux divided by the band floor (e.g. 5.3e-6 -> C5.3).
"""


def flare_class(long_flux: float | None) -> str | None:
    if long_flux is None or long_flux <= 0:
        return None
    if long_flux >= 1e-4:
        return f"X{long_flux / 1e-4:.1f}"
    if long_flux >= 1e-5:
        return f"M{long_flux / 1e-5:.1f}"
    if long_flux >= 1e-6:
        return f"C{long_flux / 1e-6:.1f}"
    if long_flux >= 1e-7:
        return f"B{long_flux / 1e-7:.1f}"
    return f"A{long_flux / 1e-8:.1f}"
