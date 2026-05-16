"""Data sanitisation for the interactive viewer export (S14-2).

Sanitisation removes or obscures information that should not leave the
analysis environment when the viewer is delivered to a customer.  Three
levels are supported:

``minimal``
    Only round geographic coordinates to the configured precision.
    All sensor specifications and analysis results are preserved.

``redacted``  (default for customer delivery)
    Sensor names replaced with generic labels, exact range values
    replaced with band categories (short/medium/long), coordinates
    rounded, proprietary fields removed.  Coverage percentages and
    gap areas are preserved as they are the customer's own data.

``full``
    All of ``redacted`` plus corridor paths, kill-chain timing, and
    saturation sweep data are removed.  Only aggregate statistics
    remain.
"""

from __future__ import annotations

import copy
import logging
import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from salus.viewer.export import ViewerData

_log = logging.getLogger(__name__)

# Range band boundaries (metres) used when level >= redacted.
_RANGE_BANDS: list[tuple[str, float]] = [
    ("short", 500.0),
    ("medium", 2000.0),
    ("long", float("inf")),
]

# Sensor library entry fields retained at REDACTED level. These are
# characteristics of a *sensor class* (radar / EO-IR / RF / acoustic) that are
# publicly knowable from the product type, not the proprietary specs of a
# particular vendor unit. Everything else (vendor name, exact ranges, cost,
# frequency bands, mounting height, vegetation penetration coefficient,
# elevation boresight, free-text notes) is discarded.
_PUBLIC_SENSOR_FIELDS: frozenset[str] = frozenset(
    {"type", "azimuth_coverage_deg", "elevation_coverage_deg", "requires_los"}
)

# Effector library entries do not currently expose an elevation coverage field
# in the YAML schema; the whitelist is the type-class-knowable subset.
_PUBLIC_EFFECTOR_FIELDS: frozenset[str] = frozenset(
    {"type", "azimuth_coverage_deg", "requires_los"}
)


class SanitiseLevel(StrEnum):
    """Controls how aggressively the viewer data is scrubbed."""

    MINIMAL = "minimal"
    REDACTED = "redacted"
    FULL = "full"


@dataclass
class SanitiseConfig:
    """Configuration for :func:`sanitise_for_export`."""

    level: SanitiseLevel = SanitiseLevel.REDACTED
    """Sanitisation depth."""

    coordinate_precision: int = field(default=4)
    """Decimal places for WGS84 coordinates (4 dp ≈ 11 m accuracy). Must be >= 0."""

    def __post_init__(self) -> None:
        if not isinstance(self.coordinate_precision, int):
            got = type(self.coordinate_precision).__name__
            raise TypeError(f"coordinate_precision must be an int, got {got}")
        if self.coordinate_precision < 0:
            raise ValueError(f"coordinate_precision must be >= 0, got {self.coordinate_precision}")


def sanitise_for_export(viewer_data: ViewerData, config: SanitiseConfig) -> ViewerData:
    """Return a sanitised copy of *viewer_data* according to *config*.

    The original object is never mutated — a deep copy is made and then
    modified in place before being returned.

    Args:
        viewer_data: The :class:`~salus.viewer.export.ViewerData` to sanitise.
        config: Controls which fields are removed or obfuscated.

    Returns:
        A new :class:`~salus.viewer.export.ViewerData` with sensitive fields
        removed or replaced per *config*.
    """
    out = copy.deepcopy(viewer_data)
    prec = config.coordinate_precision

    # Always: round coordinates in sensor placements
    _round_sensor_coords(out.sensor_placements, prec)

    # Always: round GeoJSON coordinates in coverage layers
    for layer in out.layers.values():
        _round_geojson_coords(layer, prec)

    # Always: round bounds and centre
    out.bounds_wgs84 = tuple(round(v, prec) for v in out.bounds_wgs84)  # type: ignore[assignment]
    out.centre_wgs84 = (round(out.centre_wgs84[0], prec), round(out.centre_wgs84[1], prec))

    if config.level in (SanitiseLevel.REDACTED, SanitiseLevel.FULL):
        # Replace sensor names with generic labels
        _anonymise_sensors(out.sensor_placements)

        # Remove bearing and height properties (reveal deployment tactics).
        # sensor_type and azimuth_coverage_deg are intentionally NOT stripped here:
        # sensor_type is a property of the sensor model (same for every unit of that type,
        # publicly knowable), and azimuth_coverage_deg is also model-level, not placement-level.
        # bearing_deg is the sensitive field — it reveals the deployment direction.
        _strip_sensor_properties(out.sensor_placements, {"bearing_deg", "height_override_m"})

        # Replace per-layer keys with band labels in stats
        out.stats = _redact_stats(out.stats)

        # Redact the embedded sensor/effector libraries — strip vendor fields,
        # band exact ranges. Without this, a REDACTED customer-delivered viewer
        # would still ship the full proprietary sensor DB via SALUS_DATA (D-498).
        out.sensor_library = _redact_library(out.sensor_library, _PUBLIC_SENSOR_FIELDS)
        out.effector_library = _redact_library(out.effector_library, _PUBLIC_EFFECTOR_FIELDS)

        # Sanitise corridor paths (round to precision only; keep fraction)
        for corridor in out.corridor_results:
            _round_path(corridor.get("path_wgs84", []), prec)

    if config.level == SanitiseLevel.FULL:
        # Drop libraries entirely — no library metadata leaves the analysis
        # environment at the highest sanitisation level.
        out.sensor_library = {}
        out.effector_library = {}

        # Remove corridor paths entirely
        for corridor in out.corridor_results:
            corridor.pop("path_wgs84", None)

        # Remove kill-chain timing detail (keep feasibility booleans only)
        for kc in out.kill_chain_results:
            for timing_field in (
                "available_time_s",
                "required_time_s",
                "first_detection_range_m",
                "margin_s",
            ):
                kc.pop(timing_field, None)

        # Remove per-effector utilisation detail from saturation result
        if out.saturation_result is not None:
            out.saturation_result.pop("per_effector_utilisation", None)

    out.sanitised = True
    _log.info(
        "Sanitised viewer data at level '%s' (coord precision: %d dp)",
        config.level,
        prec,
    )
    return out


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _range_band(value_m: float) -> str:
    """Map an exact range (metres) to a band label."""
    for label, upper in _RANGE_BANDS:
        if value_m <= upper:
            return label
    return "long"


