"""Tests for the Zone and ZoneType models."""

from __future__ import annotations

import pytest
from shapely.geometry import MultiPolygon, Polygon

from salus.models.zone import Zone, ZoneType


class TestZoneType:
    def test_all_values_exist(self):
        """All four zone types must be defined."""
        assert ZoneType.perimeter == "perimeter"
        assert ZoneType.inner == "inner"
        assert ZoneType.critical_asset == "critical_asset"
        assert ZoneType.exclusion == "exclusion"

    def test_from_string_perimeter(self):
        """ZoneType must be constructible from its string value."""
        assert ZoneType("perimeter") is ZoneType.perimeter

    def test_from_string_critical_asset(self):
        """ZoneType must be constructible from 'critical_asset'."""
        assert ZoneType("critical_asset") is ZoneType.critical_asset

    def test_invalid_string_raises(self):
        """An unrecognised string must raise ValueError."""
        with pytest.raises(ValueError):
            ZoneType("unknown_type")


class TestZone:
    def _square(self, x0: float = 0.0, y0: float = 0.0, size: float = 100.0) -> Polygon:
        return Polygon([(x0, y0), (x0 + size, y0), (x0 + size, y0 + size), (x0, y0 + size)])

    def test_basic_construction(self):
        """Zone must accept valid name, zone_type, and polygon geometry."""
        z = Zone(name="Main Gate", zone_type=ZoneType.perimeter, geometry=self._square())
        assert z.name == "Main Gate"
        assert z.zone_type is ZoneType.perimeter
        assert isinstance(z.geometry, Polygon)

    def test_zone_type_from_string(self):
        """zone_type must accept its string value directly."""
        z = Zone(name="Tower", zone_type="critical_asset", geometry=self._square())
        assert z.zone_type is ZoneType.critical_asset

    def test_multipolygon_geometry_accepted(self):
        """Zone must accept a MultiPolygon geometry."""
        mp = MultiPolygon([self._square(0, 0), self._square(200, 200)])
        z = Zone(name="Dispersed Zone", zone_type=ZoneType.inner, geometry=mp)
        assert isinstance(z.geometry, MultiPolygon)

    def test_empty_name_raises(self):
        """An empty name must raise ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            Zone(name="", zone_type=ZoneType.perimeter, geometry=self._square())

    def test_whitespace_name_raises(self):
        """A whitespace-only name must raise ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            Zone(name="   ", zone_type=ZoneType.perimeter, geometry=self._square())

    def test_invalid_zone_type_raises(self):
        """An invalid zone_type string must raise ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            Zone(name="Test", zone_type="bad_type", geometry=self._square())

    def test_all_zone_types_valid(self):
        """Zone must accept every valid ZoneType value."""
        poly = self._square()
        for zt in ZoneType:
            z = Zone(name="Test", zone_type=zt, geometry=poly)
            assert z.zone_type is zt

    def test_name_is_stripped_implicitly(self):
        """Name with leading/trailing spaces must NOT be stripped — it should raise."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            Zone(name="  ", zone_type=ZoneType.exclusion, geometry=self._square())
