"""Coverage analysis — boundary masking, coverage percentage, layer unions, and gap analysis."""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from shapely.geometry import MultiPolygon, Polygon

from salus.models.scenario import SensorPlacement
from salus.models.sensor import SensorDefinition, SensorType
from salus.models.site import SiteModel


@dataclass(frozen=True)
class GapAnalysis:
    """Result of a coverage gap analysis within a site boundary.

    Attributes:
        gap_area_m2: Total uncovered area within the boundary in square metres.
        gap_percentage: Uncovered area as a percentage of the total boundary area.
        gap_polygons: Shapely geometry representing the uncovered regions, or
            ``None`` if there are no gaps.
    """

    gap_area_m2: float
    gap_percentage: float
    gap_polygons: MultiPolygon | Polygon | None


_DEFAULT_SENSITIVITY_DBM: float = -70.0
_DEFAULT_AMBIENT_NOISE_DB: float = 0.0


def compute_layer_coverage(
    site: SiteModel,
    placements_by_type: dict[SensorType, list[tuple[SensorDefinition, SensorPlacement]]],
    *,
    sensitivity_dbm: float = _DEFAULT_SENSITIVITY_DBM,
    ambient_noise_db: float = _DEFAULT_AMBIENT_NOISE_DB,
) -> dict[SensorType, npt.NDArray[np.bool_]]:
    """Compute per-layer coverage by unioning all sensors of each type.

    For each sensor type key in *placements_by_type*, computes individual
    coverage arrays for every ``(SensorDefinition, SensorPlacement)`` pair and
    combines them with logical OR.  A cell is covered by a layer if **any**
    sensor of that type can detect it.

    Empty sensor lists produce an all-False array of shape
    ``(site.rows, site.cols)``.

    Args:
        site: The site terrain model.
        placements_by_type: Mapping from :class:`~salus.models.sensor.SensorType`
            to a list of ``(sensor_definition, placement)`` pairs.
        sensitivity_dbm: Detection threshold for RF sensors (dBm).
        ambient_noise_db: Ambient noise level for acoustic sensors (dB).

    Returns:
        Mapping from each :class:`~salus.models.sensor.SensorType` present in
        *placements_by_type* to a boolean 2D array of shape
        ``(site.rows, site.cols)`` — True where at least one sensor of that
        type provides coverage.

    Raises:
        ValueError: If any individual sensor coverage array has a shape that
            does not match ``(site.rows, site.cols)``.
    """
    from salus.engine.dispatcher import compute_sensor_coverage

    result: dict[SensorType, npt.NDArray[np.bool_]] = {}

    for sensor_type, pairs in placements_by_type.items():
        union: npt.NDArray[np.bool_] = np.zeros((site.rows, site.cols), dtype=bool)

        for sensor_def, placement in pairs:
            cov = compute_sensor_coverage(
                site,
                sensor_def,
                placement,
                sensitivity_dbm=sensitivity_dbm,
                ambient_noise_db=ambient_noise_db,
            )
            if cov is None:  # D-097: guard against unexpected None return
                raise ValueError(
                    f"compute_sensor_coverage returned None for sensor '{sensor_def.name}'"
                )
            if cov.shape != (site.rows, site.cols):
                raise ValueError(
                    f"Coverage array shape {cov.shape} does not match site shape "
                    f"({site.rows}, {site.cols}) for sensor '{sensor_def.name}'"
                )
            union |= cov.astype(bool)  # D-098: explicit cast guards non-bool dtypes

        result[sensor_type] = union

    return result


def compute_composite_coverage(
    layer_coverages: dict[SensorType, npt.NDArray[np.bool_]],
) -> npt.NDArray[np.bool_]:
    """Combine per-layer coverage maps into a single any-sensor-detects raster.

    Performs a logical OR across all layer arrays.  A cell is True in the
    composite if **any** sensor layer covers it.

    Args:
        layer_coverages: Mapping from sensor type to boolean coverage arrays
            (e.g. the output of :func:`compute_layer_coverage`). All arrays
            must have the same shape.

    Returns:
        Boolean 2D array — True where at least one sensor layer covers the cell.

    Raises:
        ValueError: If *layer_coverages* is empty, or if any array shape
            differs from the first array's shape.
    """
    if not layer_coverages:
        raise ValueError("layer_coverages must contain at least one entry")

    arrays = list(layer_coverages.values())
    reference_shape = arrays[0].shape

    for sensor_type, arr in layer_coverages.items():
        if arr.shape != reference_shape:
            raise ValueError(
                f"Layer {sensor_type!r} has shape {arr.shape}, expected {reference_shape}"
            )

    composite = np.zeros(reference_shape, dtype=bool)
    for arr in arrays:
        composite |= arr.astype(bool)

    return composite


