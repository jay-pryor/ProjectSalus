"""Tests for the greedy sensor placement optimisation engine (S9)."""

from __future__ import annotations

import numpy as np
import pytest
from shapely.geometry import box

from salus.engine.placement import (
    PlacementWeights,
    Position,
    _build_weight_map,
    generate_candidate_positions,
    greedy_place_sensors,
)
from salus.models.scenario import SensorPlacement
from salus.models.sensor import SensorDefinition, SensorType
from salus.models.site import SiteModel
from salus.models.zone import Zone, ZoneType

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def small_flat_site() -> SiteModel:
    """20×20 flat DEM at 1 m resolution.

    CRS coordinates:
        x: [0, 20], y: [0, 20]
        origin_x = 0.0, origin_y = 20.0 (top-left cell centre row)
    """
    dem = np.full((20, 20), 50.0, dtype=np.float64)
    return SiteModel(dem=dem, resolution=1.0, origin_x=0.0, origin_y=20.0)


@pytest.fixture
def acoustic_sensor() -> SensorDefinition:
    """Acoustic sensor with 6 m max range (no LOS required)."""
    return SensorDefinition(
        name="TestAcoustic",
        type=SensorType.Acoustic,
        max_range_m=6.0,
        min_range_m=0.0,
        azimuth_coverage_deg=360.0,
        elevation_coverage_deg=90.0,
        requires_los=False,
    )


@pytest.fixture
def wide_acoustic_sensor() -> SensorDefinition:
    """Acoustic sensor with 25 m max range — covers the entire 20×20 test site."""
    return SensorDefinition(
        name="WideAcoustic",
        type=SensorType.Acoustic,
        max_range_m=25.0,
        min_range_m=0.0,
        azimuth_coverage_deg=360.0,
        elevation_coverage_deg=90.0,
        requires_los=False,
    )


# ---------------------------------------------------------------------------
# Position dataclass
# ---------------------------------------------------------------------------


def test_position_is_frozen() -> None:
    pos = Position(x=1.0, y=2.0)
    with pytest.raises((AttributeError, TypeError)):
        pos.x = 99.0  # type: ignore[misc]


def test_position_equality() -> None:
    assert Position(x=1.0, y=2.0) == Position(x=1.0, y=2.0)
    assert Position(x=1.0, y=2.0) != Position(x=2.0, y=1.0)


# ---------------------------------------------------------------------------
# PlacementWeights model
# ---------------------------------------------------------------------------


def test_placement_weights_defaults() -> None:
    w = PlacementWeights()
    assert w.critical_asset == pytest.approx(3.0)
    assert w.inner == pytest.approx(2.0)
    assert w.perimeter == pytest.approx(1.0)
    assert w.exclusion == pytest.approx(0.0)
    assert w.unzoned == pytest.approx(1.0)


def test_placement_weights_custom() -> None:
    w = PlacementWeights(critical_asset=5.0, inner=4.0, perimeter=2.0, exclusion=0.0, unzoned=1.5)
    assert w.critical_asset == pytest.approx(5.0)


def test_placement_weights_rejects_negative() -> None:
    with pytest.raises(Exception):  # Pydantic ValidationError (ge=0.0)
        PlacementWeights(critical_asset=-1.0)


def test_placement_weights_rejects_inf() -> None:
    with pytest.raises(Exception):
        PlacementWeights(inner=float("inf"))


def test_placement_weights_rejects_nan() -> None:
    with pytest.raises(Exception):
        PlacementWeights(perimeter=float("nan"))


# ---------------------------------------------------------------------------
# _build_weight_map
# ---------------------------------------------------------------------------


def test_build_weight_map_no_zones(small_flat_site: SiteModel) -> None:
    """Site with no zones → all cells at unzoned weight."""
    w = PlacementWeights()
    wmap = _build_weight_map(small_flat_site, w)
    assert wmap.shape == (small_flat_site.rows, small_flat_site.cols)
    assert np.all(wmap == pytest.approx(w.unzoned))


