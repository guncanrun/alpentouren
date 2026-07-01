#!/usr/bin/env python3
"""Quick geometry type audit of all intermediate files."""
import json, pathlib
HERE = pathlib.Path(__file__).parent

for fname in ("soiusa_sts.geojson", "soiusa_sts_colored.geojson", "soiusa_mask.geojson", "soiusa_highlights.geojson"):
    p = HERE / fname
    if not p.exists():
        print(f"MISSING: {fname}"); continue
    fc = json.loads(p.read_text(encoding="utf-8"))
    types = {}
    for f in fc.get("features", []):
        t = f.get("geometry", {}).get("type", "NULL") if f.get("geometry") else "NULL"
        types[t] = types.get(t, 0) + 1
    print(f"{fname}:  {dict(types)}")
    # Report any non-polygon
    bad = {k:v for k,v in types.items() if k not in ("Polygon","MultiPolygon")}
    if bad:
        print(f"  !! NON-POLYGON: {bad}")
    # For mask: report ring count
    if fname == "soiusa_mask.geojson" and fc.get("features"):
        g = fc["features"][0].get("geometry", {})
        rings = len(g.get("coordinates", [])) if g.get("type") == "Polygon" else "MultiPolygon"
        coords_total = sum(len(r) for r in g.get("coordinates", [])) if g.get("type") == "Polygon" else "?"
        print(f"  mask rings: {rings}  total_coords: {coords_total}")
