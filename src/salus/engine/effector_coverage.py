"""Effector coverage computation — engagement zones for cUAS defeat systems.

Computes where each effector can engage a drone target.  Two models are used
depending on whether the effector requires line-of-sight:

- **LOS-required** (Kinetic, Directed Energy): viewshed-based engagement zone,
  clipped to the effector's maximum range and engagement arc.
- **Non-LOS** (RF Jammer, Cyber): range circle only — no terrain occlusion is
  applied.  The result is still clipped to the engagement arc.

The output is a separate boolean layer distinct from sensor detection coverage,
intended for "detection-without-engagement" gap analysis (S11-2).
"""

from __future__ import annotations

import logging
import math

import numpy as np
import numpy.typing as npt

from salus.models.scenario import EffectorPlacement
from salus.models.sensor import EffectorDefinition
from salus.models.site import SiteModel

_log = logging.getLogger(__name__)

# Engagement arc threshold above which no wedge masking is applied.
_FULL_ARC_DEG: float = 360.0

# Default effector height AGL when placement.height_override_m is None.
_DEFAULT_EFFECTOR_HEIGHT_M: float = 0.0


def compute_single_effector_coverage(
    site: SiteModel,
    effector: EffectorDefinition,
    placement: EffectorPlacement,
) -> npt.NDArray[np.bool_]:
    """Compute the engagement zone for a single effector placement.

    The engagement zone is the set of cells where the effector can defeat a
    target.  Two propagation models are used depending on the effector type:

    - ``requires_los=True`` (Kinetic, Directed Energy): a viewshed is computed
      from the effector position and clipped to the effector's range and
      engagement arc.
    - ``requires_los=False`` (RF Jammer, Cyber): a range circle is used — no
      terrain occlusion is applied.  The result is still clipped to the
      engagement arc and min/max range.

    In both cases the dead zone (``effector.min_range_m``) is excluded.

    Note on the effector's own position cell (dist == 0): when
    ``min_range_m == 0.0``, the cell at the exact effector position is included.
    ``np.arctan2(0, 0)`` returns 0.0, so that cell is assigned bearing north (0°)
    for arc-mask purposes.  Set ``min_range_m > 0`` to exclude the dead zone
    around the effector itself.

    Args:
        site: Site terrain model.
        effector: Effector capability definition.
        placement: Effector deployment position and boresight bearing.

    Returns:
        Boolean 2D array of shape ``(site.rows, site.cols)``.  ``True`` where
        the effector can engage a target.

    Raises:
        ValueError: If the effector height AGL is non-finite.
        ValueError: If placement.position_x or placement.position_y is non-finite.
        ValueError: If ``site.resolution`` is not a finite positive number.
        ValueError: If the effector position is outside the raster extent (LOS
            effectors only — raised by the underlying viewshed engine).
    """
    # D-193: guard non-finite positions before any array arithmetic
    if not math.isfinite(placement.position_x) or not math.isfinite(placement.position_y):
        raise ValueError(
            f"placement position must be finite, got "
            f"({placement.position_x}, {placement.position_y})"
        )

    effector_agl: float = (
        placement.height_override_m
        if placement.height_override_m is not None
        else _DEFAULT_EFFECTOR_HEIGHT_M
    )
    if not math.isfinite(effector_agl):
        raise ValueError(
            f"effector height AGL is non-finite ({effector_agl}); check placement.height_override_m"
        )

    if effector.requires_los:
        _log.debug(
            "Effector '%s' requires LOS — computing viewshed from (%.1f, %.1f) AGL %.1f m",
            effector.name,
            placement.position_x,
            placement.position_y,
            effector_agl,
        )
        base = _los_engagement_zone(site, effector, placement, effector_agl)
    else:
        _log.debug(
            "Effector '%s' does not require LOS — using range circle",
            effector.name,
        )
        base = np.ones((site.rows, site.cols), dtype=bool)

    return _clip_to_effector(base, site, effector, placement)


