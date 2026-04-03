"""Tests for scenario Pydantic models (models/scenario.py)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from salus.models.scenario import EffectorPlacement, ScenarioConfig, SensorPlacement


class TestSensorPlacement:
    def test_valid_minimal(self):
        """Minimal valid SensorPlacement with required fields only."""
        sp = SensorPlacement(
            sensor_name="DroneShield RfOne Mk2",
            position_x=500050.0,
            position_y=6100050.0,
            bearing_deg=0.0,
        )
        assert sp.sensor_name == "DroneShield RfOne Mk2"
        assert sp.position_x == pytest.approx(500050.0)
        assert sp.position_y == pytest.approx(6100050.0)
        assert sp.bearing_deg == pytest.approx(0.0)
        assert sp.height_override_m is None

    def test_valid_with_height_override(self):
        """SensorPlacement with optional height_override_m set."""
        sp = SensorPlacement(
            sensor_name="Anduril WISP",
            position_x=0.0,
            position_y=0.0,
            bearing_deg=180.0,
            height_override_m=5.0,
        )
        assert sp.height_override_m == pytest.approx(5.0)

    def test_bearing_zero_valid(self):
        """bearing_deg=0.0 (north) is valid."""
        sp = SensorPlacement(sensor_name="S", position_x=0.0, position_y=0.0, bearing_deg=0.0)
        assert sp.bearing_deg == pytest.approx(0.0)

    def test_bearing_just_below_360_valid(self):
        """bearing_deg=359.9 is valid (just below exclusive upper bound)."""
        sp = SensorPlacement(sensor_name="S", position_x=0.0, position_y=0.0, bearing_deg=359.9)
        assert sp.bearing_deg == pytest.approx(359.9)

    def test_bearing_360_raises(self):
        """bearing_deg=360.0 is invalid — must be in [0, 360)."""
        with pytest.raises(ValidationError, match="bearing_deg"):
            SensorPlacement(sensor_name="S", position_x=0.0, position_y=0.0, bearing_deg=360.0)

    def test_bearing_negative_raises(self):
        """Negative bearing_deg is invalid."""
        with pytest.raises(ValidationError, match="bearing_deg"):
            SensorPlacement(sensor_name="S", position_x=0.0, position_y=0.0, bearing_deg=-1.0)

    def test_empty_sensor_name_raises(self):
        """Empty sensor_name is invalid."""
        with pytest.raises(ValidationError, match="sensor_name"):
            SensorPlacement(sensor_name="", position_x=0.0, position_y=0.0, bearing_deg=0.0)

    def test_whitespace_only_sensor_name_raises(self):
        """Whitespace-only sensor_name is invalid."""
        with pytest.raises(ValidationError, match="sensor_name"):
            SensorPlacement(sensor_name="   ", position_x=0.0, position_y=0.0, bearing_deg=0.0)

    def test_height_override_zero_valid(self):
        """height_override_m=0.0 is valid (ground level)."""
        sp = SensorPlacement(
            sensor_name="S",
            position_x=0.0,
            position_y=0.0,
            bearing_deg=0.0,
            height_override_m=0.0,
        )
        assert sp.height_override_m == pytest.approx(0.0)

    def test_height_override_negative_raises(self):
        """Negative height_override_m is invalid."""
        with pytest.raises(ValidationError, match="height_override_m"):
            SensorPlacement(
                sensor_name="S",
                position_x=0.0,
                position_y=0.0,
                bearing_deg=0.0,
                height_override_m=-1.0,
            )

    def test_height_override_none_valid(self):
        """height_override_m=None is valid (use sensor default)."""
        sp = SensorPlacement(
            sensor_name="S",
            position_x=0.0,
            position_y=0.0,
            bearing_deg=0.0,
            height_override_m=None,
        )
        assert sp.height_override_m is None

    def test_position_can_be_negative(self):
        """position_x and position_y can be any float including negative."""
        sp = SensorPlacement(
            sensor_name="S", position_x=-1000.0, position_y=-2000.0, bearing_deg=45.0
        )
        assert sp.position_x == pytest.approx(-1000.0)
        assert sp.position_y == pytest.approx(-2000.0)

    def test_bearing_90_east_valid(self):
        """bearing_deg=90.0 (east) is valid and stored exactly."""
        sp = SensorPlacement(sensor_name="S", position_x=0.0, position_y=0.0, bearing_deg=90.0)
        assert sp.bearing_deg == pytest.approx(90.0)


class TestEffectorPlacement:
    def test_valid_minimal(self):
        """Minimal valid EffectorPlacement."""
        ep = EffectorPlacement(
            effector_name="EOS Slinger",
            position_x=500060.0,
            position_y=6100060.0,
            bearing_deg=90.0,
        )
        assert ep.effector_name == "EOS Slinger"
        assert ep.bearing_deg == pytest.approx(90.0)
        assert ep.height_override_m is None

    def test_empty_effector_name_raises(self):
        """Empty effector_name is invalid."""
        with pytest.raises(ValidationError, match="effector_name"):
            EffectorPlacement(effector_name="", position_x=0.0, position_y=0.0, bearing_deg=0.0)

    def test_bearing_360_raises(self):
        """bearing_deg=360.0 is invalid."""
        with pytest.raises(ValidationError, match="bearing_deg"):
            EffectorPlacement(effector_name="E", position_x=0.0, position_y=0.0, bearing_deg=360.0)

    def test_bearing_negative_raises(self):
        """Negative bearing_deg is invalid."""
        with pytest.raises(ValidationError, match="bearing_deg"):
            EffectorPlacement(effector_name="E", position_x=0.0, position_y=0.0, bearing_deg=-5.0)

    def test_negative_height_override_raises(self):
        """Negative height_override_m is invalid."""
        with pytest.raises(ValidationError, match="height_override_m"):
            EffectorPlacement(
                effector_name="E",
                position_x=0.0,
                position_y=0.0,
                bearing_deg=0.0,
                height_override_m=-1.0,
            )

    def test_height_override_zero_valid(self):
        """height_override_m=0.0 is valid."""
        ep = EffectorPlacement(
            effector_name="E",
            position_x=0.0,
            position_y=0.0,
            bearing_deg=0.0,
            height_override_m=0.0,
        )
        assert ep.height_override_m == pytest.approx(0.0)


class TestScenarioConfig:
    def test_valid_minimal(self, tmp_path):
        """ScenarioConfig with only site_dem_path is valid."""
        dem = tmp_path / "site.tif"
        sc = ScenarioConfig(site_dem_path=dem)
        assert sc.site_dem_path == dem
        assert sc.site_dsm_path is None
        assert sc.boundary_path is None
        assert sc.sensor_placements == []
        assert sc.effector_placements == []
        assert sc.threat_profiles == []

    def test_valid_full(self, tmp_path):
        """ScenarioConfig accepts all fields."""
        dem = tmp_path / "dem.tif"
        dsm = tmp_path / "dsm.tif"
        boundary = tmp_path / "boundary.geojson"
        sc = ScenarioConfig(
            site_dem_path=dem,
            site_dsm_path=dsm,
            boundary_path=boundary,
            sensor_placements=[
                SensorPlacement(
                    sensor_name="DroneShield RfOne Mk2",
                    position_x=500050.0,
                    position_y=6100050.0,
                    bearing_deg=0.0,
                )
            ],
            effector_placements=[
                EffectorPlacement(
                    effector_name="EOS Slinger",
                    position_x=500060.0,
                    position_y=6100060.0,
                    bearing_deg=90.0,
                )
            ],
            threat_profiles=["DJI Phantom 4"],
        )
        assert len(sc.sensor_placements) == 1
        assert len(sc.effector_placements) == 1
        assert sc.threat_profiles == ["DJI Phantom 4"]

    def test_missing_site_dem_path_raises(self):
        """site_dem_path is required."""
        with pytest.raises(ValidationError):
            ScenarioConfig()  # type: ignore[call-arg]

    def test_empty_site_dem_path_raises(self):
        """Empty string for site_dem_path is invalid."""
        with pytest.raises(ValidationError, match="site_dem_path"):
            ScenarioConfig(site_dem_path="")

    def test_site_dem_path_string_coerced_to_path(self, tmp_path):
        """A string value for site_dem_path is coerced to Path."""
        sc = ScenarioConfig(site_dem_path=str(tmp_path / "dem.tif"))
        assert isinstance(sc.site_dem_path, Path)

    def test_sensor_placements_default_empty_list(self, tmp_path):
        """sensor_placements defaults to an empty list, not a shared mutable."""
        sc1 = ScenarioConfig(site_dem_path=tmp_path / "a.tif")
        sc2 = ScenarioConfig(site_dem_path=tmp_path / "b.tif")
        assert sc1.sensor_placements is not sc2.sensor_placements

    def test_invalid_sensor_placement_in_list_raises(self, tmp_path):
        """An invalid SensorPlacement dict inside sensor_placements raises ValidationError."""
        with pytest.raises(ValidationError):
            ScenarioConfig(
                site_dem_path=tmp_path / "dem.tif",
                sensor_placements=[
                    {
                        "sensor_name": "",
                        "position_x": 0,
                        "position_y": 0,
                        "bearing_deg": 0,
                    }
                ],
            )

    def test_non_path_site_dem_path_raises(self, tmp_path):
        """Passing an integer for site_dem_path raises ValidationError."""
        with pytest.raises(ValidationError, match="site_dem_path"):
            ScenarioConfig(site_dem_path=42)  # type: ignore[arg-type]

    def test_empty_threat_profile_entry_raises(self, tmp_path):
        """An empty string in threat_profiles raises ValidationError."""
        with pytest.raises(ValidationError, match="threat_profiles"):
            ScenarioConfig(
                site_dem_path=tmp_path / "dem.tif",
                threat_profiles=["DJI Phantom 4", ""],
            )

    def test_whitespace_threat_profile_entry_raises(self, tmp_path):
        """A whitespace-only string in threat_profiles raises ValidationError."""
        with pytest.raises(ValidationError, match="threat_profiles"):
            ScenarioConfig(
                site_dem_path=tmp_path / "dem.tif",
                threat_profiles=["  "],
            )

    def test_protected_point_default_none(self, tmp_path):
        """protected_point defaults to None."""
        sc = ScenarioConfig(site_dem_path=tmp_path / "dem.tif")
        assert sc.protected_point is None

    def test_protected_point_valid(self, tmp_path):
        """protected_point accepts a finite (x, y) tuple."""
        sc = ScenarioConfig(
            site_dem_path=tmp_path / "dem.tif",
            protected_point=(500050.0, 6100050.0),
        )
        assert sc.protected_point == (500050.0, 6100050.0)

    def test_protected_point_nan_raises(self, tmp_path):
        """NaN coordinates in protected_point raise ValidationError."""
        import math

        with pytest.raises(ValidationError, match="finite"):
            ScenarioConfig(
                site_dem_path=tmp_path / "dem.tif",
                protected_point=(math.nan, 6100050.0),
            )

    def test_protected_point_inf_raises(self, tmp_path):
        """Inf coordinates in protected_point raise ValidationError."""
        import math

        with pytest.raises(ValidationError, match="finite"):
            ScenarioConfig(
                site_dem_path=tmp_path / "dem.tif",
                protected_point=(500050.0, math.inf),
            )

    def test_trajectory_path_default_none(self, tmp_path):
        """trajectory_path defaults to None."""
        sc = ScenarioConfig(site_dem_path=tmp_path / "dem.tif")
        assert sc.trajectory_path is None

    def test_trajectory_default_none(self, tmp_path):
        """trajectory defaults to None."""
        sc = ScenarioConfig(site_dem_path=tmp_path / "dem.tif")
        assert sc.trajectory is None

    def test_trajectory_path_accepts_path(self, tmp_path):
        """trajectory_path accepts a Path value."""
        traj = tmp_path / "approach.yaml"
        sc = ScenarioConfig(site_dem_path=tmp_path / "dem.tif", trajectory_path=traj)
        assert sc.trajectory_path == traj

    def test_trajectory_path_accepts_string(self, tmp_path):
        """trajectory_path accepts a string, coerced to Path."""
        traj = tmp_path / "approach.yaml"
        sc = ScenarioConfig(site_dem_path=tmp_path / "dem.tif", trajectory_path=str(traj))
        assert isinstance(sc.trajectory_path, Path)

    def test_trajectory_path_empty_string_raises(self, tmp_path):
        """Empty string for trajectory_path is invalid."""
        with pytest.raises(ValidationError, match="trajectory_path"):
            ScenarioConfig(site_dem_path=tmp_path / "dem.tif", trajectory_path="")

    def test_trajectory_path_whitespace_raises(self, tmp_path):
        """Whitespace-only trajectory_path is invalid."""
        with pytest.raises(ValidationError, match="trajectory_path"):
            ScenarioConfig(site_dem_path=tmp_path / "dem.tif", trajectory_path="   ")

    def test_trajectory_path_non_path_raises(self, tmp_path):
        """Non-string/Path value for trajectory_path is invalid."""
        with pytest.raises(ValidationError, match="trajectory_path"):
            ScenarioConfig(site_dem_path=tmp_path / "dem.tif", trajectory_path=42)  # type: ignore[arg-type]

    def test_sweep_altitudes_default_none(self, tmp_path):
        """sweep_altitudes_m defaults to None."""
        sc = ScenarioConfig(site_dem_path=tmp_path / "dem.tif")
        assert sc.sweep_altitudes_m is None

    def test_sweep_altitudes_valid(self, tmp_path):
        """sweep_altitudes_m accepts a list of non-negative finite floats."""
        sc = ScenarioConfig(
            site_dem_path=tmp_path / "dem.tif",
            sweep_altitudes_m=[0.0, 50.0, 150.0],
        )
        assert sc.sweep_altitudes_m == [0.0, 50.0, 150.0]

    def test_sweep_altitudes_empty_list_raises(self, tmp_path):
        """sweep_altitudes_m=[] raises ValidationError (would silently produce empty sweep)."""
        with pytest.raises(ValidationError, match="sweep_altitudes_m"):
            ScenarioConfig(
                site_dem_path=tmp_path / "dem.tif",
                sweep_altitudes_m=[],
            )

    def test_sweep_altitudes_negative_raises(self, tmp_path):
        """Negative altitude in sweep_altitudes_m raises ValidationError."""
        with pytest.raises(ValidationError, match="sweep_altitudes_m"):
            ScenarioConfig(
                site_dem_path=tmp_path / "dem.tif",
                sweep_altitudes_m=[50.0, -10.0],
            )

    def test_sweep_dive_angles_default_none(self, tmp_path):
        """sweep_dive_angles_deg defaults to None."""
        sc = ScenarioConfig(site_dem_path=tmp_path / "dem.tif")
        assert sc.sweep_dive_angles_deg is None

    def test_sweep_dive_angles_valid(self, tmp_path):
        """sweep_dive_angles_deg accepts values in [-90, 0]."""
        sc = ScenarioConfig(
            site_dem_path=tmp_path / "dem.tif",
            sweep_dive_angles_deg=[-90.0, -45.0, 0.0],
        )
        assert sc.sweep_dive_angles_deg == [-90.0, -45.0, 0.0]

    def test_sweep_dive_angles_empty_list_raises(self, tmp_path):
        """sweep_dive_angles_deg=[] raises ValidationError (would silently produce empty sweep)."""
        with pytest.raises(ValidationError, match="sweep_dive_angles_deg"):
            ScenarioConfig(
                site_dem_path=tmp_path / "dem.tif",
                sweep_dive_angles_deg=[],
            )

    def test_sweep_dive_angles_positive_raises(self, tmp_path):
        """Positive dive angle (ascending) raises ValidationError."""
        with pytest.raises(ValidationError, match="sweep_dive_angles_deg"):
            ScenarioConfig(
                site_dem_path=tmp_path / "dem.tif",
                sweep_dive_angles_deg=[10.0],
            )

    def test_sweep_dive_angles_below_minus_90_raises(self, tmp_path):
        """Dive angle below -90 raises ValidationError."""
        with pytest.raises(ValidationError, match="sweep_dive_angles_deg"):
            ScenarioConfig(
                site_dem_path=tmp_path / "dem.tif",
                sweep_dive_angles_deg=[-91.0],
            )

    def test_sweep_segment_length_default(self, tmp_path):
        """sweep_segment_length_m defaults to 5.0."""
        sc = ScenarioConfig(site_dem_path=tmp_path / "dem.tif")
        assert sc.sweep_segment_length_m == pytest.approx(5.0)

    def test_sweep_segment_length_valid(self, tmp_path):
        """Positive sweep_segment_length_m is accepted."""
        sc = ScenarioConfig(
            site_dem_path=tmp_path / "dem.tif",
            sweep_segment_length_m=0.5,
        )
        assert sc.sweep_segment_length_m == pytest.approx(0.5)

    def test_sweep_segment_length_zero_raises(self, tmp_path):
        """sweep_segment_length_m=0 raises ValidationError."""
        with pytest.raises(ValidationError, match="sweep_segment_length_m"):
            ScenarioConfig(
                site_dem_path=tmp_path / "dem.tif",
                sweep_segment_length_m=0.0,
            )

    def test_sweep_segment_length_negative_raises(self, tmp_path):
        """Negative sweep_segment_length_m raises ValidationError."""
        with pytest.raises(ValidationError, match="sweep_segment_length_m"):
            ScenarioConfig(
                site_dem_path=tmp_path / "dem.tif",
                sweep_segment_length_m=-1.0,
            )


# ---------------------------------------------------------------------------
# KillChainConfig model tests (S7-1)
# ---------------------------------------------------------------------------


class TestKillChainConfig:
    """Tests for KillChainConfig Pydantic model."""

    def _valid_config(self) -> dict:
        return {
            "track_time_s": 5.0,
            "identify_time_s": 10.0,
            "decide_time_s": 8.0,
            "assess_time_s": 3.0,
        }

    def test_valid_construction(self):
        """Valid KillChainConfig constructs without error."""
        from salus.models.scenario import KillChainConfig

        cfg = KillChainConfig(**self._valid_config())
        assert cfg.track_time_s == 5.0
        assert cfg.identify_time_s == 10.0
        assert cfg.decide_time_s == 8.0
        assert cfg.assess_time_s == 3.0

    def test_all_phases_positive(self):
        """All phase durations must be positive finite floats."""
        from salus.models.scenario import KillChainConfig

        cfg = KillChainConfig(
            track_time_s=1.0, identify_time_s=2.0, decide_time_s=3.0, assess_time_s=4.0
        )
        assert cfg.track_time_s == 1.0

    def test_zero_phase_raises(self):
        """Zero phase duration raises ValidationError."""
        from salus.models.scenario import KillChainConfig

        with pytest.raises(ValidationError):
            KillChainConfig(
                track_time_s=0.0,
                identify_time_s=10.0,
                decide_time_s=8.0,
                assess_time_s=3.0,
            )

    def test_negative_phase_raises(self):
        """Negative phase duration raises ValidationError."""
        from salus.models.scenario import KillChainConfig

        with pytest.raises(ValidationError):
            KillChainConfig(
                track_time_s=5.0,
                identify_time_s=-1.0,
                decide_time_s=8.0,
                assess_time_s=3.0,
            )

    def test_inf_phase_raises(self):
        """Infinite phase duration raises ValidationError."""
        import math

        from salus.models.scenario import KillChainConfig

        with pytest.raises(ValidationError):
            KillChainConfig(
                track_time_s=math.inf,
                identify_time_s=10.0,
                decide_time_s=8.0,
                assess_time_s=3.0,
            )


# ---------------------------------------------------------------------------
# KillChainResult dataclass tests (S7-1)
# ---------------------------------------------------------------------------


class TestKillChainResult:
    """Tests for KillChainResult frozen dataclass."""

    def test_construction(self):
        """KillChainResult constructs and exposes all fields."""
        from salus.models.scenario import KillChainResult

        r = KillChainResult(
            available_time_s=30.0,
            required_time_s=20.0,
            margin_s=10.0,
            first_detection_range_m=600.0,
            engagement_feasible=True,
            second_engagement_possible=False,
        )
        assert r.available_time_s == 30.0
        assert r.required_time_s == 20.0
        assert r.margin_s == 10.0
        assert r.first_detection_range_m == 600.0
        assert r.engagement_feasible is True
        assert r.second_engagement_possible is False

    def test_is_frozen(self):
        """KillChainResult is immutable."""
        from salus.models.scenario import KillChainResult

        r = KillChainResult(
            available_time_s=30.0,
            required_time_s=20.0,
            margin_s=10.0,
            first_detection_range_m=600.0,
            engagement_feasible=True,
            second_engagement_possible=False,
        )
        with pytest.raises((AttributeError, TypeError)):
            r.margin_s = 5.0  # type: ignore[misc]

    def test_none_first_detection(self):
        """first_detection_range_m may be None."""
        from salus.models.scenario import KillChainResult

        r = KillChainResult(
            available_time_s=0.0,
            required_time_s=20.0,
            margin_s=-20.0,
            first_detection_range_m=None,
            engagement_feasible=False,
            second_engagement_possible=False,
        )
        assert r.first_detection_range_m is None
