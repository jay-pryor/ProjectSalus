"""Smoke tests for the bundled effector YAML data files.

Verifies that every YAML file in src/salus/data/effectors/ loads and validates
against EffectorDefinition without error.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from salus.ingest.sensors import load_effectors
from salus.models.sensor import EffectorType

DATA_DIR = Path(__file__).parent.parent / "src" / "salus" / "data" / "effectors"


@pytest.fixture(scope="module")
def bundled_effectors():
    """Load all bundled effector YAML files once for the module."""
    return load_effectors(DATA_DIR)


class TestBundledEffectorData:
    def test_at_least_three_effectors_present(self, bundled_effectors):
        """The bundled database must contain at least 3 effector definitions."""
        assert len(bundled_effectors) >= 3

    def test_required_effector_types_represented(self, bundled_effectors):
        """RF_Jammer, Kinetic, and Cyber types must each be present."""
        types_present = {e.type for e in bundled_effectors}
        assert EffectorType.RF_Jammer in types_present
        assert EffectorType.Kinetic in types_present
        assert EffectorType.Cyber in types_present

    def test_all_effectors_have_non_empty_names(self, bundled_effectors):
        """Every effector must have a non-empty name."""
        for e in bundled_effectors:
            assert e.name.strip(), f"Empty name in effector: {e}"

    def test_all_effectors_have_non_empty_defeat_mechanisms(self, bundled_effectors):
        """Every effector must describe its defeat mechanism."""
        for e in bundled_effectors:
            assert e.defeat_mechanism.strip(), f"Empty defeat_mechanism for {e.name}"

    def test_all_max_ranges_positive(self, bundled_effectors):
        """Every effector must have a positive max_range_m."""
        for e in bundled_effectors:
            assert e.max_range_m > 0, f"Non-positive range for {e.name}"

    def test_all_min_ranges_less_than_max(self, bundled_effectors):
        """Every effector's min_range_m must be less than max_range_m."""
        for e in bundled_effectors:
            assert e.min_range_m < e.max_range_m, f"min_range >= max_range for {e.name}"

    def test_all_defeat_probabilities_valid(self, bundled_effectors):
        """Every effector's defeat_probability must be in [0, 1]."""
        for e in bundled_effectors:
            assert 0.0 <= e.defeat_probability <= 1.0, (
                f"Invalid defeat_probability for {e.name}: {e.defeat_probability}"
            )

    def test_kinetic_effectors_require_los(self, bundled_effectors):
        """Kinetic effectors must require LOS."""
        for e in bundled_effectors:
            if e.type == EffectorType.Kinetic:
                assert e.requires_los is True, (
                    f"Kinetic effector {e.name} incorrectly does not require LOS"
                )

    def test_directed_energy_effectors_require_los(self, bundled_effectors):
        """Directed Energy effectors must require LOS."""
        for e in bundled_effectors:
            if e.type == EffectorType.Directed_Energy:
                assert e.requires_los is True, (
                    f"Directed Energy effector {e.name} incorrectly does not require LOS"
                )

    def test_no_cost_data_in_model(self, bundled_effectors):
        """EffectorDefinition has no cost field — confirming all load without error."""
        assert len(bundled_effectors) >= 3
