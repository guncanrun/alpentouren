#!/usr/bin/env python3
"""Fetch OSM peaks (ele>=2000) + mountain huts in the Alps via Overpass API.

Output: soiusa_osm_peaks.geojson, soiusa_osm_huts.geojson (compact, committed).
Loaded by build.py as URL-based MapLibre sources (NOT inlined) to keep index.html small.
© OpenStreetMap contributors, ODbL.
"""
import io
import json
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = pathlib.Path(__file__).parent

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
BBOX = "42.5,3.5,49.5,18.5"   # S,W,N,E — Alpenraum (deckt maxBounds ab)
MIN_ELE = 2000

PEAKS_Q = f'[out:json][timeout:300];(node["natural"="peak"]["name"]["ele"]({BBOX}););out qt;'
HUTS_Q = (f'[out:json][timeout:300];'
          f'(node["tourism"="alpine_hut"]["name"]({BBOX});'
          f'node["tourism"="wilderness_hut"]["name"]({BBOX}););out qt;')
PASS_Q = (f'[out:json][timeout:300];'
          f'(node["mountain_pass"="yes"]["name"]({BBOX}););out qt;')  # named road/mountain passes

# ── Peak hierarchy tiers (0 Mont Blanc · 1 Länder-Höchste · 2/3/4 Höhenbänder) ──
NAMED_PEAKS = {   # name substring : (tier, approx ele) — Wikidata-verified values
    "Mont Blanc":       (0, 4806),
    "Dufourspitze":     (1, 4634),
    "Gran Paradiso":    (1, 4061),
    "Großglockner":     (1, 3798),
    "Zugspitze":        (1, 2962),
    "Triglav":          (1, 2864),
    "Vorder Grauspitz": (1, 2599),
}


def peak_tier(name, ele):
    low = (name or "").lower()
    for key, (t, kele) in NAMED_PEAKS.items():
        if key.lower() in low and abs(ele - kele) <= 45:
            return t
    if ele >= 4000:
        return 2
    if ele >= 3000:
        return 3
    return 4


# Famous passes — matched against OSM name in any language.
FAMOUS_PASS_RE = re.compile(
    r"Stilfser|Stelvio|Timmelsjoch|Passo del Rombo|Hochtor|Brennerpass|Passo del Brennero|"
    r"Reschenpass|Passo di Resia|Fernpass|Arlbergpass|Grimselpass|Furkapass|Sustenpass|"
    r"Gotthardpass|Passo del San Gottardo|San Bernardino|Splügenpass|Passo dello Spluga|"
    r"Julierpass|Malojapass|Berninapass|Passo del Bernina|Flüelapass|Simplonpass|Passo del Sempione|"
    r"Grosser Sankt Bernhard|Großer Sankt Bernhard|Grand-Saint-Bernard|Gran San Bernardo|"
    r"Col du Galibier|Col de l.Iseran|Bonette|Mont ?Cenis|Moncenisio|Sellajoch|Passo (di )?Sella|"
    r"Pordoijoch|Passo Pordoi|Grödnerjoch|Groednerjoch|Passo Gardena|Falzarego|Gaviapass|Passo di Gavia|"
    r"Tonalepass|Passo del Tonale", re.IGNORECASE)


def query(q):
    data = urllib.parse.urlencode({"data": q}).encode()
    last = None
    for attempt in range(3):
        for ep in OVERPASS_ENDPOINTS:
            try:
                req = urllib.request.Request(ep, data=data,
                                             headers={"User-Agent": "Bergtouren-Map/1.0"})
                with urllib.request.urlopen(req, timeout=320) as r:
                    return json.loads(r.read())
            except Exception as e:  # noqa: BLE001
                last = e
                print(f"   {ep.split('/')[2]} fehlgeschlagen ({type(e).__name__}); naechster...")
        time.sleep(8)
    raise last


def peaks_geojson(elements):
    feats = []
    for el in elements:
        if el.get("type") != "node":
            continue
        lon, lat = el.get("lon"), el.get("lat")
        name = (el.get("tags") or {}).get("name")
        if lon is None or not name:
            continue
        raw = str((el["tags"]).get("ele", "")).replace(",", ".").split()
        try:
            ele = float(raw[0])
        except (ValueError, IndexError):
            continue
        if ele < MIN_ELE:
            continue
        feats.append({"type": "Feature",
                      "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
                      "properties": {"name": name, "ele": round(ele)}})
    feats.sort(key=lambda f: -f["properties"]["ele"])
    return feats


import re

# Exclude alpine dairy farms / pastures / non-hut noise, keep real hiking huts.
ALM_RE = re.compile(r"Alm|Alpe|Alpage|Malga|\bAlp\b|Rifugio Alpe|Bergerie|forestale|camper|Stazzo",
                    re.IGNORECASE)
