#!/usr/bin/env python3
"""Fetch SOIUSA polygons from ARPA Piemonte ArcGIS REST service.

Saves:
  soiusa_sezioni.geojson     - all 36 Sezioni outlines (Layer 5), simplified
  soiusa_highlights.geojson  - Michaels 12 visited SOIUSA polygons, with DE labels
"""
import json
import pathlib
import urllib.parse
import urllib.request

HERE = pathlib.Path(__file__).parent
BASE = (
    "https://webgis.arpa.piemonte.it/ags/rest/services"
    "/topografia_dati_di_base/SOIUSA/MapServer"
)

try:
    from shapely.geometry import shape, mapping
    from shapely.ops import unary_union
    HAS_SHAPELY = True
    print("shapely OK — union + simplify aktiv")
except ImportError:
    HAS_SHAPELY = False
    print("shapely fehlt — nur Server-Simplification + Koord-Runden")

# ── DE → SOIUSA mapping (12 unique SOIUSA-Flächen) ──────────────────────────
# tour_ids verweisen auf touren.json-IDs; Silvretta/Verwall teilen eine STS.
HIGHLIGHTS = [
    {
        "name_de": "Berchtesgadener Alpen",
        "layer": 7, "field": "STS",
        "soiusa": "Alpi di Berchtesgaden",
        "tour_ids": [1],
    },
    {
        "name_de": "Ötztaler Alpen / Texelgruppe",
        "layer": 7, "field": "STS",
        "soiusa": "Alpi Venoste (Ötztaler Alpen)",
        "tour_ids": [2],
    },
    {
        "name_de": "Lechquellengebirge",
        "layer": 7, "field": "STS",
        "soiusa": "Monti delle Lechquellen",
        "tour_ids": [3],
    },
    {
        "name_de": "Kaisergebirge",
        "layer": 7, "field": "STS",
        "soiusa": "Monti del Kaiser",
        "tour_ids": [4],
    },
    {
        "name_de": "Grajische Alpen / Mont-Blanc",
        "layer": 7, "field": "STS",
        "soiusa": "Alpi del Monte Bianco",
        "tour_ids": [5],
    },
    {
        "name_de": "Silvretta / Verwall",
        "layer": 7, "field": "STS",
        "soiusa": "Alpi del Silvretta, del Samnaun e del Verwall",
        "tour_ids": [6, 11, 12],
    },
    {
        "name_de": "Karnische Alpen",
        "layer": 7, "field": "STS",
        "soiusa": "Alpi Carniche",
        "tour_ids": [7],
    },
    {
        "name_de": "Rätikon",
        "layer": 7, "field": "STS",
        "soiusa": "Rätikon",
        "tour_ids": [8],
    },
    {
        "name_de": "Dolomiten / Rosengarten",
        "layer": 11, "field": "GR",
        "soiusa": "Gruppo del Catinaccio",
        "tour_ids": [9],
    },
    {
        "name_de": "Gardaseeberge",
        "layer": 7, "field": "STS",
        "soiusa": "Prealpi Gardesane",
        "tour_ids": [10],
    },
    {
        "name_de": "Stubaier Alpen",
        "layer": 7, "field": "STS",
        "soiusa": "Alpi dello Stubai",
        "tour_ids": [13],
    },
    {
        "name_de": "Dachsteingebirge / Gosaukamm",
        "layer": 7, "field": "STS",
        "soiusa": "Monti del Dachstein",
        "tour_ids": [14],
    },
]


# ── Helpers ──────────────────────────────────────────────────────────────────

