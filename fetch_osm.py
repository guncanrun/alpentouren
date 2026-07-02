#!/usr/bin/env python3
"""Fetch OSM peaks (ele>=2000) + mountain huts in the Alps via Overpass API.

Output: soiusa_osm_peaks.geojson, soiusa_osm_huts.geojson (compact, committed).
Loaded by build.py as URL-based MapLibre sources (NOT inlined) to keep index.html small.
© OpenStreetMap contributors, ODbL.
"""
import io
import json
import pathlib
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

# Exclude alpine dairy farms / pastures (Almen), keep real hiking huts.
ALM_RE = re.compile(r"Alm|Alpe|Alpage|Malga|\bAlp\b|Rifugio Alpe", re.IGNORECASE)
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


out_p = HERE / "soiusa_osm_peaks.geojson"
if out_p.exists() and len(json.loads(out_p.read_text(encoding="utf-8"))["features"]) > 1000:
    print(f"Gipfel bereits vorhanden ({out_p.stat().st_size//1024} KB) — ueberspringe.")
else:
    print("Overpass: Gipfel (kann etwas dauern)...")
    pf = peaks_geojson(query(PEAKS_Q).get("elements", []))
    out_p.write_text(json.dumps({"type": "FeatureCollection", "features": pf}, ensure_ascii=False),
                     encoding="utf-8")
    print(f"-> soiusa_osm_peaks.geojson  {len(pf)} Gipfel (ele>={MIN_ELE})  {out_p.stat().st_size//1024} KB")

print("Overpass: Huetten...")
hf = huts_geojson(query(HUTS_Q).get("elements", []))
out_h = HERE / "soiusa_osm_huts.geojson"
out_h.write_text(json.dumps({"type": "FeatureCollection", "features": hf}, ensure_ascii=False),
                 encoding="utf-8")
print(f"-> soiusa_osm_huts.geojson  {len(hf)} Huetten  {out_h.stat().st_size//1024} KB")
print("Naechster Schritt: python build.py")