def compute_gaps(
    composite: npt.NDArray[np.bool_],
    boundary_mask_arr: npt.NDArray[np.bool_],
) -> npt.NDArray[np.bool_]:
    """Identify uncovered cells within the site boundary.

    A gap cell is inside the boundary but not covered by any sensor.

    Args:
        composite: Boolean 2D composite coverage array (output of
            :func:`compute_composite_coverage`).
        boundary_mask_arr: Boolean 2D boundary mask — True = inside boundary
            (output of :func:`boundary_mask`).

    Returns:
        Boolean 2D array — True where a cell is inside the boundary and
        **not** covered by any sensor.

    Raises:
        ValueError: If *composite* and *boundary_mask_arr* have different shapes.
    """
    if composite.shape != boundary_mask_arr.shape:
        raise ValueError(
            f"composite shape {composite.shape} does not match "
            f"boundary_mask shape {boundary_mask_arr.shape}"
        )
    return boundary_mask_arr.astype(bool) & ~composite.astype(bool)


def build_gap_analysis(
    gap_raster: npt.NDArray[np.bool_],
    boundary_mask_arr: npt.NDArray[np.bool_],
    cell_size_m: float,
) -> GapAnalysis:
    """Compute gap statistics and convert gap raster to Shapely polygons.

    Args:
        gap_raster: Boolean 2D gap raster (output of :func:`compute_gaps`).
        boundary_mask_arr: Boolean 2D boundary mask used to compute the
            denominator for gap percentage.
        cell_size_m: Side length of each raster cell in metres. Used to
            convert cell counts to area in square metres.

    Returns:
        :class:`GapAnalysis` with total gap area (m²), gap percentage, and
        the gap geometry as a Shapely ``Polygon`` or ``MultiPolygon``
        (``None`` if there are no gaps).

    Raises:
        ValueError: If *gap_raster* and *boundary_mask_arr* have different shapes.
        ValueError: If *cell_size_m* is not finite or not positive.
    """
    import math

    from rasterio.features import shapes
    from rasterio.transform import from_origin
    from shapely.geometry import shape as shapely_shape

    if not math.isfinite(cell_size_m) or cell_size_m <= 0.0:
        raise ValueError(f"cell_size_m must be a finite positive number, got {cell_size_m}")
    if gap_raster.shape != boundary_mask_arr.shape:
        raise ValueError(
            f"gap_raster shape {gap_raster.shape} does not match "
            f"boundary_mask shape {boundary_mask_arr.shape}"
        )
    # D-101: guard against float arrays with NaN silently counting as True
    if np.issubdtype(gap_raster.dtype, np.floating) and not np.all(np.isfinite(gap_raster)):
        raise ValueError(
            "gap_raster contains non-finite values (NaN or inf); "
            "pass a boolean array from compute_gaps()"
        )

    gap_bool = gap_raster.astype(bool)
    cell_area_m2 = cell_size_m * cell_size_m
    gap_cells = int(gap_bool.sum())
    boundary_cells = int(boundary_mask_arr.astype(bool).sum())

    gap_area_m2 = float(gap_cells) * cell_area_m2

    if boundary_cells == 0:
        warnings.warn(
            "boundary_mask contains no True cells — gap_percentage will be 0.0. "
            "Check that the boundary polygon overlaps the raster extent.",
            UserWarning,
            stacklevel=2,
        )
        gap_percentage = 0.0
    else:
        gap_percentage = float(gap_cells) / float(boundary_cells) * 100.0

    gap_polygons: MultiPolygon | Polygon | None = None
    if gap_cells > 0:
        # rasterio.features.shapes requires uint8 input
        gap_uint8: npt.NDArray[np.uint8] = gap_bool.astype(np.uint8)
        # Identity transform — pixel coordinates; geometry is in pixel space
        # (area/percentage already computed from cell counts above)
        transform = from_origin(0.0, float(gap_raster.shape[0]), 1.0, 1.0)
        polys: list[Polygon] = []
        try:
            for geom_dict, value in shapes(gap_uint8, mask=gap_uint8, transform=transform):
                if value == 1:
                    geom = shapely_shape(geom_dict)
                    # D-099: repair then validate before accepting
                    if not geom.is_valid:
                        geom = geom.buffer(0)
                    if not geom.is_empty and geom.is_valid:
                        polys.append(geom)  # type: ignore[arg-type]
        except Exception as exc:  # D-100: surface vectorisation failures with context
            raise RuntimeError(
                f"Gap vectorisation failed for raster shape {gap_raster.shape} "
                f"with {gap_cells} gap cells: {exc}"
            ) from exc

        if len(polys) == 1:
            gap_polygons = polys[0]
        elif len(polys) > 1:
            gap_polygons = MultiPolygon(polys)
        else:
            # D-102: polys empty despite non-zero gap_cells — warn rather than silently
            # return an inconsistent GapAnalysis (area > 0, polygons = None)
            warnings.warn(
                f"Gap vectorisation produced no valid polygons for {gap_cells} gap "
                "cells — gap_polygons will be None. Cell count and area are still "
                "correct; geometry may be degenerate (e.g. single-pixel diagonal).",
                UserWarning,
                stacklevel=2,
            )

    return GapAnalysis(
        gap_area_m2=gap_area_m2,
        gap_percentage=gap_percentage,
        gap_polygons=gap_polygons,
    )


