#!/usr/bin/env python3
"""Build clipped seasonal Sentinel-2 median composites and spectral indices.

This command processes item URLs from a discovery manifest. It writes NDVI,
NDBI, and bare-soil index GeoTIFFs only; it does not threshold candidates or
claim that any output is a dumpsite detection.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
from datetime import UTC, date, datetime
from pathlib import Path

import geopandas as gpd
import numpy as np
import planetary_computer
import rasterio
import stackstac
import xarray as xr
from pystac import Item
from rasterio.crs import CRS
from rasterio.features import geometry_mask
from rasterio.transform import from_bounds
from shapely.geometry import mapping


ASSETS = ["B02", "B04", "B08", "B11", "SCL"]
CLEAR_SCL_CLASSES = [4, 5, 6]
INDEX_FORMULAS = {
    "NDVI": "(B08 - B04) / (B08 + B04)",
    "NDBI": "(B11 - B08) / (B11 + B08)",
    "BSI": "((B11 + B04) - (B08 + B02)) / ((B11 + B04) + (B08 + B02))",
}


def parse_period(value: str) -> tuple[str, date, date]:
    try:
        name, date_range = value.split("=", 1)
        start_text, end_text = date_range.split("/", 1)
        start, end = date.fromisoformat(start_text), date.fromisoformat(end_text)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "period format must be NAME=YYYY-MM-DD/YYYY-MM-DD"
        ) from error

    valid_name = all(
        character in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
        for character in name
    )
    if not name.strip() or not valid_name or start > end:
        raise argparse.ArgumentTypeError(
            "period name must use letters, digits, '-' or '_' and start must not follow end"
        )
    return name.strip(), start, end


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--aoi", required=True, type=Path)
    parser.add_argument(
        "--period",
        action="append",
        required=True,
        type=parse_period,
        help="Repeat as NAME=YYYY-MM-DD/YYYY-MM-DD for each comparison period",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).parent / "data/processed/composites",
    )
    return parser.parse_args()


def read_inputs(manifest_path: Path, aoi_path: Path):
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = manifest.get("items", [])
    if not records or any(not record.get("item_url") for record in records):
        raise ValueError("manifest has no item URLs; run discovery with the current CLI first")

    frame = gpd.read_file(aoi_path)
    if frame.empty or frame.geometry.isna().all() or frame.crs is None:
        raise ValueError("AOI must be a non-empty polygon file with a declared CRS")

    geometry = frame.to_crs("EPSG:4326").geometry.union_all()
    if geometry.is_empty or not geometry.is_valid or geometry.geom_type not in {
        "Polygon",
        "MultiPolygon",
    }:
        raise ValueError("AOI must contain valid polygon geometry")

    projected_crs = frame.estimate_utm_crs()
    if projected_crs is None:
        raise ValueError("Could not estimate a local UTM CRS for the AOI")

    projected = frame.to_crs(projected_crs)
    projected_geometry = projected.geometry.union_all()
    epsg = projected.crs.to_epsg()
    if epsg is None:
        raise ValueError("Could not determine an EPSG code for the AOI's estimated UTM CRS")

    return manifest, records, projected_geometry, epsg, projected.total_bounds


def load_items(records: list[dict], start: date, end: date) -> list[Item]:
    selected = []
    for record in records:
        value = record.get("datetime")
        if not value:
            raise ValueError(f"catalog item {record.get('id', '<unknown>')} has no datetime")
        observed_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if start <= observed_at.date() <= end:
            item = Item.from_file(record["item_url"])
            planetary_computer.sign_inplace(item)
            selected.append(item)

    return selected


def make_indices(
    items: list[Item], epsg: int, bounds: np.ndarray
) -> tuple[xr.DataArray, xr.DataArray]:
    missing_assets = sorted(
        {asset for item in items for asset in ASSETS if asset not in item.assets}
    )
    if missing_assets:
        raise ValueError(f"selected STAC items are missing required assets: {missing_assets}")

    stack = stackstac.stack(
        items,
        assets=ASSETS,
        epsg=epsg,
        resolution=20,
        bounds=tuple(float(value) for value in bounds),
        chunksize=1024,
        dtype="float32",
        rescale=True,
    )

    clear_pixels = stack.sel(band="SCL").isin(CLEAR_SCL_CLASSES)
    reflectance = stack.sel(band=["B02", "B04", "B08", "B11"]).where(clear_pixels)
    median = reflectance.median(dim="time", skipna=True)
    blue, red, nir, swir = (
        median.sel(band=band) for band in ["B02", "B04", "B08", "B11"]
    )

    def safe_ratio(numerator: xr.DataArray, denominator: xr.DataArray) -> xr.DataArray:
        return (numerator / denominator).where(abs(denominator) > 1e-6)

    indices = xr.concat(
        [
            safe_ratio(nir - red, nir + red),
            safe_ratio(swir - nir, swir + nir),
            safe_ratio((swir + red) - (nir + blue), (swir + red) + (nir + blue)),
        ],
        dim=xr.IndexVariable("index", list(INDEX_FORMULAS)),
    ).astype("float32")
    return indices, stack


def write_period(
    name: str,
    start: date,
    end: date,
    manifest_path: Path,
    manifest: dict,
    items: list[Item],
    projected_geometry,
    epsg: int,
    bounds: np.ndarray,
    output_dir: Path,
    aoi_path: Path,
) -> dict:
    if not items:
        raise ValueError(f"period {name!r} has no catalog items in the discovery manifest")

    index_array, reference_stack = make_indices(items, epsg, bounds)
    output_bounds = stackstac.array_bounds(reference_stack)
    indices = index_array.compute()
    height, width = indices.shape[-2:]
    transform = from_bounds(*output_bounds, width=width, height=height)
    inside_aoi = geometry_mask(
        [mapping(projected_geometry)],
        out_shape=(height, width),
        transform=transform,
        invert=True,
    )
    values = indices.values
    values[:, ~inside_aoi] = np.nan

    output_path = output_dir / f"{name}_indices.tif"
    output_dir.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        output_path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=len(INDEX_FORMULAS),
        dtype="float32",
        crs=CRS.from_epsg(epsg),
        transform=transform,
        nodata=np.nan,
        compress="deflate",
    ) as dataset:
        dataset.write(values)
        for band_number, (name_, formula) in enumerate(INDEX_FORMULAS.items(), start=1):
            dataset.set_band_description(band_number, f"{name_}: {formula}")

    metadata = {
        "period": name,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "source_collection": "sentinel-2-l2a",
        "catalog_manifest": str(manifest_path.resolve()),
        "catalog_query": manifest.get("query", {}),
        "item_ids": [item.id for item in items],
        "item_datetimes": {
            item.id: item.datetime.isoformat() if item.datetime else None for item in items
        },
        "item_licenses": {item.id: item.license for item in items},
        "item_count": len(items),
        "bands": INDEX_FORMULAS,
        "pixel_resolution_m": 20,
        "crs": f"EPSG:{epsg}",
        "scene_classification_clear_values": CLEAR_SCL_CLASSES,
        "aoi_file": str(aoi_path.resolve()),
        "output_file": output_path.name,
        "created_at": datetime.now(UTC).isoformat(),
        "processing_versions": {
            package: importlib.metadata.version(package)
            for package in [
                "stackstac",
                "rasterio",
                "geopandas",
                "xarray",
                "numpy",
            "pyproj",
                "planetary-computer",
            ]
        },
        "limitations": [
            "Indices are spectral signals, not dumpsite detections.",
            "The 20 m grid matches the coarser B11 and SCL assets; it does not add spatial detail.",
            "Scene-level cloud filtering and SCL masking do not remove every image artifact.",
            "No candidate thresholds or validation metrics have been applied.",
        ],
    }
    output_path.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n")
    return metadata


def main() -> int:
    args = parse_args()
    try:
        manifest, records, projected_geometry, epsg, bounds = read_inputs(
            args.manifest, args.aoi
        )
        if manifest.get("source", {}).get("collection") != "sentinel-2-l2a":
            raise ValueError("manifest source collection must be sentinel-2-l2a")

        names = [name for name, _start, _end in args.period]
        if len(names) != len(set(names)):
            raise ValueError("period names must be unique to avoid overwriting output files")

        for name, start, end in args.period:
            items = load_items(records, start, end)
            metadata = write_period(
                name,
                start,
                end,
                args.manifest,
                manifest,
                items,
                projected_geometry,
                epsg,
                bounds,
                args.output_dir,
                args.aoi,
            )
            print(f"Wrote {metadata['item_count']} item median to {args.output_dir / (name + '_indices.tif')}")
    except (OSError, ValueError, KeyError) as error:
        raise SystemExit(str(error)) from error

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
