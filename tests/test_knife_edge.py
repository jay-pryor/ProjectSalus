"""Tests for knife-edge diffraction and terrain profile extraction (S4-2)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from salus.engine.rf_propagation import (
    _knife_edge_loss_db,
    compute_knife_edge_loss,
    extract_terrain_profile,
)
from salus.ingest.terrain import load_dem

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _flat_profile(
    total_dist: float,
    n: int,
    ground_height: float,
) -> np.ndarray:
    """Profile with uniform ground height — no obstruction above LOS."""
    distances = np.linspace(0.0, total_dist, n)
    heights = np.full(n, ground_height)
    return np.column_stack([distances, heights])


def _obstacle_profile(
    total_dist: float,
    obstacle_dist: float,
    obstacle_height: float,
    ground_height: float = 50.0,
    n: int = 101,
) -> np.ndarray:
    """Profile with a single obstacle spike at obstacle_dist."""
    distances = np.linspace(0.0, total_dist, n)
    heights = np.full(n, ground_height)
    # Place spike at the nearest sample to obstacle_dist
    idx = int(round(obstacle_dist / total_dist * (n - 1)))
    heights[idx] = obstacle_height
    return np.column_stack([distances, heights])


# ---------------------------------------------------------------------------
# _knife_edge_loss_db
# ---------------------------------------------------------------------------


class TestKnifeEdgeLossDb:
    def test_below_threshold_returns_zero(self):
        """nu <= -0.78: no diffraction loss."""
        assert _knife_edge_loss_db(-0.78) == pytest.approx(0.0, abs=0.01)
        assert _knife_edge_loss_db(-1.0) == 0.0
        assert _knife_edge_loss_db(-5.0) == 0.0

    def test_nu_zero_approx_6db(self):
        """nu = 0 (obstacle exactly on LOS): loss ≈ 6 dB (textbook)."""
        assert _knife_edge_loss_db(0.0) == pytest.approx(6.0, abs=0.1)

    def test_nu_one_approx_13db(self):
        """nu = 1: loss ≈ 13.9 dB (standard reference)."""
        assert _knife_edge_loss_db(1.0) == pytest.approx(13.9, abs=0.1)

    def test_nu_negative_near_threshold(self):
        """Slight positive nu just above threshold — small positive loss."""
        loss = _knife_edge_loss_db(-0.5)
        assert 0.0 < loss < 6.0

    def test_monotonically_increasing(self):
        """Loss increases with nu for nu > -0.78."""
        nus = [-0.5, 0.0, 0.5, 1.0, 1.5, 2.0, 3.0]
        losses = [_knife_edge_loss_db(n) for n in nus]
        assert all(losses[i] < losses[i + 1] for i in range(len(losses) - 1))

    def test_return_type_float(self):
        assert isinstance(_knife_edge_loss_db(1.0), float)

    def test_result_non_negative(self):
        for nu in [-2.0, -0.78, 0.0, 1.0, 5.0]:
            assert _knife_edge_loss_db(nu) >= 0.0

    def test_nan_nu_raises(self):
        """NaN nu must raise ValueError, not propagate silently."""
        with pytest.raises(ValueError, match="nu"):
            _knife_edge_loss_db(float("nan"))

    def test_inf_nu_raises(self):
        """Infinite nu must raise ValueError."""
        with pytest.raises(ValueError, match="nu"):
            _knife_edge_loss_db(float("inf"))


# ---------------------------------------------------------------------------
# compute_knife_edge_loss — textbook reference cases
# ---------------------------------------------------------------------------


class TestComputeKnifeEdgeLoss:
    def test_clear_los_returns_zero(self):
        """Flat terrain well below TX/RX LOS — no diffraction loss."""
        # TX and RX both at 60 m, flat ground at 50 m — 10 m below LOS
        profile = _flat_profile(10_000.0, 101, ground_height=50.0)
        loss = compute_knife_edge_loss(profile, tx_height=60.0, rx_height=60.0, frequency_hz=900e6)
        assert loss == pytest.approx(0.0)

    def test_obstacle_on_los_approx_6db(self):
        """Obstacle exactly on the TX-RX LOS (h=0): loss ≈ 6 dB."""
        # TX=60m, RX=60m, obstacle at midpoint at 60m → h = 0
        profile = _obstacle_profile(
            total_dist=10_000.0,
            obstacle_dist=5_000.0,
            obstacle_height=60.0,
            ground_height=50.0,
        )
        loss = compute_knife_edge_loss(profile, tx_height=60.0, rx_height=60.0, frequency_hz=900e6)
        assert loss == pytest.approx(6.0, abs=0.15)

    def test_textbook_midpoint_obstacle_900mhz(self):
        """Textbook example: 10 km path, obstacle 10 m above LOS at midpoint, 900 MHz."""
        # TX=RX=60m (flat), obstacle=70m at 5km → h=10m above LOS of 60m
        profile = _obstacle_profile(
            total_dist=10_000.0,
            obstacle_dist=5_000.0,
            obstacle_height=70.0,
            ground_height=50.0,
            n=1001,
        )
        loss = compute_knife_edge_loss(profile, tx_height=60.0, rx_height=60.0, frequency_hz=900e6)
        # nu ≈ 0.49 → J ≈ 10.2 dB
        assert loss == pytest.approx(10.2, abs=0.3)

    def test_textbook_midpoint_obstacle_2400mhz(self):
        """Same geometry at 2.4 GHz: higher frequency → higher nu → more loss."""
        profile = _obstacle_profile(
            total_dist=10_000.0,
            obstacle_dist=5_000.0,
            obstacle_height=70.0,
            ground_height=50.0,
            n=1001,
        )
        loss_900 = compute_knife_edge_loss(
            profile, tx_height=60.0, rx_height=60.0, frequency_hz=900e6
        )
        loss_2400 = compute_knife_edge_loss(
            profile, tx_height=60.0, rx_height=60.0, frequency_hz=2.4e9
        )
        assert loss_2400 > loss_900

    def test_dominant_obstruction_selected(self):
        """With two obstacles, the taller one (higher nu) drives the loss."""
        distances = np.linspace(0.0, 10_000.0, 201)
        heights = np.full(201, 50.0)
        heights[50] = 62.0  # small obstacle, ~2 m above LOS
        heights[150] = 70.0  # dominant obstacle, ~10 m above LOS
        profile = np.column_stack([distances, heights])
        loss_both = compute_knife_edge_loss(
            profile, tx_height=60.0, rx_height=60.0, frequency_hz=900e6
        )
        # Loss should match dominant obstacle only (heights[150])
        dominant_only = _obstacle_profile(10_000.0, 7500.0, 70.0, 50.0, n=201)
        loss_dominant = compute_knife_edge_loss(
            dominant_only, tx_height=60.0, rx_height=60.0, frequency_hz=900e6
        )
        assert loss_both == pytest.approx(loss_dominant, abs=0.5)

    def test_loss_is_non_negative(self):
        """Diffraction loss is always >= 0."""
        profile = _obstacle_profile(5_000.0, 2_500.0, 55.0, ground_height=50.0)
        assert compute_knife_edge_loss(profile, 60.0, 60.0, 1e9) >= 0.0

    def test_two_point_profile_returns_zero(self):
        """Only TX and RX, no interior points — no obstruction possible."""
        profile = np.array([[0.0, 50.0], [10_000.0, 50.0]])
        assert compute_knife_edge_loss(profile, 60.0, 60.0, 900e6) == 0.0

    # ------------------------------------------------------------------
    # Guard clauses
    # ------------------------------------------------------------------

    def test_wrong_profile_ndim_raises(self):
        with pytest.raises(ValueError, match="shape"):
            compute_knife_edge_loss(np.array([50.0, 60.0, 50.0]), 60.0, 60.0, 900e6)

    def test_wrong_profile_columns_raises(self):
        with pytest.raises(ValueError, match="shape"):
            compute_knife_edge_loss(np.zeros((10, 3)), 60.0, 60.0, 900e6)

    def test_single_point_profile_raises(self):
        with pytest.raises(ValueError, match="at least 2"):
            compute_knife_edge_loss(np.array([[0.0, 50.0]]), 60.0, 60.0, 900e6)

    def test_zero_path_length_raises(self):
        profile = np.array([[0.0, 50.0], [0.0, 50.0]])
        with pytest.raises(ValueError, match="path length"):
            compute_knife_edge_loss(profile, 60.0, 60.0, 900e6)

    def test_nonfinite_tx_height_raises(self):
        profile = _flat_profile(1_000.0, 5, 50.0)
        with pytest.raises(ValueError, match="tx_height"):
            compute_knife_edge_loss(profile, float("nan"), 60.0, 900e6)

    def test_nonfinite_rx_height_raises(self):
        profile = _flat_profile(1_000.0, 5, 50.0)
        with pytest.raises(ValueError, match="rx_height"):
            compute_knife_edge_loss(profile, 60.0, float("inf"), 900e6)

    def test_invalid_frequency_raises(self):
        profile = _flat_profile(1_000.0, 5, 50.0)
        with pytest.raises(ValueError, match="frequency_hz"):
            compute_knife_edge_loss(profile, 60.0, 60.0, 0.0)

    def test_nan_height_in_profile_raises(self):
        """NaN terrain height (DEM nodata) must be rejected, not silently used."""
        profile = _flat_profile(10_000.0, 11, 50.0)
        profile[5, 1] = float("nan")
        with pytest.raises(ValueError, match="non-finite"):
            compute_knife_edge_loss(profile, 60.0, 60.0, 900e6)

    def test_nonzero_first_distance_raises(self):
        """Profile distances[0] != 0.0 indicates a malformed profile."""
        profile = _flat_profile(10_000.0, 5, 50.0)
        profile[:, 0] += 100.0  # shift all distances — first is no longer 0
        with pytest.raises(ValueError, match="0.0"):
            compute_knife_edge_loss(profile, 60.0, 60.0, 900e6)


# ---------------------------------------------------------------------------
# extract_terrain_profile
# ---------------------------------------------------------------------------


class TestExtractTerrainProfile:
    def test_output_shape(self, flat_dem_path):
        """Output must be (N, 2)."""
        site = load_dem(flat_dem_path)
        min_x, max_x, min_y, max_y = site.extent
        profile = extract_terrain_profile(site, min_x + 10, max_y - 10, max_x - 10, min_y + 10)
        assert profile.ndim == 2
        assert profile.shape[1] == 2

    def test_distance_column_starts_at_zero(self, flat_dem_path):
        """First distance must be 0.0."""
        site = load_dem(flat_dem_path)
        min_x, max_x, min_y, max_y = site.extent
        profile = extract_terrain_profile(site, min_x + 10, max_y - 10, max_x - 10, min_y + 10)
        assert profile[0, 0] == pytest.approx(0.0)

    def test_distance_column_ends_at_path_length(self, flat_dem_path):
        """Last distance must equal the straight-line path length."""
        site = load_dem(flat_dem_path)
        x1, y1 = site.origin_x + 10, site.origin_y - 10
        x2, y2 = site.origin_x + 90, site.origin_y - 90
        expected_dist = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
        profile = extract_terrain_profile(site, x1, y1, x2, y2)
        assert profile[-1, 0] == pytest.approx(expected_dist, rel=1e-6)

    def test_distances_monotonically_increasing(self, flat_dem_path):
        """Distance column must be strictly increasing."""
        site = load_dem(flat_dem_path)
        min_x, max_x, min_y, max_y = site.extent
        profile = extract_terrain_profile(site, min_x + 5, max_y - 5, max_x - 5, min_y + 5)
        diffs = np.diff(profile[:, 0])
        assert (diffs > 0).all()

    def test_flat_dem_uniform_heights(self, flat_dem_path):
        """On a flat DEM all heights should equal the DEM value."""
        site = load_dem(flat_dem_path)
        x1, y1 = site.origin_x + 10, site.origin_y - 10
        x2, y2 = site.origin_x + 80, site.origin_y - 80
        profile = extract_terrain_profile(site, x1, y1, x2, y2, num_samples=20)
        assert np.allclose(profile[:, 1], site.dem[0, 0], atol=0.01)

    def test_num_samples_respected(self, flat_dem_path):
        """num_samples controls the number of rows in the output."""
        site = load_dem(flat_dem_path)
        x1, y1 = site.origin_x + 5, site.origin_y - 5
        x2, y2 = site.origin_x + 95, site.origin_y - 5
        for n in [5, 10, 50]:
            profile = extract_terrain_profile(site, x1, y1, x2, y2, num_samples=n)
            assert profile.shape[0] == n

    def test_identical_endpoints_raises(self, flat_dem_path):
        site = load_dem(flat_dem_path)
        x = site.origin_x + 50
        y = site.origin_y - 50
        with pytest.raises(ValueError, match="identical"):
            extract_terrain_profile(site, x, y, x, y)

    def test_num_samples_less_than_2_raises(self, flat_dem_path):
        site = load_dem(flat_dem_path)
        x1, y1 = site.origin_x + 10, site.origin_y - 10
        x2, y2 = site.origin_x + 90, site.origin_y - 90
        with pytest.raises(ValueError, match="num_samples"):
            extract_terrain_profile(site, x1, y1, x2, y2, num_samples=1)

    def test_profile_integrates_with_knife_edge(self, flat_dem_path):
        """Profile extracted from flat DEM should give 0 dB knife-edge loss."""
        site = load_dem(flat_dem_path)
        x1, y1 = site.origin_x + 10, site.origin_y - 10
        x2, y2 = site.origin_x + 90, site.origin_y - 90
        profile = extract_terrain_profile(site, x1, y1, x2, y2)
        # Antennas 10 m above flat ground — clear LOS
        tx_h = site.dem[0, 0] + 10.0
        rx_h = site.dem[0, 0] + 10.0
        loss = compute_knife_edge_loss(profile, tx_h, rx_h, 900e6)
        assert loss == pytest.approx(0.0)

    def test_nonfinite_x1_raises(self, flat_dem_path):
        """Non-finite start coordinate must be rejected immediately."""
        site = load_dem(flat_dem_path)
        x2, y2 = site.origin_x + 90, site.origin_y - 50
        with pytest.raises(ValueError, match="x1"):
            extract_terrain_profile(site, float("nan"), site.origin_y - 50, x2, y2)

    def test_nonfinite_y2_raises(self, flat_dem_path):
        """Non-finite end coordinate must be rejected immediately."""
        site = load_dem(flat_dem_path)
        x1, y1 = site.origin_x + 10, site.origin_y - 50
        with pytest.raises(ValueError, match="y2"):
            extract_terrain_profile(site, x1, y1, site.origin_x + 90, float("inf"))

    def test_out_of_bounds_coordinates_raises(self, flat_dem_path):
        """Coordinates outside the DEM extent must raise ValueError."""
        site = load_dem(flat_dem_path)
        x1, y1 = site.origin_x + 10, site.origin_y - 10
        # x2 far beyond DEM boundary
        x2 = site.origin_x + 10_000.0
        y2 = site.origin_y - 10
        with pytest.raises(ValueError, match="outside the DEM"):
            extract_terrain_profile(site, x1, y1, x2, y2)
