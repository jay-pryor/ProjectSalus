"""Tests for sensor coverage dispatcher (S4-5)."""

from __future__ import annotations

import warnings

import pytest

from salus.engine.dispatcher import (
    _DEFAULT_AMBIENT_NOISE_DB,
    _DEFAULT_SENSITIVITY_DBM,
    compute_sensor_coverage,
)
from salus.ingest.terrain import load_dem
from salus.models.scenario import SensorPlacement
from salus.models.sensor import SensorDefinition, SensorType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sensor(
    sensor_type: SensorType,
    max_range_m: float = 30.0,
    azimuth_coverage_deg: float = 360.0,
    mounting_height_m: float = 5.0,
    frequency_bands: list[str] | None = None,
) -> SensorDefinition:
    return SensorDefinition(
        name=f"Test{sensor_type.value}",
        type=sensor_type,
        max_range_m=max_range_m,
        azimuth_coverage_deg=azimuth_coverage_deg,
        elevation_coverage_deg=90.0,
        requires_los=sensor_type in (SensorType.Radar, SensorType.EO_IR),
        mounting_height_m=mounting_height_m,
        frequency_bands=frequency_bands or (["2.4 GHz"] if sensor_type == SensorType.RF else []),
    )


def _placement(
    site_origin_x: float,
    site_origin_y: float,
    offset_x: float = 50.0,
    offset_y: float = -50.0,
) -> SensorPlacement:
    return SensorPlacement(
        sensor_name="TestSensor",
        position_x=site_origin_x + offset_x,
        position_y=site_origin_y + offset_y,
        bearing_deg=0.0,
    )


# ---------------------------------------------------------------------------
# Output shape and dtype
# ---------------------------------------------------------------------------


class TestDispatcherOutput:
    def test_radar_output_shape(self, flat_dem_path):
        site = load_dem(flat_dem_path)
        result = compute_sensor_coverage(
            site, _sensor(SensorType.Radar), _placement(site.origin_x, site.origin_y)
        )
        assert result.shape == site.dem.shape

    def test_eo_ir_output_shape(self, flat_dem_path):
        site = load_dem(flat_dem_path)
        result = compute_sensor_coverage(
            site, _sensor(SensorType.EO_IR), _placement(site.origin_x, site.origin_y)
        )
        assert result.shape == site.dem.shape

    def test_rf_output_shape(self, flat_dem_path):
        site = load_dem(flat_dem_path)
        result = compute_sensor_coverage(
            site, _sensor(SensorType.RF), _placement(site.origin_x, site.origin_y)
        )
        assert result.shape == site.dem.shape

    def test_acoustic_output_shape(self, flat_dem_path):
        site = load_dem(flat_dem_path)
        result = compute_sensor_coverage(
            site, _sensor(SensorType.Acoustic), _placement(site.origin_x, site.origin_y)
        )
        assert result.shape == site.dem.shape

    def test_all_outputs_bool(self, flat_dem_path):
        site = load_dem(flat_dem_path)
        placement = _placement(site.origin_x, site.origin_y)
        for sensor_type in SensorType:
            sensor = _sensor(sensor_type)
            result = compute_sensor_coverage(site, sensor, placement)
            assert result.dtype == bool, f"Expected bool for {sensor_type}"


# ---------------------------------------------------------------------------
# Routing correctness
# ---------------------------------------------------------------------------


