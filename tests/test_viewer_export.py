"""Tests for salus.viewer.export and salus.viewer.sanitise (S14)."""

from __future__ import annotations

import base64
from pathlib import Path

import numpy as np
import pytest

from salus.engine.coverage import CoverageStats
from salus.models.scenario import ScenarioConfig, SensorPlacement
from salus.models.sensor import SensorType
from salus.models.site import SiteModel
from salus.viewer.export import (
    ViewerData,
    _encode_terrarium,
    _rgb_to_png,
    export_viewer_data,
    package_viewer,
)
from salus.viewer.sanitise import SanitiseConfig, SanitiseLevel, sanitise_for_export

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_site(rows: int = 20, cols: int = 20, epsg: int = 28354) -> SiteModel:
    dem = np.full((rows, cols), 100.0, dtype=np.float32)
    dem[5:15, 5:15] = 150.0  # small hill in centre
    return SiteModel(
        dem=dem,
        resolution=5.0,
        origin_x=500000.0,
        origin_y=6100100.0,  # top-left (north edge)
        crs_epsg=epsg,
    )


def _make_sim_results(site: SiteModel):
    """Build a minimal SimulationResults-like object for testing."""
    from salus.report.pdf import SimulationResults

    composite = np.zeros((site.rows, site.cols), dtype=bool)
    composite[8:12, 8:12] = True  # small covered area

    layer_cov = {SensorType.EO_IR: composite.copy()}

    rmap = np.zeros((site.rows, site.cols), dtype=np.intp)
    stats = CoverageStats(
        total_coverage_pct=25.0,
        per_layer_coverage_pct={SensorType.EO_IR: 25.0},
        per_zone_coverage_pct={},
        gap_area_m2=750.0,
        redundancy_map=rmap,
        largest_contiguous_gap_m2=750.0,
    )

    placement = SensorPlacement(
        sensor_name="TestSensor",
        position_x=500050.0,
        position_y=6100050.0,
        bearing_deg=0.0,
    )
    sc = ScenarioConfig(
        site_dem_path="demo_terrain.tif",
        sensor_placements=[placement],
    )

    from salus.models.sensor import SensorDefinition

    sensor_def = SensorDefinition(
        name="TestSensor",
        type=SensorType.EO_IR,
        max_range_m=500.0,
        azimuth_coverage_deg=120.0,
        elevation_coverage_deg=30.0,
        mounting_height_m=3.0,
        requires_los=True,
    )

    return SimulationResults(
        site=site,
        scenario=sc,
        composite=composite,
        layer_coverages=layer_cov,
        stats=stats,
        sensor_defs=[sensor_def],
        gaps=~composite,
    )


# ---------------------------------------------------------------------------
# TestEncodeTerrarium
# ---------------------------------------------------------------------------


class TestEncodeTerrarium:
    def test_zero_elevation_gives_known_rgb(self):
        """Elevation 0 m → val = 32768 → R=128, G=0, B=0."""
        arr = np.array([[0.0]], dtype=np.float32)
        rgb = _encode_terrarium(arr)
        assert rgb[0, 0, 0] == 128  # R = 32768 >> 8
        assert rgb[0, 0, 1] == 0  # G = 32768 & 0xFF
        assert rgb[0, 0, 2] == 0  # B = 0 (no fractional part)

    def test_roundtrip_integer_elevation(self):
        """Decode Terrarium encoding and verify it round-trips cleanly."""
        elevation = np.array([[180.0]], dtype=np.float32)
        rgb = _encode_terrarium(elevation)
        r, g, b = int(rgb[0, 0, 0]), int(rgb[0, 0, 1]), int(rgb[0, 0, 2])
        decoded = (r * 256 + g + b / 256) - 32768
        assert abs(decoded - 180.0) < 0.01

    def test_roundtrip_fractional_elevation(self):
        elevation = np.array([[180.5]], dtype=np.float32)
        rgb = _encode_terrarium(elevation)
        r, g, b = int(rgb[0, 0, 0]), int(rgb[0, 0, 1]), int(rgb[0, 0, 2])
        decoded = (r * 256 + g + b / 256) - 32768
        assert abs(decoded - 180.5) < 0.01

    def test_output_shape(self):
        arr = np.ones((10, 10), dtype=np.float32) * 50.0
        rgb = _encode_terrarium(arr)
        assert rgb.shape == (10, 10, 3)
        assert rgb.dtype == np.uint8

    def test_negative_elevation_clamped(self):
        """Elevation below −32768 clamps to 0."""
        arr = np.array([[-40000.0]], dtype=np.float32)
        rgb = _encode_terrarium(arr)
        assert rgb[0, 0, 0] == 0
        assert rgb[0, 0, 1] == 0

    def test_high_elevation_clamped(self):
        """Elevation above 32767 clamps to max representable value."""
        arr = np.array([[32768.0]], dtype=np.float32)
        rgb = _encode_terrarium(arr)
        # h = 65536 clamped to 65535.999; h_floor = 65535; R = 65535 >> 8 = 255, clipped to 255
        assert rgb[0, 0, 0] == 255


class TestRgbToPng:
    def test_returns_bytes(self):
        rgb = np.zeros((256, 256, 3), dtype=np.uint8)
        result = _rgb_to_png(rgb)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_valid_png_header(self):
        rgb = np.zeros((256, 256, 3), dtype=np.uint8)
        result = _rgb_to_png(rgb)
        assert result[:8] == b"\x89PNG\r\n\x1a\n"

    def test_small_tile(self):
        """Works for non-256 tile sizes."""
        rgb = np.full((64, 64, 3), 128, dtype=np.uint8)
        result = _rgb_to_png(rgb)
        assert len(result) > 100


# ---------------------------------------------------------------------------
# TestExportViewerData
# ---------------------------------------------------------------------------


