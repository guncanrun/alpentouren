#!/usr/bin/env python3
"""Assign country + ColorBrewer color to each SOIUSA STS polygon.
Injects visited/name_de/tour_ids from highlights.
Creates mask polygon (bounding box minus STS union) for non-Alpine darkening.
Generates label anchor points (one per STS) and cleaned highlight geometries.

Reads:  soiusa_sts.geojson + soiusa_highlights.geojson
Writes: soiusa_sts_colored.geojson + soiusa_mask.geojson
        soiusa_sts_label_points.geojson   (1 point per STS for symbol layers)
        soiusa_highlights_clean.geojson   (unary_union per group, no internal borders)

Pipeline: fetch_soiusa.py -> simplify_sts.py -> assign_countries.py -> build.py
"""
import hashlib
import json
import pathlib
import sys
import urllib.request
from collections import defaultdict

try:
    from shapely.geometry import box, mapping, shape
    from shapely.ops import unary_union
    try:
        from shapely.validation import make_valid as _mk
        def _ensure_valid(g): return _mk(g)
    except ImportError:
        def _ensure_valid(g): return g.buffer(0)
except ImportError:
    print("FEHLER: shapely fehlt -- pip install shapely")
    sys.exit(1)

HERE = pathlib.Path(__file__).parent

# ── ColorBrewer qualitative families per country ──────────────────────────────
# Multiple shades; shade chosen deterministically from STS name hash.
# Saturation/brightness chosen to be visible at fill-opacity 0.30 over satellite.
COUNTRY_PALETTES = {
    "AT": ["#7c3aed", "#8b5cf6", "#a78bfa", "#9333ea", "#6d28d9", "#7e22ce", "#a855f7", "#5b21b6"],
    "CH": ["#dc2626", "#ef4444", "#b91c1c", "#e53e3e", "#c53030", "#fc8181", "#f56565", "#991b1b"],
    "DE": ["#d97706", "#f59e0b", "#b45309", "#f6ad55", "#ed8936", "#92400e", "#fbbf24", "#c05621"],
    "FR": ["#2563eb", "#3b82f6", "#1d4ed8", "#4299e1", "#1e40af", "#2b6cb0", "#63b3ed", "#1e3a8a"],
    "IT": ["#16a34a", "#22c55e", "#15803d", "#48bb78", "#166534", "#38a169", "#276749", "#14532d"],
    "SI": ["#0891b2", "#06b6d4", "#0e7490", "#22d3ee", "#155e75", "#4fd1c7", "#38b2ac", "#164e63"],
    "LI": ["#d97706", "#f59e0b", "#b45309"],  # same family as DE
    "MC": ["#2563eb", "#3b82f6"],              # same family as FR
    "OTHER": ["#6b7280", "#9ca3af", "#4b5563", "#64748b", "#475569"],
}

ALPINE_ISO = {"AT", "CH", "DE", "FR", "IT", "SI", "LI", "MC"}

# ── Natural Earth 110m countries ─────────────────────────────────────────────
NE_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
    "master/geojson/ne_110m_admin_0_countries.geojson"
)
NE_CACHE = HERE / "ne_110m_countries.geojson"


def load_ne_countries():
    if NE_CACHE.exists():
        print(f"  NE-Cache: {NE_CACHE.stat().st_size // 1024} KB")
    else:
        print("  Lade Natural Earth 110m countries von GitHub...")
        req = urllib.request.Request(NE_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=90) as r:
            data = r.read()
        NE_CACHE.write_bytes(data)
        print(f"  -> {len(data) // 1024} KB gecacht")
    ne = json.loads(NE_CACHE.read_text(encoding="utf-8"))
    alpine = {}
    for feat in ne["features"]:
        p = feat["properties"]
        iso = p.get("ISO_A2", "")
        if not iso or iso.startswith("-"):   # NE uses "-99" for some countries
            iso = p.get("ADM0_A3", "")[:2]
        if iso not in ALPINE_ISO:
            continue
        try:
            g = shape(feat["geometry"])
            if not g.is_valid:
                g = g.buffer(0)
            alpine[iso] = g
        except Exception:
            pass
    print(f"  Alpine Laender geladen: {sorted(alpine.keys())}")
    return alpine


