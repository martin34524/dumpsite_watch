#!/usr/bin/env python3
"""Render a clearly labeled SVG overview from the pilot boundary and lead CSV."""

from __future__ import annotations

import argparse
import csv
import html
import math
from pathlib import Path

import geopandas as gpd
from shapely.geometry import MultiPolygon, Point, Polygon


ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boundary", type=Path, default=ROOT / "geo/data/pilot_county.geojson")
    parser.add_argument("--sites", type=Path, default=ROOT / "geo/data/known_sites.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "web/priv/static/images/pilot-leads.svg")
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
    boundary_paths = []
    for polygon in polygons:
        if not isinstance(polygon, Polygon):
            continue
        path_data = ring_path(polygon.exterior)
        path_data += " " + " ".join(ring_path(ring) for ring in polygon.interiors)
        boundary_paths.append(f'<path d="{path_data}" fill-rule="evenodd"/>')

    with args.sites.open(newline="", encoding="utf-8") as stream:
        sites = list(csv.DictReader(stream))
    points = []
    outside_count = 0
    for site in sites:
        lon, lat = float(site["longitude"]), float(site["latitude"])
        if not county_geometry.covers(Point(lon, lat)):
            outside_count += 1
        x, y = screen(lon, lat)
        label = html.escape(site["name"], quote=True)
        points.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" aria-label="Unreviewed study sampling point: {label}"><title>{label} — unreviewed 2021 study sampling point</title></circle>')

    args.output.parent.mkdir(parents=True, exist_ok=True)
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="map-title map-desc">
<title id="map-title">Nairobi County and unreviewed river-study sampling points</title>
<desc id="map-desc">A simplified outline of Nairobi County with {len(sites)} points from a 2021 Ngong River water-quality study. Points indicate sampling locations where the paper reported nearby dumping, not dumpsite footprints or verified current conditions. {outside_count} points fall outside the county polygon and require review.</desc>
<rect width="{width}" height="{height}" fill="#eef3ed"/>
<g fill="#c9d8cd" stroke="#6d8977" stroke-width="2.2" stroke-linejoin="round">{''.join(boundary_paths)}</g>
<g fill="#d35d42" stroke="#fffdf8" stroke-width="2">{''.join(points)}</g>
<g font-family="system-ui,sans-serif" font-size="13" fill="#53675b"><text x="28" y="34">Nairobi County · simplified outline</text><text x="28" y="{height-24}">● {len(sites)} unreviewed 2021 study sampling points · not dump footprints</text></g>
</svg>'''
    args.output.write_text(svg, encoding="utf-8")
    print(f"Wrote {len(sites)} study points to {args.output}; {outside_count} points fall outside county boundary.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