class TestExportViewerData:
    def test_returns_viewer_data_instance(self, flat_dem_path):
        from salus.ingest.terrain import load_dem

        site = load_dem(flat_dem_path)
        sim = _make_sim_results(site)
        result = export_viewer_data(sim)
        assert isinstance(result, ViewerData)

    def test_scenario_name_from_dem_stem(self, flat_dem_path):
        from salus.ingest.terrain import load_dem

        site = load_dem(flat_dem_path)
        sim = _make_sim_results(site)
        # Override scenario to use actual flat_dem_path so stem == "flat"
        from salus.models.scenario import ScenarioConfig

        sim.scenario = ScenarioConfig(
            site_dem_path=str(flat_dem_path),
            sensor_placements=sim.scenario.sensor_placements,
        )
        result = export_viewer_data(sim)
        assert result.scenario_name == "flat"

    def test_bounds_wgs84_is_tuple_of_four_floats(self, flat_dem_path):
        from salus.ingest.terrain import load_dem

        site = load_dem(flat_dem_path)
        sim = _make_sim_results(site)
        result = export_viewer_data(sim)
        assert len(result.bounds_wgs84) == 4
        west, south, east, north = result.bounds_wgs84
        assert west < east
        assert south < north

    def test_centre_wgs84_within_bounds(self, flat_dem_path):
        from salus.ingest.terrain import load_dem

        site = load_dem(flat_dem_path)
        sim = _make_sim_results(site)
        result = export_viewer_data(sim)
        w, s, e, n = result.bounds_wgs84
        lon, lat = result.centre_wgs84
        assert w <= lon <= e
        assert s <= lat <= n

    def test_layers_contains_composite_and_gaps(self, flat_dem_path):
        from salus.ingest.terrain import load_dem

        site = load_dem(flat_dem_path)
        sim = _make_sim_results(site)
        result = export_viewer_data(sim)
        assert "composite" in result.layers
        assert "gaps" in result.layers

    def test_layers_are_geojson_feature_collections(self, flat_dem_path):
        from salus.ingest.terrain import load_dem

        site = load_dem(flat_dem_path)
        sim = _make_sim_results(site)
        result = export_viewer_data(sim)
        for key, fc in result.layers.items():
            assert fc["type"] == "FeatureCollection", f"layer '{key}' is not FeatureCollection"
            assert "features" in fc

    def test_per_layer_exported(self, flat_dem_path):
        from salus.ingest.terrain import load_dem

        site = load_dem(flat_dem_path)
        sim = _make_sim_results(site)
        result = export_viewer_data(sim)
        assert SensorType.EO_IR.value in result.layers

    def test_sensor_placements_geojson(self, flat_dem_path):
        from salus.ingest.terrain import load_dem

        site = load_dem(flat_dem_path)
        sim = _make_sim_results(site)
        result = export_viewer_data(sim)
        assert result.sensor_placements["type"] == "FeatureCollection"
        assert len(result.sensor_placements["features"]) == 1
        feat = result.sensor_placements["features"][0]
        assert feat["geometry"]["type"] == "Point"

    def test_stats_dict_contains_coverage_pct(self, flat_dem_path):
        from salus.ingest.terrain import load_dem

        site = load_dem(flat_dem_path)
        sim = _make_sim_results(site)
        result = export_viewer_data(sim)
        assert "total_coverage_pct" in result.stats
        assert "gap_area_m2" in result.stats

    def test_terrain_tiles_non_empty(self, flat_dem_path):
        from salus.ingest.terrain import load_dem

        site = load_dem(flat_dem_path)
        sim = _make_sim_results(site)
        result = export_viewer_data(sim)
        assert len(result.terrain_tiles) > 0

    def test_libraries_loaded_from_disk(self, flat_dem_path):
        """`export_viewer_data` populates sensor_library/effector_library from
        the bundled YAML data dir so the sanitiser controls a single trust
        boundary (D-498).
        """
        from salus.ingest.terrain import load_dem

        site = load_dem(flat_dem_path)
        sim = _make_sim_results(site)
        result = export_viewer_data(sim)
        # The bundled data/sensors directory has at least one YAML — the load
        # must produce a non-empty dict here so package_viewer can embed it
        # without re-reading the filesystem.
        assert isinstance(result.sensor_library, dict)
        assert len(result.sensor_library) > 0
        assert isinstance(result.effector_library, dict)
        assert len(result.effector_library) > 0

    def test_terrain_tiles_are_valid_base64(self, flat_dem_path):
        from salus.ingest.terrain import load_dem

        site = load_dem(flat_dem_path)
        sim = _make_sim_results(site)
        result = export_viewer_data(sim)
        for key, b64 in result.terrain_tiles.items():
            data = base64.b64decode(b64)
            assert data[:8] == b"\x89PNG\r\n\x1a\n", f"tile {key} is not PNG"

    def test_terrain_tile_keys_are_z_x_y(self, flat_dem_path):
        from salus.ingest.terrain import load_dem

        site = load_dem(flat_dem_path)
        sim = _make_sim_results(site)
        result = export_viewer_data(sim)
        for key in result.terrain_tiles:
            parts = key.split("/")
            assert len(parts) == 3, f"tile key '{key}' not in z/x/y format"
            assert all(p.isdigit() for p in parts)

    def test_not_sanitised_by_default(self, flat_dem_path):
        from salus.ingest.terrain import load_dem

        site = load_dem(flat_dem_path)
        sim = _make_sim_results(site)
        result = export_viewer_data(sim)
        assert result.sanitised is False

    def test_no_kill_chain_when_empty(self, flat_dem_path):
        from salus.ingest.terrain import load_dem

        site = load_dem(flat_dem_path)
        sim = _make_sim_results(site)
        result = export_viewer_data(sim)
        assert result.kill_chain_results == []

    def test_no_saturation_when_none(self, flat_dem_path):
        from salus.ingest.terrain import load_dem

        site = load_dem(flat_dem_path)
        sim = _make_sim_results(site)
        result = export_viewer_data(sim)
        assert result.saturation_result is None

    def test_sensor_feature_has_sensor_type_property(self, flat_dem_path):
        from salus.ingest.terrain import load_dem

        site = load_dem(flat_dem_path)
        sim = _make_sim_results(site)
        result = export_viewer_data(sim)
        feat = result.sensor_placements["features"][0]
        assert "sensor_type" in feat["properties"]
        assert feat["properties"]["sensor_type"] == "EO_IR"

    def test_sensor_feature_has_azimuth_coverage_deg_property(self, flat_dem_path):
        from salus.ingest.terrain import load_dem

        site = load_dem(flat_dem_path)
        sim = _make_sim_results(site)
        result = export_viewer_data(sim)
        feat = result.sensor_placements["features"][0]
        assert "azimuth_coverage_deg" in feat["properties"]
        assert feat["properties"]["azimuth_coverage_deg"] == 120.0

    def test_sensor_type_defaults_when_no_sensor_def(self, flat_dem_path):
        """If sensor_defs is empty the type defaults to empty string and azimuth to 360."""
        from salus.ingest.terrain import load_dem
        from salus.report.pdf import SimulationResults

        site = load_dem(flat_dem_path)
        sim = _make_sim_results(site)
        # Override sensor_defs to empty list — simulates missing lookup
        sim_no_defs = SimulationResults(
            site=sim.site,
            scenario=sim.scenario,
            composite=sim.composite,
            layer_coverages=sim.layer_coverages,
            stats=sim.stats,
            sensor_defs=[],
            gaps=sim.gaps,
        )
        result = export_viewer_data(sim_no_defs)
        feat = result.sensor_placements["features"][0]
        assert feat["properties"]["sensor_type"] == ""
        assert feat["properties"]["azimuth_coverage_deg"] == 360.0