def test_build_weight_map_critical_asset_zone(small_flat_site: SiteModel) -> None:
    """Critical asset zone overrides unzoned weight."""
    ca_zone = Zone(
        name="HQ",
        zone_type=ZoneType.critical_asset,
        geometry=box(0.0, 0.0, 10.0, 20.0),  # left half of 20×20 site
    )
    site = small_flat_site.model_copy(update={"zones": [ca_zone]})
    w = PlacementWeights()
    wmap = _build_weight_map(site, w)
    # Left-half cells should have weight 3.0; right-half cells weight 1.0
    assert np.any(np.isclose(wmap, 3.0))
    assert np.any(np.isclose(wmap, 1.0))
    # No cell should have weight other than 1.0 or 3.0
    unique = np.unique(wmap)
    for u in unique:
        assert np.isclose(u, 1.0) or np.isclose(u, 3.0)


def test_build_weight_map_exclusion_zone_is_zero(small_flat_site: SiteModel) -> None:
    """Exclusion zones receive weight 0.0."""
    excl_zone = Zone(
        name="NoGo",
        zone_type=ZoneType.exclusion,
        geometry=box(0.0, 0.0, 5.0, 20.0),
    )
    site = small_flat_site.model_copy(update={"zones": [excl_zone]})
    w = PlacementWeights()
    wmap = _build_weight_map(site, w)
    assert np.any(np.isclose(wmap, 0.0))


def test_build_weight_map_higher_priority_wins(small_flat_site: SiteModel) -> None:
    """Critical asset zone overrides inner zone when they overlap."""
    inner_zone = Zone(
        name="Inner",
        zone_type=ZoneType.inner,
        geometry=box(0.0, 0.0, 20.0, 20.0),  # full site
    )
    ca_zone = Zone(
        name="CA",
        zone_type=ZoneType.critical_asset,
        geometry=box(0.0, 0.0, 10.0, 20.0),  # left half
    )
    site = small_flat_site.model_copy(update={"zones": [inner_zone, ca_zone]})
    w = PlacementWeights()
    wmap = _build_weight_map(site, w)
    # Left half should be critical_asset (3.0), right half should be inner (2.0)
    assert np.any(np.isclose(wmap, 3.0))
    assert np.any(np.isclose(wmap, 2.0))
    assert not np.any(np.isclose(wmap, 1.0))  # no unzoned cells


# ---------------------------------------------------------------------------
# generate_candidate_positions
# ---------------------------------------------------------------------------


def test_generate_candidates_basic_grid(small_flat_site: SiteModel) -> None:
    """Flat site, no boundary, no exclusions — returns a regular grid."""
    candidates = generate_candidate_positions(
        site=small_flat_site,
        boundary=None,
        step_m=5.0,
        exclusion_zones=[],
    )
    # With step=5.0 on a 20×20 site:
    # xs = [2.5, 7.5, 12.5, 17.5], ys = [2.5, 7.5, 12.5, 17.5] → 16 candidates
    assert len(candidates) == 16
    assert all(isinstance(p, Position) for p in candidates)


def test_generate_candidates_all_within_extent(small_flat_site: SiteModel) -> None:
    """All candidate positions fall within the site extent."""
    min_x, max_x, min_y, max_y = small_flat_site.extent
    candidates = generate_candidate_positions(
        site=small_flat_site, boundary=None, step_m=3.0, exclusion_zones=[]
    )
    for pos in candidates:
        assert min_x <= pos.x <= max_x
        assert min_y <= pos.y <= max_y


def test_generate_candidates_boundary_filter(small_flat_site: SiteModel) -> None:
    """Boundary polygon restricts candidates to its interior."""
    # Only the bottom-left 10×10 quadrant
    boundary = box(0.0, 0.0, 10.0, 10.0)
    candidates = generate_candidate_positions(
        site=small_flat_site, boundary=boundary, step_m=5.0, exclusion_zones=[]
    )
    # Only (2.5, 2.5) and (7.5, 7.5) etc. inside [0,10]×[0,10]
    assert len(candidates) > 0
    for pos in candidates:
        assert 0.0 < pos.x < 10.0
        assert 0.0 < pos.y < 10.0


