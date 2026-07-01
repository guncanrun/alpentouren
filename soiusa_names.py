#!/usr/bin/env python3
"""Abfrage aller STS- und GR-Namen vom ARPA-SOIUSA-Dienst (keyless).
Dient zur Verifikation des DE->SOIUSA-Mappings vor dem Build.
"""
import urllib.request
import urllib.parse
import json

BASE = "https://webgis.arpa.piemonte.it/ags/rest/services/topografia_dati_di_base/SOIUSA/MapServer"


def query_layer(layer, fields="SZ,STS,GR,CODICE", where="1=1", geom=False):
    url = (
        f"{BASE}/{layer}/query"
        f"?where={urllib.parse.quote(where)}"
        f"&outFields={fields}"
        f"&returnGeometry={str(geom).lower()}"
        f"&f=json"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


# ── Layer 5: Sezioni (36 Stück) ──────────────────────────────────────────────
print("=== Layer 5 (Sezioni) unique SZ ===")
r5 = query_layer(5, fields="SZ,CODICE")
if "error" in r5:
    print("ERROR L5:", r5)
else:
    sz_set = sorted({f["attributes"].get("SZ", "") for f in r5["features"]} - {""})
    print(f"Anzahl Features: {len(r5['features'])}, unique SZ: {len(sz_set)}")
    for s in sz_set:
        print("  ", s)

print()

# ── Layer 7: Sottosezioni — alle STS-Namen ───────────────────────────────────
print("=== Layer 7 (Sottosezioni) unique STS ===")
r7 = query_layer(7)
if "error" in r7:
    print("ERROR L7:", r7)
else:
    sts_set = sorted({f["attributes"].get("STS", "") for f in r7["features"]} - {""})
    print(f"Anzahl Features: {len(r7['features'])}, unique STS: {len(sts_set)}")
    for s in sts_set:
        print("  ", s)

print()

# ── Layer 11: Gruppo — alle GR-Namen ────────────────────────────────────────
print("=== Layer 11 (Gruppo) unique GR ===")
r11 = query_layer(11)
if "error" in r11:
    print("ERROR L11:", r11)
else:
    gr_set = sorted({f["attributes"].get("GR", "") for f in r11["features"]} - {""})
    print(f"Anzahl Features: {len(r11['features'])}, unique GR: {len(gr_set)}")
    for g in gr_set:
        print("  ", g)