# ---------------------------------------------------------------------------
# TestPackageViewer
# ---------------------------------------------------------------------------


class TestPackageViewer:
    def _make_minimal_viewer_data(self) -> ViewerData:
        return ViewerData(
            scenario_name="test_site",
            generated_at="2026-04-10T00:00:00Z",
            bounds_wgs84=(150.0, -34.0, 151.0, -33.0),
            centre_wgs84=(150.5, -33.5),
            layers={
                "composite": {"type": "FeatureCollection", "features": []},
                "gaps": {"type": "FeatureCollection", "features": []},
            },
            sensor_placements={"type": "FeatureCollection", "features": []},
            stats={
                "total_coverage_pct": 50.0,
                "gap_area_m2": 100.0,
                "per_layer_coverage_pct": {},
                "per_zone_coverage_pct": {},
                "largest_contiguous_gap_m2": 100.0,
            },
            corridor_results=[],
            kill_chain_results=[],
            saturation_result=None,
            terrain_tiles={
                "12/3689/2493": base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100).decode()
            },
            terrain_min_zoom=12,
            terrain_max_zoom=12,
            # Libraries flow through ViewerData (D-498). Tests that assert
            # embedding must populate them here — package_viewer no longer
            # loads from disk.
            sensor_library={
                "Radar": [{"name": "Test Radar", "type": "Radar", "max_range_m": 1500.0}],
                "EO_IR": [{"name": "Test EO", "type": "EO_IR", "max_range_m": 800.0}],
            },
            effector_library={
                "Jammer": [{"name": "Test Jammer", "type": "Jammer", "max_range_m": 600.0}],
            },
        )

    def test_creates_output_directory(self, tmp_path):
        vd = self._make_minimal_viewer_data()
        out = tmp_path / "viewer_out"
        result = package_viewer(vd, out)
        assert out.exists()
        assert result == out

    def test_writes_index_html(self, tmp_path):
        vd = self._make_minimal_viewer_data()
        out = tmp_path / "viewer_out"
        package_viewer(vd, out)
        assert (out / "index.html").exists()

    def test_writes_app_js(self, tmp_path):
        vd = self._make_minimal_viewer_data()
        out = tmp_path / "viewer_out"
        package_viewer(vd, out)
        assert (out / "app.js").exists()

    def test_writes_style_css(self, tmp_path):
        vd = self._make_minimal_viewer_data()
        out = tmp_path / "viewer_out"
        package_viewer(vd, out)
        assert (out / "style.css").exists()

    def test_writes_viewer_data_js(self, tmp_path):
        vd = self._make_minimal_viewer_data()
        out = tmp_path / "viewer_out"
        package_viewer(vd, out)
        data_js = out / "viewer_data.js"
        assert data_js.exists()
        content = data_js.read_text()
        assert "window.SALUS_DATA" in content
        # Terrain tiles are now served as files, not embedded in viewer_data.js
        assert "window.SALUS_TILES" not in content

    def test_viewer_data_js_contains_scenario_name(self, tmp_path):
        vd = self._make_minimal_viewer_data()
        out = tmp_path / "viewer_out"
        package_viewer(vd, out)
        content = (out / "viewer_data.js").read_text()
        assert "test_site" in content

    def test_terrain_tile_files_written(self, tmp_path):
        vd = self._make_minimal_viewer_data()
        out = tmp_path / "viewer_out"
        package_viewer(vd, out)
        # Tile 12/3689/2493 should be written as tiles/12/3689/2493.png
        tile_path = out / "tiles" / "12" / "3689" / "2493.png"
        assert tile_path.exists()
        assert tile_path.stat().st_size > 0

    def test_viewer_data_js_does_not_contain_tile_data(self, tmp_path):
        vd = self._make_minimal_viewer_data()
        out = tmp_path / "viewer_out"
        package_viewer(vd, out)
        content = (out / "viewer_data.js").read_text()
        # Tile keys must not be embedded in viewer_data.js anymore
        assert "12/3689/2493" not in content

    def test_viewer_data_js_contains_terrain_tile_count(self, tmp_path):
        vd = self._make_minimal_viewer_data()
        out = tmp_path / "viewer_out"
        package_viewer(vd, out)
        import json

        content = (out / "viewer_data.js").read_text()
        # Strip the window.SALUS_DATA= prefix and trailing semicolon/newline
        json_str = content.removeprefix("window.SALUS_DATA=").rstrip(";\n")
        data = json.loads(json_str)
        assert data["terrain_tile_count"] == 1  # one tile in _make_minimal_viewer_data

    def test_vendor_directory_created(self, tmp_path):
        vd = self._make_minimal_viewer_data()
        out = tmp_path / "viewer_out"
        package_viewer(vd, out)
        assert (out / "vendor").is_dir()

    def test_zip_output_creates_zip_file(self, tmp_path):
        vd = self._make_minimal_viewer_data()
        out = tmp_path / "viewer_out"
        package_viewer(vd, out, zip_output=True)
        zip_path = Path(str(out) + ".zip")
        assert zip_path.exists()

    def test_returns_resolved_path(self, tmp_path):
        vd = self._make_minimal_viewer_data()
        out = tmp_path / "viewer_out"
        result = package_viewer(vd, out)
        assert result.is_absolute()

    def test_viewer_data_js_contains_sensor_library(self, tmp_path):
        """package_viewer embeds sensor_library in SALUS_DATA."""
        import json

        vd = self._make_minimal_viewer_data()
        out = tmp_path / "viewer_out"
        package_viewer(vd, out)
        content = (out / "viewer_data.js").read_text()
        json_str = content.removeprefix("window.SALUS_DATA=").rstrip(";\n")
        data = json.loads(json_str)
        assert "sensor_library" in data
        assert isinstance(data["sensor_library"], dict)

    def test_viewer_data_js_contains_effector_library(self, tmp_path):
        """package_viewer embeds effector_library in SALUS_DATA."""
        import json

        vd = self._make_minimal_viewer_data()
        out = tmp_path / "viewer_out"
        package_viewer(vd, out)
        content = (out / "viewer_data.js").read_text()
        json_str = content.removeprefix("window.SALUS_DATA=").rstrip(";\n")
        data = json.loads(json_str)
        assert "effector_library" in data
        assert isinstance(data["effector_library"], dict)

    def test_sensor_library_grouped_by_type(self, tmp_path):
        """Each key in sensor_library is a sensor type; items are lists of dicts."""
        import json

        vd = self._make_minimal_viewer_data()
        out = tmp_path / "viewer_out"
        package_viewer(vd, out)
        content = (out / "viewer_data.js").read_text()
        json_str = content.removeprefix("window.SALUS_DATA=").rstrip(";\n")
        data = json.loads(json_str)
        for type_key, items in data["sensor_library"].items():
            assert isinstance(type_key, str), f"Expected string key, got {type(type_key)}"
            assert isinstance(items, list), f"Expected list under '{type_key}'"
            for item in items:
                assert isinstance(item, dict)
                assert item.get("type") == type_key, (
                    f"Item type mismatch: {item.get('type')!r} != {type_key!r}"
                )

    def test_redacted_viewer_does_not_leak_library_secrets(self, tmp_path):
        """End-to-end: a REDACTED packaged viewer has no proprietary content (D-498)."""
        import json

        from salus.viewer.sanitise import SanitiseConfig, SanitiseLevel, sanitise_for_export

        vd = self._make_minimal_viewer_data()
        # Inject content that would be unsafe to leak if it survived sanitisation.
        vd.sensor_library["Radar"][0]["name"] = "Echodyne EchoGuard"
        vd.sensor_library["Radar"][0]["cost_aud"] = 50000.0
        vd.sensor_library["EO_IR"][0]["name"] = "Anduril WISP"
        vd.effector_library["Jammer"][0]["name"] = "DroneShield DroneCannon"
        vd.effector_library["Jammer"][0]["cost_aud"] = 30000.0

        redacted = sanitise_for_export(vd, SanitiseConfig(level=SanitiseLevel.REDACTED))
        out = tmp_path / "viewer_out"
        package_viewer(redacted, out)

        content = (out / "viewer_data.js").read_text()
        # No vendor names in the packaged viewer.
        assert "Echodyne EchoGuard" not in content
        assert "Anduril WISP" not in content
        assert "DroneShield DroneCannon" not in content
        # No exact range values surfaced — and no cost numbers.
        json_str = content.removeprefix("window.SALUS_DATA=").rstrip(";\n")
        data = json.loads(json_str)
        for entries in data["sensor_library"].values():
            for entry in entries:
                assert "max_range_m" not in entry
                assert "cost_aud" not in entry
        for entries in data["effector_library"].values():
            for entry in entries:
                assert "max_range_m" not in entry
                assert "cost_aud" not in entry

    def test_full_sanitised_viewer_omits_libraries(self, tmp_path):
        """A FULL-sanitised packaged viewer carries no library content at all."""
        import json

        from salus.viewer.sanitise import SanitiseConfig, SanitiseLevel, sanitise_for_export

        vd = self._make_minimal_viewer_data()
        full = sanitise_for_export(vd, SanitiseConfig(level=SanitiseLevel.FULL))
        out = tmp_path / "viewer_out"
        package_viewer(full, out)

        content = (out / "viewer_data.js").read_text()
        json_str = content.removeprefix("window.SALUS_DATA=").rstrip(";\n")
        data = json.loads(json_str)
        assert data["sensor_library"] == {}
        assert data["effector_library"] == {}


