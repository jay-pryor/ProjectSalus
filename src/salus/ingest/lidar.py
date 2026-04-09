"""LiDAR point cloud ingestion via PDAL (S12).

Provides three public functions:

- :func:`load_point_cloud` — load a LAS/LAZ file and return an executed PDAL
  pipeline.
- :func:`point_cloud_to_dem` — classify ground returns (SMRF) and rasterise
  to a GeoTIFF DEM.
- :func:`point_cloud_to_dsm` — rasterise first-return points to a GeoTIFF
  DSM capturing surface features (buildings, vegetation).

PDAL is an optional dependency installed via conda-forge (see pyproject.toml).
All three functions raise :class:`ImportError` with installation instructions
when PDAL is not available.  Input validation (path checks, resolution guards)
is performed before the PDAL import so those errors surface in all environments.
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import numpy.typing as npt

if TYPE_CHECKING:
    from salus.models.site import SiteModel

_log = logging.getLogger(__name__)

# Supported LiDAR file extensions.
_SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".las", ".laz"})

# GDAL compression option written into output GeoTIFFs.
_GDAL_COMPRESS_OPT: str = "COMPRESS=DEFLATE"

# Nodata sentinel written to GeoTIFFs; replaced by NaN on load.
_NODATA_VALUE: float = -9999.0


def _require_pdal() -> Any:
    """Import and return the ``pdal`` module, or raise ImportError.

    Raises:
        ImportError: If PDAL is not installed, with conda-forge install hint.
    """
    try:
        import pdal  # type: ignore[import-not-found]

        return pdal
    except ImportError as exc:
        raise ImportError(
            "pdal is required for LiDAR ingestion but is not installed. "
            "Install via conda-forge: conda install -c conda-forge pdal python-pdal"
        ) from exc


def load_point_cloud(path: str | Path) -> Any:
    """Load a LAS/LAZ point cloud and return the executed PDAL pipeline.

    Reads header metadata (CRS, point count, bounds) and validates that the
    CRS is defined.

    Args:
        path: Path to a ``.las`` or ``.laz`` file.

    Returns:
        Executed ``pdal.Pipeline`` with all point arrays loaded.  Access
        point data via ``pipeline.arrays`` (list of numpy structured arrays)
        and metadata via ``pipeline.metadata``.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file extension is not ``.las`` or ``.laz``, or if
            the point cloud has no CRS defined.
        RuntimeError: If the PDAL pipeline fails to execute.
        ImportError: If PDAL is not installed.
    """
    path = Path(path).resolve()

    if path.suffix.lower() not in _SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported LiDAR format: {path.suffix!r}. "
            f"Supported extensions: {sorted(_SUPPORTED_EXTENSIONS)}"
        )

    if not path.exists():
        raise FileNotFoundError(f"LiDAR file not found: {path}")

    pdal = _require_pdal()

    _log.info("Loading point cloud from %s", path)

    pipeline_json = json.dumps({"pipeline": [str(path)]})
    pipeline = pdal.Pipeline(pipeline_json)

    try:
        pipeline.execute()
    except Exception as exc:
        raise RuntimeError(f"PDAL failed to load point cloud from {path}: {exc}") from exc

    metadata = json.loads(pipeline.metadata)
    _validate_point_cloud_crs(metadata, path)

    total_points = sum(len(arr) for arr in pipeline.arrays) if pipeline.arrays else 0

    # D-240: raise on empty point cloud before returning — zero points produces
    # degenerate DEM/DSM rasters that silently enter the simulation.
    if total_points == 0:
        raise ValueError(
            f"Point cloud contains no points: {path.name}. "
            "Check that the file is not empty and that the LAS/LAZ header is valid."
        )

    # D-242: read and log header bounds (minx, miny, minz, maxx, maxy, maxz).
    bounds = _extract_bounds(metadata)
    if bounds is not None:
        _log.info(
            "Point cloud loaded: %d point(s) from %s — "
            "bounds X [%.2f, %.2f] Y [%.2f, %.2f] Z [%.2f, %.2f]",
            total_points,
            path.name,
            bounds[0],
            bounds[3],
            bounds[1],
            bounds[4],
            bounds[2],
            bounds[5],
        )
    else:
        _log.info(
            "Point cloud loaded: %d point(s) from %s (bounds not available in metadata)",
            total_points,
            path.name,
        )

    return pipeline


def point_cloud_to_dem(
    pipeline: Any,
    resolution_m: float,
    output_path: str | Path,
) -> "SiteModel":
    """Convert a loaded point cloud to a DEM using SMRF ground classification.

    Applies PDAL's SMRF (Simple Morphological Filter) to isolate ground-class
    points, rasterises them to a GeoTIFF via ``writers.gdal``, then fills any
    nodata cells (no ground returns) via nearest-neighbour interpolation.

    Args:
        pipeline: Executed ``pdal.Pipeline`` as returned by
            :func:`load_point_cloud`.
        resolution_m: Output raster resolution in metres.  Must be a finite
            positive number.
        output_path: Path to write the output DEM GeoTIFF.  Parent directory
            must already exist.

    Returns:
        :class:`~salus.models.site.SiteModel` loaded from the written GeoTIFF.

    Raises:
        ValueError: If *resolution_m* is not a finite positive number.
        FileNotFoundError: If the parent directory of *output_path* does not
            exist, or if PDAL completes without writing the output file.
        RuntimeError: If PDAL ground classification or rasterisation fails.
        ImportError: If PDAL is not installed.
    """
    if not math.isfinite(resolution_m) or resolution_m <= 0.0:
        raise ValueError(f"resolution_m must be a finite positive number, got {resolution_m}")

    output_path = Path(output_path).resolve()
    _validate_output_parent(output_path)

    pdal = _require_pdal()

    _log.info(
        "Converting point cloud to DEM at %.2f m resolution → %s",
        resolution_m,
        output_path,
    )

    pipeline_json = json.dumps(
        [
            {"type": "filters.smrf"},
            # Keep only ground-classified points (ASPRS class 2).
            {"type": "filters.range", "limits": "Classification[2:2]"},
            {
                "type": "writers.gdal",
                "filename": str(output_path),
                "resolution": resolution_m,
                "output_type": "mean",
                "gdalopts": _GDAL_COMPRESS_OPT,
                "nodata": _NODATA_VALUE,
            },
        ]
    )

    try:
        dem_pipeline = pdal.Pipeline(pipeline_json, arrays=pipeline.arrays)
        dem_pipeline.execute()
    except Exception as exc:
        raise RuntimeError(
            f"PDAL DEM rasterisation failed for output {output_path}: {exc}"
        ) from exc

    if not output_path.exists():
        raise FileNotFoundError(
            f"PDAL completed without error but output DEM was not written: {output_path}"
        )

    _log.info("DEM written to %s", output_path)

    from salus.ingest.terrain import load_dem

    site = load_dem(output_path)

    if np.any(np.isnan(site.dem)):
        n_nodata = int(np.isnan(site.dem).sum())
        _log.warning(
            "DEM has %d nodata cell(s) after rasterisation — "
            "filling via nearest-neighbour interpolation.",
            n_nodata,
        )
        filled = _fill_nodata_nearest(site.dem)
        site = site.model_copy(update={"dem": filled})

    return site


def point_cloud_to_dsm(
    pipeline: Any,
    resolution_m: float,
    output_path: str | Path,
) -> "SiteModel":
    """Convert a loaded point cloud to a DSM using first-return rasterisation.

    Filters to first-return points and rasterises the highest elevation per
    cell, capturing buildings, vegetation, and other above-ground features.

    Args:
        pipeline: Executed ``pdal.Pipeline`` as returned by
            :func:`load_point_cloud`.
        resolution_m: Output raster resolution in metres.  Must be a finite
            positive number.
        output_path: Path to write the output DSM GeoTIFF.  Parent directory
            must already exist.

    Returns:
        :class:`~salus.models.site.SiteModel` loaded from the written GeoTIFF.

    Raises:
        ValueError: If *resolution_m* is not a finite positive number.
        FileNotFoundError: If the parent directory of *output_path* does not
            exist, or if PDAL completes without writing the output file.
        RuntimeError: If PDAL rasterisation fails.
        ImportError: If PDAL is not installed.
    """
    if not math.isfinite(resolution_m) or resolution_m <= 0.0:
        raise ValueError(f"resolution_m must be a finite positive number, got {resolution_m}")

    output_path = Path(output_path).resolve()
    _validate_output_parent(output_path)

    pdal = _require_pdal()

    _log.info(
        "Converting point cloud to DSM at %.2f m resolution → %s",
        resolution_m,
        output_path,
    )

    # Filter to first returns (ReturnNumber == 1) — highest point per cell.
    pipeline_json = json.dumps(
        [
            {"type": "filters.range", "limits": "ReturnNumber[1:1]"},
            {
                "type": "writers.gdal",
                "filename": str(output_path),
                "resolution": resolution_m,
                "output_type": "max",
                "gdalopts": _GDAL_COMPRESS_OPT,
                "nodata": _NODATA_VALUE,
            },
        ]
    )

    try:
        dsm_pipeline = pdal.Pipeline(pipeline_json, arrays=pipeline.arrays)
        dsm_pipeline.execute()
    except Exception as exc:
        raise RuntimeError(
            f"PDAL DSM rasterisation failed for output {output_path}: {exc}"
        ) from exc

    if not output_path.exists():
        raise FileNotFoundError(
            f"PDAL completed without error but output DSM was not written: {output_path}"
        )

    _log.info("DSM written to %s", output_path)

    from salus.ingest.terrain import load_dem

    # D-238: apply the same nodata-fill step as point_cloud_to_dem so that
    # cells with no first-return points do not propagate NaN into viewshed arithmetic.
    site = load_dem(output_path)

    if np.any(np.isnan(site.dsm if site.dsm is not None else site.dem)):
        surface = site.dsm if site.dsm is not None else site.dem
        n_nodata = int(np.isnan(surface).sum())
        _log.warning(
            "DSM has %d nodata cell(s) after rasterisation — "
            "filling via nearest-neighbour interpolation.",
            n_nodata,
        )
        filled = _fill_nodata_nearest(surface)
        update_key = "dsm" if site.dsm is not None else "dem"
        site = site.model_copy(update={update_key: filled})

    return site


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_bounds(
    metadata: dict[str, Any],
) -> tuple[float, float, float, float, float, float] | None:
    """Extract XYZ bounding box from PDAL metadata.

    Returns a 6-tuple ``(minx, miny, minz, maxx, maxy, maxz)`` when available,
    or ``None`` if the metadata does not contain recognisable bounds fields.
    PDAL's ``readers.las`` block exposes ``minx``/``maxx`` etc. at the top
    level of the reader entry.
    """
    readers_block = metadata.get("metadata", {})
    for key, value in readers_block.items():
        if "readers" not in key:
            continue
        entries: list[dict[str, Any]] = value if isinstance(value, list) else [value]
        for entry in entries:
            try:
                return (
                    float(entry["minx"]),
                    float(entry["miny"]),
                    float(entry["minz"]),
                    float(entry["maxx"]),
                    float(entry["maxy"]),
                    float(entry["maxz"]),
                )
            except (KeyError, TypeError, ValueError):
                continue
    return None


def _validate_point_cloud_crs(metadata: dict[str, Any], path: Path) -> None:
    """Validate that the point cloud has a CRS defined in its PDAL metadata.

    PDAL exposes the CRS via ``comp_spatialreference`` in the reader metadata
    block.  An empty or missing value means the file has no embedded CRS.

    Raises:
        ValueError: If no CRS is found in the metadata.
    """
    readers_block = metadata.get("metadata", {})
    for key, value in readers_block.items():
        if "readers" not in key:
            continue
        entries: list[dict[str, Any]] = value if isinstance(value, list) else [value]
        for entry in entries:
            srs: str = (
                entry.get("comp_spatialreference", "") or entry.get("spatialreference", "")
            ).strip()
            if srs:
                return

    raise ValueError(
        f"Point cloud has no CRS defined — cannot process without a coordinate "
        f"reference system: {path}"
    )


def _validate_output_parent(path: Path) -> None:
    """Validate that the parent directory of *path* exists.

    Raises:
        FileNotFoundError: If the parent directory does not exist.
    """
    if not path.parent.exists():
        raise FileNotFoundError(f"Output directory does not exist: {path.parent}")


def _fill_nodata_nearest(array: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """Fill NaN cells in a 2D array using nearest-neighbour interpolation.

    For each NaN cell, assigns the value of the nearest non-NaN cell
    (Euclidean distance).  Uses :func:`scipy.ndimage.distance_transform_edt`.

    Args:
        array: 2D float array.  Cells where ``np.isnan(array)`` is True are
            replaced.

    Returns:
        Copy of *array* with all NaN cells filled.  Returns the original array
        unchanged if no NaN cells are present.

    Raises:
        ValueError: If every cell is NaN — there are no valid source values to
            interpolate from.  This indicates that ground classification
            produced zero ground returns for DEM, or zero first returns for
            DSM.
    """
    mask: npt.NDArray[np.bool_] = np.isnan(array)
    if not mask.any():
        return array.copy()

    # D-237: guard against all-NaN input before calling distance_transform_edt.
    # When mask is entirely True, the EDT returns indices into the source array
    # which is itself all-NaN — the fill is a no-op and the caller receives an
    # all-NaN array without any error.
    if mask.all():
        raise ValueError(
            "Cannot fill nodata: every cell in the array is NaN. "
            "Ground classification may have produced zero ground returns (DEM) "
            "or zero first-return points (DSM) for this point cloud."
        )

    from scipy.ndimage import distance_transform_edt  # type: ignore[import-untyped]

    filled = array.copy()
    # return_distances=False avoids allocating a full float64 distance array
    # that is not needed for nearest-neighbour value assignment.
    indices: npt.NDArray[np.intp] = distance_transform_edt(
        mask, return_distances=False, return_indices=True
    )
    row_idx: npt.NDArray[np.intp] = indices[0]
    col_idx: npt.NDArray[np.intp] = indices[1]
    filled[mask] = array[row_idx[mask], col_idx[mask]]
    return filled