def compute_effector_layer_coverage(
    site: SiteModel,
    effector_pairs: list[tuple[EffectorDefinition, EffectorPlacement]],
) -> npt.NDArray[np.bool_]:
    """Compute a union engagement zone for a list of effector placements.

    A cell is ``True`` if **any** effector in the list can engage a target
    there.  An empty list returns an all-False array of shape
    ``(site.rows, site.cols)``.

    Args:
        site: Site terrain model.
        effector_pairs: List of ``(effector_definition, placement)`` pairs.

    Returns:
        Boolean 2D array of shape ``(site.rows, site.cols)``.

    Raises:
        ValueError: If any individual coverage array has a shape that does not
            match ``(site.rows, site.cols)``.
        RuntimeError: If the underlying viewshed engine fails for a specific
            effector.  The effector name is included in the error message.
    """
    # D-196: warn when no effectors are configured — silent all-False could mask
    # a scenario configuration error.
    if not effector_pairs:
        _log.warning(
            "compute_effector_layer_coverage called with no effectors — returning all-False layer"
        )

    union: npt.NDArray[np.bool_] = np.zeros((site.rows, site.cols), dtype=bool)

    for effector, placement in effector_pairs:
        # D-195: wrap per-effector computation to surface the failing effector name
        try:
            cov = compute_single_effector_coverage(site, effector, placement)
        except Exception as exc:
            raise RuntimeError(
                f"Effector coverage computation failed for effector '{effector.name}' "
                f"at ({placement.position_x}, {placement.position_y}): {exc}"
            ) from exc

        if cov.shape != (site.rows, site.cols):
            raise ValueError(
                f"Effector coverage shape {cov.shape} does not match site shape "
                f"({site.rows}, {site.cols}) for effector '{effector.name}'"
            )
        union |= cov
        _log.debug(
            "Effector '%s' added to union layer — covered cells: %d",
            effector.name,
            int(cov.sum()),
        )

    _log.info(
        "Effector layer coverage complete — %d effectors, %d cells covered",
        len(effector_pairs),
        int(union.sum()),
    )
    return union


def _los_engagement_zone(
    site: SiteModel,
    effector: EffectorDefinition,
    placement: EffectorPlacement,
    effector_agl: float,
) -> npt.NDArray[np.bool_]:
    """Compute a raw viewshed from the effector position over the full scene.

    Range clipping is intentionally deferred to :func:`_clip_to_effector`
    so the returned array always matches the full site DEM shape.  Passing
    ``max_range`` to GDAL ViewshedGenerate clips its output raster; omitting it
    keeps the output shape consistent with ``site.dem.shape``.
    """
    from salus.engine.viewshed import compute_viewshed

    return compute_viewshed(
        site,
        placement.position_x,
        placement.position_y,
        effector_agl,
        max_range=None,
    )


def _clip_to_effector(
    base: npt.NDArray[np.bool_],
    site: SiteModel,
    effector: EffectorDefinition,
    placement: EffectorPlacement,
) -> npt.NDArray[np.bool_]:
    """Clip a base engagement map to the effector's range and engagement arc.

    Applies:
    - **Range mask**: retains cells in [min_range_m, max_range_m].
    - **Arc mask**: retains cells within engagement_arc_deg of the boresight.
      Skipped when engagement_arc_deg >= 360°.

    Args:
        base: Boolean base array (viewshed or all-True for non-LOS).
        site: Site terrain model (provides grid geometry for distance calc).
        effector: Effector capability definition.
        placement: Effector deployment position and boresight bearing.

    Returns:
        Clipped boolean 2D array.

    Raises:
        ValueError: If ``site.resolution`` is not a finite positive number.
    """
    # D-194: guard against zero/negative resolution producing a uniform-distance grid
    if not math.isfinite(site.resolution) or site.resolution <= 0.0:
        raise ValueError(f"site.resolution must be a finite positive number, got {site.resolution}")

    rows, cols = base.shape

    # D-197: annotate all intermediate float arrays
    col_coords: npt.NDArray[np.float64] = (
        site.origin_x + np.arange(cols, dtype=np.float64) * site.resolution
    )
    row_coords: npt.NDArray[np.float64] = (
        site.origin_y - np.arange(rows, dtype=np.float64) * site.resolution
    )
    cell_x: npt.NDArray[np.float64]
    cell_y: npt.NDArray[np.float64]
    cell_x, cell_y = np.meshgrid(col_coords, row_coords)

    dx: npt.NDArray[np.float64] = cell_x - placement.position_x
    dy: npt.NDArray[np.float64] = cell_y - placement.position_y

    dist: npt.NDArray[np.float64] = np.sqrt(dx**2 + dy**2)
    range_mask: npt.NDArray[np.bool_] = (dist >= effector.min_range_m) & (
        dist <= effector.max_range_m
    )

    if effector.engagement_arc_deg >= _FULL_ARC_DEG:
        arc_mask: npt.NDArray[np.bool_] = np.ones((rows, cols), dtype=bool)
    else:
        # Compass bearing from effector to each cell: 0=north, 90=east, clockwise.
        bearing_to_cell: npt.NDArray[np.float64] = np.degrees(np.arctan2(dx, dy)) % _FULL_ARC_DEG
        half_arc: float = effector.engagement_arc_deg / 2.0
        boresight: float = placement.bearing_deg % _FULL_ARC_DEG
        # Signed angular difference, wrapped to [-180, +180].
        diff: npt.NDArray[np.float64] = (
            bearing_to_cell - boresight + 180.0
        ) % _FULL_ARC_DEG - 180.0
        arc_mask = np.abs(diff) <= half_arc

    return base.astype(bool) & range_mask & arc_mask
