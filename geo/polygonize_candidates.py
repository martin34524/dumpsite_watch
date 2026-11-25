#!/usr/bin/env python3
"""Polygonize exploratory spectral-index candidates for human review.

All thresholds and minimum area are required inputs. The output is explicitly
unreviewed candidate geometry, not a confirmed dumpsite layer.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import shapes
from scipy import ndimage
from shapely.geometry import shape


INDEX_BANDS = ("NDVI", "NDBI", "BSI")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--indices", required=True, type=Path)
    parser.add_argument("--ndbi-min", required=True, type=float)
    parser.add_argument("--bsi-min", required=True, type=float)
    parser.add_argument("--ndvi-max", required=True, type=float)
    parser.add_argument("--min-area-m2", required=True, type=float)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def read_indices(path: Path):
    metadata_path = path.with_suffix(".json")
    if not metadata_path.is_file():
        raise ValueError(f"index provenance sidecar not found: {metadata_path}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    with rasterio.open(path) as dataset:
        if dataset.crs is None or not dataset.crs.is_projected:
            raise ValueError("index raster must use a projected CRS with metre units")
        if dataset.crs.linear_units.lower() not in {"metre", "meter"}:
            raise ValueError("index raster CRS units must be metres")

        descriptions = {description.split(":", 1)[0]: index + 1 for index, description in enumerate(dataset.descriptions) if description}
        if any(name not in descriptions for name in INDEX_BANDS):
            raise ValueError(f"index raster must contain bands {INDEX_BANDS}")

        arrays = {
            name: dataset.read(band_number, masked=True).filled(np.nan)
            for name, band_number in descriptions.items()
            if name in INDEX_BANDS
        }
        return arrays, dataset.transform, dataset.crs, metadata


def candidates_from_mask(mask: np.ndarray, transform, minimum_area: float):
    # Use 4-neighbour connectivity so diagonal-only pixels remain separate regions.
    structure = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=np.uint8)
    labels, count = ndimage.label(mask, structure=structure)
    pixel_area = abs(transform.a * transform.e)
    component_sizes = np.bincount(labels.ravel())
    retained = []
    next_candidate = 1

    for component_id in range(1, count + 1):
        pixel_count = int(component_sizes[component_id])
        area_m2 = pixel_count * pixel_area
        if area_m2 < minimum_area:
            continue

        component_mask = labels == component_id
        polygons = [
            shape(geometry)
            for geometry, value in shapes(
                component_mask.astype(np.uint8),
                mask=component_mask,
                transform=transform,
                connectivity=4,
            )
            if value == 1
        ]
        if not polygons:
            continue

        retained.append(
            {
                "candidate_id": next_candidate,
                "area_m2": round(area_m2, 2),
                "pixel_count": pixel_count,
                "status": "unreviewed_candidate",
                "review_status": "pending",
                "review_reason": "",
                "reviewed_by": "",
                "reviewed_on": "",
                "review_evidence_url": "",
                "geometry": polygons[0],
            }
        )
        next_candidate += 1

    return retained


def main() -> int:
    args = parse_args()
    if not all(-1 <= value <= 1 for value in [args.ndbi_min, args.bsi_min, args.ndvi_max]):
        raise SystemExit("index thresholds must be between -1 and 1")
    if args.min_area_m2 <= 0:
        raise SystemExit("--min-area-m2 must be greater than zero")

    try:
        arrays, transform, crs, input_metadata = read_indices(args.indices)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(str(error)) from error

    valid = np.logical_and.reduce([np.isfinite(arrays[name]) for name in INDEX_BANDS])
    candidate_mask = (
        valid
        & (arrays["NDBI"] >= args.ndbi_min)
        & (arrays["BSI"] >= args.bsi_min)
        & (arrays["NDVI"] <= args.ndvi_max)
    )
    candidates = candidates_from_mask(candidate_mask, transform, args.min_area_m2)

    period = input_metadata.get("period", "period")
    output_path = args.output or Path(__file__).parent / "data/outputs" / f"{period}_candidates.gpkg"
    metadata_path = output_path.with_suffix(".json")
    if output_path.exists() or metadata_path.exists():
        raise SystemExit(f"output already exists; choose a new --output path: {output_path}")

    for candidate in candidates:
        candidate.update(
            {
                "period": period,
                "ndbi_min": args.ndbi_min,
                "bsi_min": args.bsi_min,
                "ndvi_max": args.ndvi_max,
                "min_area_m2": args.min_area_m2,
            }
        )

    if candidates:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        frame = gpd.GeoDataFrame(candidates, geometry="geometry", crs=crs)
        frame.to_file(output_path, driver="GPKG", layer="unreviewed_candidates", index=False)
        output_file = str(output_path.resolve())
    else:
        output_file = None

    metadata = {
        "created_at": datetime.now(UTC).isoformat(),
        "status": "unreviewed_candidates",
        "input_raster": str(args.indices.resolve()),
        "input_metadata": input_metadata,
        "thresholds": {
            "ndbi_min": args.ndbi_min,
            "bsi_min": args.bsi_min,
            "ndvi_max": args.ndvi_max,
            "minimum_area_m2": args.min_area_m2,
        },
        "connectivity": 4,
        "candidate_count": len(candidates),
        "output_file": output_file,
        "limitations": [
            "These polygons are spectral candidates only and are not confirmed dumpsites.",
            "Thresholds and minimum area were supplied by the operator and require review against reference sites.",
            "Candidate masks can include bare soil, construction, quarries, farms, and other false positives.",
            "No accuracy, precision, recall, or growth claims are calculated.",
        ],
    }
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(candidates)} unreviewed candidates; metadata: {metadata_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