def boundary_mask(site: SiteModel, boundary: Polygon | MultiPolygon) -> npt.NDArray[np.bool_]:
    """Rasterize a boundary polygon to a boolean mask matching the site grid.

    Cells whose centre falls inside the boundary are True; all others False.

    Args:
        site: The site terrain model (defines the raster grid dimensions and transform).
        boundary: The site boundary polygon in the same CRS as the site DEM.

    Returns:
        Boolean 2D array with shape ``(site.rows, site.cols)``.
    """
    from rasterio.features import rasterize
    from rasterio.transform import from_origin
    from shapely.geometry import mapping

    transform = from_origin(site.origin_x, site.origin_y, site.resolution, site.resolution)
    raw: npt.NDArray[np.uint8] = rasterize(
        shapes=[(mapping(boundary), 1)],
        out_shape=(site.rows, site.cols),
        transform=transform,
        fill=0,
        dtype="uint8",
    )
    return raw.astype(bool)


def clip_coverage_to_boundary(
    coverage: npt.NDArray[np.bool_],
    site: SiteModel,
    boundary: Polygon | MultiPolygon,
) -> npt.NDArray[np.bool_]:
    """Mask a coverage array to the site boundary — cells outside are set to False.

    Args:
        coverage: Boolean 2D array from :func:`~salus.engine.viewshed.compute_viewshed`
            or :func:`~salus.engine.viewshed.clip_viewshed_to_sensor`.
        site: The site terrain model.
        boundary: The site boundary polygon in the same CRS as the site DEM.

    Returns:
        Boolean 2D array — True only where coverage is True **and** inside boundary.

    Raises:
        ValueError: If ``coverage`` shape does not match ``site.dem`` shape.
    """
    if coverage.ndim != 2:
        raise ValueError(f"coverage must be a 2D array, got {coverage.ndim}D")
    if coverage.shape != site.dem.shape:
        raise ValueError(
            f"coverage shape {coverage.shape} does not match site.dem shape {site.dem.shape}"
        )
    mask = boundary_mask(site, boundary)
    return coverage.astype(bool) & mask


def coverage_percentage(
    coverage: npt.NDArray[np.bool_],
    mask: npt.NDArray[np.bool_] | None = None,
) -> float:
    """Compute the coverage percentage, optionally restricted to a boundary mask.

    Args:
        coverage: Boolean 2D array — True = covered.
        mask: Optional boolean mask (e.g. from :func:`boundary_mask`). When
            provided the denominator is the count of True cells in ``mask``;
            only masked cells are counted in the numerator. When ``None`` the
            entire raster is used as the denominator.

    Returns:
        Coverage percentage in the range [0.0, 100.0].
    """
    cov_bool = coverage.astype(bool)

    if mask is not None:
        denominator = int(mask.sum())
        if denominator == 0:
            warnings.warn(
                "boundary mask contains no True cells — returning 0.0 coverage. "
                "Check that the boundary polygon overlaps the raster extent.",
                UserWarning,
                stacklevel=2,
            )
            return 0.0
        numerator = int((cov_bool & mask).sum())
    else:
        denominator = cov_bool.size
        numerator = int(cov_bool.sum())

    if denominator == 0:
        return 0.0
    return float(numerator) / float(denominator) * 100.0
