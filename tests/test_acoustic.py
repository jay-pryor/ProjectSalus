"""Tests for acoustic coverage model (S4-4)."""

from __future__ import annotations

import pytest

from salus.engine.acoustic import _ACOUSTIC_NOISE_EXPONENT, compute_acoustic_coverage
from salus.ingest.terrain import load_dem
from salus.models.scenario import SensorPlacement
from salus.models.sensor import SensorDefinition, SensorType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _acoustic_sensor(
    max_range_m: float = 100.0,
    min_range_m: float = 0.0,
    mounting_height_m: float = 2.0,
) -> SensorDefinition:
    return SensorDefinition(
        name="TestAcoustic",
        type=SensorType.Acoustic,
        max_range_m=max_range_m,
        min_range_m=min_range_m,
        azimuth_coverage_deg=360.0,
        elevation_coverage_deg=90.0,
        requires_los=False,
        mounting_height_m=mounting_height_m,
    )


def _placement(
    site_origin_x: float,
    site_origin_y: float,
    offset_x: float = 50.0,
    offset_y: float = -50.0,
) -> SensorPlacement:
    return SensorPlacement(
        sensor_name="TestAcoustic",
        position_x=site_origin_x + offset_x,
        position_y=site_origin_y + offset_y,
        bearing_deg=0.0,
    )


# ---------------------------------------------------------------------------
# Output shape and type
# ---------------------------------------------------------------------------


class TestComputeAcousticCoverageOutput:
    def test_output_shape_matches_dem(self, flat_dem_path):
        site = load_dem(flat_dem_path)
        sensor = _acoustic_sensor()
        placement = _placement(site.origin_x, site.origin_y)
        result = compute_acoustic_coverage(site, sensor, placement, 0.0)
        assert result.shape == site.dem.shape

    def test_output_dtype_is_bool(self, flat_dem_path):
        site = load_dem(flat_dem_path)
        sensor = _acoustic_sensor()
        placement = _placement(site.origin_x, site.origin_y)
        result = compute_acoustic_coverage(site, sensor, placement, 0.0)
        assert result.dtype == bool


# ---------------------------------------------------------------------------
# Propagation behaviour
# ---------------------------------------------------------------------------


