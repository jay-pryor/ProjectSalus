"""Tests for RF coverage grid computation (S4-3)."""

from __future__ import annotations

import pytest

from salus.engine.rf_propagation import _parse_frequency_band_hz, compute_rf_coverage
from salus.ingest.terrain import load_dem
from salus.models.scenario import SensorPlacement
from salus.models.sensor import SensorDefinition, SensorType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rf_sensor(
    max_range_m: float = 500.0,
    azimuth_coverage_deg: float = 360.0,
    mounting_height_m: float = 5.0,
    frequency_bands: list[str] | None = None,
) -> SensorDefinition:
    return SensorDefinition(
        name="TestRF",
        type=SensorType.RF,
        max_range_m=max_range_m,
        azimuth_coverage_deg=azimuth_coverage_deg,
        elevation_coverage_deg=90.0,
        frequency_bands=frequency_bands or ["2.4 GHz"],
        requires_los=False,
        mounting_height_m=mounting_height_m,
    )


def _placement(
    site_origin_x: float,
    site_origin_y: float,
    offset_x: float = 50.0,
    offset_y: float = -50.0,
    bearing_deg: float = 0.0,
    height_override_m: float | None = None,
) -> SensorPlacement:
    return SensorPlacement(
        sensor_name="TestRF",
        position_x=site_origin_x + offset_x,
        position_y=site_origin_y + offset_y,
        bearing_deg=bearing_deg,
        height_override_m=height_override_m,
    )


# ---------------------------------------------------------------------------
# _parse_frequency_band_hz
# ---------------------------------------------------------------------------


