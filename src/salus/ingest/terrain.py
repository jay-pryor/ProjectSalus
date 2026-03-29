"""Terrain data ingestion — load DEM/DSM from GeoTIFF."""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import Resampling
from rasterio.warp import reproject as warp_reproject

from salus.models.site import SiteModel


def load_dem(path: str | Path, dsm_path: str | Path | None = None) -> SiteModel:
    """Load a DEM (and optionally DSM) from GeoTIFF files.

    If the DSM CRS differs from the DEM CRS, the DSM is reprojected to match
    the DEM grid — a :class:`UserWarning` is emitted when this occurs.

    Args:
        path: Path to the DEM GeoTIFF.
        dsm_path: Optional path to a DSM GeoTIFF. If the DSM CRS matches the
            DEM, its shape must also match. If the CRS differs, the DSM is
            reprojected to the DEM grid automatically.

    Returns:
        A :class:`~salus.models.site.SiteModel` with terrain data loaded.

    Raises:
        FileNotFoundError: If the DEM or DSM file does not exist.
        ValueError: If the DEM (or DSM) has no CRS defined, or if the DSM
            shape does not match the DEM when both share the same CRS.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"DEM not found: {path}")

    with rasterio.open(path) as src:
        if src.crs is None:
            raise ValueError(
                f"DEM has no CRS defined — cannot load without a coordinate "
                f"reference system: {path}"
            )

        dem = src.read(1).astype(np.float64)
        transform = src.transform
        resolution = transform.a  # pixel width in CRS units
        origin_x = transform.c  # top-left x
        origin_y = transform.f  # top-left y

        crs_epsg: int | None = None
        try:
            crs_epsg = src.crs.to_epsg()
        except Exception as exc:
            warnings.warn(
                f"Could not parse EPSG from CRS {src.crs!r}: {exc}. "
                "crs_epsg will be None — coordinate reprojection will not be available.",
                stacklevel=2,
            )

        # Handle nodata — skip equality check when nodata is NaN (NaN != NaN in IEEE 754)
        if src.nodata is not None and not np.isnan(src.nodata):
            nodata_mask = dem == src.nodata
            if nodata_mask.any():
                dem[nodata_mask] = np.nan

        dem_crs = src.crs
        dem_transform = src.transform
        dem_shape: tuple[int, int] = (src.height, src.width)

    dsm: np.ndarray | None = None
    if dsm_path is not None:
        dsm_path = Path(dsm_path)
        if not dsm_path.exists():
            raise FileNotFoundError(f"DSM not found: {dsm_path}")

        with rasterio.open(dsm_path) as src:
            if src.crs is None:
                raise ValueError(
                    f"DSM has no CRS defined — cannot load without a coordinate "
                    f"reference system: {dsm_path}"
                )

            dsm_raw = src.read(1).astype(np.float64)
            # Convert nodata to NaN before any reprojection
            if src.nodata is not None and not np.isnan(src.nodata):
                nodata_mask = dsm_raw == src.nodata
                if nodata_mask.any():
                    dsm_raw[nodata_mask] = np.nan

            # Use EPSG codes for CRS comparison when available (avoids WKT false-negatives);
            # fall back to rasterio WKT comparison when either code is unavailable.
            try:
                dsm_epsg = src.crs.to_epsg()
            except Exception:
                dsm_epsg = None

            if dsm_epsg is not None and crs_epsg is not None:
                crs_mismatch = dsm_epsg != crs_epsg
            else:
                crs_mismatch = src.crs != dem_crs

            if crs_mismatch:
                warnings.warn(
                    f"DSM CRS ({src.crs.to_string()}) does not match DEM CRS "
                    f"({dem_crs.to_string()}); reprojecting DSM to match DEM — "
                    "verify the DSM covers the same geographic area.",
                    UserWarning,
                    stacklevel=2,
                )
                dsm = _reproject_array(
                    src_array=dsm_raw,
                    src_crs=src.crs,
                    src_transform=src.transform,
                    dst_crs=dem_crs,
                    dst_transform=dem_transform,
                    dst_shape=dem_shape,
                )
                if np.all(np.isnan(dsm)):
                    raise ValueError(
                        f"DSM reprojection produced an entirely NaN result — the DSM "
                        f"may not overlap the DEM extent: {dsm_path}"
                    )
            else:
                dsm = dsm_raw
                if dsm.shape != dem.shape:
                    raise ValueError(f"DSM shape {dsm.shape} does not match DEM shape {dem.shape}")

    return SiteModel(
        dem=dem,
        dsm=dsm,
        resolution=abs(resolution),
        origin_x=origin_x,
        origin_y=origin_y,
        crs_epsg=crs_epsg,
    )


def _reproject_array(
    src_array: np.ndarray,
    src_crs: rasterio.crs.CRS,
    src_transform: rasterio.transform.Affine,
    dst_crs: rasterio.crs.CRS,
    dst_transform: rasterio.transform.Affine,
    dst_shape: tuple[int, int],
) -> np.ndarray:
    """Reproject a 2D float array to a target CRS, transform, and shape.

    Cells in the destination that fall outside the source extent are filled
    with NaN. Bilinear resampling is used.
    """
    dst = np.full(dst_shape, np.nan, dtype=np.float64)
    warp_reproject(
        source=src_array,
        destination=dst,
        src_transform=src_transform,
        src_crs=src_crs,
        dst_transform=dst_transform,
        dst_crs=dst_crs,
        resampling=Resampling.bilinear,
        src_nodata=np.nan,
        dst_nodata=np.nan,
    )
    return dst
