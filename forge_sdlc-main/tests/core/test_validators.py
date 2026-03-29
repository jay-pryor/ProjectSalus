"""Tests for forge_core.validators — schema validation."""
import pytest
from forge_core.validators import validate_schema, ConfigValidationError


class TestValidateSchema:
    def test_valid_config(self):
        schema = {
            "version": {"type": "str", "required": True},
            "name": {"type": "str", "required": True},
        }
        data = {"version": "1.0.0", "name": "test"}
        errors = validate_schema(data, schema)
        assert errors == []

    def test_missing_required_field(self):
        schema = {
            "version": {"type": "str", "required": True},
            "name": {"type": "str", "required": True},
        }
        data = {"version": "1.0.0"}
        errors = validate_schema(data, schema)
        assert len(errors) == 1
        assert "name" in errors[0]["field"]

    def test_wrong_type(self):
        schema = {
            "version": {"type": "str", "required": True},
            "count": {"type": "int", "required": False},
        }
        data = {"version": "1.0.0", "count": "not_a_number"}
        errors = validate_schema(data, schema)
        assert len(errors) == 1
        assert "count" in errors[0]["field"]

    def test_strict_mode_unknown_keys(self):
        schema = {
            "version": {"type": "str", "required": True},
        }
        data = {"version": "1.0.0", "unknown_field": "value"}
        errors = validate_schema(data, schema, strict=True)
        assert len(errors) == 1
        assert "unknown_field" in errors[0]["field"]

    def test_non_strict_allows_unknown_keys(self):
        schema = {
            "version": {"type": "str", "required": True},
        }
        data = {"version": "1.0.0", "unknown_field": "value"}
        errors = validate_schema(data, schema, strict=False)
        assert errors == []

    def test_allowed_values(self):
        schema = {
            "profile": {"type": "str", "required": True, "allowed": ["standard", "light"]},
        }
        data = {"profile": "invalid"}
        errors = validate_schema(data, schema)
        assert len(errors) == 1

    def test_allowed_values_valid(self):
        schema = {
            "profile": {"type": "str", "required": True, "allowed": ["standard", "light"]},
        }
        data = {"profile": "standard"}
        errors = validate_schema(data, schema)
        assert errors == []

    def test_non_dict_input(self):
        schema = {"version": {"type": "str", "required": True}}
        errors = validate_schema("not_a_dict", schema)
        assert len(errors) == 1
        assert "(root)" in errors[0]["field"]
