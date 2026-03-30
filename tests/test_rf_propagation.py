"""Tests for RF propagation — Free-Space Path Loss (FSPL)."""

from __future__ import annotations

import math

import pytest

from salus.engine.rf_propagation import _C_M_S, _FSPL_CONSTANT_DB, compute_fspl


class TestComputeFspl:
    # ------------------------------------------------------------------
    # Reference values
    # ------------------------------------------------------------------

    def test_1km_1ghz_reference(self):
        """ITU-R P.525 canonical example: 1 km @ 1 GHz → 92.44 dB."""
        result = compute_fspl(1_000.0, 1e9)
        assert result == pytest.approx(92.44, abs=0.01)

    def test_1km_2400mhz_reference(self):
        """Well-known 2.4 GHz WiFi reference: 1 km @ 2.4 GHz → ~100.05 dB."""
        result = compute_fspl(1_000.0, 2.4e9)
        assert result == pytest.approx(100.05, abs=0.01)

    def test_1km_900mhz_reference(self):
        """900 MHz cellular band: 1 km @ 900 MHz → ~91.53 dB."""
        # 20*log10(1000) + 20*log10(900e6) + FSPL_CONSTANT
        expected = 20 * math.log10(1_000.0) + 20 * math.log10(900e6) + _FSPL_CONSTANT_DB
        result = compute_fspl(1_000.0, 900e6)
        assert result == pytest.approx(expected, abs=1e-9)

    def test_100m_2400mhz(self):
        """Short range: 100 m @ 2.4 GHz → ~80.05 dB (20 dB less than 1 km)."""
        loss_1km = compute_fspl(1_000.0, 2.4e9)
        loss_100m = compute_fspl(100.0, 2.4e9)
        assert loss_1km - loss_100m == pytest.approx(20.0, abs=1e-9)

    # ------------------------------------------------------------------
    # Distance scaling laws
    # ------------------------------------------------------------------

    def test_doubling_distance_adds_6db(self):
        """Doubling distance increases FSPL by exactly 20·log10(2) ≈ 6.02 dB."""
        loss_d = compute_fspl(500.0, 1e9)
        loss_2d = compute_fspl(1_000.0, 1e9)
        assert loss_2d - loss_d == pytest.approx(20.0 * math.log10(2.0), abs=1e-9)

    def test_decade_distance_adds_20db(self):
        """10× distance increase adds exactly 20 dB."""
        loss_d = compute_fspl(100.0, 1e9)
        loss_10d = compute_fspl(1_000.0, 1e9)
        assert loss_10d - loss_d == pytest.approx(20.0, abs=1e-9)

    def test_large_distance(self):
        """10 km @ 900 MHz — loss is finite and greater than 1 km value."""
        loss_1km = compute_fspl(1_000.0, 900e6)
        loss_10km = compute_fspl(10_000.0, 900e6)
        assert loss_10km > loss_1km
        assert loss_10km - loss_1km == pytest.approx(20.0, abs=1e-9)

    # ------------------------------------------------------------------
    # Frequency scaling laws
    # ------------------------------------------------------------------

    def test_decade_frequency_adds_20db(self):
        """10× frequency increase adds exactly 20 dB."""
        loss_f = compute_fspl(1_000.0, 1e8)
        loss_10f = compute_fspl(1_000.0, 1e9)
        assert loss_10f - loss_f == pytest.approx(20.0, abs=1e-9)

    def test_doubling_frequency_adds_6db(self):
        """Doubling frequency increases FSPL by 20·log10(2) ≈ 6.02 dB."""
        loss_f = compute_fspl(1_000.0, 1e9)
        loss_2f = compute_fspl(1_000.0, 2e9)
        assert loss_2f - loss_f == pytest.approx(20.0 * math.log10(2.0), abs=1e-9)

    # ------------------------------------------------------------------
    # Return type and value properties
    # ------------------------------------------------------------------

    def test_return_type_is_float(self):
        assert isinstance(compute_fspl(100.0, 1e9), float)

    def test_result_is_positive_for_practical_values(self):
        """FSPL is positive for practical UAS detection frequencies and ranges."""
        # Minimum practical case: 1 m @ 900 MHz
        assert compute_fspl(1.0, 900e6) > 0.0
        assert compute_fspl(1_000.0, 1e9) > 0.0
        assert compute_fspl(1.0, 2.4e9) > 0.0

    def test_result_is_finite(self):
        assert math.isfinite(compute_fspl(1_000.0, 2.4e9))

    # ------------------------------------------------------------------
    # Physical constant
    # ------------------------------------------------------------------

    def test_speed_of_light_constant(self):
        """Speed of light constant must match ITU-R value exactly."""
        assert _C_M_S == 299_792_458.0

    def test_fspl_constant_value(self):
        """Precomputed FSPL constant must equal 20·log10(4π/c)."""
        expected = 20.0 * math.log10(4.0 * math.pi / 299_792_458.0)
        assert _FSPL_CONSTANT_DB == pytest.approx(expected, abs=1e-12)

    # ------------------------------------------------------------------
    # Guard clauses
    # ------------------------------------------------------------------

    def test_zero_distance_raises(self):
        with pytest.raises(ValueError, match="distance_m"):
            compute_fspl(0.0, 1e9)

    def test_negative_distance_raises(self):
        with pytest.raises(ValueError, match="distance_m"):
            compute_fspl(-100.0, 1e9)

    def test_zero_frequency_raises(self):
        with pytest.raises(ValueError, match="frequency_hz"):
            compute_fspl(1_000.0, 0.0)

    def test_negative_frequency_raises(self):
        with pytest.raises(ValueError, match="frequency_hz"):
            compute_fspl(1_000.0, -1e9)

    def test_nan_distance_raises(self):
        with pytest.raises(ValueError, match="distance_m"):
            compute_fspl(float("nan"), 1e9)

    def test_inf_distance_raises(self):
        with pytest.raises(ValueError, match="distance_m"):
            compute_fspl(float("inf"), 1e9)

    def test_nan_frequency_raises(self):
        with pytest.raises(ValueError, match="frequency_hz"):
            compute_fspl(1_000.0, float("nan"))

    def test_inf_frequency_raises(self):
        with pytest.raises(ValueError, match="frequency_hz"):
            compute_fspl(1_000.0, float("inf"))