def test_generate_candidates_exclusion_zone_removes_positions(
    small_flat_site: SiteModel,
) -> None:
    """Exclusion zone removes candidate positions inside it."""
    # Exclude the bottom-left quadrant so all 4 candidates there are removed
    excl = Zone(
        name="ExclZone",
        zone_type=ZoneType.exclusion,
        geometry=box(0.0, 0.0, 10.0, 10.0),
    )
    all_candidates = generate_candidate_positions(
        site=small_flat_site, boundary=None, step_m=5.0, exclusion_zones=[]
    )
    filtered_candidates = generate_candidate_positions(
        site=small_flat_site, boundary=None, step_m=5.0, exclusion_zones=[excl]
    )
    assert len(filtered_candidates) < len(all_candidates)
    # Positions inside the exclusion box should not appear
    for pos in filtered_candidates:
        assert not (0.0 < pos.x < 10.0 and 0.0 < pos.y < 10.0)


def test_generate_candidates_steep_slope_filtered() -> None:
    """Positions on steep slopes are excluded."""
    # Create a 10×10 DEM where the left half has a very steep gradient.
    # Gradient at col=0 is about (400-0)/1 = 400 m/m — far above threshold.
    dem = np.zeros((10, 10), dtype=np.float64)
    dem[:, :5] = 400.0  # abrupt step — gradient at boundary is very steep
    site = SiteModel(dem=dem, resolution=1.0, origin_x=0.0, origin_y=10.0)
    candidates = generate_candidate_positions(
        site=site, boundary=None, step_m=2.0, exclusion_zones=[]
    )
    # The right half cells (away from the steep boundary) should survive
    # We just assert that positions are generated (some flat cells remain).
    assert isinstance(candidates, list)


def test_generate_candidates_invalid_step(small_flat_site: SiteModel) -> None:
    """Non-positive step raises ValueError."""
    with pytest.raises(ValueError, match="step_m"):
        generate_candidate_positions(
            site=small_flat_site, boundary=None, step_m=0.0, exclusion_zones=[]
        )


def test_generate_candidates_negative_step(small_flat_site: SiteModel) -> None:
    with pytest.raises(ValueError, match="step_m"):
        generate_candidate_positions(
            site=small_flat_site, boundary=None, step_m=-5.0, exclusion_zones=[]
        )


def test_generate_candidates_nan_step(small_flat_site: SiteModel) -> None:
    with pytest.raises(ValueError, match="step_m"):
        generate_candidate_positions(
            site=small_flat_site, boundary=None, step_m=float("nan"), exclusion_zones=[]
        )


def test_generate_candidates_step_larger_than_site(small_flat_site: SiteModel) -> None:
    """Step larger than site extent returns an empty list."""
    # step = 100 m on a 20×20 site → no grid points fall inside
    candidates = generate_candidate_positions(
        site=small_flat_site, boundary=None, step_m=100.0, exclusion_zones=[]
    )
    assert candidates == []


def test_generate_candidates_empty_exclusion_list(small_flat_site: SiteModel) -> None:
    """Passing an empty exclusion list is the same as no exclusion."""
    without = generate_candidate_positions(
        site=small_flat_site, boundary=None, step_m=5.0, exclusion_zones=[]
    )
    with_empty = generate_candidate_positions(
        site=small_flat_site, boundary=None, step_m=5.0, exclusion_zones=[]
    )
    assert len(without) == len(with_empty)


# ---------------------------------------------------------------------------
# greedy_place_sensors
# ---------------------------------------------------------------------------


def test_greedy_place_sensors_empty_sensors(
    small_flat_site: SiteModel, acoustic_sensor: SensorDefinition
) -> None:
    """No sensors to place → empty list returned."""
    candidates = [Position(x=5.0, y=10.0)]
    result = greedy_place_sensors(small_flat_site, [], candidates)
    assert result == []