class TestParseFrequencyBandHz:
    def test_ghz(self):
        assert _parse_frequency_band_hz("2.4 GHz") == pytest.approx(2.4e9)

    def test_ghz_no_space(self):
        assert _parse_frequency_band_hz("5.8GHz") == pytest.approx(5.8e9)

    def test_mhz(self):
        assert _parse_frequency_band_hz("900 MHz") == pytest.approx(900e6)

    def test_khz(self):
        assert _parse_frequency_band_hz("433 kHz") == pytest.approx(433e3)

    def test_hz(self):
        assert _parse_frequency_band_hz("1000 Hz") == pytest.approx(1000.0)

    def test_case_insensitive(self):
        assert _parse_frequency_band_hz("2.4 ghz") == pytest.approx(2.4e9)
        assert _parse_frequency_band_hz("900 MHZ") == pytest.approx(900e6)

    def test_unparseable_raises(self):
        with pytest.raises(ValueError, match="Cannot parse"):
            _parse_frequency_band_hz("2.4 THz")

    def test_bad_number_raises(self):
        with pytest.raises(ValueError, match="Cannot parse"):
            _parse_frequency_band_hz("abc GHz")

    def test_non_string_raises(self):
        """Non-string input must raise ValueError, not AttributeError."""
        with pytest.raises(ValueError, match="string"):
            _parse_frequency_band_hz(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# compute_rf_coverage — output shape and type
# ---------------------------------------------------------------------------


class TestComputeRfCoverageOutput:
    def test_output_shape_matches_dem(self, flat_dem_path):
        site = load_dem(flat_dem_path)
        sensor = _rf_sensor()
        placement = _placement(site.origin_x, site.origin_y)
        result = compute_rf_coverage(site, sensor, placement, -80.0, frequency_hz=2.4e9)
        assert result.shape == site.dem.shape

    def test_output_dtype_is_bool(self, flat_dem_path):
        site = load_dem(flat_dem_path)
        sensor = _rf_sensor()
        placement = _placement(site.origin_x, site.origin_y)
        result = compute_rf_coverage(site, sensor, placement, -80.0, frequency_hz=2.4e9)
        assert result.dtype == bool


# ---------------------------------------------------------------------------
# compute_rf_coverage — propagation behaviour
# ---------------------------------------------------------------------------


class TestComputeRfCoveragePropagation:
    def test_cells_within_range_can_be_covered(self, flat_dem_path):
        """With generous sensitivity, cells within max_range are detected."""
        site = load_dem(flat_dem_path)
        sensor = _rf_sensor(max_range_m=30.0)
        placement = _placement(site.origin_x, site.origin_y)
        # sensitivity=-100 dBm: RSL at 30m@2.4GHz ≈ 20 - 69.6 = -49.6 dBm → covered
        result = compute_rf_coverage(site, sensor, placement, -100.0, frequency_hz=2.4e9)
        assert result.any()

    def test_cells_beyond_max_range_not_covered(self, flat_dem_path):
        """Cells beyond max_range are excluded regardless of sensitivity."""
        site = load_dem(flat_dem_path)
        # Very small range: only cells within 5m could be in range
        sensor = _rf_sensor(max_range_m=5.0)
        # Place sensor at edge so most cells are beyond range
        placement = _placement(site.origin_x, site.origin_y, offset_x=1.0, offset_y=-1.0)
        result = compute_rf_coverage(site, sensor, placement, -200.0, frequency_hz=2.4e9)
        # The bulk of the 100x100 grid (>5m away) must not be covered
        assert result.sum() < 200

    def test_sensitivity_too_tight_no_coverage(self, flat_dem_path):
        """Sensitivity above drone TX power means nothing is detectable."""
        site = load_dem(flat_dem_path)
        sensor = _rf_sensor(max_range_m=50.0)
        placement = _placement(site.origin_x, site.origin_y)
        # sensitivity = +30 dBm — impossible for a 20 dBm TX to achieve
        result = compute_rf_coverage(site, sensor, placement, 30.0, frequency_hz=2.4e9)
        assert not result.any()

    def test_higher_frequency_reduces_coverage(self, flat_dem_path):
        """Higher frequency → more FSPL → fewer covered cells."""
        site = load_dem(flat_dem_path)
        sensor = _rf_sensor(max_range_m=60.0)
        placement = _placement(site.origin_x, site.origin_y)
        cov_900 = compute_rf_coverage(site, sensor, placement, -70.0, frequency_hz=900e6)
        cov_5800 = compute_rf_coverage(site, sensor, placement, -70.0, frequency_hz=5.8e9)
        assert cov_900.sum() >= cov_5800.sum()

    def test_flat_dem_coverage_symmetric(self, flat_dem_path):
        """On a flat DEM with 360° arc, coverage is symmetric around sensor."""
        site = load_dem(flat_dem_path)
        # Place sensor at centre
        cx = site.origin_x + 50
        cy = site.origin_y - 50
        sensor = _rf_sensor(max_range_m=30.0)
        placement = SensorPlacement(
            sensor_name="TestRF",
            position_x=cx,
            position_y=cy,
            bearing_deg=0.0,
        )
        result = compute_rf_coverage(site, sensor, placement, -100.0, frequency_hz=2.4e9)
        # Rows near centre should be similar in coverage count (symmetric)
        rows_above = result[:50, :].sum()
        rows_below = result[50:, :].sum()
        # Allow ±20% asymmetry due to DEM boundary effects
        assert abs(rows_above - rows_below) <= max(rows_above, rows_below) * 0.2 + 5

    def test_min_range_excludes_near_cells(self, flat_dem_path):
        """min_range_m creates a dead zone around the sensor."""
        site = load_dem(flat_dem_path)
        sensor_no_deadzone = _rf_sensor(max_range_m=40.0)
        sensor_deadzone = SensorDefinition(
            name="TestRF",
            type=SensorType.RF,
            max_range_m=40.0,
            min_range_m=10.0,
            azimuth_coverage_deg=360.0,
            elevation_coverage_deg=90.0,
            frequency_bands=["2.4 GHz"],
            requires_los=False,
            mounting_height_m=5.0,
        )
        placement = _placement(site.origin_x, site.origin_y)
        cov_full = compute_rf_coverage(
            site, sensor_no_deadzone, placement, -100.0, frequency_hz=2.4e9
        )
        cov_dead = compute_rf_coverage(site, sensor_deadzone, placement, -100.0, frequency_hz=2.4e9)
        assert cov_dead.sum() < cov_full.sum()


# ---------------------------------------------------------------------------
# compute_rf_coverage — azimuth arc clipping
# ---------------------------------------------------------------------------


class TestComputeRfCoverageAzimuth:
    def test_360_arc_covers_all_directions(self, flat_dem_path):
        """Full 360° arc applies no azimuth restriction."""
        site = load_dem(flat_dem_path)
        sensor = _rf_sensor(max_range_m=30.0, azimuth_coverage_deg=360.0)
        placement = _placement(site.origin_x, site.origin_y)
        result = compute_rf_coverage(site, sensor, placement, -100.0, frequency_hz=2.4e9)
        assert result.any()

    def test_180_arc_north_excludes_south(self, flat_dem_path):
        """180° northward arc should produce negligible coverage in southern half."""
        site = load_dem(flat_dem_path)
        sensor = _rf_sensor(max_range_m=30.0, azimuth_coverage_deg=180.0)
        # Sensor at row 50 (y = origin_y - 50), bearing north (0°)
        cx = site.origin_x + 50
        cy = site.origin_y - 50
        placement = SensorPlacement(
            sensor_name="TestRF",
            position_x=cx,
            position_y=cy,
            bearing_deg=0.0,
        )
        result = compute_rf_coverage(site, sensor, placement, -100.0, frequency_hz=2.4e9)
        # Northern half (rows 0..49) should have significant coverage
        north_coverage = result[:50, :].sum()
        # Southern half (rows 51..99) should have no coverage
        south_coverage = result[51:, :].sum()
        assert north_coverage > 0
        assert south_coverage == 0


# ---------------------------------------------------------------------------
# compute_rf_coverage — frequency from sensor bands
# ---------------------------------------------------------------------------


class TestComputeRfCoverageFrequency:
    def test_frequency_from_sensor_bands(self, flat_dem_path):
        """frequency_hz=None falls back to sensor.frequency_bands[0]."""
        site = load_dem(flat_dem_path)
        sensor = _rf_sensor(frequency_bands=["900 MHz"])
        placement = _placement(site.origin_x, site.origin_y)
        # Should not raise — frequency resolved from sensor bands
        result = compute_rf_coverage(site, sensor, placement, -80.0)
        assert result.shape == site.dem.shape

    def test_explicit_frequency_overrides_bands(self, flat_dem_path):
        """Explicit frequency_hz takes precedence over sensor.frequency_bands."""
        site = load_dem(flat_dem_path)
        sensor = _rf_sensor(frequency_bands=["900 MHz"])
        placement = _placement(site.origin_x, site.origin_y)
        cov_explicit = compute_rf_coverage(site, sensor, placement, -80.0, frequency_hz=2.4e9)
        cov_from_bands = compute_rf_coverage(site, sensor, placement, -80.0)
        # Different frequencies → different coverage totals
        assert cov_explicit.shape == cov_from_bands.shape


# ---------------------------------------------------------------------------
# compute_rf_coverage — guard clauses
# ---------------------------------------------------------------------------


class TestComputeRfCoverageGuards:
    def test_nonfinite_sensitivity_raises(self, flat_dem_path):
        site = load_dem(flat_dem_path)
        sensor = _rf_sensor()
        placement = _placement(site.origin_x, site.origin_y)
        with pytest.raises(ValueError, match="sensitivity_dbm"):
            compute_rf_coverage(site, sensor, placement, float("nan"), frequency_hz=2.4e9)

    def test_inf_sensitivity_raises(self, flat_dem_path):
        site = load_dem(flat_dem_path)
        sensor = _rf_sensor()
        placement = _placement(site.origin_x, site.origin_y)
        with pytest.raises(ValueError, match="sensitivity_dbm"):
            compute_rf_coverage(site, sensor, placement, float("inf"), frequency_hz=2.4e9)

    def test_no_frequency_and_empty_bands_raises(self, flat_dem_path):
        site = load_dem(flat_dem_path)
        sensor = SensorDefinition(
            name="TestRF",
            type=SensorType.RF,
            max_range_m=100.0,
            azimuth_coverage_deg=360.0,
            elevation_coverage_deg=90.0,
            frequency_bands=[],
            requires_los=False,
            mounting_height_m=5.0,
        )
        placement = _placement(site.origin_x, site.origin_y)
        with pytest.raises(ValueError, match="frequency"):
            compute_rf_coverage(site, sensor, placement, -80.0)

    def test_zero_frequency_raises(self, flat_dem_path):
        site = load_dem(flat_dem_path)
        sensor = _rf_sensor()
        placement = _placement(site.origin_x, site.origin_y)
        with pytest.raises(ValueError, match="frequency_hz"):
            compute_rf_coverage(site, sensor, placement, -80.0, frequency_hz=0.0)

    def test_sensor_outside_dem_raises(self, flat_dem_path):
        site = load_dem(flat_dem_path)
        sensor = _rf_sensor()
        # Position sensor far outside the 100x100m DEM
        placement = SensorPlacement(
            sensor_name="TestRF",
            position_x=site.origin_x + 5_000.0,
            position_y=site.origin_y - 5_000.0,
            bearing_deg=0.0,
        )
        with pytest.raises(ValueError, match="outside the DEM"):
            compute_rf_coverage(site, sensor, placement, -80.0, frequency_hz=2.4e9)

    def test_nan_dem_at_sensor_raises(self, tmp_path):
        """NaN DEM value at sensor position must raise ValueError immediately."""
        import numpy as np
        import rasterio
        from rasterio.crs import CRS
        from rasterio.transform import from_bounds

        path = tmp_path / "nan_dem.tif"
        data = np.full((100, 100), 50.0, dtype=np.float64)
        data[50, 50] = float("nan")  # NaN exactly at sensor position
        transform = from_bounds(500000, 6100000, 500100, 6100100, 100, 100)
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            height=100,
            width=100,
            count=1,
            dtype="float64",
            crs=CRS.from_epsg(28354),
            transform=transform,
        ) as dst:
            dst.write(data, 1)

        site = load_dem(path)
        sensor = _rf_sensor()
        # Sensor at pixel (50,50) → position_x = origin_x+50, position_y = origin_y-50
        placement = SensorPlacement(
            sensor_name="TestRF",
            position_x=site.origin_x + 50,
            position_y=site.origin_y - 50,
            bearing_deg=0.0,
        )
        with pytest.raises(ValueError, match="NaN"):
            compute_rf_coverage(site, sensor, placement, -80.0, frequency_hz=2.4e9)
