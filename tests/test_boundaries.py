"""Tests for load_boundary and load_zones."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from shapely.geometry import Polygon

from salus.ingest.boundaries import load_boundary, load_zones
from salus.models.zone import ZoneType

# ---------------------------------------------------------------------------
# GeoJSON fixture helpers
# ---------------------------------------------------------------------------

_SITE_EPSG = 28354  # GDA94 / MGA Zone 54 — matches synthetic_site.tif


def _square_coords(x0: float, y0: float, size: float) -> list[list[list[float]]]:
    """GeoJSON coordinate ring for a square polygon."""
    return [
        [
            [x0, y0],
            [x0 + size, y0],
            [x0 + size, y0 + size],
            [x0, y0 + size],
            [x0, y0],
        ]
    ]


def _geojson_feature(coords: list, properties: dict | None = None) -> dict:
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": coords},
        "properties": properties or {},
    }


def _feature_collection(features: list, epsg: int | None = None) -> dict:
    fc: dict = {"type": "FeatureCollection", "features": features}
    if epsg is not None:
        fc["crs"] = {
            "type": "name",
            "properties": {"name": f"urn:ogc:def:crs:EPSG::{epsg}"},
        }
    return fc


def _write_json(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def boundary_file(tmp_path: Path) -> Path:
    """Single square boundary polygon in EPSG:28354."""
    coords = _square_coords(500000.0, 6100000.0, 500.0)
    data = _feature_collection([_geojson_feature(coords)], epsg=_SITE_EPSG)
    return _write_json(tmp_path / "boundary.geojson", data)


@pytest.fixture
def boundary_file_no_crs(tmp_path: Path) -> Path:
    """Boundary polygon with no CRS member (defaults to WGS84)."""
    # Use WGS84 coordinates for a valid no-CRS boundary
    coords = _square_coords(149.0, -35.0, 0.01)
    data = _feature_collection([_geojson_feature(coords)])
    return _write_json(tmp_path / "boundary_no_crs.geojson", data)


@pytest.fixture
def multi_feature_boundary_file(tmp_path: Path) -> Path:
    """Two polygon features in the same file — union should give one polygon."""
    coords1 = _square_coords(500000.0, 6100000.0, 200.0)
    coords2 = _square_coords(500200.0, 6100000.0, 200.0)
    data = _feature_collection(
        [_geojson_feature(coords1), _geojson_feature(coords2)], epsg=_SITE_EPSG
    )
    return _write_json(tmp_path / "multi_boundary.geojson", data)


@pytest.fixture
def zones_file(tmp_path: Path) -> Path:
    """Three-zone FeatureCollection in EPSG:28354."""
    features = [
        _geojson_feature(
            _square_coords(500000.0, 6100000.0, 500.0),
            {"name": "Outer Perimeter", "type": "perimeter"},
        ),
        _geojson_feature(
            _square_coords(500100.0, 6100100.0, 200.0),
            {"name": "Command Post", "type": "critical_asset"},
        ),
        _geojson_feature(
            _square_coords(500050.0, 6100050.0, 50.0),
            {"name": "No-Fly Buffer", "type": "exclusion"},
        ),
    ]
    data = _feature_collection(features, epsg=_SITE_EPSG)
    return _write_json(tmp_path / "zones.geojson", data)


# ---------------------------------------------------------------------------
# TestLoadBoundary
# ---------------------------------------------------------------------------


class TestLoadBoundary:
    def test_returns_polygon(self, boundary_file: Path) -> None:
        """load_boundary must return a Shapely Polygon."""
        result = load_boundary(boundary_file, site_epsg=_SITE_EPSG)
        assert isinstance(result, Polygon)

    def test_correct_area(self, boundary_file: Path) -> None:
        """Returned polygon area must match the 500×500 m square."""
        result = load_boundary(boundary_file, site_epsg=_SITE_EPSG)
        assert result.area == pytest.approx(500.0 * 500.0)

    def test_accepts_path_object(self, boundary_file: Path) -> None:
        """load_boundary must accept a Path object."""
        result = load_boundary(boundary_file)
        assert isinstance(result, Polygon)

    def test_accepts_string_path(self, boundary_file: Path) -> None:
        """load_boundary must accept a string path."""
        result = load_boundary(str(boundary_file))
        assert isinstance(result, Polygon)

    def test_no_crs_validation_when_site_epsg_none(self, boundary_file_no_crs: Path) -> None:
        """When site_epsg is None, CRS validation must be skipped."""
        result = load_boundary(boundary_file_no_crs, site_epsg=None)
        assert isinstance(result, Polygon)

    def test_no_crs_file_with_matching_site_epsg_4326(self, boundary_file_no_crs: Path) -> None:
        """A file with no CRS member must pass validation when site_epsg=4326."""
        result = load_boundary(boundary_file_no_crs, site_epsg=4326)
        assert isinstance(result, Polygon)

    def test_crs_mismatch_reprojects_with_warning(self, boundary_file: Path) -> None:
        """A CRS mismatch must reproject the boundary and emit a UserWarning."""
        with pytest.warns(UserWarning, match="eprojecting"):
            result = load_boundary(boundary_file, site_epsg=4326)
        assert isinstance(result, Polygon)
        assert result.area > 0

    def test_no_crs_file_mismatched_site_epsg_reprojects(self, boundary_file_no_crs: Path) -> None:
        """A no-CRS file (assumed WGS84) must reproject when site_epsg != 4326."""
        with pytest.warns(UserWarning, match="eprojecting"):
            result = load_boundary(boundary_file_no_crs, site_epsg=_SITE_EPSG)
        assert isinstance(result, Polygon)
        assert result.area > 0

    def test_unparseable_crs_member_raises(self, tmp_path: Path) -> None:
        """A GeoJSON with a 'crs' member that cannot be parsed must raise ValueError."""
        coords = _square_coords(500000.0, 6100000.0, 500.0)
        data = _feature_collection([_geojson_feature(coords)])
        data["crs"] = {"type": "name", "properties": {"name": "EPSG:not-a-real-crs"}}
        path = _write_json(tmp_path / "bad_crs.geojson", data)
        with pytest.raises(ValueError, match="[Cc][Rr][Ss]"):
            load_boundary(path, site_epsg=_SITE_EPSG)

    def test_multi_feature_unioned(self, multi_feature_boundary_file: Path) -> None:
        """Multiple polygon features must be unioned into a single Polygon."""
        result = load_boundary(multi_feature_boundary_file, site_epsg=_SITE_EPSG)
        assert isinstance(result, Polygon)
        # Two 200×200 squares side by side = 400×200 = 80000 m²
        assert result.area == pytest.approx(200.0 * 400.0)

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        """A missing file must raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_boundary(tmp_path / "missing.geojson")

    def test_invalid_json_raises(self, tmp_path: Path) -> None:
        """Invalid JSON must raise ValueError."""
        bad = tmp_path / "bad.geojson"
        bad.write_text("not json", encoding="utf-8")
        with pytest.raises(ValueError, match="Invalid GeoJSON"):
            load_boundary(bad)

    def test_no_polygons_raises(self, tmp_path: Path) -> None:
        """A GeoJSON with no polygon geometries must raise ValueError."""
        data = _feature_collection([])
        path = _write_json(tmp_path / "empty.geojson", data)
        with pytest.raises(ValueError, match="No polygon"):
            load_boundary(path)

    def test_bare_polygon_geometry_accepted(self, tmp_path: Path) -> None:
        """A bare GeoJSON Polygon geometry (no Feature wrapper) must be accepted."""
        data = {
            "type": "Polygon",
            "coordinates": _square_coords(500000.0, 6100000.0, 100.0),
        }
        path = _write_json(tmp_path / "bare_polygon.geojson", data)
        result = load_boundary(path)
        assert isinstance(result, Polygon)

    def test_unsupported_geojson_type_raises(self, tmp_path: Path) -> None:
        """An unsupported GeoJSON type must raise ValueError."""
        data = {"type": "GeometryCollection", "geometries": []}
        path = _write_json(tmp_path / "gc.geojson", data)
        with pytest.raises(ValueError):
            load_boundary(path)


