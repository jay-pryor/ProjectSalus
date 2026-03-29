"""Terrain data ingestion — load DEM/DSM from GeoTIFF."""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import rasterio

from salus.models.site import SiteModel


def load_dem(path: str | Path, dsm_path: str | Path | None = None) -> SiteModel:
    """Load a DEM (and optionally DSM) from GeoTIFF files.

    Args:
        path: Path to the DEM GeoTIFF.
        dsm_path: Optional path to a DSM GeoTIFF. Must match DEM extent and resolution.

    Returns:
        A SiteModel with terrain data loaded.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"DEM not found: {path}")

    with rasterio.open(path) as src:
        dem = src.read(1).astype(np.float64)
        transform = src.transform
        resolution = transform.a  # pixel width in CRS units
        origin_x = transform.c  # top-left x
        origin_y = transform.f  # top-left y

        crs_epsg = None
        if src.crs is not None:
            try:
                crs_epsg = src.crs.to_epsg()
            except Exception as exc:
                warnings.warn(
                    f"Could not parse EPSG from CRS {src.crs!r}: {exc}. "
                    "crs_epsg will be None — coordinate reprojection will not be available.",
                    stacklevel=2,
                )

        # Handle nodata
        if src.nodata is not None:
            nodata_mask = dem == src.nodata
            if nodata_mask.any():
                dem[nodata_mask] = np.nan

    dsm = None
    if dsm_path is not None:
        dsm_path = Path(dsm_path)
        if not dsm_path.exists():
            raise FileNotFoundError(f"DSM not found: {dsm_path}")

        with rasterio.open(dsm_path) as src:
            dsm = src.read(1).astype(np.float64)
            if dsm.shape != dem.shape:
                raise ValueError(f"DSM shape {dsm.shape} does not match DEM shape {dem.shape}")
            if src.nodata is not None:
                nodata_mask = dsm == src.nodata
                if nodata_mask.any():
                    dsm[nodata_mask] = np.nan

    return SiteModel(
        dem=dem,
        dsm=dsm,
        resolution=abs(resolution),
        origin_x=origin_x,
        origin_y=origin_y,
        crs_epsg=crs_epsg,
    )