# Alpine-club operators → prioritised "club" category (tier 1).
CLUB_RE = re.compile(r"Alpenverein|DAV|ÖAV|OeAV|AVS|SAC|CAI|FFCAM|Naturfreunde", re.IGNORECASE)


def huts_geojson(elements):
    feats = []
    for el in elements:
        if el.get("type") != "node":
            continue
        lon, lat = el.get("lon"), el.get("lat")
        tags = el.get("tags") or {}
        name = tags.get("name")
        if lon is None or not name:
            continue
        if ALM_RE.search(name):        # drop Almen/Alpe/Malga
            continue
        op = tags.get("operator", "") or ""
        # 3 tiers: club (Verband) > wild (unbewirtschaftet) > hut (sonstige bewirtschaftet)
        if CLUB_RE.search(op):
            kat = "club"
        elif tags.get("tourism") == "wilderness_hut":
            kat = "wild"
        else:
            kat = "hut"
        props = {"name": name, "kat": kat}
        if op:
            props["operator"] = op        # keep for reproducibility / DAV cross-check
        if tags.get("tourism"):
            props["tourism"] = tags["tourism"]
        raw = str(tags.get("ele", "")).replace(",", ".").split()
        if raw:
            try:
                props["ele"] = round(float(raw[0]))
            except (ValueError, IndexError):
                pass
        feats.append({"type": "Feature",
                      "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
                      "properties": props})
    return feats


def passes_geojson(elements):
    feats = []
    for el in elements:
        if el.get("type") != "node":
            continue
        lon, lat = el.get("lon"), el.get("lat")
        tags = el.get("tags") or {}
        name = tags.get("name")
        if lon is None or not name:
            continue
        props = {"name": name, "famous": 1 if FAMOUS_PASS_RE.search(name) else 0}
        raw = str(tags.get("ele", "")).replace(",", ".").split()
        if raw:
            try:
                props["ele"] = round(float(raw[0]))
            except (ValueError, IndexError):
                pass
        feats.append({"type": "Feature",
                      "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
                      "properties": props})
    return feats


def alps_filter(feats):
    """Keep only features whose point lies inside the SOIUSA polygons (drop non-alpine)."""
    try:
        from shapely.geometry import Point, shape
        from shapely.ops import unary_union
        from shapely.prepared import prep
    except ImportError:
        print("  (shapely fehlt -> kein SOIUSA-Clip)")
        return feats
    fc = json.loads((HERE / "soiusa_sts_colored.geojson").read_text(encoding="utf-8"))
    union = prep(unary_union([shape(f["geometry"]) for f in fc["features"]]))
    return [f for f in feats if union.contains(Point(f["geometry"]["coordinates"]))]


def save(name, feats, label):
    (HERE / name).write_text(json.dumps({"type": "FeatureCollection", "features": feats},
                                        ensure_ascii=False), encoding="utf-8")
    kb = (HERE / name).stat().st_size // 1024
    print(f"-> {name}  {len(feats)} {label}  {kb} KB")


out_p = HERE / "soiusa_osm_peaks.geojson"
if out_p.exists() and len(json.loads(out_p.read_text(encoding="utf-8"))["features"]) > 1000:
    print("Gipfel vorhanden — lade + clippe auf SOIUSA...")
    pf = json.loads(out_p.read_text(encoding="utf-8"))["features"]
else:
    print("Overpass: Gipfel (kann etwas dauern)...")
    pf = peaks_geojson(query(PEAKS_Q).get("elements", []))
before = len(pf)
pf = alps_filter(pf)
for f in pf:                       # hierarchy tier (0 Mont Blanc / 1 Länder-Höchste / 2-4 bands)
    f["properties"]["tier"] = peak_tier(f["properties"].get("name", ""), f["properties"].get("ele", 0))
save("soiusa_osm_peaks.geojson", pf, f"Gipfel (von {before} nach SOIUSA-Clip)")
tier01 = [f["properties"]["name"] for f in pf if f["properties"]["tier"] <= 1]
print(f"   Tier 0/1 (Alpen-König + Länder-Höchste): {tier01}")

print("Overpass: Huetten...")
hf = huts_geojson(query(HUTS_Q).get("elements", []))
before = len(hf)
hf = alps_filter(hf)
save("soiusa_osm_huts.geojson", hf, f"Huetten (von {before} nach SOIUSA-Clip)")

print("Overpass: Paesse...")
xf = passes_geojson(query(PASS_Q).get("elements", []))
before = len(xf)
xf = alps_filter(xf)
fam = sum(1 for f in xf if f["properties"]["famous"])
save("soiusa_osm_passes.geojson", xf, f"Paesse (von {before} nach Clip, {fam} famous)")
print("Naechster Schritt: python build.py")