def country_for(sts_geom, alpine_countries):
    """Return ISO code of the country with the largest intersection area."""
    best_iso = "OTHER"
    best_area = 0.0
    for iso, cgeom in alpine_countries.items():
        try:
            inter = sts_geom.intersection(cgeom)
            a = inter.area
            if a > best_area:
                best_area = a
                best_iso = iso
        except Exception:
            pass
    return best_iso


def shade_for(sts_name, palette):
    """Pick a palette shade deterministically from STS name hash. (unused since Settore recolor)"""
    idx = int(hashlib.md5(sts_name.encode("utf-8")).hexdigest()[:4], 16) % len(palette)
    return palette[idx]


# ── SOIUSA Grandi Settori (flat fill colors) ──────────────────────────────────
# Fill follows the 5 big SOIUSA sectors, derived from CODICE (PARTE/letter),
# not country. `country` property is kept for the later 2c panel iteration.
SETTORE = {
    "I/A":  ("Südwestalpen",    "#c25a68"),
    "I/B":  ("Nordwestalpen",   "#2f6fed"),
    "II/B": ("Nordostalpen",    "#16a34a"),
    "II/A": ("Zentralostalpen", "#8b5cf6"),
    "II/C": ("Südostalpen",     "#0ea5b5"),
}


def settore_of(codice):
    """Derive the Settore key (e.g. 'II/B') from a CODICE like 'II/B.28.5'."""
    c = str(codice or "")
    if "/" not in c:
        return None
    parte, rest = c.split("/", 1)
    letter = rest[0] if rest else ""
    return f"{parte}/{letter}"


# ── Label text normalization (remove chars outside loaded glyph ranges) ─────────
_NORM = [
    ('—', '-'),  # em dash
    ('–', '-'),  # en dash
    ('‒', '-'),  # figure dash
    ('‘', "'"),  # left single quote
    ('’', "'"),  # right single quote
    ('ʼ', "'"),  # modifier apostrophe
    ('“', '"'),  # left double quote
    ('”', '"'),  # right double quote
    (' ', ' '),  # non-breaking space
    (' ', ' '),  # narrow no-break space
    (' ', ' '),  # thin space
    ('≈', '~'),  # approximately equal (not in Latin-1)
    ('…', '...'),# horizontal ellipsis
]

def normalize_label(s):
    if not s:
        return s
    for old, new in _NORM:
        s = s.replace(old, new)
    return s.strip()


# ── Load inputs ───────────────────────────────────────────────────────────────
for fname in ("soiusa_sts.geojson", "soiusa_highlights.geojson"):
    if not (HERE / fname).exists():
        print(f"FEHLER: {fname} fehlt -- Pipeline-Reihenfolge pruefen.")
        sys.exit(1)

sts_data = json.loads((HERE / "soiusa_sts.geojson").read_text(encoding="utf-8").replace("\x00", ""))
hl_data  = json.loads((HERE / "soiusa_highlights.geojson").read_text(encoding="utf-8").replace("\x00", ""))

print(f"STS-Eingabe: {len(sts_data['features'])} Features")
print(f"Highlights:  {len(hl_data['features'])} Features")

# ── Build visited lookup: soiusa_name (or parent_sts) -> hl properties ────────
visited_by_sts = {}
for feat in hl_data["features"]:
    p = feat["properties"]
    if p.get("match_field", "STS") == "STS":
        key = p["soiusa_name"]
    else:
        # GR-level (Catinaccio): mark parent STS as visited
        key = p.get("parent_sts", "")
    if key:
        visited_by_sts[key] = p

print(f"Visited-Lookup: {len(visited_by_sts)} STS-Namen")

# ── Load Natural Earth country polygons ───────────────────────────────────────
print("\nNatural Earth laden...")
alpine_countries = load_ne_countries()

