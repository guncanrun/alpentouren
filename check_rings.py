#!/usr/bin/env python3
"""Deep ring-level audit: open rings, short rings, NaN, null, z-components."""
import json, math, pathlib, sys

HERE = pathlib.Path(__file__).parent

def audit_file(fname):
    p = HERE / fname
    if not p.exists():
        print(f"MISSING: {fname}"); return 0
    fc = json.loads(p.read_text(encoding="utf-8"))
    bad = []
    for f in fc.get("features", []):
        g = f.get("geometry")
        if not g: continue
        t = g["type"]
        sts = f.get("properties", {}).get("STS", "?")
        coords = g.get("coordinates", [])

        # Normalize to list of rings (Polygon) or list of polygon ring lists (MultiPolygon)
        if t == "Polygon":
            ring_groups = [coords]  # one polygon
        elif t == "MultiPolygon":
            ring_groups = coords    # list of polygons
        else:
            continue

        for pi, rings in enumerate(ring_groups):
            for ri, ring in enumerate(rings):
                tag = f"{sts}[poly{pi}][ring{ri}]"

                if len(ring) == 0:
                    bad.append((tag, "EMPTY ring"))
                    continue
                if len(ring) < 4:
                    bad.append((tag, f"SHORT ring: {len(ring)} points (need >=4)"))
                    continue

                # Check each position
                for vi, pos in enumerate(ring):
                    if not isinstance(pos, list):
                        bad.append((tag, f"pos[{vi}] is not a list: {type(pos).__name__}"))
                        break
                    if len(pos) < 2:
                        bad.append((tag, f"pos[{vi}] has <2 values: {pos}"))
                        break
                    if len(pos) > 2:
                        bad.append((tag, f"z-component at pos[{vi}]: {pos}"))
                        break
                    x, y = pos[0], pos[1]
                    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
                        bad.append((tag, f"non-numeric at pos[{vi}]: {pos}"))
                        break
                    if math.isnan(x) or math.isnan(y):
                        bad.append((tag, f"NaN at pos[{vi}]"))
                        break
                    if not math.isfinite(x) or not math.isfinite(y):
                        bad.append((tag, f"Inf at pos[{vi}]"))
                        break
                    if x < -180 or x > 180 or y < -90 or y > 90:
                        bad.append((tag, f"out-of-range at pos[{vi}]: [{x},{y}]"))
                        break
                else:
                    # Check ring closed (first == last)
                    first, last = ring[0], ring[-1]
                    if first[0] != last[0] or first[1] != last[1]:
                        bad.append((tag, f"NOT CLOSED: first={first} last={last}"))

    if bad:
        print(f"\n{fname}: {len(bad)} Probleme:")
        for tag, reason in bad[:30]:
            print(f"  {tag}: {reason}")
        if len(bad) > 30:
            print(f"  ... (+{len(bad)-30} weitere)")
    else:
        n = len(fc["features"])
        print(f"{fname}: OK ({n} features, alle Ringe valid)")
    return len(bad)

total = 0
for fname in ("soiusa_sts_raw.geojson", "soiusa_sts.geojson", "soiusa_sts_colored.geojson",
              "soiusa_mask.geojson", "soiusa_highlights.geojson"):
    total += audit_file(fname)

print()
if total:
    print(f"GESAMT: {total} Probleme gefunden — Fixes notwendig.")
    sys.exit(1)
else:
    print("Alle Dateien strukturell sauber.")
