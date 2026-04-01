"""Smoke tests for the bundled threat YAML data files.

These tests verify that every YAML file in src/salus/data/threats/ loads and
validates against ThreatProfile without error.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from salus.ingest.sensors import load_threats
from salus.models.threat import EvasionCapability

DATA_DIR = Path(__file__).parent.parent / "src" / "salus" / "data" / "threats"


@pytest.fixture(scope="module")
def bundled_threats():
    """Load all bundled threat YAML files once for the module."""
    return load_threats(DATA_DIR)


class TestBundledThreatData:
    def test_at_least_three_profiles_present(self, bundled_threats):
        assert len(bundled_threats) >= 3

    def test_all_threats_have_non_empty_names(self, bundled_threats):
        for t in bundled_threats:
            assert t.name.strip(), f"Empty name in threat: {t}"

    def test_all_rcs_positive(self, bundled_threats):
        for t in bundled_threats:
            assert t.rcs_m2 > 0, f"Non-positive rcs_m2 for {t.name}"

    def test_all_speeds_positive(self, bundled_threats):
        for t in bundled_threats:
            assert t.max_speed_ms > 0, f"Non-positive max_speed_ms for {t.name}"

    def test_all_altitudes_non_negative(self, bundled_threats):
        for t in bundled_threats:
            assert t.typical_altitude_m >= 0, f"Negative altitude for {t.name}"

    def test_evasion_capabilities_valid(self, bundled_threats):
        valid = set(EvasionCapability)
        for t in bundled_threats:
            assert t.evasion_capability in valid, (
                f"Invalid evasion_capability for {t.name}: {t.evasion_capability}"
            )

    def test_all_rf_signatures_non_empty(self, bundled_threats):
        for t in bundled_threats:
            assert t.rf_signature.strip(), f"Empty rf_signature for {t.name}"

    def test_fixed_wing_has_advanced_evasion(self, bundled_threats):
        fw = next((t for t in bundled_threats if "Fixed-Wing" in t.name), None)
        assert fw is not None, "Fixed-wing ISR profile not found"
        assert fw.evasion_capability == EvasionCapability.advanced

    def test_mavic_has_no_evasion(self, bundled_threats):
        mavic = next((t for t in bundled_threats if "Mavic" in t.name), None)
        assert mavic is not None, "DJI Mavic profile not found"
        assert mavic.evasion_capability == EvasionCapability.none

    def test_racing_drone_has_basic_evasion(self, bundled_threats):
        racing = next((t for t in bundled_threats if "Racing" in t.name or "FPV" in t.name), None)
        assert racing is not None, "Racing drone profile not found"
        assert racing.evasion_capability == EvasionCapability.basic
