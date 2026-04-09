"""Terrain data ingestion — load DEM/DSM from GeoTIFF."""

from __future__ import annotations

import logging
import warnings
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import Resampling
from rasterio.warp import reproject as warp_reproject

from salus.models.site import SiteModel

_log = logging.getLogger(__name__)


def load_dem(
    path: str | Path,
    dsm_path: str | Path | None = None,
    canopy_path: str | Path | None = None,
) -> SiteModel:
    """Load a DEM (and optionally DSM/CHM) from GeoTIFF files.

    If the DSM CRS differs from the DEM CRS, the DSM is reprojected to match
    the DEM grid — a :class:`UserWarning` is emitted when this occurs.

    Args:
        path: Path to the DEM GeoTIFF.
        dsm_path: Optional path to a DSM GeoTIFF. If the DSM CRS matches the
            DEM, its shape must also match. If the CRS differs, the DSM is
            reprojected to the DEM grid automatically.
        canopy_path: Optional path to a Canopy Height Model GeoTIFF (CHM =
            DSM − DEM).  When provided, the CHM array is attached to
            ``SiteModel.canopy_height_m``.  Must have the same shape as the
            DEM when both share the same CRS.

    Returns:
        A :class:`~salus.models.site.SiteModel` with terrain data loaded.

    Raises:
        FileNotFoundError: If the DEM, DSM, or CHM file does not exist.
        ValueError: If the DEM (or DSM/CHM) has no CRS defined, or if the
            DSM/CHM shape does not match the DEM when both share the same CRS.
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

    canopy: np.ndarray | None = None
    if canopy_path is not None:
        canopy_path = Path(canopy_path)
        if not canopy_path.exists():
            raise FileNotFoundError(f"Canopy Height Model not found: {canopy_path}")

        with rasterio.open(canopy_path) as src:
            if src.crs is None:
                raise ValueError(
                    f"CHM has no CRS defined — cannot load without a coordinate "
                    f"reference system: {canopy_path}"
                )
            canopy_raw = src.read(1).astype(np.float64)
            if src.nodata is not None and not np.isnan(src.nodata):
                nodata_mask = canopy_raw == src.nodata
                if nodata_mask.any():
                    canopy_raw[nodata_mask] = np.nan

            # D-244: validate CHM CRS matches DEM CRS to prevent silent grid misalignment.
            try:
                chm_epsg = src.crs.to_epsg()
            except Exception:
                chm_epsg = None

            if chm_epsg is not None and crs_epsg is not None:
                chm_crs_mismatch = chm_epsg != crs_epsg
            else:
                chm_crs_mismatch = src.crs != dem_crs

            if chm_crs_mismatch:
                warnings.warn(
                    f"CHM CRS ({src.crs.to_string()}) does not match DEM CRS "
                    f"({dem_crs.to_string()}); CHM cells may not align with DEM grid — "
                    "verify the CHM was derived from the same source as the DEM.",
                    UserWarning,
                    stacklevel=2,
                )

        if canopy_raw.shape != dem.shape:
            raise ValueError(f"CHM shape {canopy_raw.shape} does not match DEM shape {dem.shape}")
        canopy = canopy_raw

    return SiteModel(
        dem=dem,
        dsm=dsm,
        canopy_height_m=canopy,
        resolution=abs(resolution),
        origin_x=origin_x,
        origin_y=origin_y,
        crs_epsg=crs_epsg,
    )


def derive_canopy_height_model(
    dem_path: str | Path,
    dsm_path: str | Path,
    output_path: str | Path,
) -> np.ndarray:
    """Derive a Canopy Height Model (CHM) from DEM and DSM GeoTIFFs.

    Computes CHM = DSM − DEM, clamped to [0, ∞).  Negative values arise from
    minor DEM/DSM registration offsets in real LiDAR products — they are clamped
    to zero and a warning is emitted reporting the count of affected cells.

    The result is written as a single-band float64 GeoTIFF to *output_path* and
    also returned as a NumPy array.

    Args:
        dem_path: Path to the DEM GeoTIFF.
        dsm_path: Path to the DSM GeoTIFF.  Must have the same shape and CRS as
            the DEM.
        output_path: Destination path for the output CHM GeoTIFF.  Parent
            directory must already exist.

    Returns:
        2D float64 NumPy array of canopy heights in metres (>= 0).

    Raises:
        FileNotFoundError: If either input file does not exist, or if the output
            parent directory does not exist.
        ValueError: If the DEM and DSM shapes do not match.
    """
    dem_path = Path(dem_path)
    dsm_path = Path(dsm_path)
    output_path = Path(output_path)

    if not dem_path.exists():
        raise FileNotFoundError(f"DEM not found: {dem_path}")
    if not dsm_path.exists():
        raise FileNotFoundError(f"DSM not found: {dsm_path}")
    if not output_path.parent.exists():
        raise FileNotFoundError(f"Output directory does not exist: {output_path.parent}")

    with rasterio.open(dem_path) as dem_src:
        dem_arr = dem_src.read(1).astype(np.float64)
        if dem_src.nodata is not None and not np.isnan(dem_src.nodata):
            dem_arr[dem_arr == dem_src.nodata] = np.nan
        profile = dem_src.profile.copy()
        dem_crs = dem_src.crs

    with rasterio.open(dsm_path) as dsm_src:
        dsm_arr = dsm_src.read(1).astype(np.float64)
        if dsm_src.nodata is not None and not np.isnan(dsm_src.nodata):
            dsm_arr[dsm_arr == dsm_src.nodata] = np.nan
        dsm_crs = dsm_src.crs

    # D-243: validate that DEM and DSM share the same CRS before subtraction.
    if dem_crs is not None and dsm_crs is not None and dem_crs != dsm_crs:
        raise ValueError(
            f"DEM CRS ({dem_crs.to_string()}) does not match DSM CRS "
            f"({dsm_crs.to_string()}) — cannot derive CHM from mismatched grids. "
            "Reproject to a common CRS before calling derive_canopy_height_model."
        )

    if dem_arr.shape != dsm_arr.shape:
        raise ValueError(
            f"DEM shape {dem_arr.shape} does not match DSM shape {dsm_arr.shape} — "
            "both must be the same grid to derive a CHM"
        )

    chm = dsm_arr - dem_arr

    negative_cells = int((chm < 0).sum())
    if negative_cells > 0:
        warnings.warn(
            f"CHM has {negative_cells} negative cell(s) from DEM/DSM misregistration — "
            "clamping to zero.",
            UserWarning,
            stacklevel=2,
        )
        _log.warning(
            "CHM: %d cell(s) clamped from negative to zero (DEM/DSM registration offset)",
            negative_cells,
        )
    chm = np.where(chm < 0, 0.0, chm)

    profile.update(dtype=rasterio.float64, count=1, nodata=np.nan)
    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(chm.astype(np.float64), 1)

    _log.info(
        "CHM written to %s — max canopy height %.2f m",
        output_path,
        float(np.nanmax(chm)) if not np.all(np.isnan(chm)) else 0.0,
    )
    return chm


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
