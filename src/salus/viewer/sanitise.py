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
from dataclasses import dataclass
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

    coordinate_precision: int = 4
    """Decimal places for WGS84 coordinates (4 dp ≈ 11 m accuracy)."""


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

        # Sanitise corridor paths (round to precision only; keep fraction)
        for corridor in out.corridor_results:
            _round_path(corridor.get("path_wgs84", []), prec)

    if config.level == SanitiseLevel.FULL:
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
