#!/usr/bin/env python3
"""Topologie-erhaltende Vereinfachung der STS-Rohgeometrien via mapshaper.

Liest  : soiusa_sts_raw.geojson  (von fetch_soiusa.py erzeugt)
Schreibt: soiusa_sts.geojson     (fuer build.py)

Kann wiederholt ausgefuehrt werden ohne ARPA neu zu befragen.
Simplify-Prozentsatz anpassen (Argument oder SIMPLIFY-Konstante).
"""
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).parent
RAW  = HERE / "soiusa_sts_raw.geojson"
OUT  = HERE / "soiusa_sts.geojson"

SIMPLIFY_PCT = sys.argv[1] if len(sys.argv) > 1 else "30%"

if not RAW.exists():
    print("FEHLER: soiusa_sts_raw.geojson fehlt -- erst fetch_soiusa.py ausfuehren.")
    sys.exit(1)

kb_raw = RAW.stat().st_size / 1024
print(f"Eingabe: soiusa_sts_raw.geojson  {kb_raw:.0f} KB")
print(f"Simplify: {SIMPLIFY_PCT}  (Argument: python simplify_sts.py 5%)")

cmd = [
    "mapshaper", str(RAW),
    "-clean",
    "-simplify", SIMPLIFY_PCT, "keep-shapes",
    "-o", "format=geojson", "precision=0.0001", str(OUT),
]
print("Aufruf:", " ".join(cmd))

result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(HERE), shell=True)

if result.stdout:
    print(result.stdout.strip())
if result.returncode != 0:
    print("FEHLER mapshaper:", result.stderr.strip())
    sys.exit(1)

if not OUT.exists():
    print("FEHLER: Ausgabedatei nicht erzeugt.")
    sys.exit(1)

kb_out = OUT.stat().st_size / 1024
flag = "OK" if kb_out < 500 else "WARNUNG > 500 KB!"
print(f"Ausgabe: soiusa_sts.geojson  {kb_out:.0f} KB  [{flag}]")

fc = json.loads(OUT.read_text(encoding="utf-8"))
n = len(fc.get("features", []))
print(f"Features: {n}  (erwartet: ~132)")
if n < 100 or n > 160:
    print("WARNUNG: Anzahl weicht stark ab -- pruefen!")

# ── Post-process: validate + repair geometries via shapely ────────────────────
# mapshaper -clean fixes topology but can still emit invalid rings (self-intersections).
# MapLibre fill layers crash silently on invalid polygons → validate everything here.
try:
    from shapely.geometry import shape, mapping
    try:
        from shapely.validation import make_valid as _mk
        def _ensure_valid(g): return _mk(g)
    except ImportError:
        def _ensure_valid(g): return g.buffer(0)

    repaired = dropped = 0
    good = []
    for feat in fc["features"]:
        try:
            g = shape(feat["geometry"])
            if not g.is_valid:
                g = _ensure_valid(g)
                if not g.is_valid or g.is_empty:
                    dropped += 1; continue
                feat = {**feat, "geometry": mapping(g)}
                repaired += 1
            good.append(feat)
        except Exception as ex:
            print(f"  WARN verworfen {feat.get('properties',{}).get('STS','?')}: {ex}")
            dropped += 1
    fc["features"] = good
    OUT.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
    kb2 = OUT.stat().st_size / 1024
    print(f"Validierung: {repaired} repariert, {dropped} verworfen, {len(good)} OK  {kb2:.0f} KB")
except ImportError:
    print("shapely fehlt -- Geometrie-Validierung uebersprungen")
