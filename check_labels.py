#!/usr/bin/env python3
"""Scan label fields for characters outside safe ASCII+Latin-1 range."""
import json, pathlib

HERE = pathlib.Path(__file__).parent

SAFE_MAX = 0x00FF  # Latin Extended (covers ä,ö,ü,ß,à,è,é etc.)

def scan(label, source, field):
    issues = []
    for i, ch in enumerate(label):
        cp = ord(ch)
        if cp > SAFE_MAX:
            issues.append(f"U+{cp:04X} '{ch}' at pos {i}")
    if issues:
        print(f"  [{source}] {field}={repr(label[:40])} → {issues}")

# STS names (sts-label) and name_de (sts-label-hl)
p = HERE / "soiusa_sts_colored.geojson"
fc = json.loads(p.read_text(encoding="utf-8"))
print(f"=== soiusa_sts_colored.geojson ({len(fc['features'])} features) ===")
found = 0
for f in fc["features"]:
    sts = f["properties"].get("STS", "")
    nde = f["properties"].get("name_de", "")
    scan(sts, "STS-label", "STS")
    if nde:
        scan(nde, "HL-label", "name_de")
        found += 1

print(f"(name_de set on {found} features)")

# Also scan highlight file
p2 = HERE / "soiusa_highlights.geojson"
fc2 = json.loads(p2.read_text(encoding="utf-8"))
print(f"\n=== soiusa_highlights.geojson ({len(fc2['features'])} features) ===")
for f in fc2["features"]:
    for k in ("name_de","soiusa_name"):
        v = f["properties"].get(k,"")
        if v: scan(v, "highlight", k)

print("\nScan complete — no output above means all chars in Latin-1 range (safe).")
