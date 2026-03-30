"""RF propagation models — Free-Space Path Loss (FSPL)."""

from __future__ import annotations

import math

# Speed of light in vacuum (m/s) — ITU-R P.525
_C_M_S: float = 299_792_458.0

# Precomputed constant term: 20 * log10(4π / c)
_FSPL_CONSTANT_DB: float = 20.0 * math.log10(4.0 * math.pi / _C_M_S)


def compute_fspl(distance_m: float, frequency_hz: float) -> float:
    """Compute Free-Space Path Loss (FSPL) in dB.

    Uses the standard FSPL formula (ITU-R P.525):

        FSPL (dB) = 20·log10(d) + 20·log10(f) + 20·log10(4π/c)

    where d is distance in metres, f is frequency in Hz, and c is the speed
    of light in vacuum (299 792 458 m/s).

    Args:
        distance_m: Distance between transmitter and receiver in metres. Must be > 0.
        frequency_hz: Signal frequency in Hz. Must be > 0.

    Returns:
        Path loss in dB. Subtract from transmitted power (dBm) to obtain received
        signal level. May be negative at sub-metre distances — the formula is a
        far-field approximation only.

    Raises:
        ValueError: If distance_m or frequency_hz is non-positive, NaN, or infinite.
    """
    if not math.isfinite(distance_m) or distance_m <= 0.0:
        raise ValueError(f"distance_m must be a finite positive number, got {distance_m}")
    if not math.isfinite(frequency_hz) or frequency_hz <= 0.0:
        raise ValueError(f"frequency_hz must be a finite positive number, got {frequency_hz}")

    return 20.0 * math.log10(distance_m) + 20.0 * math.log10(frequency_hz) + _FSPL_CONSTANT_DB
