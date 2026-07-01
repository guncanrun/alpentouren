#!/usr/bin/env python3
"""Checks coordinate nesting depth matches the declared geometry type.

Polygon      → coordinates[0][0] must be a position → coordinates[0][0][0] must be a number
MultiPolygon → coordinates[0][0] must be a ring     → coordinates[0][0][0] must be a position
"""
import json, pathlib, sys

HERE = pathlib.Path(__file__).parent

def depth_ok(feat):
    g = feat.get("geometry")
    if not g:
        return False, "no geometry"
    t = g.get("type", "")
    c = g.get("coordinates")
    if not c:
        return False, "no coordinates"
    try:
        if t == "Polygon":
            # c = [ring, ...], ring = [[x,y],...], position = [x,y]
            # c[0][0][0] must be a number
            probe = c[0][0][0]
            if not isinstance(probe, (int, float)):
                # It's a list → actual depth is 4 → should be MultiPolygon
                return False, f"DEPTH-4 under Polygon (c[0][0][0]={type(probe).__name__})"
            # Also check for z-component (should be exactly 2 values)
            probe_pos = c[0][0]
            if len(probe_pos) not in (2, 3):
                return False, f"position has {len(probe_pos)} values (expected 2 or 3)"
        elif t == "MultiPolygon":
            # c = [poly,...], poly = [ring,...], ring = [[x,y],...], position = [x,y]
            # c[0][0][0][0] must be a number
            probe = c[0][0][0][0]
            if not isinstance(probe, (int, float)):
                return False, f"DEPTH wrong under MultiPolygon (c[0][0][0][0]={type(probe).__name__})"
        else:
            return False, f"unexpected type: {t}"
    except (IndexError, TypeError) as e:
        return False, f"structure error: {e}"
    return True, "ok"

errors = 0
for fname in ("soiusa_sts_raw.geojson", "soiusa_sts.geojson", "soiusa_sts_colored.geojson"):
    p = HERE / fname
    if not p.exists():
        print(f"MISSING: {fname}"); continue
    fc = json.loads(p.read_text(encoding="utf-8"))
    bad = []
    for f in fc.get("features", []):
        ok, reason = depth_ok(f)
        if not ok:
            bad.append((f.get("properties", {}).get("STS", "?"), reason))
    if bad:
        print(f"\n{fname}: {len(bad)} DEFEKTE Features:")
        for sts, reason in bad:
            print(f"  [{sts}]  → {reason}")
        errors += 1
    else:
        print(f"{fname}: OK  ({len(fc['features'])} features, Tiefe korrekt)")

sys.exit(1 if errors else 0)
