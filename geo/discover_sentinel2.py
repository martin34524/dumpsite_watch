#!/usr/bin/env python3
"""Discover Sentinel-2 L2A STAC items intersecting a study-area file.

This stage records catalog metadata only. It does not download imagery or
identify dumpsites. Supply a county boundary or other reviewed AOI as GeoJSON,
GeoPackage, or another format supported by GeoPandas.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
from pystac_client import Client
from shapely.geometry import mapping


DEFAULT_STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
DEFAULT_COLLECTION = "sentinel-2-l2a"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aoi", required=True, type=Path, help="Study-area boundary file")
    parser.add_argument("--start", required=True, help="First observation date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="Last observation date (YYYY-MM-DD)")
    parser.add_argument(
        "--max-cloud",
        type=float,
        default=20.0,
        help="Maximum catalog cloud-cover percentage (default: 20; provisional)",
    )
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--stac-url", default=DEFAULT_STAC_URL)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent / "data/raw/sentinel2-items.json",
        help="Manifest output path (default is under ignored geo/data/raw/)",
    )
    return parser.parse_args()


def load_aoi(path: Path) -> dict:
    if not path.is_file():
        raise ValueError(f"AOI file does not exist: {path}")

    frame = gpd.read_file(path)
    if frame.empty or frame.geometry.isna().all():
        raise ValueError("AOI file has no geometries")
    if frame.crs is None:
        raise ValueError("AOI file must declare a coordinate reference system")

    geometry = frame.to_crs("EPSG:4326").geometry.union_all()
    if geometry.is_empty or not geometry.is_valid:
        raise ValueError("AOI geometry must be non-empty and valid")
    if geometry.geom_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError("AOI must contain polygon geometry")

    return mapping(geometry)


def discover(args: argparse.Namespace) -> dict:
    start_date = datetime.strptime(args.start, "%Y-%m-%d").date()
    end_date = datetime.strptime(args.end, "%Y-%m-%d").date()
    if start_date > end_date:
        raise ValueError("--start must be on or before --end")
    if not 0 <= args.max_cloud <= 100:
        raise ValueError("--max-cloud must be between 0 and 100")

    aoi = load_aoi(args.aoi)
    query = {
        "collections": [args.collection],
        "intersects": aoi,
        "datetime": f"{start_date.isoformat()}/{end_date.isoformat()}",
        "query": {"eo:cloud_cover": {"lt": args.max_cloud}},
    }

    catalog = Client.open(args.stac_url)
    items = catalog.search(**query).items()
    records = []

    for item in items:
        properties = item.properties
        records.append(
            {
                "id": item.id,
                "collection": item.collection_id,
                "datetime": properties.get("datetime"),
                "cloud_cover_percent": properties.get("eo:cloud_cover"),
                "bbox": item.bbox,
                "asset_keys": sorted(item.assets),
                "license": item.license,
            }
        )

    return {
        "manifest_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "source": {
            "provider": "Microsoft Planetary Computer STAC",
            "catalog_url": args.stac_url,
            "collection": args.collection,
        },
        "query": {
            "aoi_file": str(args.aoi.resolve()),
            "aoi_crs": "EPSG:4326",
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "maximum_cloud_cover_percent": args.max_cloud,
        },
        "item_count": len(records),
        "items": records,
        "limitations": [
            "Catalog discovery only; no imagery was downloaded or processed.",
            "Cloud-cover filtering is scene-level and does not guarantee cloud-free AOI pixels.",
            "STAC items are observations, not dumpsite detections or validated findings.",
        ],
    }


def main() -> int:
    args = parse_args()
    try:
        manifest = discover(args)
    except (OSError, ValueError) as error:
        raise SystemExit(str(error)) from error

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {manifest['item_count']} catalog item records to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