# ---------------------------------------------------------------------------
# TestLoadSensorLibrary
# ---------------------------------------------------------------------------


class TestLoadSensorLibrary:
    def test_groups_yamls_by_type_field(self, tmp_path):
        """YAML files are grouped under the value of their 'type' field."""
        from salus.viewer.export import _load_sensor_library

        sensor_dir = tmp_path / "sensors"
        sensor_dir.mkdir()
        (sensor_dir / "radar_a.yaml").write_text("name: Radar A\ntype: Radar\nmax_range_m: 1000\n")
        (sensor_dir / "radar_b.yaml").write_text("name: Radar B\ntype: Radar\nmax_range_m: 2000\n")
        (sensor_dir / "rf_a.yaml").write_text("name: RF A\ntype: RF\nmax_range_m: 500\n")

        result = _load_sensor_library(sensor_dir)

        assert set(result.keys()) == {"Radar", "RF"}
        assert len(result["Radar"]) == 2
        assert len(result["RF"]) == 1

    def test_missing_directory_returns_empty_dict(self, tmp_path):
        """A non-existent directory yields an empty dict without raising."""
        from salus.viewer.export import _load_sensor_library

        result = _load_sensor_library(tmp_path / "nonexistent")
        assert result == {}

    def test_invalid_yaml_is_skipped(self, tmp_path):
        """A malformed YAML file is logged and skipped; valid files still load."""
        from salus.viewer.export import _load_sensor_library

        sensor_dir = tmp_path / "sensors"
        sensor_dir.mkdir()
        (sensor_dir / "bad.yaml").write_text("{{invalid yaml: [}")
        (sensor_dir / "good.yaml").write_text("name: Good Sensor\ntype: Radar\n")

        result = _load_sensor_library(sensor_dir)
        assert "Radar" in result
        assert len(result["Radar"]) == 1
        assert result["Radar"][0]["name"] == "Good Sensor"

    def test_missing_type_field_groups_as_unknown(self, tmp_path):
        """Entries without a 'type' field are grouped under 'Unknown'."""
        from salus.viewer.export import _load_sensor_library

        sensor_dir = tmp_path / "sensors"
        sensor_dir.mkdir()
        (sensor_dir / "notype.yaml").write_text("name: No Type Sensor\nmax_range_m: 1000\n")

        result = _load_sensor_library(sensor_dir)
        assert "Unknown" in result
        assert result["Unknown"][0]["name"] == "No Type Sensor"

    def test_all_fields_preserved(self, tmp_path):
        """All YAML fields are present in the loaded dict."""
        from salus.viewer.export import _load_sensor_library

        sensor_dir = tmp_path / "sensors"
        sensor_dir.mkdir()
        yaml_text = (
            "name: Test\ntype: EO_IR\nmax_range_m: 800\n"
            "azimuth_coverage_deg: 90\nrequires_los: true\n"
        )
        (sensor_dir / "sensor.yaml").write_text(yaml_text)

        result = _load_sensor_library(sensor_dir)
        item = result["EO_IR"][0]
        assert item["name"] == "Test"
        assert item["max_range_m"] == 800
        assert item["azimuth_coverage_deg"] == 90
        assert item["requires_los"] is True

    def test_returns_sorted_keys(self, tmp_path):
        """Keys in the returned dict are sorted alphabetically."""
        from salus.viewer.export import _load_sensor_library

        sensor_dir = tmp_path / "sensors"
        sensor_dir.mkdir()
        (sensor_dir / "z.yaml").write_text("name: Z\ntype: RF\n")
        (sensor_dir / "a.yaml").write_text("name: A\ntype: Acoustic\n")
        (sensor_dir / "r.yaml").write_text("name: R\ntype: Radar\n")

        result = _load_sensor_library(sensor_dir)
        assert list(result.keys()) == sorted(result.keys())

    def test_get_user_placements_geojson_structure(self, tmp_path):
        """Verify the exported JS contains getUserPlacementsAsGeoJSON and userPlacements."""
        # Verify app.js (the static source) contains the required functions and state.
        app_js = Path(__file__).parent.parent / "src" / "salus" / "viewer" / "static" / "app.js"
        content = app_js.read_text(encoding="utf-8")
        assert "getUserPlacementsAsGeoJSON" in content, "Public API function must be present"
        assert "userPlacements" in content, "Module-level placement array must be present"
        assert "SPEC_DISPLAY_FIELDS" in content, "Spec field config constant must be present"

        # Verify the GeoJSON returned by the function has the correct shape by checking
        # that the function body references the required properties.
        assert "FeatureCollection" in content, "Must return FeatureCollection type"
        assert "bearing_deg" in content, "Must include bearing_deg in feature properties"