# ── German name lookup for AT/DE/Südtirol SOIUSA groups ──────────────────────
# Applied to non-visited features; visited groups keep their tour-derived name_de.
# Sources: AVE-Einteilung der Ostalpen, Wikipedia "Gebirgsgruppen der Alpen".
DE_NAMES = {
    # ── Österreich ────────────────────────────────────────────────────────────
    "Alpi Nord-orientali di Stiria":         "Nordöstliche Steirische Alpen",
    "Alpi Scistose Salisburghesi":           "Salzburger Schieferalpen",
    "Alpi Venoste (Ötztaler Alpen)":         "Ötztaler Alpen",
    "Alpi del Silvretta, del Samnaun e del Verwall": "Silvretta / Samnaun / Verwall",
    "Alpi dell'Algovia":                     "Allgäuer Alpen",
    "Alpi dell'Ennstal":                     "Ennstaler Alpen",
    "Alpi dell'Ybbstal":                     "Ybbstaler Alpen",
    "Alpi della Gurktal":                    "Gurktaler Alpen",
    "Alpi della Lavanttal":                  "Lavanttaler Alpen",
    "Alpi della Lechtal":                    "Lechtaler Alpen",
    "Alpi dello Stubai":                     "Stubaier Alpen",
    "Alpi di Berchtesgaden":                 "Berchtesgadener Alpen",
    "Alpi di Brandenberg":                   "Brandenberger Alpen",
    "Alpi di Kitzbühel":                     "Kitzbüheler Alpen",
    "Alti Tauri (Hohe Tauern)":              "Hohe Tauern",
    "Caravanche":                            "Karawanken",
    "Gailtaler Alpen (Alpi della Gail)":     "Gailtaler Alpen",
    "Kreuzeckgruppe":                        "Kreuzeckgruppe",
    "Monti Totes":                           "Totes Gebirge",
    "Monti del Dachstein":                   "Dachsteingebirge",
    "Monti del Kaiser":                      "Kaisergebirge",
    "Monti del Karwendel":                   "Karwendel",
    "Monti del Salzkammergut":               "Salzkammergutberge",
    "Monti delle Lechquellen":               "Lechtaler Quellengebirge",
    "Monti dello Stein":                     "Steinernes Meer",
    "Monti di Mieming e del Wetterstein":    "Mieminger Kette / Wettersteingebirge",
    "Monti di Tennen":                       "Tennengebirge",
    "Prealpi Orientali della Bassa Austria": "Niederösterreichische Voralpen",
    "Prealpi centrali di Stiria":            "Eisenwurzen",
    "Prealpi del Tux":                       "Tuxer Voralpen",
    "Prealpi dell'Alta Austria":             "Oberösterreichische Voralpen",
    "Prealpi di Bregenz":                    "Bregenzer Wald",
    "Prealpi nord-occidentali di Stiria":    "Nordwestliche Steirische Voralpen",
    "Prealpi orientali di Stiria":           "Östliche Steirische Voralpen",
    "Prealpi sud-occidentali di Stiria":     "Südwestliche Steirische Voralpen",
    "Rätikon":                               "Rätikon",
    "Tauri di Radstadt":                     "Radstädter Tauern",
    "Tauri di Schladming e di Murau":        "Schladminger Tauern",
    "Tauri di Seckau":                       "Seckauer Tauern",
    "Tauri di Wölz e di Rottenmann":         "Wölzer / Rottenmanner Tauern",
    # ── Deutschland ───────────────────────────────────────────────────────────
    "Alpi del Chiemgau":                     "Chiemgauer Alpen",
    "Alpi del Mangfall":                     "Mangfallgebirge",
    "Alpi del Wallgau":                      "Werdenfelsner Alpen",
    "Alpi dell'Ammergau":                    "Ammergauer Alpen",
    # ── Südtirol / deutschsprachiges IT ──────────────────────────────────────
    "Alpi della Zillertal":                  "Zillertaler Alpen",
    "Alpi dell'Ortles":                      "Ortlergruppe",
    "Alpi Pusteresi (Defereggen Alpen)":     "Defereggen Alpen",
    "Alpi Sarentine (Sarntaler Alpen)":      "Sarntaler Alpen",
    # ── Schweiz (West + Rätische Alpen) ───────────────────────────────────────
    "Alpi Bernesi p.d.":                     "Berner Alpen",
    "Alpi Glaronesi p,d,":                   "Glarner Alpen",
    "Alpi Ticinesi e del Verbano":           "Tessiner Alpen",
    "Alpi Urane":                            "Urner Alpen",
    "Alpi Urano-Glaronesi":                  "Urner-Glarner Alpen",
    "Alpi del Grand Combin":                 "Grand-Combin-Gruppe",
    "Alpi del Mischabel e del Weissmies":    "Mischabel- und Weissmiesgruppe",
    "Alpi del Monte Leone e del San Gottardo":"Monte-Leone- und Gotthardgruppe",
    "Alpi del Platta":                       "Oberhalbsteiner Alpen",
    "Alpi del Plessur":                      "Plessur-Alpen",
    "Alpi del Weisshorn e del Cervino":      "Weisshorn- und Matterhorngruppe",
    "Alpi dell'Adula":                       "Adula-Alpen",
    "Alpi dell'Albula":                      "Albula-Alpen",
    "Alpi della Val Müstair":                "Münstertaler Alpen",
    "Alpi di Livigno":                       "Livigno-Alpen",
    "Alpi di Vaud":                          "Waadtländer Alpen",
    "Prealpi Appenzellesi e Sangallesi":     "Appenzeller und St. Galler Voralpen",
    "Prealpi Bernesi":                       "Berner Voralpen",
    "Prealpi Lucernesi e Untervaldesi":      "Luzerner und Unterwaldner Voralpen",
    "Prealpi Svittesi e Urane":              "Schwyzer und Urner Voralpen",
    "Prealpi di Vaud e Friburgo":            "Waadtländer und Freiburger Voralpen",
    # ── Frankreich (Toponym behalten, generisch eindeutschen) ─────────────────
    "Alpi Marittime":                        "Seealpen",
    "Alpi del Beaufortain":                  "Beaufortain",
    "Alpi del Moncenisio":                   "Mont-Cenis-Gruppe",
    "Alpi della Vanoise e del Grand Arc":    "Vanoise- und Grand-Arc-Gruppe",
    "Alpi delle Grandes Rousses e Aiguilles d'Arves": "Grandes Rousses und Aiguilles d'Arves",
    "Alpi di Provenza":                      "Provenzalische Alpen",
    "Catena di Belledonne":                  "Belledonne-Kette",
    "Massiccio degli Écrins":                "Écrins-Massiv",
    "Massiccio del Champsaur":               "Champsaur-Massiv",
    "Massiccio del Taillefer":               "Taillefer-Massiv",
    "Massiccio dell'Embrunais":              "Embrunais-Massiv",
    "Monti orientali di Gap":                "Berge östlich von Gap",     # ⚠ Cowork-Vorschlag
    "Prealpi dei Bauges":                    "Bauges-Voralpen",
    "Prealpi dei Bornes":                    "Bornes-Voralpen",
    "Prealpi del Devoluy":                   "Dévoluy-Voralpen",
    "Prealpi del Diois":                     "Diois-Voralpen",
    "Prealpi del Giffre":                    "Giffre-Voralpen",
    "Prealpi del Vercors":                   "Vercors-Voralpen",
    "Prealpi della Chartreuse":              "Chartreuse-Voralpen",
    "Prealpi delle Baronnies":               "Baronnies-Voralpen",
    "Prealpi dello Chablais":                "Chablais-Voralpen",
    "Prealpi di Digne":                      "Voralpen von Digne",
    "Prealpi di Grasse":                     "Voralpen von Grasse",
    "Prealpi di Nizza":                      "Voralpen von Nizza",
    "Prealpi di Vaucluse":                   "Vaucluse-Voralpen",
    "Prealpi occidentali di Gap":            "Westliche Voralpen von Gap",
    # ── Italien (West + Ost) ──────────────────────────────────────────────────
    "Alpi Biellesi e Cusiane":               "Bielleser und Cusianer Alpen",  # ⚠ Cowork-Vorschlag
    "Alpi Giulie":                           "Julische Alpen",
    "Alpi Orobie":                           "Bergamasker Alpen",
    "Alpi del Bernina":                      "Berninagruppe",
    "Alpi del Gran Paradiso":                "Gran-Paradiso-Gruppe",
    "Alpi del Marguareis":                   "Marguareis-Gruppe",             # ⚠ Cowork-Vorschlag
    "Alpi del Monginevro":                   "Montgenèvre-Alpen",
    "Alpi del Monte Rosa":                   "Monte-Rosa-Alpen",
    "Alpi del Monviso":                      "Monviso-Gruppe",
    "Alpi dell'Adamello e della Presanella": "Adamello-Presanella-Alpen",
    "Alpi della Grande Sassière e del Rutor":"Grande-Sassière- und Rutor-Gruppe",
    "Alpi della Val di Non":                 "Nonsberggruppe",
    "Alpi di Lanzo e dell'Alta Moriana":     "Lanzo- und Obermaurienne-Alpen", # ⚠ Cowork-Vorschlag
    "Catena delle Aiguilles Rouges":         "Aiguilles-Rouges-Kette",
    "Dolomiti Feltrine e delle Pale di San Martino": "Feltriner Dolomiten und Palagruppe",
    "Dolomiti di Brenta":                    "Brentagruppe",
    "Dolomiti di Fiemme":                    "Fleimstaler Dolomiten",
    "Dolomiti di Sesto, di Braies e d'Ampezzo": "Sextner, Pragser und Ampezzaner Dolomiten",
    "Dolomiti di Zoldo":                     "Zoldaner Dolomiten",            # ⚠ Cowork-Vorschlag
    "Prealpi Bellunesi":                     "Belluneser Voralpen",
    "Prealpi Bergamasche":                   "Bergamasker Voralpen",
    "Prealpi Bresciane":                     "Brescianer Voralpen",
    "Prealpi Carniche":                      "Karnische Voralpen",
    "Prealpi Comasche":                      "Comer Voralpen",
    "Prealpi Giulie":                        "Julische Voralpen",
    "Prealpi Liguri":                        "Ligurische Voralpen",
    "Prealpi Varesine":                      "Vareser Voralpen",
    "Prealpi vicentine":                     "Vicentiner Voralpen",
    # ── Slowenien ─────────────────────────────────────────────────────────────
    "Alpi di Kamnik e della Savinja":        "Steiner Alpen",
    "Prealpi Slovene nord-orientali":        "Nordöstliche Slowenische Voralpen",
    "Prealpi Slovene occidentali":           "Westliche Slowenische Voralpen",
    "Prealpi Slovene orientali":             "Östliche Slowenische Voralpen",
}