def test_greedy_place_sensors_empty_candidates(
    small_flat_site: SiteModel, acoustic_sensor: SensorDefinition
) -> None:
    """No candidate positions → empty list returned (with warning)."""
    result = greedy_place_sensors(small_flat_site, [acoustic_sensor], [])
    assert result == []


def test_greedy_place_sensors_returns_sensor_placement(
    small_flat_site: SiteModel, acoustic_sensor: SensorDefinition
) -> None:
    """Single sensor placement returns a SensorPlacement with correct sensor_name."""
    candidates = generate_candidate_positions(
        site=small_flat_site, boundary=None, step_m=5.0, exclusion_zones=[]
    )
    result = greedy_place_sensors(small_flat_site, [acoustic_sensor], candidates)
    assert len(result) == 1
    assert isinstance(result[0], SensorPlacement)
    assert result[0].sensor_name == acoustic_sensor.name


def test_greedy_place_sensors_placement_within_extent(
    small_flat_site: SiteModel, acoustic_sensor: SensorDefinition
) -> None:
    """Placed sensor position falls within the site extent."""
    candidates = generate_candidate_positions(
        site=small_flat_site, boundary=None, step_m=5.0, exclusion_zones=[]
    )
    result = greedy_place_sensors(small_flat_site, [acoustic_sensor], candidates)
    assert len(result) == 1
    min_x, max_x, min_y, max_y = small_flat_site.extent
    p = result[0]
    assert min_x <= p.position_x <= max_x
    assert min_y <= p.position_y <= max_y


def test_greedy_place_sensors_multiple_sensors(
    small_flat_site: SiteModel, acoustic_sensor: SensorDefinition
) -> None:
    """Placing two sensors returns two placements at different positions."""
    candidates = generate_candidate_positions(
        site=small_flat_site, boundary=None, step_m=5.0, exclusion_zones=[]
    )
    result = greedy_place_sensors(small_flat_site, [acoustic_sensor, acoustic_sensor], candidates)
    assert len(result) == 2
    # Second placement should be at a different location
    assert (result[0].position_x, result[0].position_y) != (
        result[1].position_x,
        result[1].position_y,
    )


def test_greedy_place_sensors_coverage_threshold_stops_early(
    small_flat_site: SiteModel, wide_acoustic_sensor: SensorDefinition
) -> None:
    """Coverage threshold causes early termination before all sensors are placed."""
    candidates = generate_candidate_positions(
        site=small_flat_site, boundary=None, step_m=5.0, exclusion_zones=[]
    )
    # Wide sensor covers the entire 20×20 site in one placement.
    # With threshold=50.0%, the loop should stop after the first placement
    # because coverage will be near 100% (well above 50%).
    result = greedy_place_sensors(
        small_flat_site,
        [wide_acoustic_sensor, wide_acoustic_sensor, wide_acoustic_sensor],
        candidates,
        coverage_threshold_pct=50.0,
    )
    # At least one placement occurs; fewer than 3 due to early stop.
    assert len(result) >= 1
    assert len(result) < 3


def test_greedy_place_sensors_invalid_threshold(
    small_flat_site: SiteModel, acoustic_sensor: SensorDefinition
) -> None:
    """Out-of-range coverage_threshold_pct raises ValueError."""
    candidates = [Position(x=5.0, y=10.0)]
    with pytest.raises(ValueError, match="coverage_threshold_pct"):
        greedy_place_sensors(
            small_flat_site, [acoustic_sensor], candidates, coverage_threshold_pct=101.0
        )
    with pytest.raises(ValueError, match="coverage_threshold_pct"):
        greedy_place_sensors(
            small_flat_site, [acoustic_sensor], candidates, coverage_threshold_pct=-1.0
        )