# ---------------------------------------------------------------------------
# TestSanitiseForExport
# ---------------------------------------------------------------------------


class TestSanitiseForExport:
    def _make_viewer_data_with_sensors(self) -> ViewerData:
        return ViewerData(
            scenario_name="compound_defence",
            generated_at="2026-04-10T00:00:00Z",
            bounds_wgs84=(150.0001, -34.0001, 151.0001, -33.0001),
            centre_wgs84=(150.50012, -33.50012),
            layers={
                "composite": {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "geometry": {
                                "type": "Point",
                                "coordinates": [150.123456789, -33.987654321],
                            },
                            "properties": {},
                        }
                    ],
                },
                "gaps": {"type": "FeatureCollection", "features": []},
            },
            sensor_placements={
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [150.12345678, -33.98765432]},
                        "properties": {
                            "sensor_name": "Anduril WISP",
                            "bearing_deg": 45.0,
                            "height_override_m": 6.0,
                        },
                    }
                ],
            },
            stats={
                "total_coverage_pct": 47.5,
                "gap_area_m2": 100.0,
                "per_layer_coverage_pct": {"EO_IR": 43.2, "Radar": 4.7},
                "per_zone_coverage_pct": {},
                "largest_contiguous_gap_m2": 100.0,
            },
            corridor_results=[
                {
                    "threat_name": "DJI Mavic 3",
                    "path_wgs84": [[150.123456, -33.987654], [150.234567, -33.876543]],
                    "coverage_fraction": 0.75,
                }
            ],
            kill_chain_results=[
                {
                    "available_time_s": 23.0,
                    "required_time_s": 17.7,
                    "margin_s": 5.3,
                    "first_detection_range_m": 850.0,
                    "engagement_feasible": True,
                    "second_engagement_possible": False,
                }
            ],
            saturation_result={
                "simultaneous_engagement_capacity": 3,
                "saturation_threshold_n": 4,
                "unengaged_count_at_threshold": 1,
                "per_effector_utilisation": {"EffectorA": 0.8, "EffectorB": 0.6},
            },
            terrain_tiles={},
            terrain_min_zoom=12,
            terrain_max_zoom=16,
        )

    def test_rejects_negative_coordinate_precision(self):
        with pytest.raises(ValueError, match="coordinate_precision"):
            SanitiseConfig(coordinate_precision=-1)

    def test_rejects_float_coordinate_precision(self):
        with pytest.raises(TypeError, match="coordinate_precision"):
            SanitiseConfig(coordinate_precision=4.5)  # type: ignore[arg-type]

    def test_returns_new_instance(self):
        vd = self._make_viewer_data_with_sensors()
        config = SanitiseConfig(level=SanitiseLevel.MINIMAL)
        result = sanitise_for_export(vd, config)
        assert result is not vd

    def test_does_not_mutate_original(self):
        vd = self._make_viewer_data_with_sensors()
        original_name = vd.sensor_placements["features"][0]["properties"]["sensor_name"]
        config = SanitiseConfig(level=SanitiseLevel.REDACTED)
        sanitise_for_export(vd, config)
        assert vd.sensor_placements["features"][0]["properties"]["sensor_name"] == original_name

    def test_minimal_rounds_coordinates(self):
        vd = self._make_viewer_data_with_sensors()
        config = SanitiseConfig(level=SanitiseLevel.MINIMAL, coordinate_precision=4)
        result = sanitise_for_export(vd, config)
        sensor_coord = result.sensor_placements["features"][0]["geometry"]["coordinates"]
        assert all(len(str(c).split(".")[-1]) <= 4 for c in sensor_coord)

    def test_minimal_preserves_sensor_name(self):
        vd = self._make_viewer_data_with_sensors()
        result = sanitise_for_export(vd, SanitiseConfig(level=SanitiseLevel.MINIMAL))
        name = result.sensor_placements["features"][0]["properties"]["sensor_name"]
        assert name == "Anduril WISP"

    def test_redacted_anonymises_sensor_name(self):
        vd = self._make_viewer_data_with_sensors()
        result = sanitise_for_export(vd, SanitiseConfig(level=SanitiseLevel.REDACTED))
        name = result.sensor_placements["features"][0]["properties"]["sensor_name"]
        assert name != "Anduril WISP"
        assert name.startswith("Sensor-")

    def test_redacted_strips_bearing_and_height(self):
        vd = self._make_viewer_data_with_sensors()
        result = sanitise_for_export(vd, SanitiseConfig(level=SanitiseLevel.REDACTED))
        props = result.sensor_placements["features"][0]["properties"]
        assert "bearing_deg" not in props
        assert "height_override_m" not in props

    def test_redacted_relabels_per_layer_keys(self):
        vd = self._make_viewer_data_with_sensors()
        result = sanitise_for_export(vd, SanitiseConfig(level=SanitiseLevel.REDACTED))
        keys = list(result.stats["per_layer_coverage_pct"].keys())
        assert all(k.startswith("Layer-") for k in keys)

    def test_full_removes_corridor_paths(self):
        vd = self._make_viewer_data_with_sensors()
        result = sanitise_for_export(vd, SanitiseConfig(level=SanitiseLevel.FULL))
        for corridor in result.corridor_results:
            assert "path_wgs84" not in corridor

    def test_full_removes_kill_chain_timing(self):
        vd = self._make_viewer_data_with_sensors()
        result = sanitise_for_export(vd, SanitiseConfig(level=SanitiseLevel.FULL))
        for kc in result.kill_chain_results:
            assert "available_time_s" not in kc
            assert "required_time_s" not in kc
            assert "first_detection_range_m" not in kc
            assert "margin_s" not in kc
            assert "engagement_feasible" in kc

    def test_full_removes_saturation_utilisation(self):
        vd = self._make_viewer_data_with_sensors()
        result = sanitise_for_export(vd, SanitiseConfig(level=SanitiseLevel.FULL))
        assert "per_effector_utilisation" not in (result.saturation_result or {})

    def test_marks_as_sanitised(self):
        vd = self._make_viewer_data_with_sensors()
        result = sanitise_for_export(vd, SanitiseConfig(level=SanitiseLevel.REDACTED))
        assert result.sanitised is True

    def test_preserves_coverage_stats(self):
        vd = self._make_viewer_data_with_sensors()
        result = sanitise_for_export(vd, SanitiseConfig(level=SanitiseLevel.FULL))
        assert result.stats["total_coverage_pct"] == 47.5
        assert result.stats["gap_area_m2"] == 100.0

    # ---------------------------------------------------------------------
    # D-498 / I-15: library redaction at each sanitise level
    # ---------------------------------------------------------------------

    def _make_viewer_data_with_libraries(self) -> ViewerData:
        """A ViewerData with realistic sensor/effector library entries."""
        vd = self._make_viewer_data_with_sensors()
        vd.sensor_library = {
            "EO_IR": [
                {
                    "name": "Anduril WISP",
                    "type": "EO_IR",
                    "max_range_m": 5000.0,
                    "min_range_m": 0.0,
                    "azimuth_coverage_deg": 360.0,
                    "elevation_coverage_deg": 125.0,
                    "elevation_boresight_deg": 0.0,
                    "frequency_bands": [],
                    "requires_los": True,
                    "mounting_height_m": 5.0,
                    "vegetation_penetration": 0.0,
                    "cost_aud": None,
                },
            ],
            "Radar": [
                {
                    "name": "Echodyne EchoGuard",
                    "type": "Radar",
                    "max_range_m": 1000.0,
                    "azimuth_coverage_deg": 120.0,
                    "elevation_coverage_deg": 80.0,
                    "frequency_bands": ["K-band"],
                    "requires_los": True,
                    "cost_aud": 50000.0,
                },
            ],
        }
        vd.effector_library = {
            "Jammer": [
                {
                    "name": "DroneShield DroneCannon",
                    "type": "Jammer",
                    "max_range_m": 2500.0,
                    "azimuth_coverage_deg": 90.0,
                    "requires_los": False,
                    "cost_aud": 30000.0,
                    "notes": "directional RF jammer",
                },
            ],
        }
        return vd

    def test_minimal_preserves_libraries(self):
        vd = self._make_viewer_data_with_libraries()
        result = sanitise_for_export(vd, SanitiseConfig(level=SanitiseLevel.MINIMAL))
        # MINIMAL must leave libraries unchanged so the analysis environment
        # can use the full DB while still rounding coordinates.
        assert result.sensor_library["EO_IR"][0]["name"] == "Anduril WISP"
        assert result.sensor_library["EO_IR"][0]["max_range_m"] == 5000.0
        assert result.effector_library["Jammer"][0]["cost_aud"] == 30000.0

    def test_redacted_strips_vendor_name_from_sensor_library(self):
        vd = self._make_viewer_data_with_libraries()
        result = sanitise_for_export(vd, SanitiseConfig(level=SanitiseLevel.REDACTED))
        entry = result.sensor_library["EO_IR"][0]
        assert entry["name"] != "Anduril WISP"
        assert entry["name"] == "EO_IR-1"

    def test_redacted_strips_max_range_from_sensor_library(self):
        vd = self._make_viewer_data_with_libraries()
        result = sanitise_for_export(vd, SanitiseConfig(level=SanitiseLevel.REDACTED))
        entry = result.sensor_library["EO_IR"][0]
        assert "max_range_m" not in entry
        # 5000 m exact range -> "long" band.
        assert entry["range_band"] == "long"

    def test_redacted_bands_radar_range(self):
        vd = self._make_viewer_data_with_libraries()
        result = sanitise_for_export(vd, SanitiseConfig(level=SanitiseLevel.REDACTED))
        # Echodyne range 1000 m falls in the "medium" band (500-2000 m).
        assert result.sensor_library["Radar"][0]["range_band"] == "medium"

    def test_redacted_strips_proprietary_fields(self):
        vd = self._make_viewer_data_with_libraries()
        result = sanitise_for_export(vd, SanitiseConfig(level=SanitiseLevel.REDACTED))
        eo_ir = result.sensor_library["EO_IR"][0]
        for forbidden in (
            "min_range_m",
            "elevation_boresight_deg",
            "frequency_bands",
            "mounting_height_m",
            "vegetation_penetration",
            "cost_aud",
        ):
            assert forbidden not in eo_ir, f"{forbidden} leaked into redacted entry"

    def test_redacted_retains_whitelist_fields(self):
        vd = self._make_viewer_data_with_libraries()
        result = sanitise_for_export(vd, SanitiseConfig(level=SanitiseLevel.REDACTED))
        eo_ir = result.sensor_library["EO_IR"][0]
        assert eo_ir["type"] == "EO_IR"
        assert eo_ir["azimuth_coverage_deg"] == pytest.approx(360.0)
        assert eo_ir["elevation_coverage_deg"] == pytest.approx(125.0)
        assert eo_ir["requires_los"] is True

    def test_redacted_strips_effector_proprietary_fields(self):
        vd = self._make_viewer_data_with_libraries()
        result = sanitise_for_export(vd, SanitiseConfig(level=SanitiseLevel.REDACTED))
        jammer = result.effector_library["Jammer"][0]
        assert jammer["name"] == "Jammer-1"
        assert "cost_aud" not in jammer
        assert "notes" not in jammer
        assert "max_range_m" not in jammer
        assert jammer["range_band"] == "long"  # 2500 m > 2000 m -> long
        assert jammer["type"] == "Jammer"

    def test_full_clears_libraries(self):
        vd = self._make_viewer_data_with_libraries()
        result = sanitise_for_export(vd, SanitiseConfig(level=SanitiseLevel.FULL))
        assert result.sensor_library == {}
        assert result.effector_library == {}

    def test_redacted_does_not_mutate_original_library(self):
        vd = self._make_viewer_data_with_libraries()
        original_name = vd.sensor_library["EO_IR"][0]["name"]
        original_range = vd.sensor_library["EO_IR"][0]["max_range_m"]
        sanitise_for_export(vd, SanitiseConfig(level=SanitiseLevel.REDACTED))
        # Original must be untouched — the sanitiser deep-copies before
        # redacting so the analysis-environment copy of the library survives.
        assert vd.sensor_library["EO_IR"][0]["name"] == original_name
        assert vd.sensor_library["EO_IR"][0]["max_range_m"] == original_range

    def test_redacted_handles_entry_with_no_max_range(self):
        vd = self._make_viewer_data_with_libraries()
        # Strip max_range_m to simulate a malformed/sparse YAML entry.
        del vd.sensor_library["EO_IR"][0]["max_range_m"]
        result = sanitise_for_export(vd, SanitiseConfig(level=SanitiseLevel.REDACTED))
        # The sanitiser must not blow up; range_band falls back to "unknown".
        assert result.sensor_library["EO_IR"][0]["range_band"] == "unknown"

    def test_redacted_handles_entry_with_nan_max_range(self):
        vd = self._make_viewer_data_with_libraries()
        vd.sensor_library["EO_IR"][0]["max_range_m"] = float("nan")
        result = sanitise_for_export(vd, SanitiseConfig(level=SanitiseLevel.REDACTED))
        # NaN must not silently produce "long" — caller guards _range_band.
        assert result.sensor_library["EO_IR"][0]["range_band"] == "unknown"

    def test_redacted_handles_entry_with_bool_max_range(self):
        vd = self._make_viewer_data_with_libraries()
        # bool is technically int — must not be banded as a numeric range.
        vd.sensor_library["EO_IR"][0]["max_range_m"] = True
        result = sanitise_for_export(vd, SanitiseConfig(level=SanitiseLevel.REDACTED))
        assert result.sensor_library["EO_IR"][0]["range_band"] == "unknown"


