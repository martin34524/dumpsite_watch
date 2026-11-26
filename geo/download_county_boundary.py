#!/usr/bin/env python3
"""Download and extract one county from geoBoundaries Kenya ADM1."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import requests
from shapely.geometry import mapping


API_URL = "https://www.geoboundaries.org/api/current/gbOpen/KEN/ADM1/"
DEFAULT_OUTPUT = Path(__file__).parent / "data/pilot_county.geojson"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--county", default="Nairobi", help="County name (default: Nairobi)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def download(county: str, output: Path) -> tuple[Path, Path]:
    response = requests.get(API_URL, timeout=30)
    response.raise_for_status()
    source_metadata = response.json()
    geojson_url = source_metadata.get("gjDownloadURL")
    if not geojson_url:
        raise ValueError("geoBoundaries API response has no GeoJSON download URL")

    boundary_response = requests.get(geojson_url, timeout=60)
    boundary_response.raise_for_status()
    boundary = gpd.GeoDataFrame.from_features(boundary_response.json()["features"], crs="EPSG:4326")
    if boundary.empty or boundary.crs is None:
        raise ValueError("Downloaded boundary file is empty or has no CRS")

    normalized_county = county.strip().casefold()
    name_column = next(
        (column for column in boundary.columns if column.casefold() in {"shapename", "name", "county"}),
        None,
    )
    if name_column is None:
        raise ValueError(f"No county-name column found; available fields: {list(boundary.columns)}")
    selected = boundary.loc[boundary[name_column].astype(str).str.strip().str.casefold() == normalized_county]
    if len(selected) != 1:
        names = sorted(boundary[name_column].astype(str).tolist())
        raise ValueError(f"Expected one {county!r} feature, found {len(selected)}; available: {names}")

    geometry = selected.geometry.iloc[0]
    if geometry is None or geometry.is_empty or not geometry.is_valid:
        raise ValueError(f"{county} boundary geometry is empty or invalid")
    if geometry.geom_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError(f"Expected polygon geometry, found {geometry.geom_type}")

    output.parent.mkdir(parents=True, exist_ok=True)
    feature = {
        "type": "Feature",
        "properties": {"county": county, "boundary_id": source_metadata.get("boundaryID")},
        "geometry": mapping(geometry),
    }
    output.write_text(json.dumps({"type": "FeatureCollection", "features": [feature]}, indent=2) + "\n")

    provenance = {
        "downloaded_at": datetime.now(UTC).isoformat(),
        "provider": "geoBoundaries / William & Mary geoLab",
        "api_url": API_URL,
        "geojson_url": geojson_url,
        "source_dataset": source_metadata.get("boundarySource"),
        "source_url": source_metadata.get("boundarySourceURL"),
        "boundary_id": source_metadata.get("boundaryID"),
        "boundary_type": source_metadata.get("boundaryType"),
        "boundary_year_represented": source_metadata.get("boundaryYearRepresented"),
        "license": source_metadata.get("boundaryLicense"),
        "license_source": source_metadata.get("licenseSource"),
        "county": county,
        "feature_count": 1,
        "crs": "EPSG:4326",
        "geometry_type": geometry.geom_type,
        "limitations": [
            "County geometry is from the source release and has not been checked against Kenyan government survey data.",
            "Confirm source terms and boundary fitness before external publication or operational use.",
        ],
    }
    metadata_path = output.with_suffix(".metadata.json")
    metadata_path.write_text(json.dumps(provenance, indent=2) + "\n")
    return output, metadata_path


def main() -> int:
    args = parse_args()
    try:
        boundary_path, metadata_path = download(args.county, args.output)
    except (OSError, ValueError, requests.RequestException, json.JSONDecodeError) as error:
        raise SystemExit(str(error)) from error
    print(f"Wrote county boundary to {boundary_path}")
    print(f"Wrote source metadata to {metadata_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