# ---------------------------------------------------------------------------
# TestLoadZones
# ---------------------------------------------------------------------------


class TestLoadZones:
    def test_returns_correct_count(self, zones_file: Path) -> None:
        """load_zones must return one Zone per feature."""
        zones = load_zones(zones_file, site_epsg=_SITE_EPSG)
        assert len(zones) == 3

    def test_zone_names_preserved(self, zones_file: Path) -> None:
        """Zone names must match the GeoJSON properties."""
        zones = load_zones(zones_file, site_epsg=_SITE_EPSG)
        names = [z.name for z in zones]
        assert "Outer Perimeter" in names
        assert "Command Post" in names
        assert "No-Fly Buffer" in names

    def test_zone_types_correct(self, zones_file: Path) -> None:
        """Zone types must match the GeoJSON 'type' property."""
        zones = load_zones(zones_file, site_epsg=_SITE_EPSG)
        type_map = {z.name: z.zone_type for z in zones}
        assert type_map["Outer Perimeter"] is ZoneType.perimeter
        assert type_map["Command Post"] is ZoneType.critical_asset
        assert type_map["No-Fly Buffer"] is ZoneType.exclusion

    def test_geometries_are_polygons(self, zones_file: Path) -> None:
        """Each Zone geometry must be a Shapely Polygon."""
        zones = load_zones(zones_file, site_epsg=_SITE_EPSG)
        for z in zones:
            assert isinstance(z.geometry, Polygon)

    def test_crs_mismatch_reprojects_with_warning(self, zones_file: Path) -> None:
        """A CRS mismatch must reproject zone geometries and emit a UserWarning."""
        with pytest.warns(UserWarning, match="eprojecting"):
            zones = load_zones(zones_file, site_epsg=4326)
        assert len(zones) == 3
        for z in zones:
            assert isinstance(z.geometry, Polygon)

    def test_unparseable_crs_member_raises(self, tmp_path: Path) -> None:
        """A zones GeoJSON with an unparseable 'crs' member must raise ValueError."""
        features = [
            _geojson_feature(
                _square_coords(500000.0, 6100000.0, 100.0),
                {"name": "Zone A", "type": "perimeter"},
            )
        ]
        data = _feature_collection(features)
        data["crs"] = {"type": "name", "properties": {"name": "EPSG:not-a-real-crs"}}
        path = _write_json(tmp_path / "bad_crs_zones.geojson", data)
        with pytest.raises(ValueError, match="[Cc][Rr][Ss]"):
            load_zones(path, site_epsg=_SITE_EPSG)

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        """A missing file must raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_zones(tmp_path / "missing.geojson")

    def test_not_feature_collection_raises(self, tmp_path: Path) -> None:
        """A GeoJSON that is not a FeatureCollection must raise ValueError."""
        coords = _square_coords(500000.0, 6100000.0, 100.0)
        data = _geojson_feature(coords, {"name": "x", "type": "perimeter"})
        path = _write_json(tmp_path / "not_fc.geojson", data)
        with pytest.raises(ValueError, match="FeatureCollection"):
            load_zones(path)

    def test_empty_features_raises(self, tmp_path: Path) -> None:
        """An empty FeatureCollection must raise ValueError."""
        data = _feature_collection([])
        path = _write_json(tmp_path / "empty.geojson", data)
        with pytest.raises(ValueError, match="No features"):
            load_zones(path)

    def test_missing_name_property_raises(self, tmp_path: Path) -> None:
        """A feature missing the 'name' property must raise ValueError."""
        data = _feature_collection(
            [
                _geojson_feature(
                    _square_coords(500000.0, 6100000.0, 100.0),
                    {"type": "perimeter"},
                )
            ]
        )
        path = _write_json(tmp_path / "no_name.geojson", data)
        with pytest.raises(ValueError, match="name"):
            load_zones(path)

    def test_missing_type_property_raises(self, tmp_path: Path) -> None:
        """A feature missing the 'type' property must raise ValueError."""
        data = _feature_collection(
            [
                _geojson_feature(
                    _square_coords(500000.0, 6100000.0, 100.0),
                    {"name": "Zone A"},
                )
            ]
        )
        path = _write_json(tmp_path / "no_type.geojson", data)
        with pytest.raises(ValueError, match="type"):
            load_zones(path)

    def test_invalid_zone_type_raises(self, tmp_path: Path) -> None:
        """An unrecognised zone type string must raise ValueError."""
        data = _feature_collection(
            [
                _geojson_feature(
                    _square_coords(500000.0, 6100000.0, 100.0),
                    {"name": "Zone A", "type": "launch_pad"},
                )
            ]
        )
        path = _write_json(tmp_path / "bad_type.geojson", data)
        with pytest.raises(ValueError):
            load_zones(path)

    def test_null_geometry_raises(self, tmp_path: Path) -> None:
        """A feature with null geometry must raise ValueError."""
        data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": None,
                    "properties": {"name": "Zone A", "type": "perimeter"},
                }
            ],
        }
        path = _write_json(tmp_path / "null_geom.geojson", data)
        with pytest.raises(ValueError, match="null geometry"):
            load_zones(path)

    def test_accepts_string_path(self, zones_file: Path) -> None:
        """load_zones must accept a string path."""
        zones = load_zones(str(zones_file), site_epsg=_SITE_EPSG)
        assert len(zones) == 3