# ---------------------------------------------------------------------------
# TestSerialisers
# ---------------------------------------------------------------------------


class TestSerialisers:
    """Tests for _serialise_corridor, _serialise_kill_chain, _serialise_saturation."""

    def _make_corridor_result(self):
        from salus.engine.threat_corridor import CorridorResult
        from salus.models.threat import ThreatCorridor

        corridor = ThreatCorridor(bearing_deg=45.0, altitude_m=50.0, start_distance_m=1000.0)
        return CorridorResult(
            corridor=corridor,
            threat_name="DJI Mavic 3",
            coverage_pct=72.5,
            first_detection_distance_m=650.0,
            last_gap_before_target_m=20.0,
            time_in_coverage_s=12.3,
            covered_cells=58,
            total_cells=80,
        )

    def _make_kill_chain_result(self):
        from salus.models.scenario import KillChainResult

        return KillChainResult(
            available_time_s=23.0,
            required_time_s=17.7,
            margin_s=5.3,
            first_detection_range_m=850.0,
            engagement_feasible=True,
            second_engagement_possible=False,
        )

    def _make_saturation_result(self):
        from salus.models.saturation import SaturationResult

        return SaturationResult(
            simultaneous_engagement_capacity=3,
            saturation_threshold_n=4,
            unengaged_count_at_threshold=1,
            per_effector_utilisation={"EffectorA": 0.8, "EffectorB": 0.6},
        )

    def test_serialise_corridor_maps_real_fields(self):
        from salus.viewer.export import _serialise_corridor

        result = self._make_corridor_result()
        d = _serialise_corridor(result)
        assert d["threat_name"] == "DJI Mavic 3"
        assert d["coverage_pct"] == pytest.approx(72.5)
        assert d["first_detection_distance_m"] == pytest.approx(650.0)
        assert d["covered_cells"] == 58
        assert d["total_cells"] == 80
        assert d["path_wgs84"] == []

    def test_serialise_corridor_with_path(self):
        from salus.viewer.export import _serialise_corridor

        result = self._make_corridor_result()
        path = [[150.1, -33.9], [150.2, -33.8]]
        d = _serialise_corridor(result, path_wgs84=path)
        assert d["path_wgs84"] == path

    def test_serialise_corridor_none_detection_distance(self):
        from salus.viewer.export import _serialise_corridor

        result = self._make_corridor_result()
        result = result.__class__(
            corridor=result.corridor,
            threat_name=result.threat_name,
            coverage_pct=result.coverage_pct,
            first_detection_distance_m=None,
            last_gap_before_target_m=result.last_gap_before_target_m,
            time_in_coverage_s=result.time_in_coverage_s,
            covered_cells=result.covered_cells,
            total_cells=result.total_cells,
        )
        d = _serialise_corridor(result)
        assert d["first_detection_distance_m"] is None

    def test_serialise_kill_chain_maps_real_fields(self):
        from salus.viewer.export import _serialise_kill_chain

        result = self._make_kill_chain_result()
        d = _serialise_kill_chain(result)
        assert d["available_time_s"] == pytest.approx(23.0)
        assert d["required_time_s"] == pytest.approx(17.7)
        assert d["margin_s"] == pytest.approx(5.3)
        assert d["first_detection_range_m"] == pytest.approx(850.0)
        assert d["engagement_feasible"] is True
        assert d["second_engagement_possible"] is False

    def test_serialise_saturation_maps_real_fields(self):
        from salus.viewer.export import _serialise_saturation

        result = self._make_saturation_result()
        d = _serialise_saturation(result)
        assert d["simultaneous_engagement_capacity"] == 3
        assert d["saturation_threshold_n"] == 4
        assert d["unengaged_count_at_threshold"] == 1
        assert "EffectorA" in d["per_effector_utilisation"]
        assert d["per_effector_utilisation"]["EffectorA"] == pytest.approx(0.8)

    def test_compute_corridor_path_wgs84_with_protected_point(self):
        import pyproj
        from rasterio.crs import CRS

        from salus.viewer.export import _compute_corridor_path_wgs84

        result = self._make_corridor_result()
        transformer = pyproj.Transformer.from_crs(
            CRS.from_epsg(28354), CRS.from_epsg(4326), always_xy=True
        )
        protected_point = (500050.0, 6100050.0)
        path = _compute_corridor_path_wgs84(result, protected_point, transformer)
        assert len(path) == 2
        assert len(path[0]) == 2  # [lon, lat]
        assert len(path[1]) == 2

    def test_compute_corridor_path_wgs84_no_protected_point(self):
        import pyproj
        from rasterio.crs import CRS

        from salus.viewer.export import _compute_corridor_path_wgs84

        result = self._make_corridor_result()
        transformer = pyproj.Transformer.from_crs(
            CRS.from_epsg(28354), CRS.from_epsg(4326), always_xy=True
        )
        path = _compute_corridor_path_wgs84(result, None, transformer)
        assert path == []