# ── Assign country + color + visited info to each STS feature ─────────────────
print("\nLaenderzuordnung (131 Flaechen × 6-8 Laender)...")
country_count = {}
settore_count = {}
for i, feat in enumerate(sts_data["features"]):
    sts_name = feat["properties"].get("STS", f"unbekannt_{i}")
    try:
        sts_geom = shape(feat["geometry"])
        if not sts_geom.is_valid:
            sts_geom = _ensure_valid(sts_geom)
    except Exception:
        sts_geom = None

    iso = country_for(sts_geom, alpine_countries) if sts_geom else "OTHER"
    country_count[iso] = country_count.get(iso, 0) + 1

    # Fill color follows the 5 SOIUSA Grandi Settori (flat), derived from CODICE.
    key = settore_of(feat["properties"].get("CODICE"))
    name_settore, color = SETTORE.get(key, ("—", "#6b7280"))
    settore_count[name_settore] = settore_count.get(name_settore, 0) + 1

    # Visited data
    if sts_name in visited_by_sts:
        vp = visited_by_sts[sts_name]
        feat["properties"]["visited"]  = 1
        feat["properties"]["name_de"]  = normalize_label(vp.get("name_de", ""))
        feat["properties"]["tour_ids"] = json.dumps(vp.get("tour_ids", []))
    else:
        feat["properties"]["visited"]  = 0
        feat["properties"]["name_de"]  = normalize_label(DE_NAMES.get(sts_name, ""))
        feat["properties"]["tour_ids"] = "[]"

    feat["properties"]["country"]    = iso
    feat["properties"]["settore"]    = name_settore
    feat["properties"]["fill_color"] = color
    feat["properties"]["STS"]        = normalize_label(sts_name)

    if (i + 1) % 20 == 0 or (i + 1) == len(sts_data["features"]):
        print(f"  {i+1}/{len(sts_data['features'])}  letzte: {iso} {sts_name[:40]}")