class TestDispatcherRouting:
    def test_radar_routes_to_viewshed(self, flat_dem_path):
        """Radar coverage on flat DEM is non-empty (viewshed path exercised)."""
        site = load_dem(flat_dem_path)
        sensor = _sensor(SensorType.Radar, max_range_m=40.0, mounting_height_m=5.0)
        result = compute_sensor_coverage(site, sensor, _placement(site.origin_x, site.origin_y))
        assert result.any()

    def test_eo_ir_routes_to_viewshed(self, flat_dem_path):
        """EO/IR and Radar produce identical results on flat terrain."""
        site = load_dem(flat_dem_path)
        placement = _placement(site.origin_x, site.origin_y)
        radar = _sensor(SensorType.Radar, max_range_m=30.0, mounting_height_m=5.0)
        eoir = _sensor(SensorType.EO_IR, max_range_m=30.0, mounting_height_m=5.0)
        result_radar = compute_sensor_coverage(site, radar, placement)
        result_eoir = compute_sensor_coverage(site, eoir, placement)
        # Same model, same parameters → identical results
        assert (result_radar == result_eoir).all()

    def test_rf_routes_to_rf_coverage(self, flat_dem_path):
        """RF sensor with low sensitivity produces non-empty coverage."""
        site = load_dem(flat_dem_path)
        sensor = _sensor(SensorType.RF, max_range_m=40.0)
        result = compute_sensor_coverage(
            site,
            sensor,
            _placement(site.origin_x, site.origin_y),
            sensitivity_dbm=-100.0,
        )
        assert result.any()

    def test_acoustic_routes_to_acoustic(self, flat_dem_path):
        """Acoustic sensor at 0 dB noise produces non-empty coverage."""
        site = load_dem(flat_dem_path)
        sensor = _sensor(SensorType.Acoustic, max_range_m=30.0)
        result = compute_sensor_coverage(
            site,
            sensor,
            _placement(site.origin_x, site.origin_y),
            ambient_noise_db=0.0,
        )
        assert result.any()

    def test_rf_sensitivity_kwarg_respected(self, flat_dem_path):
        """sensitivity_dbm kwarg reaches the RF model."""
        site = load_dem(flat_dem_path)
        sensor = _sensor(SensorType.RF, max_range_m=50.0)
        placement = _placement(site.origin_x, site.origin_y)
        # Very tight sensitivity → nothing covered
        result_tight = compute_sensor_coverage(site, sensor, placement, sensitivity_dbm=30.0)
        # Generous sensitivity → some coverage
        result_loose = compute_sensor_coverage(site, sensor, placement, sensitivity_dbm=-100.0)
        assert not result_tight.any()
        assert result_loose.any()

    def test_acoustic_noise_kwarg_respected(self, flat_dem_path):
        """ambient_noise_db kwarg reaches the acoustic model."""
        site = load_dem(flat_dem_path)
        sensor = _sensor(SensorType.Acoustic, max_range_m=40.0)
        placement = _placement(site.origin_x, site.origin_y)
        cov_quiet = compute_sensor_coverage(site, sensor, placement, ambient_noise_db=0.0)
        cov_noisy = compute_sensor_coverage(site, sensor, placement, ambient_noise_db=20.0)
        assert cov_noisy.sum() < cov_quiet.sum()

    def test_radar_not_affected_by_rf_kwargs(self, flat_dem_path):
        """sensitivity_dbm and ambient_noise_db are ignored for Radar."""
        site = load_dem(flat_dem_path)
        sensor = _sensor(SensorType.Radar, max_range_m=30.0)
        placement = _placement(site.origin_x, site.origin_y)
        result_default = compute_sensor_coverage(site, sensor, placement)
        result_with_kwargs = compute_sensor_coverage(
            site, sensor, placement, sensitivity_dbm=999.0, ambient_noise_db=999.0
        )
        assert (result_default == result_with_kwargs).all()


# ---------------------------------------------------------------------------
# Default constants
# ---------------------------------------------------------------------------


class TestDispatcherDefaults:
    def test_default_sensitivity_dbm(self):
        assert _DEFAULT_SENSITIVITY_DBM == -70.0

    def test_default_ambient_noise_db(self):
        assert _DEFAULT_AMBIENT_NOISE_DB == 0.0


# ---------------------------------------------------------------------------
# Guard conditions
# ---------------------------------------------------------------------------


class TestDispatcherGuards:
    def test_nonfinite_height_override_raises(self, flat_dem_path):
        """D-094: non-finite height_override_m raises ValueError for Radar."""
        site = load_dem(flat_dem_path)
        sensor = _sensor(SensorType.Radar, max_range_m=30.0)
        placement = SensorPlacement(
            sensor_name="TestSensor",
            position_x=site.origin_x + 50.0,
            position_y=site.origin_y - 50.0,
            bearing_deg=0.0,
            height_override_m=float("nan"),
        )
        with pytest.raises(ValueError, match="non-finite"):
            compute_sensor_coverage(site, sensor, placement)

    def test_inf_height_override_raises(self, flat_dem_path):
        """D-094: infinite height_override_m raises ValueError for EO/IR."""
        site = load_dem(flat_dem_path)
        sensor = _sensor(SensorType.EO_IR, max_range_m=30.0)
        placement = SensorPlacement(
            sensor_name="TestSensor",
            position_x=site.origin_x + 50.0,
            position_y=site.origin_y - 50.0,
            bearing_deg=0.0,
            height_override_m=float("inf"),
        )
        with pytest.raises(ValueError, match="non-finite"):
            compute_sensor_coverage(site, sensor, placement)

    def test_oserror_fallback_emits_warning(self, flat_dem_path, monkeypatch):
        """D-095: OSError from GDAL falls back to NumPy and emits UserWarning."""
        from salus.engine import viewshed as vs_mod

        def _raise_oserror(*_args, **_kwargs):
            raise OSError("simulated GDAL failure")

        monkeypatch.setattr(vs_mod, "_viewshed_gdal", _raise_oserror)
        site = load_dem(flat_dem_path)
        sensor = _sensor(SensorType.Radar, max_range_m=30.0, mounting_height_m=5.0)
        placement = _placement(site.origin_x, site.origin_y)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = compute_sensor_coverage(site, sensor, placement)
        assert result.shape == site.dem.shape
        assert any("OSError" in str(w.message) for w in caught)