# ---------------------------------------------------------------------------
# TestCliViewer
# ---------------------------------------------------------------------------


class TestCliViewer:
    def test_viewer_command_produces_index_html(self, tmp_path, flat_dem_path):
        """salus viewer on a minimal scenario produces index.html."""
        import yaml
        from click.testing import CliRunner

        from salus.cli import main

        scenario = {
            "site_dem_path": str(flat_dem_path),
            "sensor_placements": [
                {
                    "sensor_name": "Anduril WISP",
                    "position_x": 500050.0,
                    "position_y": 6100050.0,
                    "bearing_deg": 0.0,
                }
            ],
        }
        scenario_path = tmp_path / "scenario.yaml"
        scenario_path.write_text(yaml.dump(scenario))

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "viewer",
                str(scenario_path),
                "--output",
                str(tmp_path / "viewer"),
            ],
        )
        assert result.exit_code == 0, result.output
        assert (tmp_path / "viewer" / "index.html").exists()

    def test_viewer_command_output_message(self, tmp_path, flat_dem_path):
        import yaml
        from click.testing import CliRunner

        from salus.cli import main

        scenario = {
            "site_dem_path": str(flat_dem_path),
            "sensor_placements": [],
        }
        scenario_path = tmp_path / "scenario.yaml"
        scenario_path.write_text(yaml.dump(scenario))

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "viewer",
                str(scenario_path),
                "--output",
                str(tmp_path / "viewer"),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Viewer ready" in result.output

    def test_viewer_sanitise_redacted(self, tmp_path, flat_dem_path):
        import yaml
        from click.testing import CliRunner

        from salus.cli import main

        scenario = {
            "site_dem_path": str(flat_dem_path),
            "sensor_placements": [],
        }
        scenario_path = tmp_path / "scenario.yaml"
        scenario_path.write_text(yaml.dump(scenario))

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "viewer",
                str(scenario_path),
                "--output",
                str(tmp_path / "viewer"),
                "--sanitise",
                "redacted",
            ],
        )
        assert result.exit_code == 0, result.output

    def test_viewer_missing_scenario_exits_nonzero(self, tmp_path):
        from click.testing import CliRunner

        from salus.cli import main

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "viewer",
                str(tmp_path / "nonexistent.yaml"),
                "--output",
                str(tmp_path / "viewer"),
            ],
        )
        assert result.exit_code != 0

    def test_viewer_unreadable_boundary_exits_nonzero(self, flat_dem_path, tmp_path):
        """D-483: a scenario referencing a non-existent boundary file must abort,
        not silently fall back to the full-DEM bitmask (which would inflate the
        coverage_pct shown in the packaged viewer)."""
        import yaml
        from click.testing import CliRunner

        from salus.cli import main

        scenario_data = {
            "site_dem_path": str(flat_dem_path),
            "boundary_path": str(tmp_path / "nonexistent_boundary.geojson"),
            "sensor_placements": [
                {
                    "sensor_name": "Anduril WISP",
                    "position_x": 500050.0,
                    "position_y": 6100050.0,
                    "bearing_deg": 0.0,
                }
            ],
        }
        scenario_path = tmp_path / "scenario_bad_boundary.yaml"
        scenario_path.write_text(yaml.dump(scenario_data), encoding="utf-8")
        out_dir = tmp_path / "viewer"

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "viewer",
                str(scenario_path),
                "--output",
                str(out_dir),
            ],
        )
        assert result.exit_code != 0, result.output
        assert "Error loading boundary" in result.output
        assert not (out_dir / "index.html").exists()