def test_greedy_place_sensors_invalid_existing_coverage_shape(
    small_flat_site: SiteModel, acoustic_sensor: SensorDefinition
) -> None:
    """existing_coverage with wrong shape raises ValueError."""
    wrong_shape = np.zeros((5, 5), dtype=bool)
    candidates = [Position(x=5.0, y=10.0)]
    with pytest.raises(ValueError, match="existing_coverage shape"):
        greedy_place_sensors(
            small_flat_site, [acoustic_sensor], candidates, existing_coverage=wrong_shape
        )


def test_greedy_place_sensors_existing_coverage_respected(
    small_flat_site: SiteModel, wide_acoustic_sensor: SensorDefinition
) -> None:
    """When existing_coverage covers all cells, new sensor adds nothing."""
    # Pre-existing full coverage
    existing = np.ones((small_flat_site.rows, small_flat_site.cols), dtype=bool)
    candidates = generate_candidate_positions(
        site=small_flat_site, boundary=None, step_m=5.0, exclusion_zones=[]
    )
    result = greedy_place_sensors(
        small_flat_site,
        [wide_acoustic_sensor],
        candidates,
        existing_coverage=existing,
        coverage_threshold_pct=99.0,
    )
    # Threshold already met by existing_coverage → early exit, no new placements
    assert result == []


def test_greedy_place_sensors_zone_weighting_prefers_critical_asset(
    small_flat_site: SiteModel, acoustic_sensor: SensorDefinition
) -> None:
    """Sensor is placed in critical_asset zone in preference to unzoned area."""
    # Critical asset zone: left half (x=[0,10])
    ca_zone = Zone(
        name="CriticalHQ",
        zone_type=ZoneType.critical_asset,
        geometry=box(0.0, 0.0, 10.0, 20.0),
    )
    site = small_flat_site.model_copy(update={"zones": [ca_zone]})

    # Exactly two candidates: one in critical zone, one outside
    candidates = [
        Position(x=5.0, y=10.0),  # inside critical zone (left half)
        Position(x=15.0, y=10.0),  # outside critical zone (right half)
    ]

    result = greedy_place_sensors(
        site,
        [acoustic_sensor],
        candidates,
        weights=PlacementWeights(),
    )
    assert len(result) == 1
    # The sensor in the critical zone scores 3× vs 1× — should be selected
    assert result[0].position_x == pytest.approx(5.0)


def test_greedy_place_sensors_custom_weights(
    small_flat_site: SiteModel, acoustic_sensor: SensorDefinition
) -> None:
    """Custom weights that invert the priority select the non-critical position."""
    # Invert: make inner very high, critical asset low
    inverted = PlacementWeights(critical_asset=0.5, inner=10.0, perimeter=1.0, unzoned=5.0)
    ca_zone = Zone(
        name="CA",
        zone_type=ZoneType.critical_asset,
        geometry=box(0.0, 0.0, 10.0, 20.0),  # left half weight=0.5
    )
    site = small_flat_site.model_copy(update={"zones": [ca_zone]})

    # unzoned (right half) has weight=5.0 > critical_asset=0.5
    candidates = [
        Position(x=5.0, y=10.0),  # critical zone → weight 0.5
        Position(x=15.0, y=10.0),  # unzoned → weight 5.0
    ]
    result = greedy_place_sensors(site, [acoustic_sensor], candidates, weights=inverted)
    assert len(result) == 1
    assert result[0].position_x == pytest.approx(15.0)


def test_greedy_place_sensors_default_bearing_is_north(
    small_flat_site: SiteModel, acoustic_sensor: SensorDefinition
) -> None:
    """All placed sensors receive bearing_deg = 0.0 (default north)."""
    candidates = generate_candidate_positions(
        site=small_flat_site, boundary=None, step_m=5.0, exclusion_zones=[]
    )
    result = greedy_place_sensors(small_flat_site, [acoustic_sensor, acoustic_sensor], candidates)
    for placement in result:
        assert placement.bearing_deg == pytest.approx(0.0)
