#!/usr/bin/env python3
"""Topologie-erhaltende Vereinfachung der Sezioni-Rohgeometrien via mapshaper.

Liest  : soiusa_sezioni_raw.geojson  (von fetch_soiusa.py erzeugt)
Schreibt: soiusa_sezioni.geojson     (fuer build.py)

Kann wiederholt ausgefuehrt werden ohne ARPA neu zu befragen.
Simplify-Prozentsatz anpassen (Argument oder SIMPLIFY-Konstante).
"""
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).parent
RAW  = HERE / "soiusa_sezioni_raw.geojson"
OUT  = HERE / "soiusa_sezioni.geojson"

SIMPLIFY_PCT = sys.argv[1] if len(sys.argv) > 1 else "8%"

if not RAW.exists():
    print("FEHLER: soiusa_sezioni_raw.geojson fehlt — erst fetch_soiusa.py ausfuehren.")
    sys.exit(1)

kb_raw = RAW.stat().st_size / 1024
print(f"Eingabe: soiusa_sezioni_raw.geojson  {kb_raw:.0f} KB")
print(f"Simplify: {SIMPLIFY_PCT}  (Argument: python simplify_sezioni.py 5%)")

cmd = [
    "mapshaper", str(RAW),
    "-clean",
    "-simplify", SIMPLIFY_PCT, "keep-shapes",
    "-o", "format=geojson", f"precision=0.0001", str(OUT),
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
# Report + size check
flag = "OK" if kb_out < 400 else "WARNUNG > 400 KB!"
print(f"Ausgabe: soiusa_sezioni.geojson  {kb_out:.0f} KB  [{flag}]")

# Quick feature count check
fc = json.loads(OUT.read_text(encoding="utf-8"))
n = len(fc.get("features", []))
print(f"Features: {n}  (erwartet: 36)")
if n != 36:
    print("WARNUNG: Anzahl weicht von 36 ab — pruefen!")
