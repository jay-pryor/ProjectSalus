"""Coverage analysis — boundary masking and coverage percentage computation."""

from __future__ import annotations

import warnings

import numpy as np
import numpy.typing as npt
from shapely.geometry import MultiPolygon, Polygon

from salus.models.site import SiteModel


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