def _redact_library(
    library: dict[str, list[dict[str, Any]]],
    allowed_fields: frozenset[str],
) -> dict[str, list[dict[str, Any]]]:
    """Return a redacted copy of a sensor or effector library.

    Each entry retains only fields in *allowed_fields*; a generic
    ``name = "{type}-{i}"`` replaces the vendor name; ``max_range_m`` is
    discarded and a coarse ``range_band`` label is emitted instead. Entries
    with missing/non-finite ``max_range_m`` get ``range_band = "unknown"`` —
    we do not rely on ``_range_band`` to handle NaN (see D-551).

    Args:
        library: The library to redact, keyed by sensor/effector type.
        allowed_fields: Field names that are safe to preserve verbatim.

    Returns:
        A new dict with the same type-keyed structure but redacted entries.
    """
    redacted: dict[str, list[dict[str, Any]]] = {}
    for type_key, entries in library.items():
        out_entries: list[dict[str, Any]] = []
        for i, entry in enumerate(entries, start=1):
            new_entry: dict[str, Any] = {k: v for k, v in entry.items() if k in allowed_fields}
            new_entry["name"] = f"{type_key}-{i}"
            max_range = entry.get("max_range_m")
            # bool is a subclass of int — guard against True/False being banded
            # as a numeric range. Non-finite (NaN/inf) and missing values fall
            # back to "unknown" so _range_band's NaN behaviour (D-551) is moot.
            if (
                isinstance(max_range, (int, float))
                and not isinstance(max_range, bool)
                and math.isfinite(max_range)
            ):
                new_entry["range_band"] = _range_band(float(max_range))
            else:
                new_entry["range_band"] = "unknown"
            out_entries.append(new_entry)
        redacted[type_key] = out_entries
    return redacted


def _round_geojson_coords(fc: dict[str, Any], prec: int) -> None:
    """Round all coordinate values in a GeoJSON FeatureCollection in place."""
    for feature in fc.get("features", []):
        geom = feature.get("geometry")
        if geom:
            _round_geometry_coords(geom, prec)


def _round_geometry_coords(geom: dict[str, Any], prec: int) -> None:
    """Round coordinate arrays within a GeoJSON geometry dict in place."""
    coords = geom.get("coordinates")
    if coords is not None:
        geom["coordinates"] = _round_coords_recursive(coords, prec)


def _round_coords_recursive(obj: Any, prec: int) -> Any:
    if isinstance(obj, list):
        if obj and isinstance(obj[0], (int, float)):
            # Leaf coordinate pair/triple
            return [round(v, prec) for v in obj]
        return [_round_coords_recursive(item, prec) for item in obj]
    return obj


def _round_sensor_coords(fc: dict[str, Any], prec: int) -> None:
    """Round Point geometry coordinates in a sensor FeatureCollection."""
    for feature in fc.get("features", []):
        geom = feature.get("geometry", {})
        if geom.get("type") == "Point":
            coords = geom.get("coordinates", [])
            geom["coordinates"] = [round(v, prec) for v in coords]


def _anonymise_sensors(fc: dict[str, Any]) -> None:
    """Replace sensor_name with generic labels (Sensor-1, Sensor-2, …)."""
    for i, feature in enumerate(fc.get("features", []), start=1):
        props = feature.get("properties", {})
        if "sensor_name" in props:
            props["sensor_name"] = f"Sensor-{i}"


def _strip_sensor_properties(fc: dict[str, Any], fields: set[str]) -> None:
    """Remove specified property keys from all features."""
    for feature in fc.get("features", []):
        props = feature.get("properties", {})
        for f in fields:
            props.pop(f, None)


def _redact_stats(stats: dict[str, Any]) -> dict[str, Any]:
    """Preserve coverage percentages but remove per-layer type keys."""
    out = dict(stats)
    # Replace SensorType enum string keys with generic layer labels
    per_layer = out.get("per_layer_coverage_pct", {})
    relabelled = {f"Layer-{i + 1}": v for i, (_, v) in enumerate(per_layer.items())}
    out["per_layer_coverage_pct"] = relabelled
    return out


def _round_path(path: list[Any], prec: int) -> None:
    """Round coordinates in a GeoJSON coordinate list in place."""
    for i, coord in enumerate(path):
        if isinstance(coord, list):
            path[i] = [round(v, prec) for v in coord]