class TestComputeAcousticCoverageBehaviour:
    def test_zero_noise_full_range(self, flat_dem_path):
        """0 dB noise: effective range equals max_range_m."""
        site = load_dem(flat_dem_path)
        sensor = _acoustic_sensor(max_range_m=30.0)
        placement = _placement(site.origin_x, site.origin_y)
        result = compute_acoustic_coverage(site, sensor, placement, 0.0)
        assert result.any()

    def test_high_noise_reduces_coverage(self, flat_dem_path):
        """Higher ambient noise produces fewer covered cells."""
        site = load_dem(flat_dem_path)
        sensor = _acoustic_sensor(max_range_m=40.0)
        placement = _placement(site.origin_x, site.origin_y)
        cov_quiet = compute_acoustic_coverage(site, sensor, placement, 0.0)
        cov_noisy = compute_acoustic_coverage(site, sensor, placement, 20.0)
        assert cov_noisy.sum() < cov_quiet.sum()

    def test_6db_noise_halves_range(self, flat_dem_path):
        """6 dB ambient noise halves the effective range (acoustic inverse-distance law)."""
        site = load_dem(flat_dem_path)
        sensor = _acoustic_sensor(max_range_m=40.0)
        placement = _placement(site.origin_x, site.origin_y)
        # At 0 dB: effective range = 40m. At 6 dB: effective range ≈ 20m.
        # Coverage area ∝ r², so area should be ≈ 1/4 of the quiet case.
        cov_quiet = compute_acoustic_coverage(site, sensor, placement, 0.0)
        cov_6db = compute_acoustic_coverage(site, sensor, placement, 6.0206)  # 20*log10(2)
        ratio = cov_6db.sum() / max(cov_quiet.sum(), 1)
        assert 0.15 < ratio < 0.40  # expect ≈ 0.25 (quarter area)

    def test_negative_noise_capped_at_max_range(self, flat_dem_path):
        """Negative ambient_noise_db does not inflate range beyond max_range_m."""
        site = load_dem(flat_dem_path)
        sensor = _acoustic_sensor(max_range_m=30.0)
        placement = _placement(site.origin_x, site.origin_y)
        cov_quiet = compute_acoustic_coverage(site, sensor, placement, 0.0)
        cov_negative = compute_acoustic_coverage(site, sensor, placement, -20.0)
        # Negative noise → effective_range capped at max_range_m → same as 0 dB
        assert cov_negative.sum() == cov_quiet.sum()

    def test_very_high_noise_minimal_coverage(self, flat_dem_path):
        """Extremely high noise reduces effective range to near zero."""
        site = load_dem(flat_dem_path)
        # min_range_m=1.0 excludes the sensor's own cell (dist=0), so at very
        # high noise the near-zero effective range covers nothing.
        sensor = _acoustic_sensor(max_range_m=50.0, min_range_m=1.0)
        placement = _placement(site.origin_x, site.origin_y)
        result = compute_acoustic_coverage(site, sensor, placement, 100.0)
        # 100 dB penalty: range = 50m * 10^(-5) = 5e-4 m < 1m min_range → no cells
        assert not result.any()

    def test_cells_beyond_max_range_not_covered(self, flat_dem_path):
        """Cells beyond max_range are excluded even at 0 dB noise."""
        site = load_dem(flat_dem_path)
        # Tiny range — sensor covers almost nothing
        sensor = _acoustic_sensor(max_range_m=3.0)
        placement = _placement(site.origin_x, site.origin_y)
        result = compute_acoustic_coverage(site, sensor, placement, 0.0)
        assert result.sum() < 50

    def test_min_range_dead_zone(self, flat_dem_path):
        """min_range_m creates a dead zone that excludes near cells."""
        site = load_dem(flat_dem_path)
        sensor_no_dead = _acoustic_sensor(max_range_m=30.0, min_range_m=0.0)
        sensor_dead = _acoustic_sensor(max_range_m=30.0, min_range_m=10.0)
        placement = _placement(site.origin_x, site.origin_y)
        cov_full = compute_acoustic_coverage(site, sensor_no_dead, placement, 0.0)
        cov_dead = compute_acoustic_coverage(site, sensor_dead, placement, 0.0)
        assert cov_dead.sum() < cov_full.sum()

    def test_no_terrain_dependency(self, flat_dem_path, ridge_dem_path):
        """Coverage is identical on flat and ridge DEMs (no terrain occlusion)."""
        site_flat = load_dem(flat_dem_path)
        site_ridge = load_dem(ridge_dem_path)
        sensor = _acoustic_sensor(max_range_m=30.0)

        # Sensor near centre of flat DEM
        pl_flat = _placement(site_flat.origin_x, site_flat.origin_y)
        # Sensor at same relative position on ridge DEM (which is 200x200)
        pl_ridge = _placement(site_ridge.origin_x, site_ridge.origin_y)

        cov_flat = compute_acoustic_coverage(site_flat, sensor, pl_flat, 0.0)
        cov_ridge = compute_acoustic_coverage(site_ridge, sensor, pl_ridge, 0.0)

        # Both should produce the same coverage count (range circle, no terrain)
        assert cov_flat.sum() == cov_ridge.sum()

    def test_coverage_is_range_circle(self, flat_dem_path):
        """Coverage mask forms a circle — azimuth_coverage_deg is ignored."""
        site = load_dem(flat_dem_path)
        # Sensor with narrow azimuth_coverage_deg — must still cover full circle
        sensor = SensorDefinition(
            name="TestAcoustic",
            type=SensorType.Acoustic,
            max_range_m=30.0,
            azimuth_coverage_deg=90.0,  # narrow, but acoustic ignores this
            elevation_coverage_deg=90.0,
            requires_los=False,
            mounting_height_m=2.0,
        )
        cx = site.origin_x + 50
        cy = site.origin_y - 50
        placement = SensorPlacement(
            sensor_name="TestAcoustic",
            position_x=cx,
            position_y=cy,
            bearing_deg=0.0,
        )
        result = compute_acoustic_coverage(site, sensor, placement, 0.0)
        # Coverage should be symmetric — north and south counts roughly equal
        north_count = result[:50, :].sum()
        south_count = result[50:, :].sum()
        assert abs(north_count - south_count) <= max(north_count, south_count) * 0.15 + 2

    def test_noise_exponent_constant(self):
        """Noise exponent must be 20.0 (inverse-distance pressure law)."""
        assert _ACOUSTIC_NOISE_EXPONENT == 20.0


# ---------------------------------------------------------------------------
# Guard clauses
# ---------------------------------------------------------------------------


class TestComputeAcousticCoverageGuards:
    def test_nan_ambient_noise_raises(self, flat_dem_path):
        site = load_dem(flat_dem_path)
        sensor = _acoustic_sensor()
        placement = _placement(site.origin_x, site.origin_y)
        with pytest.raises(ValueError, match="ambient_noise_db"):
            compute_acoustic_coverage(site, sensor, placement, float("nan"))

    def test_inf_ambient_noise_raises(self, flat_dem_path):
        site = load_dem(flat_dem_path)
        sensor = _acoustic_sensor()
        placement = _placement(site.origin_x, site.origin_y)
        with pytest.raises(ValueError, match="ambient_noise_db"):
            compute_acoustic_coverage(site, sensor, placement, float("inf"))

    def test_nonfinite_placement_x_raises(self, flat_dem_path):
        """Non-finite sensor position must raise ValueError immediately."""
        site = load_dem(flat_dem_path)
        sensor = _acoustic_sensor()
        placement = SensorPlacement(
            sensor_name="TestAcoustic",
            position_x=float("nan"),
            position_y=site.origin_y - 50,
            bearing_deg=0.0,
        )
        with pytest.raises(ValueError, match="position_x"):
            compute_acoustic_coverage(site, sensor, placement, 0.0)

    def test_extreme_negative_noise_does_not_raise(self, flat_dem_path):
        """Very large negative ambient_noise_db must not raise OverflowError."""
        site = load_dem(flat_dem_path)
        sensor = _acoustic_sensor(max_range_m=30.0)
        placement = _placement(site.origin_x, site.origin_y)
        # -10000 dB: 10^(10000/20) overflows float64 → saturates to inf → capped at max_range_m
        result = compute_acoustic_coverage(site, sensor, placement, -10000.0)
        quiet_result = compute_acoustic_coverage(site, sensor, placement, 0.0)
        assert result.sum() == quiet_result.sum()