print("\nLaender-Verteilung:", dict(sorted(country_count.items())))
print("Settore-Verteilung:", dict(sorted(settore_count.items())))

# ── Write soiusa_sts_colored.geojson ─────────────────────────────────────────
out_colored = HERE / "soiusa_sts_colored.geojson"
out_colored.write_text(json.dumps(sts_data, ensure_ascii=False), encoding="utf-8")
kb = out_colored.stat().st_size / 1024
print(f"\n-> soiusa_sts_colored.geojson  {len(sts_data['features'])} Features  {kb:.0f} KB")

# ── Build mask polygon: bounding box minus union of all STS ───────────────────
print("\nMaske berechnen (bbox - Union aller STS)...")
bbox = box(-30.0, 25.0, 50.0, 75.0)  # much larger than viewport, outer edge never visible
sts_geoms = []
for feat in sts_data["features"]:
    try:
        g = shape(feat["geometry"])
        if not g.is_valid:
            g = _ensure_valid(g)
        if g and not g.is_empty:
            sts_geoms.append(g)
    except Exception:
        pass

alps_union = unary_union(sts_geoms)
alps_union_simple = alps_union.simplify(0.008, preserve_topology=True)
mask_geom = bbox.difference(alps_union_simple)
mask_geom = mask_geom.simplify(0.008, preserve_topology=True)

