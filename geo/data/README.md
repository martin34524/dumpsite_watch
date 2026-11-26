# Reference data

Only add independently sourced, reviewed data here. Do not enter synthetic or
unverified locations as confirmed dumpsites.

`known_sites.csv` is the reference-site register for the pilot county. Keep one
row per location and include the source and evidence link. Use
`validation_status` values `unreviewed`, `confirmed`, `rejected`, or `uncertain`;
`confidence` is a reviewer's confidence from 0 to 1, not a model probability.
Record the date the site was observed when known. Preserve provider attribution
and licensing notes in the Obsidian Decisions and Sources note.

The register currently contains only its header. Nairobi is the provisional
pilot, but no independently reviewed source records have been entered yet.

`download_county_boundary.py` fetches the current geoBoundaries Kenya ADM1
release, extracts one named county to `pilot_county.geojson`, and writes a
provenance sidecar. Inspect the source metadata and geometry before using it;
the file is a candidate study boundary, not a legal boundary determination.
