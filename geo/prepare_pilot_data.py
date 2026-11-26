#!/usr/bin/env python3
"""Render a clearly labeled SVG overview from the pilot boundary and lead CSV."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path

import geopandas as gpd
from shapely.geometry import MultiPolygon, Point, Polygon


ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boundary", type=Path, default=ROOT / "geo/data/pilot_county.geojson")
    parser.add_argument("--sites", type=Path, default=ROOT / "geo/data/known_sites.csv")
    parser.add_argument("--data-output", type=Path, default=ROOT / "web/priv/pilot_data.json")
    return parser.parse_args()


def project_point(lon: float, lat: float, center_lat: float) -> tuple[float, float]:
    return lon * math.cos(math.radians(center_lat)), -lat


def main() -> int:
    args = parse_args()
    boundary = gpd.read_file(args.boundary)
    if len(boundary) != 1 or boundary.crs is None:
        raise SystemExit("Expected one county boundary with a declared CRS")
    if not boundary.geometry.iloc[0].is_valid:
        raise SystemExit("County boundary geometry is invalid")
    county_geometry = boundary.geometry.iloc[0]
    if str(boundary.crs).upper() not in {"EPSG:4326", "OGC:CRS84"}:
        boundary = boundary.to_crs("EPSG:4326")
        county_geometry = boundary.geometry.iloc[0]

    min_lon, min_lat, max_lon, max_lat = county_geometry.bounds
    center_lat = (min_lat + max_lat) / 2
    projected_bounds = [project_point(lon, lat, center_lat) for lon, lat in [(min_lon, min_lat), (max_lon, max_lat)]]
    min_x, max_x = sorted([projected_bounds[0][0], projected_bounds[1][0]])
    min_y, max_y = sorted([projected_bounds[0][1], projected_bounds[1][1]])

    width, height, margin = 960, 640, 52
    scale = min((width - 2 * margin) / (max_x - min_x), (height - 2 * margin) / (max_y - min_y))
    used_width, used_height = (max_x - min_x) * scale, (max_y - min_y) * scale
    offset_x, offset_y = (width - used_width) / 2, (height - used_height) / 2

    def screen(lon: float, lat: float) -> tuple[float, float]:
        x, y = project_point(lon, lat, center_lat)
        return offset_x + (x - min_x) * scale, offset_y + (y - min_y) * scale

    def ring_path(ring) -> str:
        points = [screen(lon, lat) for lon, lat in ring.coords]
        if len(points) > 1_000:
            step = max(1, len(points) // 1_000)
            points = points[::step]
        return "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in points) + " Z"

    geometry = county_geometry.simplify(0.0005, preserve_topology=True)
    polygons = list(geometry.geoms) if isinstance(geometry, MultiPolygon) else [geometry]
    map_path_parts = []
    for polygon in polygons:
        if not isinstance(polygon, Polygon):
            continue
        path_data = ring_path(polygon.exterior)
        path_data += " " + " ".join(ring_path(ring) for ring in polygon.interiors)
        map_path_parts.append(path_data)

    with args.sites.open(newline="", encoding="utf-8") as stream:
        sites = list(csv.DictReader(stream))
    lead_records = []
    outside_count = 0
    for site in sites:
        lon, lat = float(site["longitude"]), float(site["latitude"])
        if not county_geometry.covers(Point(lon, lat)):
            outside_count += 1
        x, y = screen(lon, lat)
        evidence = site["evidence_notes"].strip()
        evidence_type = "dump_site_reported" if "dumpsite" in evidence.casefold() else "river_dumping_reported"
        slug = re.sub(r"[^a-z0-9]+", "-", site["name"].casefold()).strip("-")
        lead_records.append({
            "id": slug,
            "name": site["name"],
            "latitude": lat,
            "longitude": lon,
            "map_x": round(x, 1),
            "map_y": round(y, 1),
            "source_name": site["source_name"],
            "source_url": site["source_url"],
            "validation_status": site["validation_status"],
            "study_period": "Field data, 2021",
            "evidence_type": evidence_type,
            "evidence_notes": evidence,
        })

    data = {
        "county": "Nairobi",
        "boundary_source": "geoBoundaries Kenya ADM1, 2020",
        "boundary_path": " ".join(map_path_parts),
        "view_box": [0, 0, width, height],
        "outside_point_count": outside_count,
        "lead_count": len(lead_records),
        "leads": lead_records,
    }
    args.data_output.parent.mkdir(parents=True, exist_ok=True)
    args.data_output.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(sites)} study points and county geometry to {args.data_output}; {outside_count} points fall outside county boundary.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