def fetch_geojson(layer, where, max_offset=0.003):
    params = {
        "where": where,
        "outFields": "SZ,STS,GR,CODICE",
        "outSR": "4326",
        "maxAllowableOffset": str(max_offset),
        "returnGeometry": "true",
        "f": "geojson",
    }
    url = f"{BASE}/{layer}/query?" + urllib.parse.urlencode(params)
    label = where if len(where) <= 60 else where[:57] + "..."
    print(f"  L{layer} | {label}", end=" ", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
    n = len(data.get("features", []))
    print(f"→ {n} feat")
    return data


def round_coords(geom, decimals=4):
    """Round all coordinates in a GeoJSON geometry dict in-place."""
    t = geom.get("type", "")
    c = geom.get("coordinates")
    if c is None:
        # GeometryCollection
        for g in geom.get("geometries", []):
            round_coords(g, decimals)
        return geom
    if t == "Point":
        geom["coordinates"] = [round(v, decimals) for v in c]
    elif t in ("LineString", "MultiPoint"):
        geom["coordinates"] = [[round(v, decimals) for v in p] for p in c]
    elif t in ("Polygon", "MultiLineString"):
        geom["coordinates"] = [
            [[round(v, decimals) for v in p] for p in ring] for ring in c
        ]
    elif t == "MultiPolygon":
        geom["coordinates"] = [
            [[[round(v, decimals) for v in p] for p in ring] for ring in poly]
            for poly in c
        ]
    return geom


def merge_features(features, props, tolerance=0.001, decimals=4):
    """Union features → single Feature; fallback: keep all with same props."""
    if HAS_SHAPELY and features:
        geoms = []
        for f in features:
            g = f.get("geometry")
            if g:
                try:
                    geom = shape(g)
                    if not geom.is_valid:
                        geom = geom.buffer(0)  # fix self-intersections
                    geoms.append(geom)
                except Exception:
                    pass
        if geoms:
            merged = unary_union(geoms).simplify(tolerance, preserve_topology=True)
            return [{
                "type": "Feature",
                "geometry": round_coords(mapping(merged), decimals),
                "properties": props,
            }]
    # Fallback ohne shapely: alle Features behalten, jedes mit denselben Props
    result = []
    for f in features:
        g = f.get("geometry")
        if g:
            result.append({
                "type": "Feature",
                "geometry": round_coords(g, decimals),
                "properties": props,
            })
    return result


# ════════════════════════════════════════════════════════════════════════════
# 1. Layer 7 — alle 132 Sottosezioni (STS) → nur union (kein Simplify), _raw cachen
#    Topologie-erhaltende Vereinfachung übernimmt simplify_sts.py (mapshaper).
# ════════════════════════════════════════════════════════════════════════════
print("\n--- Layer 7: Sottosezioni (alle 132 STS) → raw cache ---------------")
raw7 = fetch_geojson(7, "1=1", max_offset=0.001)

# Gruppieren nach STS-Name und nur union (kein shapely.simplify)
by_sts = {}
for feat in raw7["features"]:
    sts = feat["properties"].get("STS") or "?"
    by_sts.setdefault(sts, []).append(feat)

raw_sts_features = []
for sts in sorted(by_sts):
    feats = by_sts[sts]
    if HAS_SHAPELY:
        geoms = []
        for f in feats:
            g = f.get("geometry")
            if g:
                try:
                    geom = shape(g)
                    if not geom.is_valid:
                        geom = geom.buffer(0)
                    geoms.append(geom)
                except Exception:
                    pass
        if geoms:
            merged_geom = unary_union(geoms)
            first_codice = feats[0]["properties"].get("CODICE", "")
            raw_sts_features.append({
                "type": "Feature",
                "geometry": round_coords(mapping(merged_geom), 5),
                "properties": {"STS": sts, "CODICE": first_codice},
            })
    else:
        first_codice = feats[0]["properties"].get("CODICE", "")
        raw_sts_features.append({
            "type": "Feature",
            "geometry": round_coords(feats[0]["geometry"], 5),
            "properties": {"STS": sts, "CODICE": first_codice},
        })

raw_fc = {"type": "FeatureCollection", "features": raw_sts_features}
out_raw = HERE / "soiusa_sts_raw.geojson"
out_raw.write_text(json.dumps(raw_fc, ensure_ascii=False), encoding="utf-8")
kb_raw = out_raw.stat().st_size / 1024
print(f"  → soiusa_sts_raw.geojson  {len(raw_sts_features)} Features  {kb_raw:.0f} KB")
print("  Jetzt: python simplify_sts.py")


# ════════════════════════════════════════════════════════════════════════════
# 2. Highlights — 12 besuchte SOIUSA-Flächen
# ════════════════════════════════════════════════════════════════════════════
print("\n--- Highlights: 12 besuchte Flaechen -------------------------------")
hl_features = []

for h in HIGHLIGHTS:
    # Escape single quotes in SQL string literal
    val = h["soiusa"].replace("'", "''")
    where = f"{h['field']} = '{val}'"
    raw = fetch_geojson(h["layer"], where, max_offset=0.003)
    if not raw.get("features"):
        print(f"  !! KEIN TREFFER: {h['name_de']} | {h['soiusa']}")
        continue
    # For GR-level highlights (e.g. Catinaccio), capture the parent STS name
    first_feat_props = raw["features"][0]["properties"] if raw.get("features") else {}
    props = {
        "name_de":    h["name_de"],
        "soiusa_name": h["soiusa"],
        "tour_ids":   h["tour_ids"],
        "match_field": h["field"],
        "parent_sts":  first_feat_props.get("STS", ""),
    }
    merged_list = merge_features(raw["features"], props, tolerance=0.001)
    hl_features.extend(merged_list)

hl_fc = {"type": "FeatureCollection", "features": hl_features}
out_hl = HERE / "soiusa_highlights.geojson"
out_hl.write_text(json.dumps(hl_fc, ensure_ascii=False), encoding="utf-8")
kb_hl = out_hl.stat().st_size / 1024
print(f"  → soiusa_highlights.geojson  {len(hl_features)} Features  {kb_hl:.0f} KB")

print(f"\nHighlights: {kb_hl:.0f} KB")
print("Naechster Schritt: python simplify_sts.py")