mask_fc = {
    "type": "FeatureCollection",
    "features": [{
        "type": "Feature",
        "geometry": mapping(mask_geom),
        "properties": {},
    }],
}
out_mask = HERE / "soiusa_mask.geojson"
out_mask.write_text(json.dumps(mask_fc, ensure_ascii=False), encoding="utf-8")
kb_mask = out_mask.stat().st_size / 1024
print(f"-> soiusa_mask.geojson  {kb_mask:.0f} KB")

# ── Generate label anchor points (1 per STS, guaranteed inside polygon) ──────
# Used in build.py as source 'sts-lp' for symbol layers → one label per group,
# no per-tile / per-polygon duplicates.
print("\nLabel-Ankerpunkte (1 pro STS)...")
lp_features = []
for feat in sts_data["features"]:
    try:
        g = shape(feat["geometry"])
        if not g.is_valid:
            g = _ensure_valid(g)
        pt = g.representative_point()
        lp_features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [pt.x, pt.y]},
            "properties": dict(feat["properties"]),
        })
    except Exception as e:
        print(f"  SKIP {feat['properties'].get('STS', '?')}: {e}")

lp_fc = {"type": "FeatureCollection", "features": lp_features}
out_lp = HERE / "soiusa_sts_label_points.geojson"
out_lp.write_text(json.dumps(lp_fc, ensure_ascii=False), encoding="utf-8")
print(f"-> soiusa_sts_label_points.geojson  {len(lp_features)} Punkte  {out_lp.stat().st_size // 1024} KB")

# ── Clean highlights: replace geometry with already-simplified STS polygon ────
# Internal orange lines come from complex/raw-derived polygons in soiusa_highlights.
# Fix: swap the geometry with the corresponding simplified polygon from sts_data
# (already run through mapshaper + make_valid). Same logical area, guaranteed clean.
print("\nHighlights bereinigen (Geometrie durch simplifizierte STS-Polygon ersetzen)...")
sts_geom_by_name = {
    feat["properties"].get("STS", ""): feat["geometry"]
    for feat in sts_data["features"]
}

hl_by_key = defaultdict(list)
for feat in hl_data["features"]:
    p = feat["properties"]
    key = p.get("soiusa_name") if p.get("match_field", "STS") == "STS" else p.get("parent_sts", "")
    if key:
        hl_by_key[key].append(feat)

clean_feats = []
for key, feats in hl_by_key.items():
    if key in sts_geom_by_name:
        clean_geom = sts_geom_by_name[key]
        source = "STS-simplified"
    else:
        # Fallback: dissolve original highlight geometries
        geoms = []
        for f in feats:
            try:
                g = shape(f["geometry"])
                if not g.is_valid:
                    g = _ensure_valid(g)
                if g and not g.is_empty:
                    geoms.append(g)
            except Exception:
                pass
        if not geoms:
            continue
        clean_geom = mapping(_ensure_valid(unary_union(geoms)))
        source = "fallback-union"
    clean_feats.append({
        "type": "Feature",
        "geometry": clean_geom,
        "properties": dict(feats[0]["properties"]),
    })
    print(f"  {source}  [{key[:50]}]")

clean_hl_fc = {"type": "FeatureCollection", "features": clean_feats}
out_clean_hl = HERE / "soiusa_highlights_clean.geojson"
out_clean_hl.write_text(json.dumps(clean_hl_fc, ensure_ascii=False), encoding="utf-8")
print(f"-> soiusa_highlights_clean.geojson  {len(clean_feats)} Gruppen  {out_clean_hl.stat().st_size // 1024} KB")

print("\nNaechster Schritt: python build.py")
