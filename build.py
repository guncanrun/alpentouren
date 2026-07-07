#!/usr/bin/env python3
"""Build a standalone index.html.

Pipeline: fetch_soiusa.py -> simplify_sts.py -> assign_countries.py -> build.py

Run:  python build.py
"""
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).parent

# ── Build mode: public (default, deployed) · private (--private) · standalone ──
# --standalone => eine file://-taugliche Datei (impliziert private): alle Daten/Libs
# inline, absolute Glyphs, base64-Fotos. Kein unpkg, kein relativer fetch.
STANDALONE = "--standalone" in sys.argv
PRIVATE    = ("--private" in sys.argv) or STANDALONE
PUBLIC     = not PRIVATE
SRC   = "touren.json"   # only the private/standalone build reads tour data (E8)
OUT   = ("index_privat_standalone.html" if STANDALONE
         else "index.html" if PUBLIC else "index_privat.html")
# Nachtjob P2: private Klartext-Strings kommen aus der gitignorierten privat_template.py.
# Der oeffentliche Build braucht sie NICHT (Public-Strings sind unten hartkodiert);
# der interne Build bricht ohne die Datei mit klarer Meldung ab.
try:
    import privat_template as _PT
except ImportError:
    _PT = None
if not PUBLIC and _PT is None:
    raise SystemExit("privat_template.py fehlt -- interner Build kann private Strings nicht "
                     "aufloesen. Der oeffentliche Build (python build.py) laeuft ohne die Datei.")

TITEL = "Alpen-Atlas" if PUBLIC else _PT.TITLE
UNTER = ("Die Alpen nach SOIUSA, der internationalen Alpen-Gliederung — Gruppen, Gipfel, "
         "Hütten & Pässe interaktiv. Fläche anklicken für Steckbrief."
         if PUBLIC else
         "Alpen-Gebirgsgruppen (SOIUSA) — Orange = besucht. Fläche anklicken.")


def load_compact(name):
    p = HERE / name
    if not p.exists():
        raise FileNotFoundError(f"{name} fehlt -- Pipeline-Reihenfolge pruefen.")
    raw = p.read_text(encoding="utf-8").replace("\x00", "").strip()
    return json.dumps(json.loads(raw), ensure_ascii=False, separators=(",", ":"))


# ── Label text normalization (mirrors assign_countries.py) ────────────────────
_NORM = [
    ('—', '-'), ('–', '-'), ('‒', '-'),
    (''', "'"), (''', "'"), ('ʼ', "'"),
    ('"', '"'), ('"', '"'),
    (' ', ' '), (' ', ' '), (' ', ' '),
    ('≈', '~'), ('…', '...'),
]
def normalize_label(s):
    if not s: return s
    for old, new in _NORM: s = s.replace(old, new)
    return s.strip()


# ── Data sources ─────────────────────────────────────────────────────────────
# E8: the PUBLIC build is a neutral SOIUSA atlas — it does NOT read any tour data.
if PUBLIC:
    data = {"touren": []}
    touren_json = "[]"
    tracks_json = "null"   # E8: keine Track-Daten im Public-Build
    personen_json = "null"  # E8: kein Personen-Register im Public-Build
else:
    _raw = (HERE / SRC).read_text(encoding="utf-8").replace("\x00", "").strip()
    data = json.loads(_raw)
    for t in data["touren"]:
        for k in ("gebirge", "gegend"):
            if t.get(k): t[k] = normalize_label(t[k])
    # Standalone (file://): Foto-src -> base64-data-URI (Datei lesen), damit keine
    # relativen Pfade noetig sind. Normaler Privat-Build behaelt die relative src.
    if STANDALONE:
        import base64 as _b64
        _foto_bytes = 0
        for t in data["touren"]:
            for f in (t.get("fotos") or []):
                src = f.get("src", "")
                p = HERE / src
                if src and p.exists():
                    b = p.read_bytes(); _foto_bytes += len(b)
                    f["src"] = "data:image/jpeg;base64," + _b64.b64encode(b).decode("ascii")
        if _foto_bytes > 6 * 1024 * 1024:
            print(f"WARN Fotos gesamt {_foto_bytes//1024} KB (>6 MB) -- Qualitaet/Anzahl pruefen.")

    # ── GPX-Tracks (rekonstruiert, SPEC_GPX_Tracks_Privat, 06.07.) ────────────
    # touren.json-Feld "gpx" = Pfad unter tracks/ (gitignored). Sanitize (Zeit-
    # stempel/Waypoints verwerfen, Duplikate raus) + Douglas-Peucker (~10 m) ->
    # schlanke 2D-LineStrings inline. km/hm werden aus dem VOLLEN Track berechnet
    # und in die Tour geschrieben (track_km/track_hm), Hoehen bleiben im Quell-GPX
    # (spaeteres Hoehenprofil-Paket). Nur Privat/Standalone (E8).
    import math as _m

    def _gpx_pts(path):
        raw = path.read_text(encoding="utf-8")
        pts = [(float(lo), float(la), float(el)) for la, lo, el in re.findall(
            r'<trkpt lat="(-?[0-9.]+)" lon="(-?[0-9.]+)">\s*<ele>(-?[0-9.]+)</ele>', raw)]
        return [p for i, p in enumerate(pts) if i == 0 or p[:2] != pts[i-1][:2]]

    def _hav_m(a, b):
        la1, lo1, la2, lo2 = map(_m.radians, (a[1], a[0], b[1], b[0]))
        return 6371000 * 2 * _m.asin(_m.sqrt(_m.sin((la2-la1)/2)**2 +
               _m.cos(la1) * _m.cos(la2) * _m.sin((lo2-lo1)/2)**2))

    def _dp(pts, tol):
        # Douglas-Peucker auf Grad-Koordinaten; tol 1e-4 Grad = ~8-11 m in den Alpen.
        if len(pts) < 3:
            return pts
        def _d(p, a, b):
            ax, ay, bx, by, px, py = a[0], a[1], b[0], b[1], p[0], p[1]
            dx, dy = bx - ax, by - ay
            if dx == 0 and dy == 0:
                return _m.hypot(px - ax, py - ay)
            t = max(0.0, min(1.0, ((px-ax)*dx + (py-ay)*dy) / (dx*dx + dy*dy)))
            return _m.hypot(px - (ax + t*dx), py - (ay + t*dy))
        keep = [False] * len(pts); keep[0] = keep[-1] = True
        stack = [(0, len(pts) - 1)]
        while stack:
            i0, i1 = stack.pop()
            if i1 <= i0 + 1:
                continue
            dmax, imax = 0.0, None
            for i in range(i0 + 1, i1):
                d = _d(pts[i], pts[i0], pts[i1])
                if d > dmax:
                    dmax, imax = d, i
            if imax is not None and dmax > tol:
                keep[imax] = True
                stack += [(i0, imax), (imax, i1)]
        return [p for p, k in zip(pts, keep) if k]

    _tfeats = []
    for t in data["touren"]:
        rel = t.get("gpx")
        if not rel:
            continue
        p = HERE / rel
        if not p.exists():
            print(f"[tracks] WARN {rel} fehlt -- Tour {t['id']} ohne Linie")
            continue
        pts = _gpx_pts(p)
        km = sum(_hav_m(pts[i], pts[i+1]) for i in range(len(pts)-1)) / 1000
        hm = sum(max(0.0, pts[i+1][2] - pts[i][2]) for i in range(len(pts)-1))
        simp = _dp(pts, 1e-4)
        t["track_km"] = round(km, 1)
        t["track_hm"] = int(round(hm / 10) * 10)
        # Gap-Guard (Fliessband-Warnung): grosser Nachbarpunkt-Sprung in den ROHPUNKTEN deutet
        # auf einen GPS-Ausreisser/Teleport (Luftlinien-Diagonale im Render). WARN ab > 500 m;
        # es wird NICHTS automatisch entfernt -- der Track ist dann von Hand zu pruefen/ersetzen.
        # (Auf den ROHPUNKTEN, nicht dem DP-Ergebnis: DP laesst auf geraden Passagen bewusst
        #  groessere, legitime Abstaende zwischen zwei Stuetzpunkten.)
        _gapmax, _gapidx = 0.0, -1
        for _gi in range(len(pts) - 1):
            _gd = _hav_m(pts[_gi], pts[_gi + 1])
            if _gd > _gapmax:
                _gapmax, _gapidx = _gd, _gi
        if _gapmax > 500:
            print(f"[tracks] WARN Tour {t['id']}: Rohpunkt-Sprung {_gapmax:.0f} m bei Punkt "
                  f"{_gapidx} ({pts[_gapidx][1]:.4f},{pts[_gapidx][0]:.4f}) -> moegl. GPS-Ausreisser")
        # P5: ele (ganze Meter) als 3. Koordinatenwert behalten -> Hoehenprofil-Sparkline.
        # MapLibre nutzt fuer die 2D-Linie nur x/y; der z-Wert wird ignoriert (nur Daten).
        _tfeats.append({"type": "Feature",
            "geometry": {"type": "LineString",
                         "coordinates": [[round(x, 5), round(y, 5), round(_e)] for x, y, _e in simp]},
            "properties": {"tour_id": t["id"],
                           "rek": 1 if t.get("gpx_rekonstruiert") else 0}})
        print(f"[tracks] Tour {t['id']}: {len(pts)} -> {len(simp)} Punkte · {km:.1f} km · +{hm:.0f} hm")
    tracks_json = json.dumps({"type": "FeatureCollection", "features": _tfeats},
                             ensure_ascii=False, separators=(",", ":"))

    # ── Personen-Register (privat/gitignored, SPEC_Personenfilter) — nur Privat/Standalone ──
    # personen.json inline (const PERSONEN, PRIV-Block). Validierung: jede teilnehmer_ids-id
    # muss im Register existieren -> sonst WARN (check.py FAILt zusätzlich über die Rohdaten).
    _preg = HERE / "personen.json"
    if _preg.exists():
        _pdata = json.loads(_preg.read_text(encoding="utf-8").replace("\x00", "").strip())
        _known = {p["id"] for p in _pdata.get("personen", [])}
        _bad = 0
        for t in data["touren"]:
            for _pid in (t.get("teilnehmer_ids") or []):
                if _pid not in _known:
                    print(f"[personen] WARN Tour {t['id']}: unbekannte teilnehmer_id '{_pid}'")
                    _bad += 1
        print(f"  Personen-Register: {len(_known)} Personen · {_bad} unbekannte teilnehmer_ids")
        personen_json = json.dumps(_pdata, ensure_ascii=False, separators=(",", ":"))
    else:
        print("[personen] WARN personen.json fehlt -- Register leer (Filter-Chips ohne Namen)")
        personen_json = '{"personen":[]}'

    touren_json = json.dumps(data["touren"], ensure_ascii=False)

sts_json        = load_compact("soiusa_sts_colored.geojson")
highlights_json = load_compact("soiusa_highlights_clean.geojson") if (HERE / "soiusa_highlights_clean.geojson").exists() else '{"type":"FeatureCollection","features":[]}'
lp_json         = load_compact("soiusa_sts_label_points.geojson")
mask_json       = load_compact("soiusa_mask.geojson")

# ── Nachtjob P1: Besuchsmuster-Overlay (gitignored) NUR im Privat-Build mergen ──────
# Die getrackten colored/label_points sind neutral (visited:0, tour_ids:"[]"). Das
# Besuchsmuster liegt in der gitignorierten visited_overlay.json (Quelle der Wahrheit,
# {CODICE:{visited,tour_ids}}) und wird hier in-memory zurueckgemerged -> Privat-Render
# identisch wie zuvor. Public bleibt uniform (zeichnet ohnehin visited:0).
if not PUBLIC:
    _ovp = HERE / "visited_overlay.json"
    if _ovp.exists():
        _ov = json.loads(_ovp.read_text(encoding="utf-8"))
        def _merge_visited(_js):
            _d = json.loads(_js)
            for _f in _d["features"]:
                _c = _f["properties"].get("CODICE")
                if _c in _ov:
                    _f["properties"]["visited"] = _ov[_c].get("visited", 1)
                    _f["properties"]["tour_ids"] = json.dumps(_ov[_c].get("tour_ids", []))
            return json.dumps(_d, ensure_ascii=False, separators=(",", ":"))
        sts_json = _merge_visited(sts_json)
        lp_json  = _merge_visited(lp_json)
        print(f"  P1-Overlay: {len(_ov)} Gruppen visited/tour_ids gemerged (Privat)")
    else:
        print("[overlay] WARN visited_overlay.json fehlt -- Privat-Build ohne Besuchsmuster")

# ── Anreise-Orte v2: city/town + villages (Nutzer-Fund Tschagguns/Schruns) ──────
# v1 hatte NUR city/town -> Montafon-Talorte (village) fehlten. v2 nimmt villages
# wieder auf (kleinste Klasse); im Client erst ab z>=10 gerendert (Dichte-Schutz),
# in der Suche aber ohne Zoom-Gate auffindbar. Hamlets bleiben draußen. Dateiname
# bleibt soiusa_osm_places_v1.geojson (deployte Quelle, alle Referenzen unverändert).
_places_full = json.loads((HERE / "soiusa_osm_places.geojson").read_text(encoding="utf-8"))
_places_v1 = {"type": "FeatureCollection",
              "features": [f for f in _places_full["features"]
                           if f["properties"].get("place") in ("city", "town", "village")]}
(HERE / "soiusa_osm_places_v1.geojson").write_text(
    json.dumps(_places_v1, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
_pv = collections_places = {k: sum(1 for f in _places_v1["features"] if f["properties"].get("place") == k)
                            for k in ("city", "town", "village")}
print(f"  Orte-v2: {len(_places_v1['features'])} (city {_pv['city']} · town {_pv['town']} · village {_pv['village']}) von {len(_places_full['features'])} roh")

# ── §1 „Ihr wart hier": OSM-Hütten-Name -> Besuchsjahre (nur Privat-Build) ──────
# Build-seitiger, normalisierter Match (lowercase · Diakritika/ß · Satzzeichen+Leerraum
# raus) — EXAKT gegen die kommaseparierten huetten-Einträge der Touren. KEIN
# Suffix-Stripping / keine Kurzform-Expansion: Fragmente wie „Kaindl-" bleiben bewusst
# unmatched -> Nicht-Match-Liste für Coworks Alias-Kuratierung (Befund).
import unicodedata as _ud
def _hutnorm(s):
    s = str(s or "").lower().replace("ß", "ss")
    s = _ud.normalize("NFKD", s)
    s = "".join(c for c in s if not _ud.combining(c))
    return re.sub(r"[^a-z0-9]", "", s)

# W6: Cowork-kuratierte Alias-Tabelle (Freitext -> exakter OSM-Name). Löst die
# Bindestrich-Kurzformen + Rifugio-Namen; die „Fallen" sind bewusst spezifisch
# (Calvi = Pier Fortunato, NICHT Fratelli; Rotwand = Roda di Vael, NICHT Rotwandhaus).
_HUT_ALIASES_RAW = {
    "Kaindl-":        "Kaindlhütte",
    "Grutten-":       "Gruttenhütte",
    "Ackerl-":        "Ackerlhütte",
    "Calvi-Hütte":    "Rifugio Pier Fortunato Calvi",
    "Rotwandhütte":   "Rifugio Roda di Vael",
    "Vajolethütte":   "Rifugio Vajolet",
    "Antermoiahütte": "Rifugio Antermoia",
    # Nachtjob P4 (kuratiert): Pisciadù-Langname; Gardeccia in OSM-Hütten (nicht huts_wiki).
    "Rifugio F. Cavazza al Pisciadù": "Utia Pisciadù - Pisciadù Hütte - Rifugio Franco Cavazza al Pisciadù",
    "Gardecciahütte": "Rifugio Gardeccia",
}

hut_visits, hut_nonmatch = {}, []
if not PUBLIC:
    _osm_hn = {}
    for _f in json.loads((HERE / "soiusa_osm_huts.geojson").read_text(encoding="utf-8"))["features"]:
        _nm = _f["properties"].get("name")
        if _nm:
            _osm_hn.setdefault(_hutnorm(_nm), set()).add(_nm)
    HUT_ALIASES = {_hutnorm(k): _hutnorm(v) for k, v in _HUT_ALIASES_RAW.items()}   # normalisiert
    for _t in data["touren"]:
        _m = re.search(r"\d{4}", str(_t.get("jahr", "")))
        _y = _m.group() if _m else None
        for _raw in (_t.get("huetten") or "").split(","):
            _e = _raw.strip()
            if not _e:
                continue
            _ne = _hutnorm(_e)
            _target = HUT_ALIASES.get(_ne, _ne)   # W6: ggf. auf normalisierten OSM-Namen umbiegen
            if _target and _target in _osm_hn:
                for _disp in _osm_hn[_target]:
                    hut_visits.setdefault(_disp, set()).add(_y)
            else:
                hut_nonmatch.append((_e, _y))
    hut_visits = {k: sorted(v) for k, v in hut_visits.items()}   # Jahre chronologisch
    print(f"  §1 Ihr-wart-hier: {len(hut_visits)} OSM-Hütten gematcht · {len(hut_nonmatch)} Nicht-Matches")
    for _e, _y in hut_nonmatch:
        print(f"     NICHT-MATCH [{_y}] {_e}")
hut_visits_json = json.dumps(hut_visits, ensure_ascii=False, separators=(",", ":"))

# E8: strip the personal "visited" layer from the PUBLIC embedded data.
# visited -> 0 everywhere (so the visited-only layers render nothing and every
# group is drawn uniformly), tour_ids dropped, highlights emptied.
if PUBLIC:
    _sts = json.loads(sts_json)
    for f in _sts["features"]:
        p = f["properties"]
        p["visited"] = 0
        p.pop("tour_ids", None)
    sts_json = json.dumps(_sts, ensure_ascii=False, separators=(",", ":"))
    _lp = json.loads(lp_json)
    for f in _lp["features"]:
        p = f["properties"]
        p["visited"] = 0
        p.pop("tour_ids", None)
    lp_json = json.dumps(_lp, ensure_ascii=False, separators=(",", ":"))
    highlights_json = '{"type":"FeatureCollection","features":[]}'
try:
    wiki_json = load_compact("soiusa_wiki.json")
except FileNotFoundError:
    wiki_json = '{"gruppen":{}}'

# E8: the wiki meta text mentions visited counts ("12 besuchte …") — neutralize
# it in the public build (the group profiles themselves are impersonal, kept).
if PUBLIC:
    _wiki = json.loads(wiki_json)
    _wiki["meta"] = {"quelle": "de.wikipedia + Wikidata",
                     "lizenz": "Text CC BY-SA; Bilder Wikimedia CC BY-SA"}
    wiki_json = json.dumps(_wiki, ensure_ascii=False, separators=(",", ":"))

# Hütten-Enrichment (Wikipedia/Wikidata/Commons) — rein enzyklopädisch, beide Builds.
# Key = OSM properties.name exakt; Lookup HUTS_WIKI.huetten[name].
try:
    huts_wiki_json = load_compact("soiusa_huts_wiki.json")
except FileNotFoundError:
    huts_wiki_json = '{"huetten":{}}'

# N3: Höchster-Gipfel-Koordinate je SOIUSA-Gruppe (Peak×Polygon-Containment + Namensabgleich).
# Eindeutig statt Namens-String (Dubletten „Krottenkopf" 2x). Beide Builds (neutrale Geodaten).
# Das Containment (131 Polygone × ~13k Peaks) ist teuer -> Ergebnis in soiusa_group_peaks.json
# cachen (getrackt); nur neu rechnen, wenn eine Eingabe neuer als der Cache ist.
group_peaks = {}
_gp_cache = HERE / "soiusa_group_peaks.json"
_gp_inputs = [HERE / "soiusa_osm_peaks.geojson", HERE / "soiusa_sts_colored.geojson", HERE / "soiusa_wiki.json"]
_gp_fresh = (_gp_cache.exists() and all(p.exists() for p in _gp_inputs)
             and _gp_cache.stat().st_mtime >= max(p.stat().st_mtime for p in _gp_inputs))
if _gp_fresh:
    group_peaks = json.load(_gp_cache.open(encoding="utf-8"))
else:
    try:
        import re as _re3, unicodedata as _ud3
        from shapely.geometry import shape as _shape3, Point as _Point3
        from shapely.prepared import prep as _prep3

        def _pnorm(s):
            s = _re3.sub(r"\s*\(.*?\)\s*", "", s or "").strip().lower()
            s = "".join(c for c in _ud3.normalize("NFD", s) if _ud3.category(c) != "Mn")
            return _re3.sub(r"[^a-z0-9]", "", s)

        _wg3 = json.loads(wiki_json).get("gruppen", {})
        _pk3 = json.load((HERE / "soiusa_osm_peaks.geojson").open(encoding="utf-8"))["features"]
        _sts3 = json.load((HERE / "soiusa_sts_colored.geojson").open(encoding="utf-8"))["features"]
        for _gf in _sts3:
            _S = _gf["properties"].get("STS")
            if not _S or not _gf.get("geometry"):
                continue
            _pp = _prep3(_shape3(_gf["geometry"]))
            _in = [f for f in _pk3 if _pp.contains(_Point3(f["geometry"]["coordinates"][:2]))]
            if not _in:
                continue
            _hb = (_wg3.get(_S) or {}).get("hoechster_berg")
            _pick = None
            if _hb:
                _nb = _pnorm(_hb)
                _cand = [f for f in _in if _nb and (_nb in _pnorm(f["properties"].get("name", ""))
                                                    or _pnorm(f["properties"].get("name", "")) in _nb)]
                if _cand:
                    _pick = max(_cand, key=lambda f: f["properties"].get("ele", 0))
            if not _pick:
                _pick = max(_in, key=lambda f: f["properties"].get("ele", 0))
            _c = _pick["geometry"]["coordinates"][:2]
            group_peaks[_S] = [round(_c[0], 5), round(_c[1], 5)]
        _gp_cache.write_text(json.dumps(group_peaks, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"  N3: {len(group_peaks)} Gruppen (neu berechnet -> soiusa_group_peaks.json)")
    except Exception as _e:  # noqa: BLE001
        print(f"[group_peaks] WARN {_e} -- Höchster-Berg-Link nutzt Fallback")
group_peaks_json = json.dumps(group_peaks, ensure_ascii=False, separators=(",", ":"))

sts_count = len(json.loads(sts_json)["features"])
hl_count  = len(json.loads(highlights_json)["features"])

# ── Public KPIs (computed from data, not hardcoded) ───────────────────────────
_sts_feats = json.loads(sts_json)["features"]
kpi_gruppen = sts_count
kpi_settori = len({f["properties"].get("settore") for f in _sts_feats if f["properties"].get("settore")})
try:
    _huts = json.loads((HERE / "soiusa_osm_huts.geojson").read_text(encoding="utf-8"))
    kpi_huetten = sum(1 for f in _huts["features"] if f["properties"].get("kat") == "club")
except Exception:
    kpi_huetten = 0

TEMPLATE = r"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>__TITEL__</title>
__HEAD_LIBS__
<style>
  :root{
    --bg:#0a0e14; --panel:rgba(14,20,28,.93); --line:rgba(255,255,255,.12);
    --txt:#e8edf2; --muted:#9fb0c0; --accent:#ffb24d; --accent2:#5fd0c5;
    /* Dichte: kompakte Desktop-Basis (fein-Zeiger). Touch ueberschreibt unten. */
    --row-h:32px; --fs-ui:13.5px; --fs-popup:14px;
    --ctl:32px;        /* Zeilen-Controls / Schliessen-X */
    --ctl-round:40px;  /* runde Aktions-Icons (Info/Home/Suche): Maus-freundlich */
    --ctl-right:12px;  /* gemeinsamer Rechtsabstand der Controls unten rechts (W4 §2) */
    /* P1 (Befund 12): gemeinsame Panel-Breite -> Title-Card + Touren-Panel/Steckbrief
       fluchten (Kanten). --radius als konsolidiertes Token (Streuwerte 12/14 px). */
    --panel-w:310px; --ebenen-w:176px; --radius:14px;
  }
  /* Touch (Tablet/Handy): grosse, komfortable Ziele. Desktop bleibt kompakt. */
  @media (pointer: coarse){
    :root{ --row-h:44px; --fs-ui:16px; --fs-popup:16px; --ctl:44px; --ctl-round:44px; }
  }
  /* Grosse Screens (27"+, feiner Zeiger): kompakte Desktop-Basis wirkt dort zu klein.
     Groessere Schrift/Controls + ~20% breitere Panels/Karten/Title. 16" (<2200px) und
     Touch (coarse) bleiben unveraendert. */
  @media (min-width: 2200px) and (pointer: fine){
    :root{ --row-h:38px; --fs-ui:15.5px; --fs-popup:15.5px; --ctl:36px; --ctl-round:46px;
           --panel-w:372px; --ebenen-w:200px; }   /* P1: ~20% breiter am 27" */
    #title h1{font-size:24px}
    #title p{font-size:15.5px}
    #title .kpi b{font-size:26px}
    #legend{width:224px}
    #about{width:min(432px,calc(100vw - 32px))}
    .hut-pop{max-width:276px}
  }
  *{box-sizing:border-box}
  html,body{margin:0;height:100%;overflow:hidden;
    font-family:"Inter",system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
    background:var(--bg);color:var(--txt)}
  #map{position:absolute;inset:0}
  /* MapLibre zoom/compass buttons: gleiche Breite wie die runden Controls (W4 §2),
     gemeinsamer Rechtsabstand -> eine Flucht mit Home/2D3D. */
  .maplibregl-ctrl-group button{width:var(--ctl-round);height:var(--ctl-round);touch-action:manipulation}
  .maplibregl-ctrl-bottom-right .maplibregl-ctrl{margin-right:var(--ctl-right)}
  .maplibregl-ctrl-group button .maplibregl-ctrl-icon{transform:scale(1.15)}
  /* B2: Maßstabsleiste — unten MITTIG im Footer, groesser (Schrift 12px, breitere Bar). */
  #mapfoot{position:absolute;left:50%;bottom:14px;transform:translateX(-50%);z-index:5;
    display:flex;flex-direction:column;align-items:center;gap:4px;pointer-events:none;transition:bottom .2s}
  .maplibregl-ctrl-scale{background:rgba(14,20,28,.72);border:2px solid rgba(232,237,242,.8);
    border-top:none;color:var(--txt);font-size:12px;line-height:1.35;padding:2px 8px;
    backdrop-filter:blur(6px);margin:0;box-shadow:0 4px 14px rgba(0,0,0,.35)}
  #coords{font-size:11px;color:var(--muted);background:var(--panel);backdrop-filter:blur(6px);
    border:1px solid var(--line);border-radius:6px;padding:2px 8px;white-space:nowrap;
    font-variant-numeric:tabular-nums;opacity:0;transition:opacity .2s;
    pointer-events:auto;cursor:pointer}         /* UX(4): klickbar (Footer ist pointer-events:none) */
  #coords.show{opacity:1}
  #coords.copied{color:var(--accent2);border-color:var(--accent2)}
  /* Punkt 1b: bei offener Chronik Scale+Koordinaten ueber die Jahresleiste heben (nicht ausblenden) */
  body.chrono #mapfoot{bottom:calc(var(--row-h) + 40px)}
  body.tilted .maplibregl-ctrl-scale{display:none}   /* Pitch>30°: Maßstab tiefenabh. falsch */

  /* ── Title card ── */
  #title{position:absolute;top:16px;left:16px;z-index:5;width:var(--panel-w);max-width:calc(100vw - 32px);
    background:var(--panel);backdrop-filter:blur(8px);border:1px solid var(--line);
    border-radius:14px;padding:13px 15px;box-shadow:0 8px 30px rgba(0,0,0,.5)}
  #title h1{margin:0;font-size:20px;letter-spacing:.2px}
  #title p{margin:6px 0 0;font-size:13px;color:var(--muted);line-height:1.45}
  /* Politur P1.2: Mini-Zeile — Logo · Titel · Mini-KPI · ▾ (nur im mini-Zustand sichtbar) */
  #title.mini{padding:9px 13px}
  #title.mini{width:auto}   /* P1: eingeklappt auf Inhalt schrumpfen (Kanten-Flucht gilt der aufgeklappten Card) */
  #title.mini > *:not(#titleMini){display:none}
  #title:not(.mini) #titleMini{display:none}
  #title:not(.mini) h1{cursor:pointer}   /* Befund 5: Titel-Klick klappt ein */
  /* Befund 3: Gipfel-Popup light */
  .pk-pop{font-size:12px;min-width:118px}
  .pk-pop .pk-name{font-weight:700;font-size:13px;color:var(--txt)}
  .pk-pop .pk-ele{color:var(--muted);font-size:11px;margin-top:1px}
  .pk-pop .pk-grp{margin-top:6px;padding-top:5px;border-top:1px solid var(--line);color:var(--accent2);cursor:pointer;font-size:11.5px}
  .pk-pop .pk-grp:hover{text-decoration:underline}
  .lift-pop{font-size:11.5px;font-weight:600;color:var(--txt)}   /* N4: Sessellift-Name */
  #titleMini{display:flex;align-items:center;gap:8px;cursor:pointer;user-select:none;max-width:calc(100vw - 60px)}
  #titleMini .tm-logo{color:var(--accent);font-size:13px;flex:0 0 auto}
  #titleMini .tm-name{font-weight:700;font-size:14px;white-space:nowrap;flex:0 0 auto}
  #titleMini .tm-kpi{font-size:10.5px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1 1 auto}
  #titleMini .tm-caret{color:var(--muted);flex:0 0 auto}
  #title .kpi{margin-top:10px;display:flex;gap:16px}
  #title .kpi b{display:block;font-size:22px;color:var(--accent)}
  #title .kpi span{font-size:11px;color:var(--muted)}
  /* ── T4: Legende (Sektoren) — aufklappbarer Abschnitt der Title-Card ── */
  #legend{margin-top:11px;border-top:1px solid var(--line);overflow:hidden}
  #legend .lh{padding:9px 0 0;font-size:12px;font-weight:600;cursor:pointer;
    display:flex;justify-content:space-between;align-items:center;gap:10px;user-select:none}
  #legend .lh .lt{display:flex;align-items:center;gap:6px}
  #legend .lh .lt::after{content:'▾';color:var(--muted);transition:transform .3s;font-size:.85em}
  #legend.open .lh .lt::after{transform:rotate(180deg)}
  #legend .ll{max-height:0;overflow:hidden;transition:max-height .35s ease}
  #legend.open .ll{max-height:280px}
  #legend .lsub{font-size:10.5px;color:var(--muted);padding:6px 0 2px}
  /* Politur P1.3: 2-spaltig (Westalpen | Ostalpen) — breiter, flacher */
  #legend .lcols{display:flex;gap:16px;padding-top:5px}
  #legend .lcol{flex:1;min-width:0}
  #legend .lgrp{font-size:10.5px;font-weight:700;color:var(--muted);text-transform:uppercase;
    letter-spacing:.6px;padding:1px 0 3px}
  #legend .lrow{display:flex;align-items:center;gap:8px;padding:3px 0;
    font-size:11.5px;color:var(--txt)}
  #legend .lsep{height:1px;background:var(--line);margin:6px 0}
  #legend .tgl{padding:0;gap:7px;font-size:11px;min-height:0;color:var(--muted)}
  #legend .tgl.locked{opacity:.4;pointer-events:none}
  .sw-hl{display:inline-block;width:13px;height:13px;border:2px solid #ffb24d;border-radius:3px;flex-shrink:0}
  .sw-nw{display:inline-block;width:13px;height:13px;background:#0072B2;border-radius:3px;flex-shrink:0}
  .sw-sw{display:inline-block;width:13px;height:13px;background:#CC79A7;border-radius:3px;flex-shrink:0}
  .sw-zo{display:inline-block;width:13px;height:13px;background:#3FC5DE;border-radius:3px;flex-shrink:0}
  .sw-no{display:inline-block;width:13px;height:13px;background:#009E73;border-radius:3px;flex-shrink:0}
  .sw-so{display:inline-block;width:13px;height:13px;background:#E6C229;border-radius:3px;flex-shrink:0}

  /* ── Controls (stacked below title card) ── */
  #controls{position:absolute;top:196px;left:16px;z-index:5;
    display:flex;flex-direction:column;gap:6px}
  .btn{background:var(--panel);border:1px solid var(--line);
    color:var(--txt);border-radius:10px;padding:7px 12px;font-size:11.5px;
    cursor:pointer;backdrop-filter:blur(8px);white-space:nowrap}
  .btn.active{border-color:var(--accent2);color:var(--accent2)}
  .btn:hover{border-color:rgba(255,255,255,.3)}

  /* ── Detail panel ── */
  #panel{position:absolute;top:174px;left:16px;z-index:7;width:var(--panel-w);
    background:var(--panel);backdrop-filter:blur(8px);border:1px solid var(--line);
    border-radius:14px;padding:0;box-shadow:0 8px 30px rgba(0,0,0,.5);
    transform:translateX(-120%);transition:transform .35s cubic-bezier(.2,.8,.2,1);overflow:hidden}
  #panel.open{transform:translateX(0)}
  #panel .ph{padding:13px 13px 10px;border-bottom:1px solid var(--line)}
  #panel .yr{font-size:11px;color:var(--accent2);font-weight:600;letter-spacing:.5px}
  #panel h2{margin:3px 0 2px;font-size:16px;line-height:1.2}
  #panel .gegend{font-size:10.5px;color:var(--muted)}
  #panel .body{padding:11px 14px 14px;font-size:15px;line-height:1.5;max-height:58vh;overflow-y:auto;   /* P1/Review §5: Grundschrift +1pt */
    -webkit-overflow-scrolling:touch}
  #panel .sec{margin:0 0 10px}
  #panel .sec h3{margin:0 0 4px;font-size:9.5px;text-transform:uppercase;letter-spacing:1px;color:var(--muted)}
  #panel ul{margin:0;padding-left:0;list-style:none}
  #panel li{padding:2px 0;display:flex;justify-content:space-between;gap:8px;
    border-bottom:1px dotted rgba(255,255,255,.08)}
  #panel li b{color:var(--accent);font-variant-numeric:tabular-nums;white-space:nowrap}
  /* P3b §10a: klickbare Gipfel-Einträge (flyTo + Puls) */
  #panel li.gip{cursor:pointer;border-radius:5px;margin:0 -4px;padding-left:4px;padding-right:4px}
  #panel li.gip:hover{background:rgba(95,208,197,.12)}
  #panel b.gip{cursor:pointer;border-bottom:1px dotted var(--accent2)}
  #panel b.gip:hover{color:var(--accent2)}
  #panel .notiz{font-size:11px;color:var(--muted);margin-top:3px;line-height:1.4}
  #panel .x{position:absolute;top:6px;right:6px;cursor:pointer;color:var(--muted);
    width:var(--ctl);height:var(--ctl);border-radius:10px;display:grid;place-items:center;font-size:22px;
    touch-action:manipulation;z-index:2}
  #panel .x:hover{background:rgba(255,255,255,.08);color:#fff}
  /* Tabs + Steckbrief */
  #panel .tabs{display:flex;border-bottom:1px solid var(--line)}
  #panel .tab{flex:1;padding:8px 10px;font-size:11px;text-align:center;cursor:pointer;
    color:var(--muted);border-bottom:2px solid transparent;user-select:none}
  #panel .tab.active{color:var(--accent2);border-bottom-color:var(--accent2)}
  #panel .pane{display:none}
  #panel .pane.active{display:block}
  #panel .sb-row{display:flex;justify-content:space-between;gap:10px;padding:5px 0;
    border-bottom:1px dotted rgba(255,255,255,.08);font-size:13.5px}
  #panel .sb-row .k{color:var(--muted);white-space:nowrap}
  #panel .sb-row .v{text-align:right}
  #panel .sb-row .v b{color:var(--accent);font-variant-numeric:tabular-nums}
  #panel .sb-img{width:100%;border-radius:8px;margin:9px 0 3px;display:block}
  #panel .sb-attr{font-size:9px;color:var(--muted);line-height:1.3}
  #panel .sb-wiki{display:inline-block;margin-top:10px;font-size:11.5px;color:var(--accent2);
    text-decoration:none}
  #panel .sb-wiki:hover{text-decoration:underline}
  #panel .sb-open{font-size:11px;color:var(--muted);margin-top:9px}

  /* ── Coverage list (default collapsed) ── */
  /* #cov: Höhe bis knapp über die Chronoleiste (JS sizeCov -> --cov-max), damit die
     Tourenliste maximal viele Zeilen zeigt; harte vh-Kappe als Fallback. */
  #cov{position:absolute;bottom:calc(var(--row-h) + 54px);left:16px;z-index:5;width:var(--panel-w);
    max-height:calc(100vh - 130px);
    background:var(--panel);backdrop-filter:blur(8px);border:1px solid var(--line);
    border-radius:14px;box-shadow:0 8px 30px rgba(0,0,0,.45);overflow:hidden}
  #cov .ch{padding:9px 14px;font-size:var(--fs-ui);font-weight:600;cursor:pointer;min-height:var(--row-h);
    display:flex;justify-content:space-between;align-items:center;user-select:none;touch-action:manipulation}
  #cov .ch span{color:var(--muted);font-weight:400;font-size:11px}
  #cov .cl{max-height:0;overflow-y:auto;transition:max-height .3s ease}
  #cov.open .cl{max-height:var(--cov-max,46vh)}
  /* PRIV:START */
  /* ── Tourenliste: eine Zeile pro Tour (Jahr · Gegend · Kategorie-Badge) ── */
  .trow{padding:7px 14px;font-size:var(--fs-ui);cursor:pointer;min-height:var(--row-h);box-sizing:border-box;
    display:flex;align-items:center;gap:9px;border-top:1px solid rgba(255,255,255,.06);touch-action:manipulation}
  .trow:hover{background:rgba(255,178,77,.10)}
  .trow.sel{background:rgba(95,208,197,.13)}
  .trow .tyr{color:var(--accent);font-weight:700;font-variant-numeric:tabular-nums;flex:0 0 auto;min-width:34px}
  .trow .tgeb{flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .trow .tkat{flex:0 0 auto;font-size:9.5px;padding:1px 6px;border-radius:5px;white-space:nowrap;
    border:1px solid var(--line);color:var(--muted)}
  .trow .tkat.br{color:var(--accent2);border-color:rgba(95,208,197,.4);background:rgba(95,208,197,.10)}
  /* ── Personen-/Strang-Filter (SPEC_Personenfilter) — sticky, Chips einklappbar ── */
  #tourFilter{padding:8px 14px 6px;position:sticky;top:0;z-index:3;
    background:var(--panel);backdrop-filter:blur(8px);border-bottom:1px solid rgba(255,255,255,.06)}
  .tf-seg{display:flex;gap:5px;margin-bottom:7px}
  .tf-sbtn{flex:1;min-height:var(--row-h);padding:5px 4px;border:1px solid var(--line);border-radius:9px;
    background:rgba(255,255,255,.04);color:var(--muted);font-size:11px;cursor:pointer;
    font-family:inherit;touch-action:manipulation;white-space:nowrap;text-align:center;line-height:1.25}
  .tf-sbtn b{font-weight:700;font-variant-numeric:tabular-nums}
  .tf-sbtn.on{background:rgba(95,208,197,.16);border-color:var(--accent2);color:var(--txt)}
  /* Befund 7: Personen-Aufklapper (Ebene 2) klar aufklappbar — Akzent2 + Chevron + Button. */
  .tf-perstoggle{display:flex;align-items:center;justify-content:space-between;gap:8px;
    padding:5px 8px;margin:4px 0 2px;cursor:pointer;font-size:11.5px;font-weight:600;color:var(--accent2);
    background:rgba(95,208,197,.09);border:1px solid rgba(95,208,197,.30);border-radius:7px;
    min-height:28px;touch-action:manipulation;user-select:none}
  .tf-perstoggle:hover{background:rgba(95,208,197,.16)}
  .tf-perstoggle .tf-picon{width:14px;height:14px;fill:none;stroke:var(--accent2);stroke-width:1.5;flex:0 0 auto}
  .tf-perstoggle .tf-pt-l{display:inline-flex;align-items:center;gap:6px}
  .tf-perstoggle .tf-caret{transition:transform .25s;font-size:.9em;color:var(--accent2)}
  #cov.pers-open .tf-perstoggle .tf-caret{transform:rotate(180deg)}
  #cov:not(.pers-open) .tf-chips{display:none}
  /* Politur P1.4: Filter-Block als Ganzes einklappbar („Filter ▾"); Bilanzzeile bleibt sichtbar */
  /* N5: Filter-Aufklapper klar als bedienbar (Personen-Icon + Akzent + Button-Optik). */
  .tf-filterhead{display:flex;align-items:center;justify-content:space-between;gap:8px;
    padding:5px 9px;margin:1px 0 3px;cursor:pointer;font-size:12px;font-weight:600;color:var(--accent);
    background:rgba(255,178,77,.09);border:1px solid rgba(255,178,77,.32);border-radius:8px;
    min-height:30px;touch-action:manipulation;user-select:none}
  .tf-filterhead:hover{background:rgba(255,178,77,.16)}
  .tf-filterhead .tf-fh-l{display:inline-flex;align-items:center;gap:7px}
  .tf-filterhead .tf-picon{width:15px;height:15px;fill:none;stroke:var(--accent);stroke-width:1.5;flex:0 0 auto}
  .tf-filterhead .tf-caret{transition:transform .25s;font-size:.9em;color:var(--accent)}
  #cov.filter-open .tf-filterhead .tf-caret{transform:rotate(180deg)}
  #cov:not(.filter-open) .tf-filterbody{display:none}
  @media (pointer: coarse){ .tf-filterhead{min-height:var(--row-h)} }
  .tf-chips{display:flex;flex-wrap:wrap;gap:5px;margin:2px 0 4px}
  .tf-chip{display:inline-flex;align-items:center;gap:5px;min-height:30px;padding:3px 9px;border-radius:16px;
    border:1px solid var(--line);background:rgba(255,255,255,.05);color:var(--txt);font-size:12px;
    font-family:inherit;cursor:pointer;touch-action:manipulation}
  .tf-chip .n{color:var(--muted);font-variant-numeric:tabular-nums;font-size:11px}
  .tf-chip.on{background:rgba(255,178,77,.18);border-color:var(--accent);font-weight:600}
  .tf-chip.on .n{color:var(--accent)}
  .tf-badges{display:flex;flex-wrap:wrap;gap:5px;margin:0 0 2px;align-items:center}
  .tf-badges:empty{display:none}
  .tf-badge{display:inline-flex;align-items:center;gap:6px;padding:2px 8px;border-radius:14px;
    background:rgba(255,178,77,.16);border:1px solid rgba(255,178,77,.45);color:var(--txt);font-size:11.5px}
  .tf-badge .rm{cursor:pointer;color:var(--muted);font-size:15px;line-height:1;touch-action:manipulation}
  .tf-badge .rm:hover{color:#fff}
  .tf-reset{cursor:pointer;color:var(--accent2);font-size:11.5px;background:none;border:none;
    font-family:inherit;padding:2px 4px;touch-action:manipulation}
  .tf-reset:hover{text-decoration:underline}
  .tf-empty{padding:10px 14px 12px;font-size:12.5px;color:var(--muted);line-height:1.5}
  .tf-empty .tf-reset{display:inline;padding:0;margin-left:4px}
  /* P3a: Jahr-Range-Slider (Doppelgriff) */
  .tf-jahr{margin:2px 0 7px}
  .tf-jahr-lbl{display:flex;justify-content:space-between;font-size:11px;color:var(--muted);margin-bottom:4px}
  .tf-jahr-lbl span:last-child{color:var(--txt);font-variant-numeric:tabular-nums;font-weight:600}
  .tf-jahr-slider{position:relative;height:22px}
  .tf-jahr-track{position:absolute;left:8px;right:8px;top:9px;height:4px;border-radius:2px;background:rgba(255,255,255,.15)}
  .tf-jahr-fill{position:absolute;top:0;height:100%;border-radius:2px;background:var(--accent2)}
  .tf-jahr-slider input[type=range]{position:absolute;left:0;right:0;top:0;width:100%;height:22px;margin:0;
    -webkit-appearance:none;appearance:none;background:none;pointer-events:none}
  .tf-jahr-slider input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;appearance:none;
    width:16px;height:16px;border-radius:50%;background:var(--accent2);border:2px solid #0a0e14;cursor:pointer;pointer-events:auto}
  .tf-jahr-slider input[type=range]::-moz-range-thumb{width:16px;height:16px;border-radius:50%;
    background:var(--accent2);border:2px solid #0a0e14;cursor:pointer;pointer-events:auto}
  .tf-jahr-slider input[type=range]::-moz-range-track{background:none;border:none}
  /* P3a: Filter-Bilanzzeile */
  #filterBadges{align-items:center}
  .tf-bilanz-txt{flex:1;font-size:12px;color:var(--txt);line-height:1.35}
  #filterBadges .tf-reset{font-size:17px;line-height:1;padding:0 7px;border:1px solid var(--line);
    border-radius:8px;min-height:26px;display:inline-flex;align-items:center}
  #filterBadges .tf-reset:hover{border-color:var(--accent2);text-decoration:none}
  @media (pointer: coarse){ .tf-chip{min-height:var(--row-h)} .tf-badge{min-height:32px} .tf-perstoggle{min-height:var(--row-h)}
    .tf-jahr-slider{height:40px} .tf-jahr-track{top:18px}
    .tf-jahr-slider input[type=range]{height:40px}
    .tf-jahr-slider input[type=range]::-webkit-slider-thumb{width:28px;height:28px}
    .tf-jahr-slider input[type=range]::-moz-range-thumb{width:28px;height:28px}
    #filterBadges .tf-reset{min-height:var(--row-h);min-width:40px;justify-content:center} }
  /* Chronik-Sync: Auswahl-Rahmen (Gebiet offen) — teal Ring, klar vom Play-Cursor (orange) getrennt */
  #chronoChips .chip.chsel{box-shadow:inset 0 0 0 2px var(--accent2)}
  /* Touren-Tracks-Toggle — Befund 8: klar als EBENE (Darstellung), nicht als Filter.
     Deutlicher Separator + Abstand + Auge-Icon, gedämpftes Layer-Styling. */
  #tourFilter .tf-tracks{padding:6px 8px;min-height:32px;font-size:12px;color:var(--muted);margin-top:9px;
    border-top:1px solid rgba(255,255,255,.14)}
  #tourFilter .tf-tracks .tf-tl{display:inline-flex;align-items:center;gap:6px}
  #tourFilter .tf-tracks .tf-eye{width:15px;height:15px;fill:none;stroke:var(--muted);stroke-width:1.3;flex:0 0 auto}
  @media (pointer: coarse){ #tourFilter .tf-tracks{min-height:var(--row-h)} }
  /* ── P2: Master-Detail — Steckbrief nutzt (Desktop, privat) die Tourenlisten-Position ── */
  #panel.as-cov{top:auto;bottom:calc(var(--row-h) + 54px);left:16px;width:var(--panel-w);
    max-height:calc(100vh - 130px);display:flex;flex-direction:column}
  #panel.as-cov .body{max-height:none;flex:1 1 auto;min-height:0}
  #panel .pback{display:none;align-items:center;gap:7px;padding:8px 13px 7px;cursor:pointer;
    font-size:12px;color:var(--accent2);border-bottom:1px solid var(--line);user-select:none;touch-action:manipulation}
  #panel.has-back .pback{display:flex}   /* Rückzeile in allen Viewports (Master-Detail) */
  #panel .pback:hover{color:var(--txt)}
  /* ── P2: Touren-Accordion (Tab „Touren (n)") ── */
  .tcard{border:1px solid var(--line);border-radius:9px;margin:0 0 7px;overflow:hidden;background:rgba(255,255,255,.02)}
  .tcard-h{display:flex;align-items:center;gap:8px;padding:7px 9px;cursor:pointer;min-height:var(--row-h);
    box-sizing:border-box;touch-action:manipulation;user-select:none}
  .tcard-h .tc-yr{color:var(--accent);font-weight:700;font-variant-numeric:tabular-nums;cursor:pointer;flex:0 0 auto}
  .tcard-h .tc-yr:hover{text-decoration:underline}
  .tcard-h .tc-geb{flex:1;font-size:12.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .tcard-h .tc-caret{color:var(--muted);transition:transform .25s;font-size:.85em;flex:0 0 auto}
  .tcard.open .tc-caret{transform:rotate(180deg)}
  .tcard-b{display:none;padding:2px 11px 10px;font-size:14px;line-height:1.5}   /* P1: +1pt */
  .tcard.open .tcard-b{display:block}
  .tcard-b .tc-row{margin:5px 0}
  .tcard-b .tc-k{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.6px;display:block;margin-bottom:1px}
  /* P5: Mini-Höhenprofil (Sparkline) im Track-Abschnitt — dezent, Besucht-Orange. */
  .tc-spark{margin:1px 0 6px;padding:0 1px}
  .tc-spark svg{width:100%;height:44px;display:block}
  .tcs-line{fill:none;stroke:var(--accent);stroke-width:1.4;vector-effect:non-scaling-stroke;stroke-linejoin:round;stroke-linecap:round}
  .tcs-area{fill:var(--accent);opacity:.10}
  .tcs-lbl{display:flex;justify-content:space-between;font-size:10px;color:var(--muted);margin-top:1px}
  .tcs-lbl .tcs-max{color:var(--accent)}
  /* P6/Befund 4: Teilnehmer als Chips (Pill + Filter-Icon) + Bestätigungs-Popover. */
  .tc-pers{display:inline-flex;align-items:center;gap:3px;padding:1px 8px;margin:1px 1px;border-radius:11px;
    background:rgba(255,178,77,.13);border:1px solid rgba(255,178,77,.42);color:var(--accent);
    cursor:pointer;font-size:11.5px;line-height:1.55;touch-action:manipulation;white-space:nowrap}
  .tc-pers:hover{background:rgba(255,178,77,.22)}
  .tc-pers.on{background:var(--accent);color:#1a1200;border-color:var(--accent)}
  .tc-pers .tc-pico{width:10px;height:10px;fill:currentColor;flex:0 0 auto;opacity:.8}
  .tc-pers-plain{color:var(--muted);white-space:nowrap;margin:0 2px}
  #persPopover{position:fixed;z-index:60;display:none;max-width:232px;background:var(--panel);
    backdrop-filter:blur(8px);border:1px solid var(--line);border-radius:10px;padding:10px 11px;
    box-shadow:0 10px 28px rgba(0,0,0,.5)}
  #persPopover.open{display:block}
  #persPopover .pp-q{font-size:12.5px;color:var(--txt);margin-bottom:9px;line-height:1.35}
  #persPopover .pp-btns{display:flex;gap:7px;justify-content:flex-end}
  #persPopover button{font:inherit;font-size:12px;padding:6px 13px;border-radius:7px;cursor:pointer;
    border:1px solid var(--line);min-height:38px;touch-action:manipulation}
  #persPopover .pp-ok{background:var(--accent);color:#1a1200;border-color:var(--accent);font-weight:700}
  #persPopover .pp-cancel{background:transparent;color:var(--muted)}
  .tcard-b .tc-chrono{display:inline-block;margin-top:6px;font-size:11.5px;color:var(--accent2);cursor:pointer}
  .tcard-b .tc-chrono:hover{text-decoration:underline}
  /* PRIV:END */

  /* ── STS group popup ── */
  .maplibregl-popup-content{
    background:rgba(14,20,28,.95);border:1px solid rgba(255,255,255,.14);
    border-radius:9px;padding:7px 11px;box-shadow:0 6px 20px rgba(0,0,0,.55);
    min-width:120px}
  .maplibregl-popup-tip{display:none}
  .maplibregl-popup-close-button{color:#9fb0c0;font-size:22px;width:var(--ctl);height:var(--ctl);
    right:2px;top:2px;line-height:1;background:none;touch-action:manipulation}
  .sp-name{font:600 var(--fs-popup)/1.3 Inter,system-ui,sans-serif;color:#e8edf2}
  .sp-sub{font-size:12px;color:#aebccb;margin-top:2px}
  .hp-n{font:600 var(--fs-popup)/1.2 Inter,system-ui,sans-serif;color:#e8edf2}
  .hp-s{font-size:11.5px;color:#aebccb;margin-top:1px}
  .hp-b{font-size:11.5px;color:#ffcf94;margin-top:3px}
  .hp-badge{display:inline-block;padding:0 6px;border-radius:8px;background:rgba(255,178,77,.2);
    border:1px solid rgba(255,178,77,.5);color:#ffcf94;font-size:10px;font-weight:600}
  .hp-hint{font-size:10px;color:var(--muted);margin-top:4px;opacity:.85}
  /* ── Hütten-Popup (Enrichment aus soiusa_huts_wiki.json) ── */
  .hut-pop{max-width:230px}
  .hut-badge{display:inline-block;margin:3px 0 5px;padding:1px 8px;border-radius:10px;
    background:rgba(226,87,76,.18);border:1px solid rgba(226,87,76,.5);color:#ffb3aa;
    font-size:10.5px;font-weight:600}
  .hut-meta{font-size:12.5px;color:#c2ccd6;line-height:1.4}
  .hut-img{width:100%;border-radius:7px;margin:8px 0 2px;display:block}
  .hut-attr{font-size:8.5px;color:#7d8b99;line-height:1.25}
  .hut-links{margin-top:7px;display:flex;flex-direction:column;gap:3px}
  .hut-links a{font-size:12px;color:var(--accent2);text-decoration:none}
  .hut-links a:hover{text-decoration:underline}
  /* §1: Besuchsjahr-Zeile (nur Privat) — warmer Erinnerungs-Akzent (Orange) */
  .hut-visit{margin:6px 0 2px;font-size:12px;color:#ffcf94;line-height:1.4}
  .hut-visit .lbl{color:var(--muted);margin-right:4px}
  .hut-visit b{color:var(--accent);font-variant-numeric:tabular-nums}
  /* §3: „Seilbahn-nah"-Chip (beide Builds) — dezent, kein neues Farbsignal (muted) */
  .hut-cable{display:inline-flex;align-items:center;gap:6px;margin:5px 0 2px;padding:1px 8px;
    border-radius:10px;background:rgba(255,255,255,.06);border:1px solid var(--line);
    font-size:11px;color:var(--muted);cursor:help}
  .hut-cable b{color:#c2ccd6;font-weight:600}

  /* ── About / Info card (rechts „?" = Bedienungshilfe) + T4: „Über diese Karte" (links) ── */
  #about,#aboutCard{position:absolute;z-index:10;
    width:min(360px,calc(100vw - 32px));background:var(--panel);backdrop-filter:blur(8px);
    border:1px solid var(--line);border-radius:14px;padding:14px 16px;
    box-shadow:0 8px 30px rgba(0,0,0,.55);display:none}
  #about{top:16px;left:50%;transform:translateX(-50%)}
  #aboutCard{top:16px;left:16px}   /* T4: an der Title-Card links oben */
  #about.open,#aboutCard.open{display:block}
  #about h3,#aboutCard h3{margin:10px 0 6px;font-size:15px}
  #about h3:first-of-type,#aboutCard h3:first-of-type{margin-top:0}
  #about p,#aboutCard p{margin:5px 0;font-size:13px;color:var(--muted);line-height:1.55}
  #about b,#aboutCard b{color:var(--txt)}
  #about .x,#aboutCard .x{position:absolute;top:5px;right:5px;cursor:pointer;color:var(--muted);font-size:22px;
    width:var(--ctl);height:var(--ctl);display:grid;place-items:center;border-radius:10px;touch-action:manipulation}
  #about .x:hover,#aboutCard .x:hover{background:rgba(255,255,255,.08);color:#fff}
  #about a,#aboutCard a{color:var(--accent2);text-decoration:none}
  /* T4: kleine ⓘ-Schaltfläche in der Title-Card (Über diese Karte) */
  #btnAbout2{margin-top:9px;display:inline-flex;align-items:center;gap:6px;cursor:pointer;
    background:none;border:none;color:var(--accent2);font-size:12px;padding:0;font-family:inherit}
  #btnAbout2:hover{text-decoration:underline}
  #btnAbout2 .ic{display:inline-grid;place-items:center;width:16px;height:16px;border-radius:50%;
    border:1px solid var(--accent2);font-size:11px;font-style:italic;font-weight:700}

  /* ── Ebenen-Panel (Toggle-Switches + Legende) ── */
  #ebenen{position:absolute;top:64px;right:16px;z-index:6;width:var(--ebenen-w);   /* P1: --ebenen-w (176px), Kanten/Touch ok */
    background:var(--panel);backdrop-filter:blur(8px);border:1px solid var(--line);
    border-radius:14px;box-shadow:0 8px 30px rgba(0,0,0,.5);overflow:hidden}
  #ebenen .eh{padding:9px 15px;font-size:var(--fs-ui);font-weight:600;cursor:pointer;min-height:var(--row-h);
    display:flex;justify-content:space-between;align-items:center;user-select:none;touch-action:manipulation}
  #ebenen .eh::after{content:'▾';color:var(--muted);transition:transform .3s}
  #ebenen.open .eh::after{transform:rotate(180deg)}
  #ebenen .eb{max-height:0;overflow:hidden;transition:max-height .35s ease}
  #ebenen.open .eb{max-height:min(72vh,600px);overflow-y:auto;scrollbar-width:thin}
  #ebenen .eb-in{padding:2px 15px 14px}
  #ebenen .grp{font-size:10.5px;text-transform:uppercase;letter-spacing:1px;
    color:var(--muted);margin:11px 0 3px}
  .tgl{display:flex;align-items:center;justify-content:space-between;gap:12px;
    padding:6px 2px;cursor:pointer;font-size:var(--fs-ui);min-height:var(--row-h);touch-action:manipulation}
  .tgl .sw{position:relative;width:40px;height:23px;border-radius:12px;background:#3a4655;
    transition:background .2s;flex-shrink:0}
  .tgl .sw::after{content:'';position:absolute;top:3px;left:3px;width:17px;height:17px;
    border-radius:50%;background:#e8edf2;transition:transform .2s}
  .tgl.on .sw{background:#3fa972}
  .tgl.on .sw::after{transform:translateX(17px)}
  #ebenen .lrow{display:flex;align-items:center;gap:9px;padding:4px 2px;font-size:12.5px}
  #ebenen .lsep{height:1px;background:var(--line);margin:6px 2px}
  /* ── Info "?" + Home ── */
  #btnInfo{position:absolute;top:16px;right:16px;z-index:8;width:var(--ctl-round);height:var(--ctl-round);
    border-radius:50%;background:var(--panel);border:1px solid var(--line);color:var(--txt);
    font-size:20px;font-weight:700;cursor:pointer;backdrop-filter:blur(8px);touch-action:manipulation}
  #btnInfo:hover{border-color:var(--accent2);color:var(--accent2)}
  /* Feinschliff 3: eigenes Kartenquellen-Control (Machart wie #btnInfo) — KEIN natives
     maplibre-details mehr (Wurzel fuer Kaestchen/Doppelklick/FOUC). Rundes helles i,
     links neben dem „?"; Popup oeffnet auf Button-Hoehe nach LINKS (Richtung Title-Card). */
  #btnAttrib{position:absolute;top:16px;right:calc(16px + var(--ctl-round) + 8px);z-index:8;
    width:var(--ctl-round);height:var(--ctl-round);border-radius:50%;cursor:pointer;
    background-color:var(--panel);border:1px solid var(--line);backdrop-filter:blur(8px);
    background-repeat:no-repeat;background-position:center;background-size:22px;touch-action:manipulation;
    background-image:url("data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' fill='%23e8edf2' fill-rule='evenodd' viewBox='0 0 20 20'%3E%3Cpath d='M4 10a6 6 0 1 0 12 0 6 6 0 1 0-12 0m5-3a1 1 0 1 0 2 0 1 1 0 1 0-2 0m0 3a1 1 0 1 1 2 0v3a1 1 0 1 1-2 0'/%3E%3C/svg%3E")}
  #btnAttrib:hover,#btnAttrib.on{border-color:var(--accent2)}
  #attribPop{position:absolute;top:16px;right:calc(16px + 2*var(--ctl-round) + 20px);z-index:11;
    display:none;width:max-content;max-width:min(420px,calc(100vw - 160px));
    background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:10px 13px;
    font-size:10.5px;line-height:1.55;color:var(--muted);backdrop-filter:blur(8px);
    box-shadow:0 8px 30px rgba(0,0,0,.5)}
  #attribPop.open{display:block}
  #attribPop a{color:var(--accent2);text-decoration:none}
  #attribPop a:hover{text-decoration:underline}
  /* §2 (W4): runde Controls rechts unten in einer Flucht (right:var(--ctl-right)),
     alle WEISS wie der Zoom-Stack (Kurator-Entscheid). Reihenfolge oben->unten:
     2D/3D · Home · [Zoom+/Zoom-/Kompass]. */
  #home{position:absolute;bottom:168px;right:var(--ctl-right);z-index:6;width:var(--ctl-round);height:var(--ctl-round);
    border-radius:9px;background:rgba(255,255,255,.95);border:1px solid rgba(0,0,0,.18);color:#2a2f36;
    font-size:19px;cursor:pointer;box-shadow:0 2px 8px rgba(0,0,0,.3);touch-action:manipulation}
  #home:hover{background:#fff;color:#000}
  #btn2d3d{position:absolute;bottom:222px;right:var(--ctl-right);z-index:6;width:var(--ctl-round);height:var(--ctl-round);
    border-radius:9px;background:rgba(255,255,255,.95);border:1px solid rgba(0,0,0,.18);color:#2a2f36;
    font-size:13px;font-weight:700;cursor:pointer;box-shadow:0 2px 8px rgba(0,0,0,.3);touch-action:manipulation}
  #btn2d3d:hover{background:#fff;color:#000}
  /* W5: Vollbild-Button (rund/weiß wie Home/2D3D), oben im Stack; per JS versteckt wo API fehlt. */
  #btnFull{position:absolute;bottom:276px;right:var(--ctl-right);z-index:6;width:var(--ctl-round);height:var(--ctl-round);
    border-radius:9px;background:rgba(255,255,255,.95);border:1px solid rgba(0,0,0,.18);color:#2a2f36;
    font-size:18px;cursor:pointer;box-shadow:0 2px 8px rgba(0,0,0,.3);touch-action:manipulation;display:none}
  #btnFull:hover{background:#fff;color:#000}
  /* ── Suche ── */
  #search{position:absolute;top:16px;left:50%;transform:translateX(-50%);z-index:9;
    display:flex;align-items:center;background:var(--panel);backdrop-filter:blur(8px);
    border:1px solid var(--line);border-radius:24px;box-shadow:0 6px 24px rgba(0,0,0,.45)}
  #sToggle{width:var(--ctl-round);height:var(--ctl-round);border:none;background:none;color:var(--txt);font-size:18px;
    cursor:pointer;border-radius:50%;flex-shrink:0;touch-action:manipulation}
  #sInput{width:0;padding:0;border:none;background:none;color:var(--txt);font-size:15px;
    outline:none;transition:width .25s,padding .25s;font-family:inherit}
  #sInput::placeholder{color:var(--muted)}
  #search.open #sInput{width:min(52vw,340px);padding:0 12px 0 2px}
  #sRes{display:none;position:absolute;top:calc(var(--ctl-round) + 6px);left:0;right:0;background:var(--panel);
    backdrop-filter:blur(8px);border:1px solid var(--line);border-radius:12px;
    box-shadow:0 8px 30px rgba(0,0,0,.5);max-height:min(60vh,420px);overflow-y:auto}
  .sr{display:flex;align-items:center;gap:10px;padding:7px 12px;min-height:var(--row-h);cursor:pointer;
    border-top:1px solid rgba(255,255,255,.06);font-size:var(--fs-ui);touch-action:manipulation}
  .sr:first-child{border-top:none}
  .sr.sel,.sr:hover{background:rgba(95,208,197,.15)}
  .sr .ic{width:22px;text-align:center;flex-shrink:0;font-size:15px}
  .sr .nm{flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .sr .sb{color:var(--muted);font-size:12px;flex-shrink:0;white-space:nowrap}
  /* ── Basemap segmented (Ebenen-Panel) ── */
  .seg{display:flex;flex-direction:column;gap:6px;margin:2px 0 2px}   /* Politur P1.5: Satellit/Topo untereinander */
  .seg button{flex:1;min-height:var(--row-h);padding:6px;border:1px solid var(--line);border-radius:9px;
    background:rgba(255,255,255,.04);color:var(--muted);font-size:var(--fs-ui);cursor:pointer;
    font-family:inherit;touch-action:manipulation}
  .seg button.on{background:rgba(95,208,197,.16);border-color:var(--accent2);color:var(--txt);font-weight:600}
  .seg button.disabled{opacity:.4;pointer-events:none}          /* Topo-Gate: unter z11 */
  .tgl.locked{opacity:.4;pointer-events:none}                    /* Färbung/Namen bei Topo gesperrt */
  /* ── Toast (kurzlebiger Hinweis, kein Modal) ── */
  #toast{position:absolute;left:50%;bottom:88px;transform:translateX(-50%);z-index:9;
    background:var(--panel);backdrop-filter:blur(8px);border:1px solid var(--line);
    border-radius:10px;padding:8px 14px;font-size:13px;color:var(--txt);text-align:center;
    box-shadow:0 8px 30px rgba(0,0,0,.5);opacity:0;transition:opacity .3s;
    pointer-events:none;max-width:calc(100vw - 32px)}
  #toast.show{opacity:1}
  /* §6b (W4)/Fix6: „Letzte Ansicht"-Chip; Fade statt display-Toggle, pointer-events
     via JS erst NACH dem Fade aus -> kein Durchklicken zur Karte im Verschwinde-Moment. */
  #undoChip{position:absolute;left:50%;bottom:104px;transform:translateX(-50%);z-index:9;
    display:inline-flex;align-items:center;gap:4px;background:var(--panel);backdrop-filter:blur(8px);
    border:1px solid var(--line);border-radius:20px;padding:8px 16px;min-height:40px;font-size:13px;
    color:var(--txt);cursor:pointer;box-shadow:0 6px 24px rgba(0,0,0,.45);touch-action:manipulation;
    opacity:0;pointer-events:none;transition:opacity .25s}
  #undoChip.show{opacity:1}
  #undoChip:hover{border-color:var(--accent2);color:var(--accent2)}

  /* PRIV:START */
  /* ── Chronologie-Modus (nur Privat-Build) ── */
  #chronoBtn{position:absolute;left:16px;bottom:16px;z-index:8;
    width:var(--ctl-round);height:var(--ctl-round);border-radius:50%;
    background:var(--panel);border:1px solid var(--line);color:var(--txt);
    font-size:18px;cursor:pointer;backdrop-filter:blur(8px);touch-action:manipulation}
  #chronoBtn:hover{border-color:var(--accent2);color:var(--accent2)}
  #chronoBtn.active{border-color:var(--accent);color:var(--accent);background:rgba(255,178,77,.14)}
  #chronoBar{position:absolute;left:74px;right:calc(var(--ctl-right) + var(--ctl-round) + 12px);bottom:16px;z-index:7;display:none;
    align-items:center;gap:8px;background:var(--panel);backdrop-filter:blur(8px);
    border:1px solid var(--line);border-radius:14px;padding:6px 8px;
    box-shadow:0 8px 30px rgba(0,0,0,.45)}
  #chronoBar.open{display:flex}
  #chronoChips{display:flex;gap:6px;overflow-x:auto;scrollbar-width:thin;scroll-behavior:smooth}
  #chronoChips .chip{flex:0 0 auto;min-height:var(--row-h);padding:3px 12px;border-radius:20px;
    border:1px solid var(--line);background:rgba(255,255,255,.05);color:var(--muted);
    font-size:var(--fs-ui);font-family:inherit;cursor:pointer;white-space:nowrap;
    touch-action:manipulation;display:flex;align-items:center}
  #chronoChips .chip.on{background:rgba(255,178,77,.18);border-color:var(--accent);
    color:var(--txt);font-weight:600}
  #chronoPlay{flex:0 0 auto;min-height:var(--row-h);min-width:var(--row-h);padding:0 10px;
    border-radius:20px;border:1px solid var(--line);background:rgba(95,208,197,.14);
    color:var(--accent2);font-size:15px;cursor:pointer;font-family:inherit;touch-action:manipulation}
  #chronoPlay.on{background:rgba(255,178,77,.16);border-color:var(--accent);color:var(--accent)}
  /* Caption-Karte ueber der Leiste */
  /* §12 (P3c): Caption mittig über der Jahresleiste (Mitte-Konvention wie Scale-Bar/
     Koordinaten) statt linksbündig -> kollidiert nicht mehr mit dem Touren-Panel. */
  #chronoCap{position:absolute;left:50%;transform:translateX(-50%);bottom:76px;z-index:7;display:none;
    width:max-content;max-width:min(72vw,460px);background:var(--panel);backdrop-filter:blur(8px);
    border:1px solid var(--line);border-radius:14px;padding:9px 13px;
    box-shadow:0 8px 30px rgba(0,0,0,.45)}
  #chronoCap.open{display:block}
  /* Befund 10: aktive Filter-Zeile über dem Jahr, dezent + zentriert, ✕ wie Bilanzzeile. */
  .cc-filter{display:flex;align-items:center;justify-content:center;gap:6px;flex-wrap:wrap;
    font-size:11px;color:var(--accent2);margin-bottom:6px;padding-bottom:5px;border-bottom:1px solid var(--line)}
  .cc-filter .cc-fx{background:transparent;border:1px solid var(--line);color:var(--muted);
    border-radius:5px;cursor:pointer;font-size:12px;line-height:1;padding:1px 6px;min-height:22px;touch-action:manipulation}
  .cc-filter .cc-fx:hover{color:var(--txt);border-color:var(--accent2)}
  .cc-h{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
  .cc-y{font-size:22px;font-weight:700;color:var(--accent);line-height:1.1}
  .cc-d{font-size:12px;color:var(--muted)}
  .cc-t{font-size:13px;color:var(--txt);line-height:1.45;margin-top:3px}
  .cc-who{font-style:italic;color:var(--muted)}
  /* §5: Kategorie-Badge in der Chronik-Caption */
  .cc-kat{display:inline-block;font-size:10.5px;font-weight:600;color:var(--accent2);
    background:rgba(95,208,197,.14);border:1px solid rgba(95,208,197,.35);border-radius:5px;
    padding:0 6px;margin-right:6px;vertical-align:1px;white-space:nowrap}
  .cc-memo{font-size:11.5px;color:var(--muted);line-height:1.4;margin-top:1px;cursor:pointer;
    border-left:2px solid rgba(255,178,77,.5);padding-left:7px}
  .cc-more{color:var(--accent2);font-weight:600;white-space:nowrap}
  #panel .tour-memo{font-size:11.5px;line-height:1.5;color:var(--muted);font-style:italic;
    margin:6px 0 3px;padding-left:9px;border-left:2px solid rgba(255,178,77,.35)}
  /* ── Fotos: Caption-Thumb, Panel-Scrollband, Lightbox (nur Privat) ── */
  .cc-media{display:flex;gap:8px;align-items:flex-start;margin-top:4px}
  .cc-media .cc-memo{margin-top:0;flex:1}
  .cc-thumb{width:72px;height:54px;border-radius:6px;object-fit:cover;cursor:pointer;
    flex:0 0 auto;touch-action:manipulation}
  .foto-band{display:flex;gap:6px;overflow-x:auto;-webkit-overflow-scrolling:touch;
    scrollbar-width:thin;margin:7px 0 2px;padding-bottom:2px}
  .fb-img{height:96px;width:auto;min-width:40px;border-radius:7px;object-fit:cover;
    cursor:pointer;flex:0 0 auto;touch-action:manipulation}
  #lightbox{position:fixed;inset:0;z-index:20;display:none;background:rgba(0,0,0,.92);
    align-items:center;justify-content:center;flex-direction:column;touch-action:none}
  #lightbox.open{display:flex}
  #lbImg{max-width:94vw;max-height:86vh;border-radius:6px;box-shadow:0 10px 40px rgba(0,0,0,.6)}
  #lightbox .lb-cap{color:#e8edf2;font-size:14px;margin-top:12px;max-width:90vw;text-align:center;min-height:18px;padding:0 12px}
  #lightbox .lb-x{position:absolute;top:10px;right:14px;color:#e8edf2;font-size:34px;cursor:pointer;
    width:44px;height:44px;display:grid;place-items:center;touch-action:manipulation}
  #lightbox .lb-nav{position:absolute;top:50%;transform:translateY(-50%);background:rgba(255,255,255,.12);
    border:none;color:#fff;font-size:30px;width:46px;height:64px;border-radius:10px;cursor:pointer;
    touch-action:manipulation}
  #lightbox .lb-prev{left:10px} #lightbox .lb-next{right:10px}
  /* PRIV:END */

  @media(max-width:640px){
    #title{max-width:calc(100vw - 90px)}
    #panel{width:auto;left:16px;right:16px;top:auto;bottom:16px;z-index:9}
    #ebenen{max-width:calc(100vw - 32px)}
    /* P1: Tourenliste auch auf dem Handy als Bottom-Sheet (Zielgerät: 10-Zoll-Tablet).
       #panel (z9) öffnet darüber; openSts klappt #cov ein -> kein Overlap-Konflikt. */
    #cov{left:16px;right:16px;width:auto;bottom:16px;z-index:8;max-height:72vh}
  }
  /* UX(2): Title-Card kollabiert bei kleiner Fensterhoehe auf die Titelzeile (Tablet quer),
     damit der Steckbrief Platz hat. */
  @media (max-height: 620px){
    #title p, #title .kpi{display:none}
    #title{padding:10px 14px}
  }
  /* UX(3): schmale Fenster — bei offener Chronik ueberlagern sich zentrierte Scale-Bar und
     linksbuendige Caption; Footer dort ausblenden (Jahresleiste + Caption tragen die Zeile). */
  @media (max-width: 680px){
    body.chrono #mapfoot{display:none}
  }
  /* ── PHONE-Stufe: schmale Breite UND Touch (Tablet-coarse bleibt die 44-px-Stufe) ── */
  @media (max-width: 480px) and (pointer: coarse){
    /* c) +/− und Pitch-Reset (Nav-Control) AUS — Pinch/Zwei-Finger decken das ab.
       Sichtbar bleiben Lupe/ⓘ/?/3D/Home (eigene Buttons), Touch-Ziele >=44px. */
    .maplibregl-ctrl-group{display:none !important}
    /* a) Title-Card antippbar; JS startet sie kollabiert (nur Titelzeile). */
    #title{cursor:pointer}
    #title.collapsed p, #title.collapsed .kpi, #title.collapsed #legend, #title.collapsed #btnAbout2{display:none}
    #title.collapsed{padding:10px 14px}
    #title.collapsed h1::after{content:' \25BE';color:var(--muted);font-size:.7em;vertical-align:middle}
    /* d) Chronik-Caption auf max. 2 Zeilen begrenzen. */
    #chronoCap .cc-t{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
  }
</style>
</head>
<body>
<div id="map"></div>
<div id="mapfoot"><div id="coords" title="WGS84 (Grad-Dezimal)"></div></div>
<div id="toast"></div>
<div id="undoChip" onclick="restoreUndo(event)" title="Vorherige Ansicht wiederherstellen">&#8617; Letzte Ansicht</div>

<div id="title">
  <!-- Politur P1.2: Mini-Zeile (nach erster Karten-Interaktion; Klick = aufklappen) -->
  <div id="titleMini" onclick="expandTitle()" title="Aufklappen">
    <span class="tm-logo">&#9650;</span>
    <span class="tm-name">__TITEL__</span>
    <span class="tm-kpi" id="tmKpi"></span>
    <span class="tm-caret">&#9662;</span>
  </div>
  <h1 onclick="collapseTitle()" title="Einklappen">__TITEL__</h1>
  <p>__UNTER__</p>
  <div class="kpi">
    <!-- PUB:START --><div><b>__KPI_GRUPPEN__</b><span>Gruppen</span></div><div><b>__KPI_SETTORI__</b><span>Sektoren</span></div><div><b>__KPI_HUETTEN__</b><span>Vereinsh&uuml;tten</span></div><!-- PUB:END -->
    <!-- PRIV:START --><div><b id="kTours">–</b><span>Touren</span></div><div><b id="kGroups">–</b><span>SOIUSA-Gruppen</span></div><div><b id="kYears">–</b><span>Jahre</span></div><!-- PRIV:END -->
  </div>
  <!-- Legende „Sektoren" — Politur P1.3: 2-spaltig hierarchisch (Westalpen | Ostalpen) -->
  <div id="legend" class="open">
    <div class="lh" onclick="event.stopPropagation();toggleLegend()">
      <span class="lt">Sektoren</span>
      <div id="tglFarbung" class="tgl on" onclick="event.stopPropagation();toggleFarbung()" title="F&auml;rbung an/aus"><span>F&auml;rbung</span><span class="sw"></span></div>
    </div>
    <div class="ll">
      <div class="lcols">
        <div class="lcol">
          <div class="lgrp">Westalpen</div>
          <div class="lrow"><span class="sw-nw"></span>Nordwestalpen</div>
          <div class="lrow"><span class="sw-sw"></span>S&uuml;dwestalpen</div>
        </div>
        <div class="lcol">
          <div class="lgrp">Ostalpen</div>
          <div class="lrow"><span class="sw-no"></span>Nordostalpen</div>
          <div class="lrow"><span class="sw-zo"></span>Zentralostalpen</div>
          <div class="lrow"><span class="sw-so"></span>S&uuml;dostalpen</div>
        </div>
      </div>
      <!-- PRIV:START --><div class="lsep"></div>
      <div class="lrow"><span class="sw-hl"></span>besucht</div><!-- PRIV:END -->
    </div>
  </div>
  <button id="btnAbout2" onclick="event.stopPropagation();toggleAboutCard()" title="&Uuml;ber diese Karte"><span class="ic">i</span>&Uuml;ber diese Karte</button>
</div>

<button id="btnInfo" onclick="toggleAbout()" title="Info &amp; Anleitung">?</button>
<button id="btnAttrib" onclick="toggleAttrib(event)" title="Kartenquellen" aria-label="Kartenquellen"></button>
<div id="attribPop" role="dialog" aria-label="Kartenquellen"></div>
<button id="home" onclick="overview()" title="Standardansicht">&#8962;</button>
<button id="btn2d3d" onclick="toggle2D3D()" title="2D / 3D umschalten">3D</button>
<button id="btnFull" onclick="toggleFullscreen()" title="Vollbild">&#9974;</button>

<div id="search">
  <button id="sToggle" onclick="toggleSearch()" title="Suche" aria-label="Suche">&#128269;</button>
  <input id="sInput" type="text" autocomplete="off" spellcheck="false"
    placeholder="Gipfel, H&uuml;tte, Pass, Gruppe, Koordinate&hellip;" />
  <div id="sRes"></div>
</div>

<!-- „?" rechts oben = reine Bedienungshilfe (T4) -->
<div id="about">
  <div class="x" onclick="toggleAbout()">&times;</div>
  <h3>So bedienst du die Karte</h3>
  <!-- PUB:START --><p>Auf eine <b>farbige Fl&auml;che tippen</b> &rarr; Steckbrief der Gebirgsgruppe
     (h&ouml;chster Berg, Lage, Land).</p><!-- PUB:END -->
  <!-- PRIV:START --><p>Auf eine <b>farbige Fl&auml;che tippen</b> &rarr; Steckbrief &amp; besuchte Touren.
     Unten links <b>„Touren ansehen"</b> f&uuml;hrt zu den besuchten Gebieten.</p><!-- PRIV:END -->
  <p><b>Ebenen</b> (Panel rechts): Namen, Landesgrenzen, Gipfel, H&uuml;tten, P&auml;sse, Orte &amp;
     Seilbahnen zuschalten. Die <b>F&auml;rbung</b> schaltest du oben links in der Legende.</p>
  <p><b>Drehen &amp; Neigen:</b> mit gedr&uuml;ckter <b>rechter Maustaste ziehen</b> (oder zwei
     Finger) &ndash; waagerecht dreht, senkrecht kippt. <b>Zoom:</b> Mausrad oder <b>+/&minus;</b>.
     Der <b>Kompass</b> stellt Norden &amp; flache Sicht wieder her.</p>
  <p><b>Suchen</b> &#128269; (oben): Gipfel, H&uuml;tte, Pass, Gruppe oder Koordinate. Das
     <b>Haus-Icon</b> setzt die Standardansicht zur&uuml;ck, &#9974; schaltet Vollbild.</p>
</div>

<!-- ⓘ „Über diese Karte" an der Title-Card links (T4) -->
<div id="aboutCard">
  <div class="x" onclick="toggleAboutCard()">&times;</div>
  <h3>&Uuml;ber diese Karte</h3>
  <!-- PRIV:START --><p>__PT_ABOUT_INTRO__</p><!-- PRIV:END -->
  <p>Die <b>Suddivisione Orografica Internazionale Unificata del Sistema Alpino</b> (SOIUSA)
     ist ein geographisches Klassifizierungssystem der Alpen, entwickelt von
     <b>Sergio Marazzi</b> (Standard 2005).</p>
  <p>SOIUSA gliedert die Alpen in <b>2 Teile</b>, <b>5 Sektoren</b> und <b>36 Sektionen</b>
     mit <b>132 Untersektionen</b> &ndash; die farbigen Fl&auml;chen dieser Karte sind die
     Untersektionen, hier vereinfacht <b>„Gebirgsgruppen"</b>.</p>
  <p><a href="https://de.wikipedia.org/wiki/SOIUSA" target="_blank" rel="noopener">Mehr auf Wikipedia &rarr;</a></p>
  <p><b>Tech:</b> Datenaufbereitung in <b>Python</b>, Rendering mit <b>MapLibre GL JS</b>,
     3D-Terrain aus offenem DEM. Komplett <b>statisch &amp; keyless</b> auf GitHub Pages
     (kein Server, kein API-Key).
     <a href="https://github.com/guncanrun/alpentouren" target="_blank" rel="noopener">Quellcode auf GitHub &rarr;</a></p>
  <p><b>Daten:</b> SOIUSA (ARPA Piemonte) &middot; OpenStreetMap &ndash; Gipfel/H&uuml;tten (ODbL)
     &middot; Wikipedia/Wikidata &ndash; Steckbriefe (CC BY-SA) &middot; Natural Earth
     &middot; Esri World Imagery.</p>
</div>

<!-- PRIV:START --><div id="persPopover"></div><!-- PRIV:END -->
<div id="panel">
  <div class="x" onclick="closePanel()">&times;</div>
  <!-- PRIV:START --><div class="pback" id="pBack" onclick="backToList()">&#8592; Touren</div><!-- PRIV:END -->
  <div class="ph">
    <div class="yr" id="pYear"></div>
    <h2 id="pGroup"></h2>
    <div class="gegend" id="pGegend"></div>
  </div>
  __PTABS__
  <div class="body">
    <div class="pane active" id="pAbout"></div>
    <div class="pane" id="pTour"></div>
  </div>
</div>

<!-- PRIV:START -->
<div id="cov">
  <div class="ch" onclick="toggleCov()">
Touren ansehen <span id="covCount"></span>
  </div>
  <div class="cl">
    <div id="tourFilter">
      <div class="tf-filterhead" id="tfFilterHead" onclick="toggleFilterBlock()"><span class="tf-fh-l"><svg class="tf-picon" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="5" r="3"/><path d="M2.5 14c0-3.2 2.5-5 5.5-5s5.5 1.8 5.5 5"/></svg>Personen · Jahre · Tourentyp filtern</span><span class="tf-caret">&#9662;</span></div>
      <div class="tf-filterbody">
        <div class="tf-seg" id="strangSeg">
          <button class="tf-sbtn on" data-strang="alle" onclick="setStrang('alle')">Alle (<b id="cntAlle">18</b>)</button>
          <button class="tf-sbtn" data-strang="brueder" onclick="setStrang('brueder')">__PT_LBL_BRUEDER__ (<b id="cntBrueder">10</b>)</button>
          <button class="tf-sbtn" data-strang="weitere" onclick="setStrang('weitere')">Weitere (<b id="cntWeitere">8</b>)</button>
        </div>
        <div class="tf-jahr" id="tfJahr">
          <div class="tf-jahr-lbl"><span>Jahre</span><span id="tfJahrVal">1993&ndash;2023</span></div>
          <div class="tf-jahr-slider">
            <div class="tf-jahr-track"><div class="tf-jahr-fill" id="tfJahrFill"></div></div>
            <input type="range" id="tfJahrVon" min="1993" max="2023" step="1" value="1993" aria-label="Jahr von">
            <input type="range" id="tfJahrBis" min="1993" max="2023" step="1" value="2023" aria-label="Jahr bis">
          </div>
        </div>
        <div class="tf-perstoggle" id="tfPersToggle" onclick="togglePersGrid()"><span class="tf-pt-l"><svg class="tf-picon" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="5" r="3"/><path d="M2.5 14c0-3.2 2.5-5 5.5-5s5.5 1.8 5.5 5"/></svg>__PT_LBL_PERSFILTER__</span><span class="tf-caret">&#9662;</span></div>
        <div class="tf-chips" id="personChips"></div>
      </div>
      <div class="tf-badges" id="filterBadges"></div>
      <div id="tglTracks" class="tgl on tf-tracks" onclick="toggleTracks()" title="Ebene ein-/ausblenden: Routen der Touren"><span class="tf-tl"><svg class="tf-eye" viewBox="0 0 16 16" aria-hidden="true"><path d="M1 8s2.6-4.3 7-4.3S15 8 15 8s-2.6 4.3-7 4.3S1 8 1 8z"/><circle cx="8" cy="8" r="2.1"/></svg>Touren-Tracks</span><span class="sw"></span></div>
    </div>
    <div id="covList"></div>
    <div id="covEmpty" class="tf-empty" style="display:none"></div>
  </div>
</div>
<!-- Chronologie-Modus: runder Toggle unten links + Caption + Jahresleiste (Play) -->
<button id="chronoBtn" onclick="chronoToggle()" title="Chronologie &ndash; Jahre durchgehen">&#128344;</button>
<div id="chronoCap"></div>
<div id="chronoBar">
  <button id="chronoPlay" onclick="chronoPlayToggle()" title="Abspielen" aria-label="Abspielen">&#9654;</button>
  <div id="chronoChips"></div>
</div>
<!-- Foto-Lightbox (Fullscreen) -->
<div id="lightbox" onclick="lbClose()">
  <div class="lb-x" onclick="lbClose()" title="Schlie&szlig;en">&times;</div>
  <button class="lb-nav lb-prev" id="lbPrev" onclick="lbPrev(event)" aria-label="Zur&uuml;ck">&#8249;</button>
  <img id="lbImg" src="" alt="" onclick="event.stopPropagation()" />
  <button class="lb-nav lb-next" id="lbNext" onclick="lbNext(event)" aria-label="Weiter">&#8250;</button>
  <div class="lb-cap" id="lbCap"></div>
</div>
<!-- PRIV:END -->

<div id="ebenen" class="open">
  <div class="eh" onclick="document.getElementById('ebenen').classList.toggle('open');_applyPanelPad&&_applyPanelPad()">Ebenen</div>
  <div class="eb"><div class="eb-in">
    <div class="grp">Karte</div>
    <div class="seg">
      <button id="bmSat" class="on" onclick="setBasemap('sat')">Satellit</button>
      <button id="bmTopo" onclick="setBasemap('topo')">Topo</button>
    </div>
    <div class="grp">Struktur</div>
    <div id="tglNamen" class="tgl" onclick="toggleLayers()"><span>Namen</span><span class="sw"></span></div>
    <div id="tglBorders" class="tgl" onclick="toggleBorders()"><span>Landesgrenzen</span><span class="sw"></span></div>
    <div class="grp">Punkte</div>
    <div id="tglPeaks" class="tgl" onclick="togglePeaks()"><span>Gipfel</span><span class="sw"></span></div>
    <div id="tglHuts" class="tgl" onclick="toggleHuts()"><span>H&uuml;tten</span><span class="sw"></span></div>
    <div id="tglPasses" class="tgl" onclick="togglePasses()"><span>P&auml;sse</span><span class="sw"></span></div>
    <div class="grp" title="Wie komme ich hin? Talorte + Personen-Seilbahnen">Anreise</div>
    <div id="tglPlaces" class="tgl" onclick="togglePlaces()"><span>Orte</span><span class="sw"></span></div>
    <div id="tglCable" class="tgl" onclick="toggleCable()"><span>Seilbahnen</span><span class="sw"></span></div>
  </div></div>
</div>

<script>
const TOUREN = __TOUREN_GEOJSON__;
const SOIUSA_STS = __SOIUSA_STS_GEOJSON__;
const SOIUSA_HIGHLIGHTS = __SOIUSA_HIGHLIGHTS_GEOJSON__;
const SOIUSA_LBL_PTS    = __SOIUSA_LBL_PTS_GEOJSON__;
const MASK = __MASK_GEOJSON__;
const COUNTRY_LABELS = {type:'FeatureCollection',features:[
  {type:'Feature',geometry:{type:'Point',coordinates:[11.40,47.62]},properties:{name:'Deutschland',iso:'DE'}},
  {type:'Feature',geometry:{type:'Point',coordinates:[13.80,47.30]},properties:{name:'Österreich',iso:'AT'}},
  {type:'Feature',geometry:{type:'Point',coordinates:[8.00,46.75]},properties:{name:'Schweiz',iso:'CH'}},
  {type:'Feature',geometry:{type:'Point',coordinates:[11.05,46.35]},properties:{name:'Italien',iso:'IT'}},
  {type:'Feature',geometry:{type:'Point',coordinates:[6.50,45.42]},properties:{name:'Frankreich',iso:'FR'}},
  {type:'Feature',geometry:{type:'Point',coordinates:[14.10,46.30]},properties:{name:'Slowenien',iso:'SI'}},
  {type:'Feature',geometry:{type:'Point',coordinates:[9.55,47.15]},properties:{name:'Liechtenstein',iso:'LI'}}
]};
const WIKI = __SOIUSA_WIKI_JSON__;
const HUTS_WIKI = __SOIUSA_HUTS_WIKI_JSON__;   // Hütten-Steckbriefe, Key = OSM-Name
// Standalone: inline-GeoJSONs (sonst null -> relative URL/Fetch wie im Normal-Build).
const OSM_PEAKS  = __OSM_PEAKS__;
const OSM_HUTS   = __OSM_HUTS__;
const OSM_PASSES = __OSM_PASSES__;
const OSM_PLACES = __OSM_PLACES__;
const OSM_CABLE  = __OSM_CABLE__;
const OSM_CABLE_LINES = __OSM_CABLE_LINES__;   // W4: Seilbahn-Linien (voller Verlauf)
const OSM_CHAIRLIFTS  = __OSM_CHAIRLIFTS__;    // Anreise-Folgepaket: Sessellift-Linien (chair_lift)
const BORDERS_GJ = __BORDERS__;
const GROUP_PEAKS = __GROUP_PEAKS__;   // N3: STS -> [lon,lat] des höchsten Gipfels (Build-time, eindeutig)
const PRIV = __PRIV__;
const TOUR_LAYERS = PRIV ? ['t-hit','t-cluster-halo'] : [];   // tour markers only exist in the private build (Hit-Kreis + Cluster)
const CNAMES = {AT:'Österreich',CH:'Schweiz',DE:'Deutschland',
  FR:'Frankreich',IT:'Italien',SI:'Slowenien',LI:'Liechtenstein'};

console.log('SOIUSA:', SOIUSA_STS.features.length, 'Untergruppen,',
            SOIUSA_HIGHLIGHTS.features.length, 'Highlights');

// ── Coverage (private build only — visited groups + years) ────────────────────
/* PRIV:START */
// Frühestes Besuchsjahr einer Gruppe (jahr_sort-Logik, aus dem Chronik-Block hoisted).
function _groupMinYear(props){
  let ids=[]; try{ ids = typeof props.tour_ids==='string'?JSON.parse(props.tour_ids||'[]'):(props.tour_ids||[]); }catch(_){}
  let min=Infinity;
  ids.forEach(id=>{ const t=TOUREN.find(x=>x.id==id); const y=t&&jahrSort(t.jahr); if(y&&y<min) min=y; });
  return min;
}
// Coverage-Liste chronologisch AUFSTEIGEND (ältestes Besuchsjahr zuerst; Tie-Break name_de).
const visitedGroups = SOIUSA_STS.features.filter(f=>f.properties.visited===1)
  .map(f=>f.properties)
  .sort((a,b)=>{
    const ya=_groupMinYear(a), yb=_groupMinYear(b);
    if(ya!==yb) return ya-yb;
    return String(a.name_de||a.STS).localeCompare(String(b.name_de||b.STS));
  });
document.getElementById('kGroups').textContent = SOIUSA_HIGHLIGHTS.features.length+'/'+SOIUSA_STS.features.length;
document.getElementById('kTours').textContent = TOUREN.length;
document.getElementById('covCount').textContent =
  SOIUSA_HIGHLIGHTS.features.length + ' Gebiete · ' + TOUREN.length + ' Touren';
{ const ys=TOUREN.map(t=>parseInt(String(t.jahr||'').replace(/[^0-9]/g,'').slice(0,4))).filter(Boolean);
  if(ys.length) document.getElementById('kYears').textContent = Math.min(...ys)+'–'+Math.max(...ys); }
/* PRIV:END */

// ── Tour point markers (privat only — public JSON has no coordinates) ─────────
/* PRIV:START */
// Rekonstruierte GPX-Track-Linien (SPEC_GPX_Tracks_Privat) — nur Privat-Build.
const TRACKS = __TRACKS_GEOJSON__;
// Personen-Register (SPEC_Personenfilter, privat/gitignored) — Namen/Aliasse/Rollen.
const PERSONEN = __PERSONEN_JSON__;
// Politur P2.7: Wanderer-Clustering — Gebiete mit >=2 Touren zeigen bei z<9 EIN Cluster-
// Icon (Zähler) am Touren-Zentroid; ab z>=9 Split in Einzel-Icons. „multi"-Flag gated die
// Einzel-Icon-Größe (0 bei z<9), ohne die P3b-Opacity (emphasizeTour) zu berühren.
const _multiIds=new Set(); const _clusterFeats=[];
visitedGroups.forEach(g=>{
  const ids=_groupTourIds(g); if(ids.length<2) return;
  const pts=ids.map(id=>TOUREN.find(t=>t.id==id)).filter(t=>t&&t.lon!=null&&t.lat!=null);
  if(pts.length<2) return;
  ids.forEach(id=>_multiIds.add(id));
  const cx=pts.reduce((a,t)=>a+t.lon,0)/pts.length, cy=pts.reduce((a,t)=>a+t.lat,0)/pts.length;
  _clusterFeats.push({type:'Feature', geometry:{type:'Point',coordinates:[cx,cy]},
    properties:{sts:g.STS, count:pts.length}});
});
const fc = {type:'FeatureCollection', features: TOUREN.map(t=>({
  type:'Feature', id:t.id,
  geometry:{type:'Point', coordinates:[t.lon, t.lat]},
  properties:{id:t.id, jahr:t.jahr, gegend:t.gegend, gebirge:t.gebirge,
              land:t.land, verifiziert:t.verifiziert?1:0, multi:_multiIds.has(t.id)?1:0}
}))};
const clusterFC={type:'FeatureCollection', features:_clusterFeats};
/* PRIV:END */

// ── Default camera: full Alpine view, slightly SW-biased ──────────────────────
const ALPS = {center:[10.2,46.1], zoom:5.3, pitch:0, bearing:0};

// Große-Screen-Stufe (27"+, feiner Zeiger): spiegelt die CSS-Media-Query. Steuert
// Popup-Breiten und einen leichten Karten-Label-Boost (initialer Viewport-Check).
const _bigScr = !!(window.matchMedia && window.matchMedia('(min-width: 2200px) and (pointer: fine)').matches);
const LB = _bigScr ? 1.5 : 0;   // Label-Zuschlag (px) für Gipfel/Hütten/Pässe
// A3 (Review §1): Rauchtest-Schalter ?smoke=1 (aktiviert u.a. preserveDrawingBuffer
// fuer den Pixel-Check nach idle). Sonst kein Perf-Einfluss.
const _SMOKE = (function(){ try{ return new URLSearchParams(location.search).get('smoke')==='1'; }catch(_){ return false; } })();

// A4: Standalone inlint die Glyphs (Noto Sans Bold, 4 Ranges) als base64 und liefert sie
// ueber ein glyphs://-Protokoll -> keine Font-Requests ans Netz (nur Tiles bleiben online).
// Muss VOR der Map-Erstellung stehen (Style referenziert glyphs). Sonst GLYPHS_DATA=null.
const GLYPHS_DATA = __GLYPHS_DATA__;
if(GLYPHS_DATA){
  maplibregl.addProtocol('glyphs', (params)=>new Promise((resolve,reject)=>{
    const m=params.url.match(/\/(\d+-\d+)\.pbf$/), b64=m&&GLYPHS_DATA[m[1]];
    if(!b64){ reject(new Error('glyph range not inlined: '+params.url)); return; }
    const bin=atob(b64), arr=new Uint8Array(bin.length);
    for(let i=0;i<bin.length;i++) arr[i]=bin.charCodeAt(i);
    resolve({data:arr.buffer});
  }));
}

const map = new maplibregl.Map({
  container:'map',
  pixelRatio: window.devicePixelRatio || 2,
  preserveDrawingBuffer: _SMOKE,
  minZoom: 5.0,
  maxBounds: [[3.5,42.5],[18.5,49.5]],
  style:{
    version:8,
    glyphs:'__GLYPHS__',
    sources:{
      sat:{type:'raster', tileSize:256,
        tiles:['https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}']},
      topo:{type:'raster', tileSize:256, maxzoom:17,
        tiles:['https://a.tile.opentopomap.org/{z}/{x}/{y}.png',
               'https://b.tile.opentopomap.org/{z}/{x}/{y}.png',
               'https://c.tile.opentopomap.org/{z}/{x}/{y}.png']},
      dem:{type:'raster-dem', tileSize:256, encoding:'terrarium', maxzoom:10,
        tiles:['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png']}
    },
    layers:[
      {id:'bg',  type:'background', paint:{'background-color':'#0a0e14'}},
      {id:'sat', type:'raster', source:'sat', paint:{'raster-opacity':0.95}},
      {id:'topo',type:'raster', source:'topo', layout:{visibility:'none'}, paint:{'raster-opacity':1}},
      {id:'hill',type:'hillshade', source:'dem',
        paint:{'hillshade-exaggeration':0.25,'hillshade-shadow-color':'#1a2840'}}
    ]
  },
  center:ALPS.center, zoom:ALPS.zoom, pitch:ALPS.pitch, bearing:ALPS.bearing,
  maxPitch:70, hash:true,
  // Punkt 3: deutsche Tooltips fuer die maplibre-Default-Controls (Zoom/Kompass).
  locale:{
    'NavigationControl.ZoomIn':'Hineinzoomen',
    'NavigationControl.ZoomOut':'Herauszoomen',
    'NavigationControl.ResetBearing':'Nach Norden ausrichten'
  },
  attributionControl:false   // eigenes Kartenquellen-Control (#btnAttrib/#attribPop, setAttrib)
});
// Befund 6/11: beide Seiten-Panels aus dem Kartenbild „herausrechnen" (persistentes
// Kamera-Padding) — Home/Initial/Suche zeigen den Alpenbogen MITTIG zwischen dem linken
// Touren-Panel (left) und dem rechten Ebenen-Panel (right). Nur Desktop (Maus + breit);
// Tablet/Mobile (Bottom-Sheet) unverändert. flyTo/fitBounds mit eigenem padding überschreiben.
function _padGate(){ return window.innerWidth > 900 && window.matchMedia('(pointer: fine)').matches; }
// P1: linkes Padding = Footprint des Touren-Panels am DOM (folgt --panel-w automatisch).
function _panelPadPx(){
  if(!_padGate()) return 0;
  try{ const el=document.getElementById('cov'); if(el){ const r=el.getBoundingClientRect(); if(r.width>0) return Math.round(r.right + 12); } }catch(_){}
  return 340;
}
// B11: rechtes Padding = Footprint des Ebenen-Panels, AM DOM GEMESSEN (nicht hardcoden) und
// dynamisch: nur wenn aufgeklappt (dann steht die Box im Kartenbild); eingeklappt = nur der
// schmale Header oben rechts -> 0 (Bogen darf die Fläche nutzen).
function _ebenenPadPx(){
  if(!_padGate()) return 0;
  try{
    const el=document.getElementById('ebenen');
    if(!el || !el.classList.contains('open')) return 0;
    const r=el.getBoundingClientRect();
    return r.width>0 ? Math.round(Math.max(0, window.innerWidth - r.left)) : 0;
  }catch(_){ return 0; }
}
function _applyPanelPad(){ try{ map.setPadding({left:_panelPadPx(), top:0, right:_ebenenPadPx(), bottom:0}); }catch(_){ } }
_applyPanelPad();
window.addEventListener('resize', _applyPanelPad);
// ── Attribution (dynamic per basemap) ─────────────────────────────────────────
const ATTRIB = {
  sat:'Imagery © Esri, Maxar, Earthstar · Höhen: Mapzen/AWS · SOIUSA © Arpa Piemonte · '+
      'Gipfel/Hütten/Pässe © OpenStreetMap (ODbL) · Wege © OpenFreeMap (OpenMapTiles/OSM) · '+
      'Höhenlinien: maplibre-contour aus DEM',
  topo:'© OpenStreetMap-Mitwirkende, SRTM · Kartendarstellung © OpenTopoMap (CC-BY-SA) · '+
       'Höhen: Mapzen/AWS · SOIUSA © Arpa Piemonte'
};
// Feinschliff 3: eigenes Attribution-Control (kein natives maplibre-details-Element mehr,
// das war die Wurzel fuer Kaestchen/Doppelklick/FOUC). setAttrib fuellt nur noch das
// eigene Popup-Div (#attribPop); Inhalt weiter aus dem ATTRIB-Objekt.
function setAttrib(topo){
  const el=document.getElementById('attribPop');
  if(el) el.innerHTML = topo?ATTRIB.topo:ATTRIB.sat;
}
// ⓘ oeffnet/schliesst das Kartenquellen-Popup (Klick auf ⓘ, ausserhalb oder Esc).
function toggleAttrib(e){
  if(e) e.stopPropagation();
  const pop=document.getElementById('attribPop'), btn=document.getElementById('btnAttrib');
  const open=pop && pop.classList.toggle('open');
  if(btn) btn.classList.toggle('on', !!open);
}
function _closeAttrib(){
  const pop=document.getElementById('attribPop'), btn=document.getElementById('btnAttrib');
  if(pop) pop.classList.remove('open'); if(btn) btn.classList.remove('on');
}
// Ausserhalb-Klick schliesst (Klick auf ⓘ selbst laeuft ueber toggleAttrib + stopPropagation;
// Klick auf Links IM Popup nicht schliessen).
document.addEventListener('click', e=>{
  const pop=document.getElementById('attribPop');
  if(pop && pop.classList.contains('open') && !pop.contains(e.target)) _closeAttrib();
  // W1.3: Hintergrund-Klick schließt auch die „?"-Hilfe (Klick auf ? läuft über toggleAbout).
  const ab=document.getElementById('about'), info=document.getElementById('btnInfo');
  if(ab && ab.classList.contains('open') && !ab.contains(e.target) && e.target!==info) ab.classList.remove('open');
  // T4: dito für „Über diese Karte" (Klick auf ⓘ läuft über toggleAboutCard + stopPropagation).
  const ac=document.getElementById('aboutCard');
  if(ac && ac.classList.contains('open') && !ac.contains(e.target)) ac.classList.remove('open');
});
document.addEventListener('keydown', e=>{ if(e.key==='Escape') closeAllOverlays(); });
setAttrib(false);   // W1.5: Kartenquellen-Div beim Init befuellen (Sat-Default) — sonst leeres ⓘ-Popup
// W1.2 (Kurator-Entscheid): Kompass-Klick = Norden UND Pitch-Reset -> visualizePitch:true.
map.addControl(new maplibregl.NavigationControl({visualizePitch:true}), 'bottom-right');
// B2: Maßstabsleiste (metrisch) — jetzt unten MITTIG + groesser, im zentrierten Footer.
map.addControl(new maplibregl.ScaleControl({maxWidth:170, unit:'metric'}), 'bottom-left');
// Scale-Element aus der maplibre-Ecke in den zentrierten Footer holen (Rechenlogik bleibt).
(function(){ const sc=document.querySelector('.maplibregl-ctrl-scale'),
  mf=document.getElementById('mapfoot'); if(sc && mf) mf.insertBefore(sc, mf.firstChild); })();

// ── PHONE-Stufe: Title-Card startet kollabiert (antippbar) · Ebenen-Panel eingeklappt ──
// Tablet (coarse, breiter als 480) bleibt unveraendert. Reagiert auf Rotation.
(function(){
  const title=document.getElementById('title'), ebenen=document.getElementById('ebenen');
  if(title) title.addEventListener('click', ()=>title.classList.toggle('collapsed'));
  const mq = window.matchMedia && window.matchMedia('(max-width: 480px) and (pointer: coarse)');
  function apply(on){ if(title) title.classList.toggle('collapsed', on); if(on && ebenen) ebenen.classList.remove('open'); }
  if(mq){ apply(mq.matches); (mq.addEventListener?mq.addEventListener('change',e=>apply(e.matches)):mq.addListener(e=>apply(e.matches))); }
})();

// ── Touch-Gesten ──────────────────────────────────────────────────────────────
// a) Doppeltipp = Hineinzoomen: maplibre-Standard, sicherstellen dass aktiv.
map.doubleClickZoom.enable();
// b) Long-Press = kontinuierliches sanftes Herauszoomen (~0,7 z/s), solange gehalten.
//    Schwelle ~500 ms, 8-px-Bewegungstoleranz; nicht auf UI/Popup/Controls starten.
(function(){
  const HOLD=500, MOVE=8, RATE=0.7;   // ms · px · Zoomstufen pro Sekunde
  let timer=null, start=null, raf=null, zooming=false;
  const UI='.maplibregl-ctrl, .maplibregl-popup, #title, #ebenen, #panel, #search, #about, #aboutCard, #cov, #legend, button';
  // rAF-Schleife (setZoom je Frame) statt easeTo: haelt beim Loslassen sofort an
  // (kein Nachlauf). Zoom aus ABSOLUTER Haltezeit -> konstante ~0,7 z/s, frame-rate-
  // unabhaengig (robust gegen Jank).
  function begin(){
    zooming=true; const z0=map.getZoom(), t0=performance.now();
    (function step(){
      if(!zooming) return;
      const z=Math.max(map.getMinZoom(), z0 - RATE*(performance.now()-t0)/1000);
      map.setZoom(z);
      if(z<=map.getMinZoom()){ zooming=false; raf=null; return; }
      raf=requestAnimationFrame(step);
    })();
  }
  function cancel(){ if(timer){clearTimeout(timer);timer=null;} zooming=false;
    if(raf){cancelAnimationFrame(raf);raf=null;} start=null; }
  const c=map.getCanvasContainer();
  c.addEventListener('touchstart',e=>{
    if(e.touches.length!==1){ cancel(); return; }              // nur Ein-Finger
    if(e.target.closest && e.target.closest(UI)) return;       // Guard: nicht auf UI/Popup
    const t=e.touches[0]; start={x:t.clientX,y:t.clientY};
    timer=setTimeout(begin, HOLD);
  },{passive:true});
  // Move/Ende auf WINDOW (Capture) -> Release/Bewegung werden zuverlaessig gefangen,
  // egal wo der Finger endet (kein Nachlauf beim Loslassen).
  window.addEventListener('touchmove',e=>{
    if(!start||!e.touches.length) return;
    const t=e.touches[0];
    if(Math.hypot(t.clientX-start.x,t.clientY-start.y)>MOVE) cancel();   // Bewegung -> Pan, Long-Press abbrechen
  },{passive:true, capture:true});
  window.addEventListener('touchend',cancel,{passive:true, capture:true});
  window.addEventListener('touchcancel',cancel,{passive:true, capture:true});
})();

// B2: Koordinaten-Anzeige (WGS84 Grad-Dezimal, 5 Stellen). Desktop: bei mousemove;
// Touch (coarse): Kartenmitte bei moveend. Dezent ueber der Scale-Bar.
(function(){
  const el=document.getElementById('coords'); if(!el) return;
  let _paused=0;   // UX(4): waehrend „kopiert"-Feedback Live-Update kurz pausieren (stabiles Klick-Ziel)
  const show=(lng,lat)=>{
    if(Date.now()<_paused) return;
    const txt=lat.toFixed(5)+', '+lng.toFixed(5);
    el.dataset.coord=txt; el.textContent=txt; el.classList.add('show');
  };
  const coarse=!!(window.matchMedia && window.matchMedia('(pointer: coarse)').matches);
  if(coarse){ const upd=()=>{ const c=map.getCenter(); show(c.lng,c.lat); };
    map.on('moveend',upd); map.on('load',upd); }
  else {
    map.on('mousemove',e=>show(e.lngLat.lng,e.lngLat.lat));
    map.getCanvas().addEventListener('mouseout',()=>{ if(Date.now()>=_paused) el.classList.remove('show'); });
  }
  // UX(4): Klick kopiert die Koordinate in die Zwischenablage (+ kurzes Feedback), Live-Update pausiert 2 s.
  el.addEventListener('click', e=>{
    e.stopPropagation();
    const txt=el.dataset.coord||el.textContent; if(!txt) return;
    _paused=Date.now()+2000;
    const done=()=>{ el.textContent='kopiert ✓'; el.classList.add('copied','show');
      setTimeout(()=>{ el.classList.remove('copied'); if(el.dataset.coord) el.textContent=el.dataset.coord; }, 1400); };
    try{ if(navigator.clipboard && navigator.clipboard.writeText){ navigator.clipboard.writeText(txt).then(done, done); }
         else { const t=document.createElement('textarea'); t.value=txt; document.body.appendChild(t); t.select();
                try{ document.execCommand('copy'); }catch(_){}; document.body.removeChild(t); done(); } }
    catch(_){ done(); }
  });
})();

// B2/Review 3b: Maßstab bei Neigung > 30° ausblenden (tiefenabhaengig falsch).
function updateTilted(){ document.body.classList.toggle('tilted', map.getPitch()>30); }
map.on('pitch', updateTilted); map.on('load', updateTilted);
// §5 (W4): Mausrad-Zoom weicher/feiner — Bordmittel, Default 1/450 -> 1/650.
try{ map.scrollZoom.setWheelZoomRate(1/650); }catch(_){}

// ── Auto-pitch: tilt up as you zoom in. Only on user zoom (wheel/pinch), never
// on flyTo/fitBounds (no originalEvent); manual pitch disables it until Alpenüberblick.
let _autoPitch=true;
function pitchForZoom(z){ return Math.max(0, Math.min(45, (z-8)*10)); }  // z8:0 z11:30 z12.5:45
map.on('pitchstart', e=>{ if(e && e.originalEvent) _autoPitch=false; });
// Only ease pitch AFTER the zoom gesture ends (no per-frame setPitch -> no jitter),
// and only for user zoom (originalEvent), never for flyTo/fitBounds.
map.on('zoomend', e=>{
  if(!_autoPitch || !(e && e.originalEvent)) return;
  const t=pitchForZoom(map.getZoom());
  if(Math.abs(map.getPitch()-t)>3) map.easeTo({pitch:t, duration:500});
});
// E) 2D/3D-Umschalter: bewusster, animierter Wechsel Draufsicht (0°) <-> Schrägsicht (~45°).
// Setzt das „Nutzer hat selbst gepitcht"-Flag (P5) -> Auto-Pitch übersteuert danach nicht mehr.
// Topo gewinnt: dort bleibt die Draufsicht fest (Pitch 0, s. Gate-Interim).
function toggle2D3D(){
  if(_basemap==='topo'){ showToast('Topo: Draufsicht ist fest'); return; }
  _autoPitch=false;
  const flat = map.getPitch() < 5;
  map.easeTo({pitch: flat?45:0, duration:600, essential:true});
}
function _update2D3DLabel(){
  const b=document.getElementById('btn2d3d'); if(b) b.textContent = (map.getPitch()>=5)?'2D':'3D';
}
map.on('pitchend', _update2D3DLabel);
map.on('load', _update2D3DLabel);

// W5: Vollbild-Toggle (Fullscreen API). Button nur sichtbar, wo die API existiert
// (iOS Safari fehlt sie -> versteckt). Motivation: Browser-UI frisst Tablet-Platz.
function toggleFullscreen(){
  const el=document.documentElement;
  if(document.fullscreenElement||document.webkitFullscreenElement){
    (document.exitFullscreen||document.webkitExitFullscreen||function(){}).call(document);
  } else {
    (el.requestFullscreen||el.webkitRequestFullscreen||function(){}).call(el);
  }
}
(function(){
  const b=document.getElementById('btnFull'); if(!b) return;
  const el=document.documentElement;
  if(el.requestFullscreen || el.webkitRequestFullscreen){
    b.style.display='block';
    const upd=()=>{ const on=!!(document.fullscreenElement||document.webkitFullscreenElement);
      b.title = on?'Vollbild beenden':'Vollbild'; };
    document.addEventListener('fullscreenchange',upd);
    document.addEventListener('webkitfullscreenchange',upd);
  }
})();

// A1 (Review §1): dauerhaftes Fehler-Logging. Fehlende Sources, Worker-Probleme und
// Style-Fehler landen sonst nirgends sichtbar (v.a. im Standalone ohne Netzwerk-Panel).
map.on('error', e=>{ try{ console.error('[MAP-ERROR]', (e && e.error && (e.error.message||e.error)) || e); }catch(_){} });

// A3 (Review §1): Rauchtest ?smoke=1 — nach dem ersten idle pruefen, ob die GeoJSON-
// Sources (laufen komplett durch den Worker/geojson-vt) Features liefern UND der Canvas
// nicht schwarz ist. Deutliches Konsolen-Badge — belegt den Standalone-Worker ohne
// Netzwerk-Inspektor. preserveDrawingBuffer ist unter ?smoke=1 aktiv (Pixel-Read).
if(_SMOKE){
  window.map = map;   // nur unter ?smoke=1: Karteninstanz fuer Playwright-Verifikation exponieren
  map.once('idle', ()=>{
    let sts=0, pts=0, nonblack=false, err='';
    try{ sts=map.querySourceFeatures('sts').length; }catch(e){ err+=' sts:'+e.message; }
    try{ pts=map.querySourceFeatures('osm-peaks').length; }catch(e){ err+=' peaks:'+e.message; }
    try{
      const cv=map.getCanvas(), gl=cv.getContext('webgl2')||cv.getContext('webgl');
      if(gl){ const w=cv.width, h=cv.height, px=new Uint8Array(4*400);
        gl.readPixels((w>>1)-10,(h>>1)-10,20,20,gl.RGBA,gl.UNSIGNED_BYTE,px);
        for(let i=0;i<px.length;i+=4){ if(px[i]|px[i+1]|px[i+2]){ nonblack=true; break; } } }
    }catch(e){ err+=' px:'+e.message; }
    const ok = sts>0 && nonblack;
    console.log('%c[SMOKE '+(ok?'OK':'FAIL')+']',
      'background:'+(ok?'#0a0':'#a00')+';color:#fff;padding:2px 8px;font-weight:bold',
      'sts-Features='+sts, 'peaks='+pts, 'Canvas='+(nonblack?'gezeichnet':'SCHWARZ'), err||'');
  });
}

// §3 (W4): Atmosphaerischer Himmel/Horizont-Dunst nur in 3D (Pitch>0), Satellit,
// und NICHT auf Touch-Geraeten (Performance-Schutz, altes Tablet). Sonst effektiv aus.
function updateSky(){
  const coarse = !!(window.matchMedia && window.matchMedia('(pointer: coarse)').matches);
  const on = !coarse && _basemap!=='topo' && map.getPitch()>2;
  try{
    map.setSky(on
      ? {'sky-color':'#0b1f3a','horizon-color':'#7a92ad','fog-color':'#c8d6e5',
         'sky-horizon-blend':0.6,'horizon-fog-blend':0.5,'fog-ground-blend':0.4,'atmosphere-blend':0.5}
      : {'atmosphere-blend':0});
  }catch(_){}
}
map.on('pitchend', updateSky);

// D) Rotation zoom-gated: ab z>=11 drehen erlaubt (Rechtsklick-Drag / Zwei-Finger),
// darunter genordet erzwungen. Uebersicht bleibt Atlas-stabil.
function updateRotationGate(){
  if(map.getZoom()>=11){ map.dragRotate.enable(); map.touchZoomRotate.enableRotation(); }
  else { map.dragRotate.disable(); map.touchZoomRotate.disableRotation(); }
}
map.on('zoom', updateRotationGate);
map.on('zoomend', ()=>{                       // beim Rauszoomen unter z11: sanft zuruecknorden
  if(map.getZoom()<11 && Math.abs(map.getBearing())>0.5) map.easeTo({bearing:0, duration:500, essential:true});
});
map.on('load', updateRotationGate);

// ── Group name popup — shown on every STS click ───────────────────────────────
// closeOnClick:false — sonst schließt MapLibre den im selben Klick geöffneten Popup
// wieder (Name erst beim 2. Klick). Schließen via X / closePanel / Leer-Klick unten.
const stsPopup = new maplibregl.Popup({
  closeButton:true, closeOnClick:false, offset:10, maxWidth:_bigScr?'320px':'260px'});
const hoverPop = new maplibregl.Popup({closeButton:false, closeOnClick:false, offset:8});
const hutPopup = new maplibregl.Popup({closeButton:true, closeOnClick:false, offset:12, maxWidth:_bigScr?'300px':'250px'});
let _hoverTimer=null, _hoverId=null;
// „?" = Bedienungshilfe; ⓘ (Title-Card) = „Über diese Karte". Schließen sich gegenseitig aus.
function toggleAbout(){ const c=document.getElementById('aboutCard'); if(c) c.classList.remove('open');
  document.getElementById('about').classList.toggle('open'); }
function toggleAboutCard(){ document.getElementById('about').classList.remove('open');
  document.getElementById('aboutCard').classList.toggle('open'); }
// ── Politur P1.2: Title-Card Mini-Zeile (Auto-Einklappen bei erster Karten-Interaktion) ──
function _fillTmKpi(){
  const el=document.getElementById('tmKpi'); if(!el) return;
  if(typeof PRIV!=='undefined' && PRIV){
    const ky=document.getElementById('kYears'); const yr=(ky&&ky.textContent&&ky.textContent!=='–')?' · '+ky.textContent:'';
    el.textContent = TOUREN.length+' Touren · '+SOIUSA_HIGHLIGHTS.features.length+' Gebiete'+yr;
  } else {
    el.textContent = __KPI_GRUPPEN__+' Gruppen · '+__KPI_SETTORI__+' Sektoren';
  }
}
function collapseTitle(persist){
  const t=document.getElementById('title'); if(!t) return;
  _fillTmKpi(); t.classList.add('mini');
  if(persist!==false){ try{ localStorage.setItem('alpen_title_mini','1'); }catch(_){} }
  if(typeof sizeCov==='function') sizeCov();   // P1.4: eingeklappte Card -> Touren-Panel rückt hoch
}
function expandTitle(){
  const t=document.getElementById('title'); if(!t) return;
  t.classList.remove('mini'); try{ localStorage.setItem('alpen_title_mini','0'); }catch(_){}
  if(typeof sizeCov==='function') sizeCov();
}
let _titleAuto=false, _titleChoice=null;
try{ _titleChoice=localStorage.getItem('alpen_title_mini'); }catch(_){}
// Abnahme-Befund 5: Auto-Kollaps feuert bei erster echter Interaktion, sofern die Card
// nicht schon eingeklappt ist. Der persistierte Wert steuert nur noch den STARTZUSTAND
// (mini bei '1') — er sperrt den Auto-Kollaps NICHT mehr dauerhaft (das war Michaels
// „greift nicht": ein altes '0' unter file:// deaktivierte ihn für immer).
function _autoCollapseTitle(){
  if(_titleAuto) return;
  const t=document.getElementById('title'); if(!t || t.classList.contains('mini')) return;
  _titleAuto=true; collapseTitle(true);
}
if(_titleChoice==='1'){ const _t=document.getElementById('title'); if(_t){ _fillTmKpi(); _t.classList.add('mini'); } }  // Restore ohne Re-Persist
// T4: Legende (Sektoren) auf-/zuklappen.
function toggleLegend(){ document.getElementById('legend').classList.toggle('open');
  if(typeof sizeCov==='function') sizeCov(); }   /* P1: Title-Höhe ändert sich -> #cov-Höhe neu messen */
// W1.3: Einheitliche Schließ-UX — alle schwarzen Popups (Gruppe/Hütte/Hover/Treffer/Tour).
function closeAllPopups(){
  try{ stsPopup.remove(); hutPopup.remove(); hoverPop.remove(); }catch(_){}
  document.querySelectorAll('.maplibregl-popup').forEach(el=>el.remove());   // Treffer-/Tour-Popups (nicht getrackt)
}
// Esc / Hintergrund: schließt zusätzlich „?"-Hilfe + Kartenquellen-ⓘ.
function closeAllOverlays(){
  closeAllPopups();
  const ab=document.getElementById('about'); if(ab) ab.classList.remove('open');
  const ac=document.getElementById('aboutCard'); if(ac) ac.classList.remove('open');
  _closeAttrib();
}
function showStsPopup(lngLat, props){
  hoverPop.remove();
  hutPopup.remove();   // Gruppen- und Hütten-Popup schließen sich gegenseitig aus
  const name = props.name_de || props.STS || '—';
  const sub  = props.visited!==1 && props.settore && props.settore!=='—'
    ? '<div class="sp-sub">'+props.settore+'</div>' : '';
  stsPopup.setLngLat(lngLat)
    .setHTML('<div class="sp-name">'+name+'</div>'+sub)
    .addTo(map);
}

map.on('load',()=>{
  map.setTerrain({source:'dem', exaggeration:1.0});
  updateSky();   // §3 (W4): Himmel/Dunst nur in 3D, Satellit, nicht auf Touch (Perf)

  // ── Sources ──────────────────────────────────────────────────────────────
  map.addSource('mask',       {type:'geojson', data:MASK});
  map.addSource('sts',        {type:'geojson', data:SOIUSA_STS, promoteId:'STS'});  // §4: feature-state hover
  map.addSource('highlights', {type:'geojson', data:SOIUSA_HIGHLIGHTS});
  map.addSource('sts-lp',    {type:'geojson', data:SOIUSA_LBL_PTS});
  /* PRIV:START */
  map.addSource('tours',     {type:'geojson', data:fc});
  map.addSource('tracks',    {type:'geojson', data: TRACKS || {type:'FeatureCollection',features:[]}});
  /* PRIV:END */
  // OSM overlays as URL sources (not inlined) — keeps index.html small.
  map.addSource('osm-peaks', {type:'geojson', data:OSM_PEAKS  || './soiusa_osm_peaks.geojson'});
  map.addSource('osm-huts',  {type:'geojson', data:OSM_HUTS   || './soiusa_osm_huts.geojson'});
  map.addSource('osm-passes',{type:'geojson', data:OSM_PASSES || './soiusa_osm_passes.geojson'});
  map.addSource('osm-places',{type:'geojson', data:OSM_PLACES || './soiusa_osm_places_v1.geojson'});     // Anreise: Orte (v1: nur city/town)
  map.addSource('osm-cable', {type:'geojson', data:OSM_CABLE  || './soiusa_osm_cableways.geojson'});   // Anreise: Seilbahn-Talstationen
  map.addSource('osm-cable-lines', {type:'geojson', data:OSM_CABLE_LINES || './soiusa_osm_cableways_lines.geojson'});  // W4: Seilbahn-Linien
  map.addSource('osm-chairlifts', {type:'geojson', data:OSM_CHAIRLIFTS || './soiusa_osm_chairlifts.geojson'});  // Sessellift-Linien (Standalone inline)

  // ── Non-Alpine mask — always on ───────────────────────────────────────────
  map.addLayer({id:'mask-fill', type:'fill', source:'mask',
    paint:{'fill-color':'#000816','fill-opacity':0.42}});
  map.addSource('borders', {type:'geojson', data:BORDERS_GJ || './soiusa_borders.geojson'});
  map.addLayer({id:'borders', type:'line', source:'borders',
    layout:{'visibility':'none','line-join':'round'},
    paint:{'line-color':'#e2ebf7','line-width':1.2,'line-opacity':0.6,'line-dasharray':[3,2]}});
  // Länder-Labels (im Landesteil, uppercase, zoom-gated, an den Grenzen-Toggle gekoppelt)
  map.addSource('country-labels', {type:'geojson', data:COUNTRY_LABELS});
  map.addLayer({id:'country-labels', type:'symbol', source:'country-labels', minzoom:7,
    layout:{'visibility':'none','text-field':['get','name'],'text-font':['Noto Sans Bold'],
      'text-size':['interpolate',['linear'],['zoom'], 7,11, 10,17],'text-letter-spacing':0.18,
      'text-transform':'uppercase','text-allow-overlap':false,'text-optional':true},
    paint:{'text-color':'#cdd9e8',
      'text-opacity':['step',['zoom'], ['case',['==',['get','iso'],'LI'],0,0.7], 9,0.7],
      'text-halo-color':'#06101a','text-halo-width':1.5}});

  // ── STS mosaic fill — toggle-controlled ──────────────────────────────────
  // 'coalesce' prevents MapLibre crash when fill_color is undefined on a feature.
  // Opacity higher for visited groups.
  map.addLayer({id:'sts-fill', type:'fill', source:'sts',
    paint:{
      'fill-color': ['coalesce',['get','fill_color'],'#888888'],
      // Settore-Fill als "Nebel": voll in der Übersicht, ab z10.5 stark ausdünnend,
      // ab z12 frei (freie Sicht aufs Gelände). Zoom MUSS top-level stehen.
      'fill-opacity': ['interpolate',['linear'],['zoom'], 8,0.34, 10.5,0.12, 12,0]
    }});

  // ── §4 (W4): Hover-Glow (feature-state, flackerfrei) — Kontur + leichte Aufhellung ──
  map.addLayer({id:'sts-hover-fill', type:'fill', source:'sts',
    paint:{'fill-color':'#ffffff',
      'fill-opacity':['case',['boolean',['feature-state','hover'],false], 0.07, 0]}});
  map.addLayer({id:'sts-hover-line', type:'line', source:'sts',
    layout:{'line-join':'round'},
    paint:{'line-color':'#ffffff','line-opacity':0.55,
      'line-width':['case',['boolean',['feature-state','hover'],false], 1.6, 0]}});

  // ── Fix9: unsichtbarer Hit-Layer — Klick/Hover funktionieren unabhaengig vom
  //    Faerbung-Toggle (sts-fill kann visibility:none sein). Immer sichtbar, ~transparent.
  map.addLayer({id:'sts-hit', type:'fill', source:'sts',
    paint:{'fill-color':'#000000','fill-opacity':0.001}});

  /* PRIV:START */
  // ── Chronologie-Füllungen (nur Privat): kumulativ gedimmt (≤ Jahr) + aktuelles
  //    Jahr kräftig. Filter werden je Jahr aus JS gesetzt; standardmäßig aus. ──
  map.addLayer({id:'chrono-past', type:'fill', source:'sts',
    filter:['in',['get','STS'],['literal',[]]],
    layout:{'visibility':'none'},
    paint:{'fill-color':'#ffb24d','fill-opacity':CHRONO_PAST_OP}});
  map.addLayer({id:'chrono-cur', type:'fill', source:'sts',
    filter:['in',['get','STS'],['literal',[]]],
    layout:{'visibility':'none'},
    paint:{'fill-color':'#ffb24d','fill-opacity':CHRONO_CUR_OP}});
  // W3 (§11): Mindestdarstellung — UNABHÄNGIG von Färbung/Namen zeigt die Chronik
  // immer (a) den orangefarbenen „besucht"-Außenrahmen der aktiven Gruppe und
  // (b) den fest verankerten Gebietsnamen. Filter je Jahr = aktuelle Gruppe(n).
  map.addLayer({id:'chrono-cur-line', type:'line', source:'sts',
    filter:['in',['get','STS'],['literal',[]]],
    layout:{'visibility':'none','line-join':'round','line-cap':'round'},
    paint:{'line-color':'#ffb24d','line-width':2.6,'line-opacity':0.95}});
  map.addLayer({id:'chrono-cur-name', type:'symbol', source:'sts-lp',
    filter:['in',['get','STS'],['literal',[]]],
    layout:{'visibility':'none',
      'text-field':['case',['!=',['coalesce',['get','name_de'],''],''],['get','name_de'],['get','STS']],
      'text-font':['Noto Sans Bold'],'text-size':['interpolate',['linear'],['zoom'], 6,13, 10,16],
      'text-allow-overlap':true,'text-ignore-placement':true},   // fest verankert (kein Kollisions-Drop)
    paint:{'text-color':'#ffd47a','text-halo-color':'#06101a','text-halo-width':2.0}});
  /* PRIV:END */

  // ── STS borders — toggle-controlled, only for non-visited (visited use hl-line) ──
  map.addLayer({id:'sts-line', type:'line', source:'sts',
    filter:['==',['get','visited'],0],
    layout:{'line-join':'round'},
    paint:{'line-color':'rgba(210,225,255,0.28)','line-width':0.7}});

  // ── Orange border for visited — always on ────────────────────────────────
  map.addLayer({id:'hl-line', type:'line', source:'highlights',
    layout:{'line-join':'round','line-cap':'round'},
    paint:{'line-color':'#ffb24d','line-width':3.0,'line-opacity':0.95}});

  // ── Group labels for non-visited — toggle + zoom-gated, off by default ──────
  // Source: sts-lp (one Point per STS) → one label per group, no per-tile duplicates.
  // text-field: German name (name_de) where available (AT/DE/Südtirol), else Italian STS name.
  map.addLayer({id:'sts-label', type:'symbol', source:'sts-lp', minzoom:6.5,
    filter:['==',['get','visited'],0],
    layout:{'visibility':'none',
      'text-field':['case',['!=',['coalesce',['get','name_de'],''],''],
        ['get','name_de'],['get','STS']],
      'text-font':['Noto Sans Bold'],
      'text-size':['interpolate',['linear'],['zoom'], 6.5,10, 9,13],
      // B4: Gruppennamen nehmen an der Kollision teil (kein allow-overlap) und weichen
      // per variable-anchor aus (statt Top-Gipfel-Labels zu ueberlagern, Repro A/B).
      'text-allow-overlap':false,'text-optional':false,'symbol-sort-key':0,
      'text-variable-anchor':['center','top','bottom','left','right'],'text-radial-offset':0.6},
    paint:{'text-color':'rgba(232,240,255,0.95)',
           'text-halo-color':'#06101a','text-halo-width':1.8,'text-halo-blur':0.2}});

  // ── German labels for visited — toggle-controlled, off by default ───────────
  // Font: 'Noto Sans Bold' — PBFs self-hosted under fonts/Noto Sans Bold/ (fetch_fonts.py).
  // Source: sts-lp → one label per visited group, no duplicates.
  map.addLayer({id:'sts-label-hl', type:'symbol', source:'sts-lp',
    filter:['==',['get','visited'],1],
    layout:{'visibility':'none',
      'text-field':['get','name_de'],'text-font':['Noto Sans Bold'],
      'text-size':13,'text-allow-overlap':false,'text-optional':false,'symbol-sort-key':0,
      'text-variable-anchor':['center','top','bottom','left','right'],'text-radial-offset':0.6},
    paint:{'text-color':'#ffd47a',
           'text-halo-color':'#06101a','text-halo-width':2.0,'text-halo-blur':0.2}});

  // ── OSM symbol icons (keyless canvas) ─────────────────────────────────────
  map.addImage('peak', makeIcon(22,(x,s)=>{           // black triangle, white outline
    x.beginPath(); x.moveTo(s*0.5,s*0.13); x.lineTo(s*0.9,s*0.85); x.lineTo(s*0.1,s*0.85); x.closePath();
    x.fillStyle='#0b0b0b'; x.fill(); x.lineWidth=1.7; x.strokeStyle='#ffffff'; x.lineJoin='round'; x.stroke();
  }), {pixelRatio:2});
  map.addImage('peak-hi', makeIcon(24,(x,s)=>{      // Länder-Höchste: gold-umrandetes Dreieck
    x.beginPath(); x.moveTo(s*0.5,s*0.1); x.lineTo(s*0.9,s*0.86); x.lineTo(s*0.1,s*0.86); x.closePath();
    x.fillStyle='#1a1400'; x.fill(); x.lineWidth=2.4; x.strokeStyle='#ffd24d'; x.lineJoin='round'; x.stroke();
  }), {pixelRatio:2});
  map.addImage('peak-star', makeStar('#ffcf3d'), {pixelRatio:2});     // Mont Blanc (Alpen-König)
  map.addImage('pass', makeIcon(18,(x,s)=>{         // Pass: liegende Raute
    x.beginPath(); x.moveTo(s*0.5,s*0.28); x.lineTo(s*0.78,s*0.5); x.lineTo(s*0.5,s*0.72); x.lineTo(s*0.22,s*0.5); x.closePath();
    x.fillStyle='#e8c766'; x.fill(); x.lineWidth=1.4; x.strokeStyle='#06101a'; x.lineJoin='round'; x.stroke();
  }), {pixelRatio:2});
  map.addImage('hut-club',  houseIcon('#e2574c'), {pixelRatio:2});   // Verbandshütte (Tier 1)
  map.addImage('hut-other', houseIcon('#9fb0c0'), {pixelRatio:2});   // sonstige bewirtschaftet
  map.addImage('hut-wild',  houseOutline('#a8bccc'), {pixelRatio:2}); // unbewirtschaftet/Refugio (Tier 2)
  map.addImage('gondola',   gondolaIcon(), {sdf:true, pixelRatio:2});  // Seilbahn-Logo (SDF, recolorbar)
  map.addImage('citysq',    citySquare(), {pixelRatio:2});            // Orte v2: K1 Großstadt-Quadrat
  if(PRIV) map.addImage('hiker', hikerIcon(), {sdf:true, pixelRatio:2});  // Tour-Marker v2 (SDF, recolorbar)

  // Peaks — black triangle, name+height label from higher zoom
  // Landmark-Glow (hinter den Gipfeln)
  map.addLayer({id:'osm-landmark-glow', type:'circle', source:'osm-peaks', minzoom:5,
    filter:['==',['get','landmark'],1],
    layout:{'visibility':'none'},
    paint:{'circle-radius':['interpolate',['linear'],['zoom'], 6,7, 12,16],
      'circle-color':'#ffd24d','circle-opacity':0.28,'circle-blur':0.9}});
  // ── Anreise: Orte v2 (Klassen nach EINWOHNERN, place-Typ nur Fallback) ──────
  // VOR den Gipfel-/Huetten-Layern einsortiert -> niedrigere Kollisions-Prioritaet.
  // Default aus (Toggle). K1 ≥100k = Quadrat (places-sq), K2 20–100k = großer Kreis,
  // K3 <20k / pop fehlt = kleiner Kreis (places-dot). Kein Rot. Labels staffeln mit.
  const _POP = ['coalesce',['get','pop'],0];   // fehlendes pop -> 0 -> K3
  // Orte in ATLAS-ROT (Kurator-Entscheid): K1 ≥100k = rotes Quadrat (places-sq),
  // K2 20–100k = roter Kreis, K3 <20k = kleiner heller Ring. Größe MONOTON über
  // alle Zooms: K1-Quadratkante > K2-Kreisdurchmesser > K3-Ringdurchmesser.
  map.addLayer({id:'places-dot', type:'circle', source:'osm-places', minzoom:6,
    filter:['all',['<',_POP,100000],['!=',['get','place'],'village']],   // v2: villages eigener Layer
    layout:{visibility:'none'},
    paint:{
      'circle-color':['case',['>=',_POP,20000],'#cc3322','rgba(0,0,0,0)'],       // K2 rot, K3 Ring (kein Fill)
      'circle-stroke-color':['case',['>=',_POP,20000],'#3a0f08','#f2e3c0'],      // K2 dunkler Rand, K3 helle Kontur
      'circle-stroke-width':['case',['>=',_POP,20000],1,1.3],
      'circle-radius':['interpolate',['linear'],['zoom'],
        6, ['case',['>=',_POP,20000],3.5,2.5],     // K2 Ø7 · K3 Ø5
        9, ['case',['>=',_POP,20000],4.5,3.0],     // K2 Ø9 · K3 Ø6
        12,['case',['>=',_POP,20000],6.0,4.0]]}}); // K2 Ø12 · K3 Ø8
  // K1 Großstadt: rotes Quadrat mit heller Kontur + dunklem Kern (ECKIG = städtisch).
  // icon-size so gewählt, dass die Quadratkante über alle Zooms > K2-Ø bleibt
  // (citysq: Quadrat ~0,76·20 px Canvas, pixelRatio 2 -> ~7,6 px/Größeneinheit).
  map.addLayer({id:'places-sq', type:'symbol', source:'osm-places', minzoom:6,
    filter:['all',['>=',_POP,100000],['!=',['get','place'],'village']],
    layout:{visibility:'none','icon-image':'citysq','icon-allow-overlap':true,'icon-ignore-placement':true,
      'icon-size':['interpolate',['linear'],['zoom'], 6,1.4, 9,1.8, 12,2.3]}});  // Kante ~10,6 / 13,7 / 17,5 px
  map.addLayer({id:'places-label', type:'symbol', source:'osm-places', minzoom:6,
    filter:['!=',['get','place'],'village'],
    layout:{visibility:'none',
      // Sichtbarkeit gestaffelt: K1 ab z6, K2 ab z7.5, K3 ab z9 (entzerrt die Dichte).
      'text-field':['step',['zoom'],
        ['case',['>=',_POP,100000],['get','name'],''],
        7.5,['case',['>=',_POP,20000],['get','name'],''],
        9, ['get','name']],
      'text-font':['Noto Sans Bold'],
      // Label-Größen nach Klasse staffeln (K1 größtes Label).
      'text-size':['interpolate',['linear'],['zoom'],
        6, ['case',['>=',_POP,100000],13,['>=',_POP,20000],11,9.5],
        12,['case',['>=',_POP,100000],16.5,['>=',_POP,20000],13.5,12]],
      'text-variable-anchor':['left','right','top','bottom'],'text-radial-offset':0.85,
      'text-optional':true,'text-allow-overlap':false,'symbol-sort-key':['*',-1,_POP]},   // große Städte zuerst
    paint:{'text-color':'#f2e3c0','text-halo-color':'#1a1206','text-halo-width':1.4}});
  // Orte v2: villages (Talorte) — kleinste Klasse, erst ab z>=10, kleiner Ring + gedämpftes
  // Label (heller als Karte, aber dunkler als town). In PRIO unter town einsortiert.
  map.addLayer({id:'places-village', type:'circle', source:'osm-places', minzoom:10,
    filter:['==',['get','place'],'village'], layout:{visibility:'none'},
    paint:{'circle-radius':['interpolate',['linear'],['zoom'], 10,2.0, 13,3.0],
      'circle-color':'rgba(0,0,0,0)','circle-stroke-color':'#e6d2a8','circle-stroke-width':1.1}});
  map.addLayer({id:'places-village-label', type:'symbol', source:'osm-places', minzoom:10.5,
    filter:['==',['get','place'],'village'],
    layout:{visibility:'none','text-field':['get','name'],'text-font':['Noto Sans Bold'],
      'text-size':['interpolate',['linear'],['zoom'], 10.5,9.5+LB, 13,11.5+LB],
      'text-variable-anchor':['left','right','top','bottom'],'text-radial-offset':0.7,
      'text-optional':true,'text-allow-overlap':false,'symbol-sort-key':['*',-1,_POP]},
    paint:{'text-color':'#d8c8a0','text-halo-color':'#1a1206','text-halo-width':1.2}});
  // Sessellift-LINIEN (chair_lift), minzoom 11 — N4: kräftiger/dunkler + Querstrich-Signatur
  // (klassische Lift-Konvention statt der zu dezenten Haarlinie). ZUERST hinzugefügt ->
  // zeichnet UNTER den Gondelbahn-Linien (Kollisions-/PRIO-Vorrang Gondel).
  map.addLayer({id:'chairlift-line', type:'line', source:'osm-chairlifts', minzoom:11,
    layout:{visibility:'none','line-join':'round','line-cap':'round'},
    paint:{'line-color':'#3f4a56','line-width':1.3,'line-opacity':0.9}});
  // Querstriche = senkrechte Ticks entlang der Linie (Symbol mit line-Placement, 90° gedreht).
  map.addLayer({id:'chairlift-ticks', type:'symbol', source:'osm-chairlifts', minzoom:12,
    layout:{visibility:'none','symbol-placement':'line','symbol-spacing':13,
      'text-field':'|','text-font':['Noto Sans Bold'],'text-size':11,
      'text-rotate':90,'text-keep-upright':false,'text-rotation-alignment':'map',
      'text-allow-overlap':true,'text-ignore-placement':true},
    paint:{'text-color':'#3f4a56','text-opacity':0.9}});
  // W4: Seilbahn-LINIEN (voller Verlauf Tal->Berg) — dunkle Linie mit hellem Halo,
  // dünn/dezent, Zoom-Gate z≥10; am bestehenden Seilbahnen-Toggle. Vor dem Logo.
  map.addLayer({id:'cable-line-halo', type:'line', source:'osm-cable-lines', minzoom:10,
    layout:{visibility:'none','line-join':'round','line-cap':'round'},
    paint:{'line-color':'#eaf1f5','line-width':3.0,'line-opacity':0.45}});
  map.addLayer({id:'cable-line', type:'line', source:'osm-cable-lines', minzoom:10,
    layout:{visibility:'none','line-join':'round','line-cap':'round'},
    paint:{'line-color':'#161b22','line-width':1.5,'line-opacity':0.9,
      'line-dasharray':[2,1.6]}});   // Kabelsignatur (Dash-Näherung)
  map.addLayer({id:'cable-icon', type:'symbol', source:'osm-cable', minzoom:10,
    layout:{visibility:'none','icon-image':'gondola','icon-size':1.4,'icon-allow-overlap':false,
      'text-field':['step',['zoom'], '', 12, ['get','name']],
      'text-font':['Noto Sans Bold'],'text-size':9.5,
      'text-variable-anchor':['top','bottom','left','right'],'text-radial-offset':0.6,
      'text-optional':true,'text-allow-overlap':false},
    paint:{'icon-color':'#e2f2f7','icon-halo-color':'#06141a','icon-halo-width':1.8,
      'text-color':'#bfe6ee','text-halo-color':'#06141a','text-halo-width':1.3}});

  // §11-Fix: Bulk-Gipfel (tier>=2) — die unsichtbaren tier-4-Icons (icon-opacity 0)
  // belegen Kollisionsraum und verdrängten bisher die Gold-Gipfel. Gold (tier<=1) liegt
  // deshalb in EIGENEM Layer (osm-peaks-gold) mit icon-allow-overlap -> immer sichtbar.
  map.addLayer({id:'osm-peaks', type:'symbol', source:'osm-peaks', minzoom:5,
    filter:['all',['!=',['get','landmark'],1],['>=',['get','tier'],2]],
    layout:{'visibility':'none','icon-anchor':'bottom','icon-allow-overlap':false,
      // Tier 0 = Mont Blanc (Stern), 1 = Länder-Höchste (Gold-Dreieck), 2-4 = Höhenbänder.
      'icon-image':['match',['get','tier'], 0,'peak-star', 1,'peak-hi', 'peak'],
      'icon-size':['match',['get','tier'], 0,1.9, 1,1.35, 2,1.05, 3,0.82, 0.62],
      // P3: Rang = tier + ele. Labels tier-gestaffelt bis z11; das riesige tier-4-Band
      // (2000er) ab z12 zusätzlich nach ele ausgedünnt (>=2600), ab z13 vollständig.
      'text-field':['step',['zoom'],
        ['case',['==',['get','tier'],0],['concat',['get','name'],'\n',['to-string',['get','ele']],' m'],''],
        8, ['case',['<=',['get','tier'],1],['concat',['get','name'],'\n',['to-string',['get','ele']],' m'],''],
        10,['case',['<=',['get','tier'],2],['concat',['get','name'],'\n',['to-string',['get','ele']],' m'],''],
        11,['case',['<=',['get','tier'],3],['concat',['get','name'],'\n',['to-string',['get','ele']],' m'],''],
        12,['case',['<=',['get','tier'],3],['concat',['get','name'],'\n',['to-string',['get','ele']],' m'],
           ['case',['>=',['get','ele'],2600],['concat',['get','name'],'\n',['to-string',['get','ele']],' m'],'']],
        13,['concat',['get','name'],'\n',['to-string',['get','ele']],' m']],
      'text-font':['Noto Sans Bold'],'text-size':['match',['get','tier'], 0,12+LB, 1,11+LB, 9.5+LB],
      'symbol-sort-key':['get','tier'],   // wichtige Gipfel zuerst platziert; < Pässe (80/90) -> Gipfel gewinnen
      // Punkt 2a: Gipfel-Label weicht per variable-anchor aus (oben/unten/seitlich) statt den
      // Gruppennamen zu verdraengen -> Name + „sein" Gipfel koexistieren.
      'text-variable-anchor':['top','bottom','left','right'],'text-radial-offset':0.5,
      'text-optional':true,'text-allow-overlap':false},
    paint:{'text-color':['match',['get','tier'], 0,'#ffe08a', 1,'#ffd24d', '#dbe7ff'],
      'text-halo-color':'#06101a','text-halo-width':1.4,
      // Icon-Sichtbarkeit: Tier0-2 früh, 3000er ab z8; tier-4 (2000er) nach ele gerampt
      // (z11 >=2600, z12 >=2300, z13 alle) -> ruhige Übersicht, volle Dichte im Detail.
      'icon-opacity':['step',['zoom'],
        ['case',['<=',['get','tier'],2],1,0],
        8,  ['case',['<=',['get','tier'],3],1,0],
        11, ['case',['<=',['get','tier'],3],1,['case',['>=',['get','ele'],2600],1,0]],
        12, ['case',['<=',['get','tier'],3],1,['case',['>=',['get','ele'],2300],1,0]],
        13, 1]}});

  // §11-Fix: Gold-Gipfel (tier 0 Stern / tier 1 Länder-Höchste) in EIGENEM Layer mit
  // icon-allow-overlap+ignore-placement -> Icon IMMER sichtbar (Vorrang vor Bulk-Dreiecken,
  // auf allen Zoomstufen). Label bleibt text-optional -> weicht Gruppennamen (unter ihnen).
  map.addLayer({id:'osm-peaks-gold', type:'symbol', source:'osm-peaks', minzoom:5,
    filter:['all',['!=',['get','landmark'],1],['<=',['get','tier'],1]],
    layout:{'visibility':'none','icon-anchor':'bottom','icon-allow-overlap':true,'icon-ignore-placement':true,
      'icon-image':['match',['get','tier'], 0,'peak-star', 'peak-hi'],
      'icon-size':['match',['get','tier'], 0,1.9, 1.35],
      'text-field':['concat',['get','name'],'\n',['to-string',['get','ele']],' m'],
      'text-font':['Noto Sans Bold'],'text-size':['match',['get','tier'], 0,12+LB, 11+LB],
      'symbol-sort-key':['get','tier'],
      'text-variable-anchor':['top','bottom','left','right'],'text-radial-offset':0.6,
      'text-optional':true,'text-allow-overlap':false},
    paint:{'text-color':['match',['get','tier'], 0,'#ffe08a', '#ffd24d'],
      'text-halo-color':'#06101a','text-halo-width':1.5}});

  // Landmark-Gipfel: eigener Rang — Icon nach Tier, Label immer, ab Übersicht sichtbar.
  map.addLayer({id:'osm-landmarks', type:'symbol', source:'osm-peaks', minzoom:5,
    filter:['all',['==',['get','landmark'],1],['!=',['get','land_high'],1]],   // die 6 Landeshöchsten -> osm-landhigh
    layout:{'visibility':'none','icon-anchor':'bottom','icon-allow-overlap':true,
      'icon-image':['match',['get','tier'], 0,'peak-star', 1,'peak-hi', 'peak'],
      'icon-size':['match',['get','tier'], 0,1.95, 1,1.4, 1.15],
      'text-field':['concat',['get','name'],'\n',['to-string',['get','ele']],' m'],
      'text-font':['Noto Sans Bold'],'text-size':11,'text-offset':[0,0.3],
      'text-anchor':'top','text-optional':true,'text-allow-overlap':false},
    paint:{'text-color':'#ffe6a0','text-halo-color':'#06101a','text-halo-width':1.8}});
  // Politur P2.6: Landmark-Gipfel-Tier — die 6 Landeshöchsten (land_high), ab Übersichtszoom
  // IMMER beschriftet (icon+text allow-overlap wie Gold-Fix), in PRIO UNTER den Gruppennamen.
  // Immer sichtbar (Orientierungsanker, unabhängig vom Gipfel-Toggle). Beide Builds.
  map.addLayer({id:'osm-landhigh', type:'symbol', source:'osm-peaks', minzoom:5,
    filter:['==',['get','land_high'],1],
    layout:{'icon-anchor':'bottom','icon-allow-overlap':true,'icon-ignore-placement':true,
      'icon-image':['match',['get','tier'], 0,'peak-star', 'peak-hi'],
      'icon-size':['match',['get','tier'], 0,1.95, 1.4],
      'text-field':['concat',['get','name'],'\n',['to-string',['get','ele']],' m'],
      'text-font':['Noto Sans Bold'],'text-size':11.5+LB,'text-offset':[0,0.35],
      'text-anchor':'top','text-allow-overlap':true},
    paint:{'text-color':'#ffe6a0','text-halo-color':'#06101a','text-halo-width':2.0}});

  // Huts — sonstige (grau, ab höherem Zoom)
  map.addLayer({id:'osm-huts-other', type:'symbol', source:'osm-huts', minzoom:8,
    filter:['==',['get','kat'],'hut'],
    layout:{'visibility':'none','icon-image':'hut-other','icon-anchor':'bottom','icon-allow-overlap':false,
      'icon-size':['interpolate',['linear'],['zoom'], 9,0.7, 12,1.0],
      'text-field':['step',['zoom'], '', 10.5, ['get','name']],'text-font':['Noto Sans Bold'],
      'text-size':9+LB,'text-offset':[0,0.4],'text-anchor':'top','text-optional':true,'text-allow-overlap':false},
    paint:{'text-color':'#cdd6e0','text-halo-color':'#06101a','text-halo-width':1.3}});

  // Huts — unbewirtschaftet/Refugio/Biwak (hohles Icon, nur hoher Zoom)
  map.addLayer({id:'osm-huts-wild', type:'symbol', source:'osm-huts', minzoom:10.5,
    filter:['==',['get','kat'],'wild'],
    layout:{'visibility':'none','icon-image':'hut-wild','icon-anchor':'bottom','icon-allow-overlap':false,
      'icon-size':['interpolate',['linear'],['zoom'], 10.5,0.65, 13,0.95],
      'text-field':['step',['zoom'], '', 12, ['get','name']],'text-font':['Noto Sans Bold'],
      'text-size':8.5+LB,'text-offset':[0,0.4],'text-anchor':'top','text-optional':true,'text-allow-overlap':false},
    paint:{'text-color':'#aebccb','text-halo-color':'#06101a','text-halo-width':1.2}});

  // Huts — Alpenverein/Club (rot, kräftiger, ab niedrigerem Zoom)
  map.addLayer({id:'osm-huts-club', type:'symbol', source:'osm-huts', minzoom:7.5,
    filter:['==',['get','kat'],'club'],
    layout:{'visibility':'none','icon-image':'hut-club','icon-anchor':'bottom','icon-allow-overlap':false,
      'icon-size':['interpolate',['linear'],['zoom'], 7.5,0.8, 12,1.15],
      'text-field':['step',['zoom'], '', 9, ['get','name']],'text-font':['Noto Sans Bold'],
      'text-size':9.5+LB,'text-offset':[0,0.4],'text-anchor':'top','text-optional':true,'text-allow-overlap':false},
    paint:{'text-color':'#ffcabf','text-halo-color':'#06101a','text-halo-width':1.4}});

  // ── Hütten-Klick → Enrichment-Popup (alle kat) ────────────────────────────
  const HUT_LAYERS = ['osm-huts-club','osm-huts-other','osm-huts-wild'];
  HUT_LAYERS.forEach(l=>{
    map.on('mouseenter',l,()=>map.getCanvas().style.cursor='pointer');
    map.on('mouseleave',l,()=>map.getCanvas().style.cursor='');
    map.on('click',l,e=>{
      const f=e.features[0];
      stsPopup.remove();
      hutPopup.setLngLat(f.geometry.coordinates.slice())
        .setHTML(hutPopupHtml(f.properties||{})).addTo(map);
    });
  });

  // ── §7 (W4): Cursor-Pointer auf allen klickbaren Punkt-Layern (Desktop) ────
  ['osm-peaks','osm-peaks-gold','osm-landmarks','osm-landhigh','osm-passes','osm-passes-famous','places-sq','places-dot','places-label','places-village','places-village-label','cable-icon'].forEach(l=>{
    map.on('mouseenter',l,()=>map.getCanvas().style.cursor='pointer');
    map.on('mouseleave',l,()=>map.getCanvas().style.cursor='');
  });

  // ── T3 (Kurator 03.07.): Cursor-Feedback beim Drehen/Neigen/Zoomen ─────────
  // Rechtsklick-Drag horizontal-dominant = Drehen -> 'grabbing'; vertikal-dominant =
  // Neigen -> 'nesw-resize'. Mausrad -> kurz 'zoom-in'/'zoom-out'. Nur Desktop
  // (pointer:fine); Touch/Stift unberührt. Setzt den Canvas-Cursor direkt (MapLibre-
  // eigene Cursor sind hier unauffällig). Layer-Hover-'pointer' (§7) bleibt erhalten,
  // da Rechtsklick-Drag und Hover sich nicht überschneiden.
  if(window.matchMedia && window.matchMedia('(pointer: fine)').matches){
    const _cv = map.getCanvas();
    let _rbtn=false, _sx=0, _sy=0, _zt=null;
    _cv.addEventListener('mousedown', e=>{ if(e.button===2){ _rbtn=true; _sx=e.clientX; _sy=e.clientY; _cv.style.cursor='grabbing'; } });
    window.addEventListener('mousemove', e=>{
      if(!_rbtn) return;
      const dx=Math.abs(e.clientX-_sx), dy=Math.abs(e.clientY-_sy);
      _cv.style.cursor = (dx>=dy) ? 'grabbing' : 'nesw-resize';   // Drehen bzw. Neigen
    });
    const _endRot = e=>{ if(_rbtn){ _rbtn=false; _cv.style.cursor=''; } };
    window.addEventListener('mouseup', _endRot);
    window.addEventListener('blur', _endRot);   // Sicherheitsnetz: Fenster verliert Fokus mitten im Drag
    _cv.addEventListener('wheel', e=>{
      if(_rbtn) return;                          // während Drehen/Neigen kein Zoom-Cursor
      _cv.style.cursor = e.deltaY<0 ? 'zoom-in' : 'zoom-out';
      clearTimeout(_zt); _zt=setTimeout(()=>{ if(!_rbtn) _cv.style.cursor=''; }, 260);
    }, {passive:true});
  }
  // Anreise: Klick-Popups (Ort = Name/Typ/Höhe/Einwohner; Seilbahn = Name + Tal->Berg).
  ['places-sq','places-dot','places-label','places-village','places-village-label'].forEach(l=>map.on('click',l,e=>{
    stsPopup.remove();
    hutPopup.setLngLat(e.features[0].geometry.coordinates.slice())
      .setHTML(placePopupHtml(e.features[0].properties||{})).addTo(map);
  }));
  map.on('click','cable-icon',e=>{
    stsPopup.remove();
    hutPopup.setLngLat(e.features[0].geometry.coordinates.slice())
      .setHTML(cablePopupHtml(e.features[0].properties||{})).addTo(map);
  });

  // ── Pässe (toggle): Sattel-Signatur „)(" ab z10; Name+Höhe ab ~z11 dazu ──────
  // Kein Sprite (text-Symbol). Hoher symbol-sort-key -> Pässe weichen Gipfeln/Hütten
  // (Kollision), verdrängen also nie Gipfelnamen. In der Übersicht (<z10) unsichtbar.
  // Typ-konsistenter String-Ausdruck (kein format): unter zGate nur „)(", ab zGate
  // „)(" + Name (+ Höhe, falls vorhanden) auf zweiter Zeile.
  const PASS_LABEL = zGate => ['step',['zoom'],
    ')(',
    zGate, ['concat', ')(\n', ['coalesce',['get','name'],''],
      ['case',['has','ele'], ['concat',' ',['to-string',['get','ele']],' m'], '']]];
  map.addLayer({id:'osm-passes', type:'symbol', source:'osm-passes', minzoom:10,
    filter:['==',['get','famous'],0],
    layout:{'visibility':'none','text-font':['Noto Sans Bold'],'text-size':12,
      'text-anchor':'center','text-allow-overlap':false,'text-optional':true,'symbol-sort-key':90,
      'text-field':PASS_LABEL(11)},
    paint:{'text-color':'#dbe3ee','text-halo-color':'#06101a','text-halo-width':1.3}});
  map.addLayer({id:'osm-passes-famous', type:'symbol', source:'osm-passes', minzoom:10,
    filter:['==',['get','famous'],1],
    layout:{'visibility':'none','text-font':['Noto Sans Bold'],'text-size':13,
      'text-anchor':'center','text-allow-overlap':false,'text-optional':true,'symbol-sort-key':80,
      'text-field':PASS_LABEL(10.5)},
    paint:{'text-color':'#eaf0f8','text-halo-color':'#06101a','text-halo-width':1.5}});

  // ── Peaks of the clicked group (within-filter, reuse peak icon) ────────────
  map.addLayer({id:'peaks-in-group', type:'symbol', source:'osm-peaks', minzoom:5,
    filter:['==',['get','name'],'__none__'],
    layout:{'visibility':'none','icon-image':'peak','icon-anchor':'bottom','icon-allow-overlap':false,
      'icon-size':['match',['get','tier'], 1,1.2, 2,1.0, 3,0.82, 0.64],
      'symbol-sort-key':['get','tier'],   // Top-Gipfel zuerst platziert
      // Fix3: Icon UND Label konsistent gegated (keine nackten Dreiecke ohne Namen),
      // Top-N nach Zoom wie beim Basis-Layer: z<10 tier<=1, z10 tier<=2, z12 tier<=3, z13 alle.
      'text-field':['step',['zoom'],
        ['case',['<=',['get','tier'],1],['concat',['get','name'],'\n',['to-string',['get','ele']],' m'],''],
        10,['case',['<=',['get','tier'],2],['concat',['get','name'],'\n',['to-string',['get','ele']],' m'],''],
        12,['case',['<=',['get','tier'],3],['concat',['get','name'],'\n',['to-string',['get','ele']],' m'],''],
        13,['concat',['get','name'],'\n',['to-string',['get','ele']],' m']],
      'text-font':['Noto Sans Bold'],'text-size':9.5,
      'text-variable-anchor':['top','bottom','left','right'],'text-radial-offset':0.5,  // Punkt 2a
      'text-optional':true,'text-allow-overlap':false},
    paint:{'text-color':'#eaf1ff','text-halo-color':'#06101a','text-halo-width':1.5,
      'icon-opacity':['step',['zoom'],
        ['case',['<=',['get','tier'],1],1,0],
        10,['case',['<=',['get','tier'],2],1,0],
        12,['case',['<=',['get','tier'],3],1,0],
        13,1]}});
  // Highlight: the group's highest peak (bigger triangle + bold gold label)
  map.addLayer({id:'peaks-highest', type:'symbol', source:'osm-peaks',
    filter:['==',['get','name'],'__none__'],
    layout:{'visibility':'none','icon-image':'peak','icon-anchor':'bottom','icon-allow-overlap':true,'icon-size':1.5,
      'text-field':['concat',['get','name'],'  ',['to-string',['get','ele']],' m'],
      'text-font':['Noto Sans Bold'],'text-size':12,'text-offset':[0,0.5],
      'text-anchor':'top','text-allow-overlap':true},
    paint:{'text-color':'#ffd47a','text-halo-color':'#06101a','text-halo-width':2}});

  // (Punkt 2b — Einzel-Fix der sts-label-Reihenfolge — ersetzt durch die globale
  //  Kollisions-Prioritätsliste weiter unten, W8.3/Review-#2.)

  // ── Selection ring — filter-driven, initially empty ───────────────────────
  map.addLayer({id:'sts-selected', type:'line', source:'sts',
    filter:['==',['get','STS'],''],
    layout:{'line-join':'round'},
    paint:{'line-color':'#ffffff','line-width':3.2,'line-opacity':0.95}});

  /* PRIV:START */
  // ── Touren-Tracks (rekonstruierte GPX-Linien, unter Markern & Labels) ──────
  // Weisse Casing-Linie fuer Lesbarkeit auf Satellit, darueber Besucht-Orange
  // (Konvention t-dot verifiziert #d9640f). Toggle "Touren-Tracks" default AN.
  map.addLayer({id:'trk-casing', type:'line', source:'tracks',
    layout:{'line-cap':'round','line-join':'round'},
    paint:{'line-color':'#ffffff',
           'line-width':['interpolate',['linear'],['zoom'], 7,2.6, 11,5.0, 14,7.0],
           'line-opacity':0.55}});
  map.addLayer({id:'trk-line', type:'line', source:'tracks',
    layout:{'line-cap':'round','line-join':'round'},
    paint:{'line-color':'#d9640f',
           'line-width':['interpolate',['linear'],['zoom'], 7,1.6, 11,3.0, 14,4.2],
           'line-opacity':0.95}});
  // P3b §9: breite unsichtbare Hit-Linie fuer Track-Klick (großzügig, Tablet-tauglich).
  map.addLayer({id:'trk-hit', type:'line', source:'tracks',
    layout:{'line-cap':'round','line-join':'round'},
    paint:{'line-color':'#000','line-width':18,'line-opacity':0.01}});
  map.on('mouseenter','trk-hit',()=>{ map.getCanvas().style.cursor='pointer'; });
  map.on('mouseleave','trk-hit',()=>{ map.getCanvas().style.cursor=''; });
  map.on('click','trk-hit',e=>{ const id=e.features[0].properties.tour_id; if(id!=null) openTourRow(+id); });
  // Aktive Tour hervorheben (openTour); null = alle gleich.
  function highlightTrack(id){
    try{
      // id==null: Basis-Deckkraft — respektiert einen aktiven Personen-/Strang-Filter
      // (_trackBaseOpacity), sonst voll. So bleibt der Filter-Dim nach Panel-Schliessen erhalten.
      map.setPaintProperty('trk-line','line-opacity',
        id==null ? _trackBaseOpacity('line') : ['case',['==',['get','tour_id'],id], 1.0, 0.25]);
      map.setPaintProperty('trk-casing','line-opacity',
        id==null ? _trackBaseOpacity('casing') : ['case',['==',['get','tour_id'],id], 0.7, 0.15]);
    }catch(_){}
  }
  window.highlightTrack = highlightTrack;

  // ── Tour markers v2b (privat, Eskalation 2): POI-Pin-Charakter ─────
  // Weiche Glow-Scheibe (t-halo) · KRÄFTIGE helle Badge-Scheibe (t-badge, POI-
  // Rückgrund) · unsichtbarer Hit-Kreis (t-hit, ≥40 px) · großer SDF-Wanderer
  // (t-dot, ~2–2,5×) oben. Ziel: auf Satellit-z8 sofort als Symbol erkennbar.
  // P2.7: Multi-Gebiets-Touren werden bei z<9 per setFilter ausgeblendet (Cluster übernimmt);
  // Gate zusammen mit dem F-Filter in _markerFilter (setFilter, kein zoom-Ausdruck in der Größe).
  map.addLayer({id:'t-halo', type:'circle', source:'tours',
    paint:{'circle-radius':['interpolate',['linear'],['zoom'], 5,15, 9,20, 13,26],
           'circle-color':'#ffb24d','circle-opacity':0.20,'circle-blur':0.5}});
  map.addLayer({id:'t-badge', type:'circle', source:'tours',     // helle POI-Scheibe hinter dem Wanderer
    paint:{'circle-radius':['interpolate',['linear'],['zoom'], 5,11, 8,13, 12,17],
      'circle-color':'#fff4e0','circle-opacity':0.96,
      'circle-stroke-color':['case',['==',['get','verifiziert'],1],'#c76a1a','#2c8f86'],
      'circle-stroke-width':2}});
  map.addLayer({id:'t-hit', type:'circle', source:'tours',       // ≥40 px Hit-Area, unsichtbar
    paint:{'circle-radius':22,'circle-color':'#000','circle-opacity':0.01}});
  map.addLayer({id:'t-dot', type:'symbol', source:'tours',
    layout:{'icon-image':'hiker','icon-allow-overlap':true,'icon-ignore-placement':true,
      'icon-size':['interpolate',['linear'],['zoom'], 5,1.5, 9,2.0, 13,2.6]},   // ~2–2,5× (war 0,72–1,3)
    paint:{'icon-color':['case',['==',['get','verifiziert'],1],'#d9640f','#1f7d74'],  // kräftig auf heller Scheibe
      'icon-halo-color':'rgba(40,20,5,0.35)','icon-halo-width':1.0}});
  // P3b §8: Jahr-Label am Wanderer-Icon ab z>=9 (eigener Layer -> in PRIO UNTER die Gruppennamen).
  map.addLayer({id:'t-label', type:'symbol', source:'tours', minzoom:9,
    layout:{'text-field':['to-string',['get','jahr']],'text-font':['Noto Sans Bold'],'text-size':10.5,
      'text-offset':[0,1.5],'text-anchor':'top','text-optional':true,'text-allow-overlap':false},
    paint:{'text-color':'#ffcf94','text-halo-color':'#06101a','text-halo-width':1.6}});
  // P2.7: Cluster-Icon je Multi-Gebiet — NUR z<9 (maxzoom 9), EIN Wanderer + Zähler-Badge.
  map.addSource('clusters', {type:'geojson', data:clusterFC});
  map.addLayer({id:'t-cluster-halo', type:'circle', source:'clusters', maxzoom:9,
    paint:{'circle-radius':23,'circle-color':'#ffb24d','circle-opacity':0.22,'circle-blur':0.5}});
  map.addLayer({id:'t-cluster-badge', type:'circle', source:'clusters', maxzoom:9,
    paint:{'circle-radius':15,'circle-color':'#fff4e0','circle-opacity':0.97,'circle-stroke-color':'#c76a1a','circle-stroke-width':2}});
  map.addLayer({id:'t-cluster-icon', type:'symbol', source:'clusters', maxzoom:9,
    layout:{'icon-image':'hiker','icon-allow-overlap':true,'icon-ignore-placement':true,'icon-size':1.55},
    paint:{'icon-color':'#d9640f','icon-halo-color':'rgba(40,20,5,0.35)','icon-halo-width':1.0}});
  map.addLayer({id:'t-cluster-count', type:'symbol', source:'clusters', maxzoom:9,
    layout:{'text-field':['to-string',['get','count']],'text-font':['Noto Sans Bold'],'text-size':12.5,
      'text-offset':[1.25,-1.15],'text-allow-overlap':true,'text-ignore-placement':true},
    paint:{'text-color':'#ffffff','text-halo-color':'#a5480d','text-halo-width':2.2}});
  map.on('mouseenter','t-cluster-halo',()=>{ map.getCanvas().style.cursor='pointer'; });
  map.on('mouseleave','t-cluster-halo',()=>{ map.getCanvas().style.cursor=''; });
  map.on('click','t-cluster-halo',e=>{ const sts=e.features[0].properties.sts;
    const f=SOIUSA_STS.features.find(x=>x.properties.STS===sts); if(f){ _pendingTour=null; openSts(f); showTab('tour'); } });
  const pop = new maplibregl.Popup({closeButton:false,closeOnClick:false,offset:12});
  map.on('mouseenter','t-hit',e=>{
    map.getCanvas().style.cursor='pointer';
    const p=e.features[0].properties;
    pop.setLngLat(e.features[0].geometry.coordinates)
       .setHTML('<b>'+p.gebirge+'</b> · '+p.jahr).addTo(map);
  });
  map.on('mouseleave','t-hit',()=>{map.getCanvas().style.cursor='';pop.remove();});
  map.on('click','t-hit',e=>openTour(e.features[0].properties.id));
  // P3a: Layer stehen jetzt -> restaurierten Filter F auf die Karte anwenden (Icons/Tracks/Kontur).
  try{ _applyMapFilter(matchedTours().map(t=>t.id), filterActive()); }catch(_){}
  /* PRIV:END */

  // ── W8.3 / Review-#2: EINE globale Kollisions-Prioritätsliste über alle Symbol-Layer ──
  // MapLibre platziert Labels TOP-DOWN: der oberste Layer gewinnt die Kollision
  // (hier empirisch verifiziert). Statt verstreuter Einzel-Fixes ordnen wir die
  // Label-Layer EINMALIG von höchster zu niedrigster Priorität. Der bestehende
  // symbol-sort-key je Layer (Tier/Einwohner) bleibt für die Feinordnung INNERHALB
  // eines Layers erhalten (z. B. Top-Gipfel vor 2000ern, Großstadt vor Kleinstadt).
  // Zielordnung:  Gruppenname > Gipfel-Top > Orte K1 > Hütten > Pässe > Rest.
  // (B4-Koexistenz bleibt: Gruppenname UND Gipfel behalten variable-anchor, weichen
  //  also weiter aus; die Priorität entscheidet nur den harten Gleichstand.)
  (function(){
    const PRIO = [
      'sts-label','sts-label-hl',                        // 1 Gruppenname (höchste)
      'osm-landhigh',                                    //   Landeshöchste (P2.6, immer, unter Namen)
      't-label',                                         //   Jahr-Label am Tour-Icon (P3b §8, unter Namen)
      'peaks-highest','peaks-in-group',                  // 2 Gruppen-Gipfel (Gold-Highlight)
      'osm-peaks-gold','osm-peaks',                      //   Gold-Gipfel VOR Bulk (§11-Fix)
      'places-label','places-village-label',             // 3 Orte K1>K2>K3>village (via sort-key/minzoom)
      'osm-huts-club','osm-huts-wild','osm-huts-other',  // 4 Hütten
      'osm-passes-famous','osm-passes',                  // 5 Pässe
      'osm-landmarks','cable-icon','country-labels'      // 6 Rest (niedrigste)
    ];
    // Tour-Marker (privat) bleiben ganz oben -> Gruppennamen dahängen sich darunter ein.
    let anchor = map.getLayer('t-halo') ? 't-halo' : undefined;
    for(const id of PRIO){
      if(!map.getLayer(id)) continue;
      try{ map.moveLayer(id, anchor); anchor = id; }catch(_){}
    }
  })();

  // ── N4: Sessellift-Name bei Hover/Klick (OSM-name, falls vorhanden) ───────
  map.on('mouseenter','chairlift-line',e=>{ map.getCanvas().style.cursor='pointer';
    const n=e.features[0].properties&&e.features[0].properties.name;
    if(n){ hoverPop.setLngLat(e.lngLat).setHTML('<div class="lift-pop">'+_e(n)+'</div>').addTo(map); } });
  map.on('mousemove','chairlift-line',e=>{ try{ if(hoverPop.isOpen()) hoverPop.setLngLat(e.lngLat); }catch(_){ } });
  map.on('mouseleave','chairlift-line',()=>{ map.getCanvas().style.cursor=''; hoverPop.remove(); });
  map.on('click','chairlift-line',e=>{ const n=e.features[0].properties&&e.features[0].properties.name;
    closeAllPopups();
    peakPopup.setLngLat(e.lngLat).setHTML('<div class="pk-pop"><div class="pk-name">'+_e(n||'Sessellift')+
      '</div><div class="pk-ele">Sessellift</div></div>').addTo(map); });

  // ── STS fill click — popup always; panel only for visited groups ─────────
  map.on('mouseenter','sts-hit',()=>map.getCanvas().style.cursor='pointer');
  // B) Hover-Box: Name + Settore (+ privat: Besuchs-Badge + Jahre) + Klick-Hinweis.
  map.on('mousemove','sts-hit',e=>{
    // §4 (W4): Hover-Glow via feature-state (flackerfrei, unabhaengig vom Panel).
    const hid=e.features[0].id;
    if(_hoverId!==hid){
      if(_hoverId!=null) map.setFeatureState({source:'sts',id:_hoverId},{hover:false});
      _hoverId=hid; if(hid!=null) map.setFeatureState({source:'sts',id:hid},{hover:true});
    }
    if(document.getElementById('panel').classList.contains('open')) return;  // kein Doppel-Popup
    clearTimeout(_hoverTimer);                                               // Dwell: erst nach 700 ms Ruhe
    const p=e.features[0].properties, ll=e.lngLat;
    const nm=(p.name_de||p.STS||'').replace(/</g,'&lt;');
    const settore=(p.settore||'').replace(/</g,'&lt;');
    let extra='';
    /* PRIV:START */
    if(p.visited===1){
      let yrs=[];
      try{ const ids=JSON.parse(p.tour_ids||'[]');
        yrs=[...new Set(ids.map(id=>{const t=TOUREN.find(x=>x.id==id);return t&&t.jahr;}).filter(Boolean))]
             .sort((a,b)=>(jahrSort(a)||0)-(jahrSort(b)||0)); }catch(_){}
      extra='<div class="hp-b"><span class="hp-badge">besucht</span>'+
            (yrs.length?' · '+String(yrs.join(', ')).replace(/</g,'&lt;'):'')+'</div>';
    }
    /* PRIV:END */
    _hoverTimer=setTimeout(()=>{
      hoverPop.setLngLat(ll)
        .setHTML('<div class="hp-n">'+nm+'</div>'+
          (settore?'<div class="hp-s">'+settore+'</div>':'')+extra+
          '<div class="hp-hint">Klick f&uuml;r Steckbrief</div>')
        .addTo(map);
    }, 700);
  });
  map.on('mouseleave','sts-hit',()=>{map.getCanvas().style.cursor='';clearTimeout(_hoverTimer);hoverPop.remove();
    if(_hoverId!=null){ map.setFeatureState({source:'sts',id:_hoverId},{hover:false}); _hoverId=null; }});
  // ── Abnahme-Befund 3: Gipfel-Klick -> „Gipfel-Popup light" (Name · Höhe ·
  // „<Gruppe> öffnen →"), NICHT direkt der Gruppen-Steckbrief. Erst der Klick auf
  // die Zeile öffnet die Gebirgsgruppe. Beide Builds (Gipfel = neutrale Geodaten). ─
  const PEAK_LAYERS = ['osm-peaks','osm-peaks-gold','osm-landmarks','osm-landhigh','peaks-in-group','peaks-highest'];
  const peakPopup = new maplibregl.Popup({closeButton:true, closeOnClick:false, offset:12});
  map.on('click', PEAK_LAYERS, e=>{
    const f=e.features[0], p=f.properties||{};
    const name=p.name||'Gipfel';
    const ele=(p.ele!=null && p.ele!=='')?(Math.round(+p.ele)+' m'):'';
    let sts='', gname='';
    const grp=map.queryRenderedFeatures(e.point,{layers:['sts-hit']});
    if(grp.length){ sts=grp[0].properties.STS||''; gname=grp[0].properties.name_de||sts; }
    closeAllPopups();
    peakPopup.setLngLat(f.geometry.coordinates.slice()).setHTML(peakPopupHtml(name, ele, sts, gname)).addTo(map);
  });
  // N6: Custom-Cursor über Gipfeln (vereinfachtes Bergsymbol + „?"), Fallback pointer.
  const _peakCurSvg="<svg xmlns='http://www.w3.org/2000/svg' width='28' height='28' viewBox='0 0 28 28'>"+
    "<path d='M1 24 L9 9 L14 17 L17 12 L27 24 Z' fill='#f2f6fa' stroke='#1a2530' stroke-width='1.6' stroke-linejoin='round'/>"+
    "<path d='M7.4 12.5 L9 9 L10.6 12.5 L9 13.4 Z' fill='#a9c7dd'/>"+
    "<circle cx='21' cy='7' r='6' fill='#ffb24d' stroke='#1a2530' stroke-width='1.2'/>"+
    "<text x='21' y='10.4' font-size='9' font-family='Arial,sans-serif' font-weight='bold' fill='#1a2530' text-anchor='middle'>?</text></svg>";
  const PEAK_CURSOR='url("data:image/svg+xml,'+encodeURIComponent(_peakCurSvg)+'") 5 24, pointer';
  PEAK_LAYERS.forEach(l=>{
    map.on('mouseenter',l,()=>{ map.getCanvas().style.cursor=PEAK_CURSOR; });
    map.on('mouseleave',l,()=>{ map.getCanvas().style.cursor=''; });
  });

  map.on('click','sts-hit',e=>{
    if(TOUR_LAYERS.length && map.queryRenderedFeatures(e.point,{layers:TOUR_LAYERS}).length) return;
    if(map.queryRenderedFeatures(e.point,{layers:HUT_LAYERS}).length) return;  // Hütte hat Vorrang
    if(map.queryRenderedFeatures(e.point,{layers:PEAK_LAYERS}).length) return;  // Befund 3: Gipfel-Popup hat Vorrang
    if(map.queryRenderedFeatures(e.point,{layers:['places-sq','places-dot','places-label','places-village','places-village-label','cable-icon']}).length) return;  // Ort/Seilbahn hat Vorrang
    if(map.getLayer('t-cluster-halo') && map.queryRenderedFeatures(e.point,{layers:['t-cluster-halo']}).length) return;  // P2.7: Cluster hat Vorrang
    clearTimeout(_hoverTimer); hoverPop.remove(); stsPopup.remove(); hutPopup.remove();  // B: keine klebende Box
    openSts(e.features[0]);                                                   // Steckbrief für JEDE Gruppe
  });

  // ── HL-line click — fallback when fill is toggled off ────────────────────
  // Skip if sts-fill rendered features are present (sts-fill click takes priority).
  map.on('mouseenter','hl-line',()=>map.getCanvas().style.cursor='pointer');
  map.on('mouseleave','hl-line',()=>map.getCanvas().style.cursor='');
  map.on('click','hl-line',e=>{
    if(map.queryRenderedFeatures(e.point,{layers:['sts-hit'].concat(TOUR_LAYERS)}).length) return;
    const hp = e.features[0].properties;
    const matchName = (hp.match_field==='STS') ? hp.soiusa_name : (hp.parent_sts||'');
    const stsFeat = SOIUSA_STS.features.find(f=>f.properties.STS===matchName);
    if(stsFeat){
      clearTimeout(_hoverTimer); hoverPop.remove();     // B: keine klebende Box
      openSts(stsFeat);
    }
  });

  // ── Click on empty map (no feature) closes popup + selection ──────────────
  map.on('click', e=>{
    if(!map.queryRenderedFeatures(e.point,{layers:HUT_LAYERS}).length) hutPopup.remove();
    if(!map.queryRenderedFeatures(e.point,{layers:PEAK_LAYERS.concat(['chairlift-line'])}).length) peakPopup.remove();  // Befund 3/N4: Gipfel-/Lift-Popup
    // W1c: Klick ohne Gruppen-/Linien-/Punkt-Feature -> Steckbrief schliessen + Auswahl-Rand weg.
    const feats=map.queryRenderedFeatures(e.point,{layers:
      ['sts-hit','hl-line','osm-passes','osm-passes-famous','chairlift-line',
       'places-sq','places-dot','places-label','places-village','places-village-label','cable-icon']
        .concat(PEAK_LAYERS).concat(HUT_LAYERS).concat(TOUR_LAYERS)});
    if(!feats.length) closePanel();
  });

  // ── P4: Vektor-Topo-Overlay Stufe 1+2 (über Satellit, gate z>=11) ─────────
  // UNVERIFIZIERT (keine Browser-Prüfung hier möglich) -> Cowork-Review am Morgen.
  // Alles defensiv gekapselt: faellt eine externe Quelle (contour-Global / OFM-Tiles)
  // aus, bleibt die Karte voll funktionsfaehig (Overlay erscheint dann nur nicht).
  // Toggle/Legende/Perf = Stufe 3 (bewusst NICHT hier).
  try {
    const OV_BEFORE = 'osm-landmark-glow';   // Overlay unter Gipfel/Hütten/Pässe einsortieren
    // Stufe 1 — Höhenlinien aus der vorhandenen Terrarium-DEM (maplibre-contour).
    if (typeof mlcontour !== 'undefined') {
      const demSource = new mlcontour.DemSource({
        url:'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png',
        encoding:'terrarium', maxzoom:10, worker:true });
      demSource.setupMaplibre(maplibregl);
      map.addSource('contours', { type:'vector', maxzoom:14,
        tiles:[ demSource.contourProtocolUrl({
          thresholds:{ 11:[100,500], 12:[100,500], 13:[50,250], 14:[20,100] },
          elevationKey:'ele', levelKey:'level', contourLayer:'contours' }) ] });
      map.addLayer({ id:'contour-lines', type:'line', source:'contours',
        'source-layer':'contours', minzoom:11,
        paint:{ 'line-color':'rgba(120,92,64,0.55)',
          'line-width':['match',['get','level'], 1, 1.1, 0.5] } }, OV_BEFORE);
      map.addLayer({ id:'contour-labels', type:'symbol', source:'contours',
        'source-layer':'contours', minzoom:13, filter:['>',['get','level'],0],
        layout:{ 'symbol-placement':'line','text-field':['concat',['to-string',['get','ele']],' m'],
          'text-font':['Noto Sans Bold'],'text-size':9.5,'symbol-spacing':190 },
        paint:{ 'text-color':'rgba(92,70,50,0.95)','text-halo-color':'rgba(255,255,255,0.5)','text-halo-width':1 } }, OV_BEFORE);
    }
    // Stufe 2 — Wanderwege aus OpenFreeMap (OpenMapTiles-Schema), NUR path/track.
    map.addSource('ofm', { type:'vector', url:'https://tiles.openfreemap.org/planet' });
    map.addLayer({ id:'ofm-paths', type:'line', source:'ofm', 'source-layer':'transportation',
      minzoom:11, filter:['match',['get','class'], ['path','track'], true, false],
      layout:{ 'line-join':'round','line-cap':'round' },
      paint:{ 'line-color':'rgba(242,236,226,0.62)',
        'line-width':['interpolate',['linear'],['zoom'], 11,0.8, 15,1.9],'line-dasharray':[2,1.6] } }, OV_BEFORE);
  } catch(e){ console.warn('Topo-Overlay uebersprungen:', e); }

  // ── Basemap init (localStorage) + Interim-Gate ────────────────────────────
  let _bm='sat';
  try{ if(localStorage.getItem('alpen_basemap')==='topo') _bm='topo'; }catch(_){}
  if(_bm==='topo' && map.getZoom()<11) _bm='sat';   // Gate: kein Topo in der Übersicht
  setBasemap(_bm);
  updateTopoGate();
  map.on('zoom', updateTopoGate);
  restoreToggles();   // UX(1): gespeicherte Ebenen-Zustaende wiederherstellen (nach Layer+Basemap)
  _syncPointToggles();   // W1.1: Wunsch-Zustand (auch aus Klick vor Layer-Init) auf die Layer nachziehen

  // ── Build the search index (groups now; OSM points fetched async) ──────────
  buildSearchIndex();

  // ── Fix blank canvas — map.resize() is more reliable than triggerRepaint ──
  map.resize();
  setTimeout(()=>map.resize(), 150);
  map.once('idle',()=>map.resize());
  // P0: Gate-UI erst nach dem Settle final setzen (Initial-Zoom steht dann verlässlich)
  // -> Topo-Button unter z11 sofort ausgegraut, nicht erst beim ersten Zoom-Event.
  map.once('idle',updateTopoGate);
});

// ── Keyless canvas icons for OSM symbols ──────────────────────────────────────
function makeIcon(size, draw){
  const c=document.createElement('canvas'); c.width=size; c.height=size;
  const x=c.getContext('2d'); draw(x,size);
  return x.getImageData(0,0,size,size);
}
function houseIcon(color){
  return makeIcon(20,(x,s)=>{
    x.fillStyle=color; x.strokeStyle='#06101a'; x.lineWidth=1.5; x.lineJoin='round';
    x.beginPath(); x.moveTo(s*0.5,s*0.16); x.lineTo(s*0.86,s*0.5); x.lineTo(s*0.14,s*0.5); x.closePath(); x.fill(); x.stroke();
    x.beginPath(); x.rect(s*0.27,s*0.5,s*0.46,s*0.34); x.fill(); x.stroke();
  });
}
// 5-point star (Mont Blanc / Alpen-König)
function makeStar(color){
  return makeIcon(26,(x,s)=>{
    const cx=s/2, cy=s/2, R=s*0.44, r=s*0.19;
    x.beginPath();
    for(let i=0;i<10;i++){ const a=-Math.PI/2 + i*Math.PI/5, rad=(i%2)?r:R;
      const px=cx+Math.cos(a)*rad, py=cy+Math.sin(a)*rad; i?x.lineTo(px,py):x.moveTo(px,py); }
    x.closePath(); x.fillStyle=color; x.fill(); x.lineWidth=1.6; x.strokeStyle='#06101a'; x.lineJoin='round'; x.stroke();
  });
}
// Seilbahn-Talstation: Gondel-Piktogramm (Seil + Kabine).
// W4: Seilbahn-Logo als SDF (weiße Silhouette -> icon-color + heller/dunkler Halo).
function gondolaIcon(){
  return makeIcon(22,(x,s)=>{
    x.fillStyle='#fff'; x.strokeStyle='#fff'; x.lineWidth=s*0.09; x.lineJoin='round'; x.lineCap='round';
    x.beginPath(); x.moveTo(s*0.1,s*0.22); x.lineTo(s*0.9,s*0.34); x.stroke();     // Seil
    x.beginPath(); x.moveTo(s*0.5,s*0.28); x.lineTo(s*0.5,s*0.45); x.stroke();     // Aufhaenger
    x.beginPath(); x.moveTo(s*0.33,s*0.47); x.lineTo(s*0.67,s*0.47);
      x.lineTo(s*0.62,s*0.78); x.lineTo(s*0.38,s*0.78); x.closePath(); x.fill();   // Kabine (Trapez)
  });
}
// Unbewirtschaftet / Refugio / Biwak: hollow house (outline only), muted.
function houseOutline(color){
  return makeIcon(20,(x,s)=>{
    x.strokeStyle=color; x.lineWidth=1.8; x.lineJoin='round'; x.fillStyle='rgba(10,14,20,0.5)';
    x.beginPath(); x.moveTo(s*0.5,s*0.16); x.lineTo(s*0.86,s*0.5); x.lineTo(s*0.14,s*0.5); x.closePath(); x.fill(); x.stroke();
    x.beginPath(); x.rect(s*0.27,s*0.5,s*0.46,s*0.34); x.fill(); x.stroke();
  });
}
// Orts-Klassifizierung v2: K1 (Großstadt ≥100k) = ATLAS-ROTES Quadrat mit heller
// Kontur + dunklem Kern-Akzent (ECKIG = städtisch). Quadrat füllt fast das Canvas
// (randfüllend) -> Rendergröße ≈ icon-size, damit die Kante > K2-Ø bleibt (monoton).
function citySquare(){
  return makeIcon(20,(x,s)=>{
    const a=s*0.12, b=s*0.76;
    x.fillStyle='#cc3322'; x.strokeStyle='#f2e3c0'; x.lineWidth=1.8; x.lineJoin='miter';
    x.beginPath(); x.rect(a,a,b,b); x.fill(); x.stroke();          // rotes Quadrat, helle Kontur
    x.fillStyle='#2a0d08';
    x.fillRect(s*0.4,s*0.4,s*0.2,s*0.2);                           // dunkler Kern-Akzent
  });
}
// Tour-Marker v2 (Privat): Wanderer-Silhouette als SDF (weiß -> icon-color recolort
// orange/teal; heller Halo via icon-halo-*). Punkt suggerierte Präzision — der
// Wanderer markiert die Tour-Region, kollidiert nicht mit den runden Orts-Punkten.
function hikerIcon(){
  return makeIcon(28,(x,s)=>{
    x.fillStyle='#fff'; x.strokeStyle='#fff'; x.lineJoin='round'; x.lineCap='round';
    x.beginPath(); x.arc(s*0.44,s*0.19,s*0.1,0,7); x.fill();                    // Kopf
    x.lineWidth=s*0.14; x.beginPath(); x.moveTo(s*0.45,s*0.3); x.lineTo(s*0.5,s*0.57); x.stroke();  // Rumpf
    x.lineWidth=s*0.11;
    x.beginPath(); x.moveTo(s*0.5,s*0.55); x.lineTo(s*0.35,s*0.83); x.stroke(); // hinteres Bein
    x.beginPath(); x.moveTo(s*0.5,s*0.55); x.lineTo(s*0.63,s*0.81); x.stroke(); // vorderes Bein
    x.lineWidth=s*0.08;
    x.beginPath(); x.moveTo(s*0.46,s*0.38); x.lineTo(s*0.67,s*0.49); x.stroke();// Arm
    x.beginPath(); x.moveTo(s*0.68,s*0.3); x.lineTo(s*0.72,s*0.85); x.stroke(); // Wanderstock
  });
}

// ── Peaks of the clicked group (within-filter) + highest-peak highlight ───────
function showGroupPeaks(stsName){
  // Use the FULL inline geometry (not the tile-clipped click feature).
  const f=SOIUSA_STS.features.find(x=>x.properties.STS===stsName);
  const geom=f&&f.geometry;
  if(!geom){ resetGroupPeaks(); return; }
  const w=(WIKI.gruppen||{})[stsName];
  let hoch='__none__';
  if(w && w.hoechster_berg) hoch = w.hoechster_berg.replace(/\s*\(.*?\)\s*/g,'').trim();
  map.setFilter('peaks-in-group', ['all',['within',geom],['!=',['get','name'],hoch]]);
  map.setFilter('peaks-highest',  ['all',['within',geom],['==',['get','name'],hoch]]);
  // Punkt 3: Gruppen-Gipfel (inkl. Gold-Gipfel) folgen dem Gipfel-Toggle, nicht mehr „immer an".
  _applyGroupPeaksVis();
}
// Sichtbarkeit der Gruppen-Gipfel = Gipfel-Toggle AN und eine Gruppe ist ausgewaehlt.
function _applyGroupPeaksVis(){
  const on = _peaksOn && !!_selSts;
  map.setLayoutProperty('peaks-in-group','visibility', on?'visible':'none');
  map.setLayoutProperty('peaks-highest', 'visibility', on?'visible':'none');
}
function resetGroupPeaks(){
  map.setFilter('peaks-in-group', ['==',['get','name'],'__none__']);
  map.setFilter('peaks-highest',  ['==',['get','name'],'__none__']);
  map.setLayoutProperty('peaks-in-group','visibility','none');
  map.setLayoutProperty('peaks-highest','visibility','none');
}
// P3b §10a: Gipfel-Eintrag im Steckbrief anklicken -> flyTo + kurzer Puls auf dem Punkt.
// Koordinate aus der geladenen osm-peaks-Quelle (Viewport) oder dem Inline-OSM_PEAKS (Standalone).
// Abnahme-Fix Befund 1: Zoom-Deckel ~13,5 (Gipfel im Gebirgskontext, Track/Marker sichtbar) —
// nie darüber reinzoomen; wer schon näher dran ist, behält den Zoom (Math.max). Panel-Offset
// via padding. Pitch moderat (≤30). Puls-Marker erst NACH Ankunft (moveend). Ein Kern für alle.
function _peakPad(){
  const panelOpen=document.getElementById('panel').classList.contains('open');
  const mobile=window.innerWidth<=640;
  return !panelOpen ? {left:60,right:60,top:70,bottom:90}
    : mobile ? {left:40,right:40,top:70,bottom:Math.round(window.innerHeight*0.5)}
             : {left:320,right:70,top:80,bottom:90};
}
function _focusPeakAt(c){
  if(!c || c.length<2) return;
  saveUndo();
  map.once('moveend', ()=>{ pulseGipfel(c); });
  map.flyTo({center:c, zoom:Math.max(map.getZoom(),13.5), pitch:Math.min(map.getPitch(),30), padding:_peakPad(), essential:true});
  showUndoChip();
}
function focusGipfel(name){
  if(!name) return;
  let feat=null;
  try{ const fs=map.querySourceFeatures('osm-peaks',{filter:['==',['get','name'],name]}); if(fs&&fs.length) feat=fs[0]; }catch(_){}
  if(!feat && typeof OSM_PEAKS!=='undefined' && OSM_PEAKS && OSM_PEAKS.features)
    feat=OSM_PEAKS.features.find(f=>f.properties && f.properties.name===name);
  if(!feat||!feat.geometry) return;
  _focusPeakAt(feat.geometry.coordinates.slice(0,2));
}
// N3: „Höchster Berg" einer Gruppe — eindeutige Koordinate (GROUP_PEAKS, Build-time via
// Peak×Polygon-Containment). Funktioniert für ALLE Gruppen; Gruppen ohne Gipfel ≥2000 m
// (z. B. Sonntagshorn 1961) fallen auf fitBounds der Gruppe zurück.
function focusGroupPeak(sts){
  const c = (typeof GROUP_PEAKS!=='undefined' && GROUP_PEAKS) ? GROUP_PEAKS[sts] : null;
  if(c && c.length===2){ _focusPeakAt(c); return; }
  const f=SOIUSA_STS.features.find(x=>x.properties.STS===sts);
  if(!f||!f.geometry) return;
  let minx=180,miny=90,maxx=-180,maxy=-90;
  (function walk(a){ if(typeof a[0]==='number'){ if(a[0]<minx)minx=a[0]; if(a[0]>maxx)maxx=a[0]; if(a[1]<miny)miny=a[1]; if(a[1]>maxy)maxy=a[1]; } else a.forEach(walk); })(f.geometry.coordinates);
  saveUndo();
  map.fitBounds([[minx,miny],[maxx,maxy]], {padding:_peakPad(), pitch:Math.min(map.getPitch(),30), essential:true});
  showUndoChip();
}
let _gpRAF=null;
function pulseGipfel(c){
  try{
    const data={type:'Feature',geometry:{type:'Point',coordinates:c}};
    if(!map.getSource('gipfel-pulse')){
      map.addSource('gipfel-pulse',{type:'geojson',data});
      map.addLayer({id:'gipfel-pulse',type:'circle',source:'gipfel-pulse',
        paint:{'circle-radius':6,'circle-color':'#ffd47a','circle-opacity':0.55,'circle-stroke-color':'#fff','circle-stroke-width':2}});
    } else { map.getSource('gipfel-pulse').setData(data); map.setLayoutProperty('gipfel-pulse','visibility','visible'); }
    const t0=performance.now(); if(_gpRAF) cancelAnimationFrame(_gpRAF);
    const step=t=>{ const k=(t-t0)/1400;
      if(k>=1){ try{ map.setLayoutProperty('gipfel-pulse','visibility','none'); }catch(_){} _gpRAF=null; return; }
      try{ map.setPaintProperty('gipfel-pulse','circle-radius',6+30*k); map.setPaintProperty('gipfel-pulse','circle-opacity',0.55*(1-k)); }catch(_){}
      _gpRAF=requestAnimationFrame(step); };
    _gpRAF=requestAnimationFrame(step);
  }catch(_){}
}
// Delegierter Klick auf Gipfel-Einträge im Steckbrief. „Höchster Berg" (.gip-hi) läuft
// über die eindeutige Gruppen-Koordinate (N3); Tour-Gipfel (.gip) weiter über den Namen.
(function(){ const p=document.getElementById('panel'); if(p) p.addEventListener('click', e=>{
  const gh=e.target.closest&&e.target.closest('.gip-hi'); if(gh&&gh.dataset.sts){ focusGroupPeak(gh.dataset.sts); return; }
  const g=e.target.closest&&e.target.closest('.gip'); if(g&&g.dataset.gip) focusGipfel(g.dataset.gip); }); })();

// ── featBbox: handles Polygon, MultiPolygon, GeometryCollection ───────────────
function featBbox(feat){
  if(!feat||!feat.geometry) return null;
  const lons=[],lats=[];
  function wk(c){
    if(!Array.isArray(c)) return;
    if(typeof c[0]==='number'){lons.push(c[0]);lats.push(c[1]);return;}
    c.forEach(wk);
  }
  const g=feat.geometry;
  if(g.type==='GeometryCollection') g.geometries.forEach(h=>h&&wk(h.coordinates));
  else wk(g.coordinates);
  if(!lons.length) return null;
  const w=Math.min(...lons),s=Math.min(...lats),e=Math.max(...lons),n=Math.max(...lats);
  return(isFinite(w)&&isFinite(s)&&isFinite(e)&&isFinite(n))?[[w,s],[e,n]]:null;
}

// ── Tab switching (guards missing elements in public build) ───────────────────
function showTab(name){
  const at=document.getElementById('pAbout'), to=document.getElementById('pTour');
  const ta=document.getElementById('tabAbout'), tt=document.getElementById('tabTour');
  if(at) at.classList.toggle('active', name==='about');
  if(to) to.classList.toggle('active', name==='tour');
  if(ta) ta.classList.toggle('active', name==='about');
  if(tt) tt.classList.toggle('active', name==='tour');
}
function setTourTab(html, count){
  const el=document.getElementById('pTour');
  const tabs=document.getElementById('pTabs');
  const tt=document.getElementById('tabTour');
  const show = PRIV && !!html;
  if(el) el.innerHTML = show ? html : '';
  if(tt) tt.textContent = 'Touren'+(count?' ('+count+')':'');   // P2: „Touren (n)"
  if(tabs) tabs.style.display = show ? 'flex' : 'none';
  showTab(show ? 'tour' : 'about');
}

// ── Gipfel list markup (shared) — P3b §10a: Einträge klickbar (flyTo + Puls) ──
function gipfelUl(gipfel){
  if(!gipfel||!gipfel.length) return '';
  return '<ul>'+gipfel.map(g=>{
    const da=_escp(String(g.name||'')).replace(/"/g,'&quot;');
    return '<li class="gip" data-gip="'+da+'" title="Auf der Karte zeigen"><span>'+_escp(g.name)+
      (g.hinweis?' <i style="color:var(--muted)">('+_escp(g.hinweis)+')</i>':'')+
      '</span>'+(g.hoehe_m?'<b>'+g.hoehe_m+' m</b>':'')+'</li>';
  }).join('')+'</ul>';
}

// ── Open: tour marker (privat only) ───────────────────────────────────────────
/* PRIV:START */
// P2: Tour-Marker-Klick öffnet — wie die Listen-Zeile — den Gruppen-Steckbrief
// mit dieser Tour-Karte aufgeklappt (openTourRow). Vereinheitlicht Marker & Liste.
function openTour(id){ openTourRow(id); }
/* PRIV:END */

// ── Steckbrief markup (public-safe, from soiusa_wiki.json) ────────────────────
function steckbriefHtml(stsName, props){
  const w = (WIKI.gruppen||{})[stsName] || null;
  const settore = props.settore || '';
  const rows = [];
  if(w && w.hoechster_berg){
    // N3: eindeutiger Lookup per Gruppe (Koordinate aus GROUP_PEAKS statt Namens-String —
    // Namens-Dubletten wie „Krottenkopf" 2× sonst falsch/tot). data-sts trägt die Gruppe.
    const _ds=_escp(stsName).replace(/"/g,'&quot;');
    rows.push(['Höchster Berg','<b class="gip-hi" data-sts="'+_ds+'" title="Auf der Karte zeigen">'+_escp(w.hoechster_berg)+
      '</b>'+(w.hoehe_m?' · '+w.hoehe_m+' m':'')]);
  }
  if(settore) rows.push(['Lage', settore+' (Settore)']);
  const land = (w && w.land && w.land.length) ? w.land.join(' · ')
    : (CNAMES[props.country]||props.country||'');
  if(land) rows.push(['Land', land]);
  if(w && w.region_kanton && w.region_kanton.length)
    rows.push(['Region', w.region_kanton.join(' · ')]);
  let html = rows.map(r=>'<div class="sb-row"><span class="k">'+r[0]+
    '</span><span class="v">'+r[1]+'</span></div>').join('');
  if(w && w.bild_url){
    html += '<img class="sb-img" src="'+w.bild_url+'" alt="" loading="lazy">';
    if(w.bild_attr) html += '<div class="sb-attr">'+w.bild_attr+'</div>';
  }
  if(w && w.wiki_url)
    html += '<a class="sb-wiki" href="'+w.wiki_url+'" target="_blank" rel="noopener">Auf Wikipedia →</a>';
  else if(!w)
    html += '<div class="sb-open">Weitere Angaben folgen.</div>';
  return html || '<div class="sb-open">Weitere Angaben folgen.</div>';
}

// ── Hütten-Popup (beide Builds; Daten = HUTS_WIKI, Key = OSM properties.name) ──
// Fehlt ein Feld -> weglassen. Ohne Eintrag / nur sb_* -> schlichtes Popup (Name+ele+kat).
// sb_* werden NICHT gerendert (Datenfelder fuer spaeteren Familien-Filter, G2).
const HUT_KAT = {club:'Verbandshütte', hut:'Hütte', wild:'Unbewirtschaftet'};
// Anreise-Popups (klein, kein Enrichment in v1).
function _escp(s){ return String(s==null?'':s).replace(/[<>&]/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;'}[c])); }
function placePopupHtml(p){
  const kind = {city:'Stadt', town:'Stadt', village:'Dorf', hamlet:'Bergdorf'}[p.place] || 'Ort';
  const bits = [kind];
  if(p.ele) bits.push(p.ele+' m');
  if(p.pop) bits.push(Number(p.pop).toLocaleString('de-DE')+' Einw.');
  return '<div class="hp-n">'+_escp(p.name)+'</div><div class="hp-s">'+bits.join(' · ')+'</div>';
}
function cablePopupHtml(p){
  let s = 'Seilbahn (Talstation)';
  if(p.ele && p.ele_top) s = 'Tal '+p.ele+' m &rarr; Berg '+p.ele_top+' m';
  else if(p.ele) s = 'Talstation '+p.ele+' m';
  return '<div class="hp-n">'+_escp(p.name)+'</div><div class="hp-s">'+s+'</div>';
}
function hutPopupHtml(p){
  const esc = s => String(s==null?'':s).replace(/[<>&]/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;'}[c]));
  const w = (HUTS_WIKI.huetten||{})[p.name] || null;
  const verband = (w && w.club) || p.club || '';
  const badge = verband || HUT_KAT[p.kat] || '';
  const ele = (p.ele!=null && p.ele!=='') ? p.ele : (w ? w.ele : undefined);  // OSM-ele bevorzugen
  const meta = [];
  if(ele!=null && ele!=='') meta.push(esc(ele)+' m');
  if(w && w.bj) meta.push('erbaut '+esc(w.bj));
  let html = '<div class="hut-pop"><div class="sp-name">'+esc(p.name||'Hütte')+'</div>';
  if(badge) html += '<span class="hut-badge">'+esc(badge)+'</span>';
  if(meta.length) html += '<div class="hut-meta">'+meta.join(' · ')+'</div>';
  html += hutVisitBadge(p.name);         // §1: Besuchsjahr-Badge (nur Privat)
  html += hutCableChip(w);               // §3: „Seilbahn-nah"-Chip (beide Builds)
  if(w && w.img && w.img_attr){          // Bild NUR mit Attribution (Wikimedia CC-Pflicht)
    html += '<img class="hut-img" src="'+w.img+'" alt="" loading="lazy">'+
            '<div class="hut-attr">'+esc(w.img_attr)+'</div>';
  }
  const links = [];
  if(w && w.wiki) links.push('<a href="'+w.wiki+'" target="_blank" rel="noopener">Auf Wikipedia →</a>');
  if(w && w.web)  links.push('<a href="'+w.web+'" target="_blank" rel="noopener">Website →</a>');
  if(links.length) html += '<div class="hut-links">'+links.join('')+'</div>';
  return html + '</div>';
}

// §3: „Seilbahn-nah"-Chip aus den G2-Feldern sb_* von HUTS_WIKI (beide Builds).
// Nur wenn eine Personen-Seilbahn (cable_car/gondola) ≤ 1 km entfernt ist (sb_d in Metern).
function hutCableChip(w){
  if(!w || w.sb_d==null || w.sb_d>1000) return '';
  const d=w.sb_d, dtxt = d>=1000 ? (d/1000).toFixed(1).replace('.',',')+' km' : d+' m';
  const nm = w.sb_n ? ' · '+_escp(w.sb_n) : '';
  return '<div class="hut-cable" title="Personen-Seilbahn (Talstation) in der Nähe – mögliche Aufstiegshilfe">'+
         '🚡 <b>Seilbahn-nah</b> <span>'+dtxt+nm+'</span></div>';
}

/* PRIV:START */
// §1: build-seitige Zuordnung OSM-Hütten-Name -> Besuchsjahre (nur Privat-Build).
const HUT_VISITS = __HUT_VISITS__;   // {osmName:[jahr,…]} normalisiert gematcht in build.py
function hutVisitBadge(name){
  const ys = HUT_VISITS[name];
  if(!ys || !ys.length) return '';
  return '<div class="hut-visit"><span class="lbl">Ihr wart hier:</span>'+
         ys.map(y=>'<b>'+_escp(y)+'</b>').join(' · ')+'</div>';
}
/* PRIV:END */
/* PUB:START */
function hutVisitBadge(){ return ''; }   // Public: kein Besuchs-Badge (E8-Hygiene)
/* PUB:END */

// ── Tour markup for a visited group (private build only) ──────────────────────
/* PRIV:START */
// §5 (Paket C): Tour-Kategorie (explizites Feld `kategorie` in touren.json; Fallback
// „Tour", falls fehlt). Keine Namens-Heuristik. Daten pflegt Cowork ein.
function _toursOf(props){
  const ids = typeof props.tour_ids==='string'
    ? JSON.parse(props.tour_ids||'[]') : (Array.isArray(props.tour_ids)?props.tour_ids:[]);
  return ids.map(id=>TOUREN.find(t=>t.id==id)).filter(Boolean);
}
function katOf(t){ return (t && t.kategorie && String(t.kategorie).trim()) || 'Tour'; }
function katLabel(tours){ const s=[...new Set((tours||[]).map(katOf))]; return s.length===1 ? s[0] : 'Touren'; }

// P5: Mini-Höhenprofil als SVG-Sparkline aus den Inline-Track-Höhen (3. Koordinatenwert).
// x = kumulative Distanz (Haversine), y = Höhe; dezent, Besucht-Orange. Leer ohne ele/Track.
function _trackSparkline(tid){
  try{
    if(typeof TRACKS==='undefined' || !TRACKS.features) return '';
    const f=TRACKS.features.find(x=>x.properties.tour_id===tid);
    if(!f || !f.geometry) return '';
    const c=f.geometry.coordinates;
    if(!c.length || c[0].length<3) return '';
    const R=6371000, rad=Math.PI/180;
    let d=0; const xs=[0], es=[c[0][2]];
    for(let i=1;i<c.length;i++){
      const a=c[i-1], b=c[i], la1=a[1]*rad, la2=b[1]*rad, dla=(b[1]-a[1])*rad, dlo=(b[0]-a[0])*rad;
      const h=Math.sin(dla/2)**2 + Math.cos(la1)*Math.cos(la2)*Math.sin(dlo/2)**2;
      d+=R*2*Math.asin(Math.sqrt(h))/1000; xs.push(d); es.push(b[2]);
    }
    const total=d||1, eMin=Math.min(...es), eMax=Math.max(...es), eRng=(eMax-eMin)||1;
    const W=240,H=44,PX=2,PY=5;
    const px=i=>PX+(xs[i]/total)*(W-2*PX), py=i=>PY+(1-(es[i]-eMin)/eRng)*(H-2*PY);
    let pts=''; for(let i=0;i<xs.length;i++){ pts+=(i?' ':'')+px(i).toFixed(1)+','+py(i).toFixed(1); }
    let area='M'+px(0).toFixed(1)+','+(H-PY);
    for(let i=0;i<xs.length;i++){ area+=' L'+px(i).toFixed(1)+','+py(i).toFixed(1); }
    area+=' L'+px(xs.length-1).toFixed(1)+','+(H-PY)+' Z';
    return '<div class="tc-spark" title="Höhenprofil">'+
      '<svg viewBox="0 0 '+W+' '+H+'" preserveAspectRatio="none" aria-hidden="true">'+
        '<path class="tcs-area" d="'+area+'"/><polyline class="tcs-line" points="'+pts+'"/></svg>'+
      '<div class="tcs-lbl"><span>'+Math.round(es[0])+' m</span>'+
        '<span class="tcs-max">▲ '+Math.round(eMax)+' m</span>'+
        '<span>'+Math.round(es[es.length-1])+' m</span></div></div>';
  }catch(_){ return ''; }
}
// P6/Befund 4: Teilnehmer-Namen als optische Chips (Pill + Filter-Icon, nur
// filterbar!=false). Klick öffnet ein BESTÄTIGUNGS-Popover statt sofort zu filtern
// und den Steckbrief still zu schließen. Nicht-filterbare Personen = Klartext.
function _teilnehmerHtml(t){
  const ids=(t&&t.teilnehmer_ids)||[];
  if(!ids.length) return _e((t&&t.teilnehmer)||'');
  const ico='<svg class="tc-pico" viewBox="0 0 12 12" aria-hidden="true"><path d="M1 2h10l-4 4.2V11L5 9.7V6.2z"/></svg>';
  const parts=ids.map(id=>{
    const p=PERSON_BY_ID[id]; if(!p) return null;
    const nm=_e(p.name);
    if(p.filterbar===false) return '<span class="tc-pers-plain">'+nm+'</span>';
    const on=FILTER.personen.indexOf(id)>=0?' on':'';
    const n=_personFreq[id]||0;
    return '<span class="tc-pers'+on+'" onclick="event.stopPropagation();openPersPopover(event,\''+id+'\','+n+')" '+
           'title="Touren mit '+nm+' filtern">'+ico+nm+'</span>';
  }).filter(Boolean);
  return parts.length ? parts.join(' ') : _e(t.teilnehmer||'');
}
// Befund 4: Bestätigungs-Popover „Alle Touren mit X anzeigen (n)?" [Filtern] [Abbrechen].
// Kein Sofort-Filter, kein stilles closePanel. Schließen via Abbrechen/Esc/Außenklick.
let _persPopId=null;
function openPersPopover(ev, id, n){
  ev=ev||window.event; if(ev&&ev.stopPropagation) ev.stopPropagation();
  const p=PERSON_BY_ID[id]; if(!p) return;
  _persPopId=id;
  const el=document.getElementById('persPopover'); if(!el) return;
  el.innerHTML='<div class="pp-q">Alle Touren mit <b>'+_e(p.name)+'</b> anzeigen ('+n+')?</div>'+
    '<div class="pp-btns"><button class="pp-ok" onclick="event.stopPropagation();persPopoverConfirm()">Filtern</button>'+
    '<button class="pp-cancel" onclick="event.stopPropagation();closePersPopover()">Abbrechen</button></div>';
  el.classList.add('open');
  const pad=8, w=el.offsetWidth||212, h=el.offsetHeight||74;
  let x=(ev&&ev.clientX||120), y=((ev&&ev.clientY||120)+12);
  x=Math.min(Math.max(pad,x), window.innerWidth-w-pad);
  y=Math.min(Math.max(pad,y), window.innerHeight-h-pad);
  el.style.left=x+'px'; el.style.top=y+'px';
}
function closePersPopover(){ const el=document.getElementById('persPopover'); if(el) el.classList.remove('open'); _persPopId=null; }
function persPopoverConfirm(){
  const id=_persPopId; closePersPopover(); if(id==null) return;
  if(FILTER.personen.indexOf(id)<0){ FILTER.personen.push(id); applyTourFilter(); }  // UND-Logik, kein Toggle
  closePanel();   // erst JETZT: Steckbrief zu -> gefilterte Liste sichtbar
}
document.addEventListener('click', e=>{ const el=document.getElementById('persPopover');
  if(el && el.classList.contains('open') && !el.contains(e.target)) closePersPopover(); });
document.addEventListener('keydown', e=>{ if(e.key==='Escape') closePersPopover(); });
// P2: Tab „Touren (n)" = Accordion, eine Karte pro Tour (chronologisch aufsteigend).
// Beim Einstieg über eine Listen-Zeile/Marker ist _pendingTour aufgeklappt.
function groupTourHtml(props){
  const tours = _toursOf(props).slice().sort((a,b)=>(jahrSort(a.jahr)||0)-(jahrSort(b.jahr)||0));
  if(!tours.length) return '';
  // Einstiegs-Tour aufgeklappt: die angeklickte (_pendingTour) oder – bei Karten-Klick – die erste.
  const openId = tours.some(t=>t.id===_pendingTour) ? _pendingTour : tours[0].id;
  return tours.map(t=>{
    const op=(t.id===openId)?' open':'';
    const yr=_e(String(t.jahr||'')), geb=_e(t.gebirge||t.gegend||''), kat=_e(katOf(t));
    const jj="chronoJumpYear('"+_e(String(t.jahr||''))+"',"+t.id+")";
    let b='';
    if(t.datum) b+='<div class="tc-row"><span class="tc-k">Datum</span>'+_e(t.datum)+'</div>';
    if(t.teilnehmer) b+='<div class="tc-row"><span class="tc-k">Teilnehmer</span>'+_teilnehmerHtml(t)+'</div>';
    if(t.gipfel&&t.gipfel.length) b+='<div class="tc-row"><span class="tc-k">Gipfel</span>'+gipfelUl(t.gipfel)+'</div>';
    if(t.huetten) b+='<div class="tc-row"><span class="tc-k">Hütten / Stationen</span>'+_e(t.huetten)+'</div>';
    if(t.track_km){
      // Befund 9: Quelle je nach gpx_quelle (aufgezeichnet vs. rekonstruiert), Fallback altes Flag.
      const _q=t.gpx_quelle||(t.gpx_rekonstruiert?'rekonstruiert':'');
      const _qs=_q==='aufgezeichnet'?' · <i>GPS-Aufzeichnung (gemerged)</i>'
               :_q==='rekonstruiert'?' · <i>rekonstruiert (__PT_LBL_BOOKSRC__)</i>':'';
      b+='<div class="tc-row"><span class="tc-k">Track</span>'+String(t.track_km).replace('.',',')+
        ' km · +'+t.track_hm+' hm'+_qs+'</div>';
      b+=_trackSparkline(t.id); }   // P5: Mini-Höhenprofil
    if(t.bemerkung) b+='<div class="tc-row">'+_e(t.bemerkung)+'</div>';
    if(t.memo&&t.memo.trim()) b+='<div class="tour-memo">'+_esc(t.memo.trim()).replace(/\n/g,'<br>')+'</div>';
    b+=fotoBand(t);
    b+='<span class="tc-chrono" onclick="event.stopPropagation();'+jj+'">In der Chronik zeigen &rarr;</span>';
    return '<div class="tcard'+op+'" data-tid="'+t.id+'">'+
      '<div class="tcard-h" onclick="toggleTcard(this)">'+
        '<span class="tc-yr" onclick="event.stopPropagation();'+jj+'" title="In der Chronik zeigen">'+yr+'</span>'+
        '<span class="tc-geb">'+geb+'</span><span class="cc-kat">'+kat+'</span>'+
        '<span class="tc-caret">&#9662;</span></div>'+
      '<div class="tcard-b">'+b+'</div></div>';
  }).join('');
}
function toggleTcard(h){
  if(!h||!h.parentElement) return;
  const card=h.parentElement, willOpen=!card.classList.contains('open');
  card.classList.toggle('open');
  if(willOpen) _selTourId=+card.dataset.tid;
  else { const o=document.querySelector('#pTour .tcard.open'); _selTourId=o?+o.dataset.tid:null; }
  markSelTourRow(); emphasizeTour(_selTourId);   // P3b §7: Selektion -> Karte betonen
}
// „In der Chronik zeigen" (Deep-Link, P3a.4): ist die Ziel-Tour von F ausgeschlossen,
// wird F SICHTBAR auf Default resettet (Segmented „Alle", Slider voll, Chips leer) und dann
// gesprungen — keine Sonderfälle, kein verstecktes Merken (behebt den „läuft ins Leere"-Bug).
function chronoJumpYear(jahr, tourId){
  const y=jahrSort(jahr); if(y==null) return;
  const inF = tourId==null || matchedTours().some(t=>t.id==tourId);
  if(!inF) resetFilter();   // baut CHRONO auf vollen Bereich neu -> Zieljahr wieder vorhanden
  closePanel();
  if(!_chronoOn) chronoEnter();
  const idx=CHRONO.years.indexOf(y);
  if(idx>=0) chronoSetYear(idx);
}
// Horizontales Foto-Scrollband einer Tour; Tap -> Lightbox.
function fotoBand(t){
  const fs=Array.isArray(t.fotos)?t.fotos:[];
  if(!fs.length) return '';
  return '<div class="foto-band">'+fs.map((f,i)=>
    '<img class="fb-img" src="'+f.src+'" loading="lazy" alt="'+_esc(f.caption||'')+
    '" onclick="openLightbox('+t.id+','+i+')">').join('')+'</div>';
}
// W1b: aus der Chronik-Caption den Steckbrief (Tab „Touren") mit dieser Tour-Karte öffnen.
function openTourPanel(tourId){
  const f=SOIUSA_STS.features.find(x=>{
    let ids=[]; try{ ids=JSON.parse(x.properties.tour_ids||'[]'); }catch(_){}
    return ids.some(v=>String(v)===String(tourId));
  });
  if(f){ _pendingTour=tourId; openSts(f); showTab('tour'); }
}

// ── Foto-Lightbox (Vanilla): Fullscreen, Wischen/Pfeile/×, tap ausserhalb schliesst ──
let _lbFotos=[], _lbIdx=0;
function openLightbox(tourId, idx){
  const t=TOUREN.find(x=>x.id==tourId); if(!t) return;
  _lbFotos=Array.isArray(t.fotos)?t.fotos:[];
  if(!_lbFotos.length) return;
  _lbIdx=Math.max(0,Math.min(idx|0,_lbFotos.length-1));
  _lbRender();
  document.getElementById('lightbox').classList.add('open');
}
function _lbRender(){
  const f=_lbFotos[_lbIdx]||{};
  document.getElementById('lbImg').src=f.src||'';
  document.getElementById('lbCap').textContent=f.caption||'';
  const multi=_lbFotos.length>1, d=multi?'':'none';
  document.getElementById('lbPrev').style.display=d;
  document.getElementById('lbNext').style.display=d;
}
function lbNext(e){ if(e)e.stopPropagation(); if(_lbFotos.length){ _lbIdx=(_lbIdx+1)%_lbFotos.length; _lbRender(); } }
function lbPrev(e){ if(e)e.stopPropagation(); if(_lbFotos.length){ _lbIdx=(_lbIdx-1+_lbFotos.length)%_lbFotos.length; _lbRender(); } }
function lbClose(){ document.getElementById('lightbox').classList.remove('open'); }
document.addEventListener('keydown',e=>{
  if(!document.getElementById('lightbox').classList.contains('open')) return;
  if(e.key==='Escape') lbClose();
  else if(e.key==='ArrowRight') lbNext();
  else if(e.key==='ArrowLeft') lbPrev();
});
{ let _lbX=0;
  const lb=document.getElementById('lightbox');
  if(lb){
    lb.addEventListener('touchstart',e=>{ _lbX=e.changedTouches[0].clientX; },{passive:true});
    lb.addEventListener('touchend',e=>{ const dx=e.changedTouches[0].clientX-_lbX;
      if(Math.abs(dx)>45){ dx<0?lbNext():lbPrev(); } },{passive:true});
  }
}
/* PRIV:END */

// B4: Name der AUSGEWAEHLTEN Gruppe ausblenden -> deren (nun sichtbare) Gipfel-Labels
// gewinnen den Platz (Repro A: Hochgolling vs. „Schladminger Tauern"). Der Name steht
// ohnehin im Steckbrief. Ohne Auswahl: alle Namen sichtbar (Kollision regelt Repro B).
let _selSts='';
function updateStsLabelFilter(){
  try{
    map.setFilter('sts-label',   ['all',['==',['get','visited'],0],['!=',['get','STS'],_selSts]]);
    map.setFilter('sts-label-hl', ['all',['==',['get','visited'],1],['!=',['get','STS'],_selSts]]);
  }catch(_){}
}

// ── Open: STS polygon (visited or not) ───────────────────────────────────────
function openSts(feat, camMode){   // camMode: undef=Gate(§6a), 'force'=immer fliegen (Suche), 'nofly'=nie (Chronik)
  closeAllPopups();   // Review-Befund 2: Steckbrief-Öffnen räumt offene schwarze Popups (Hütte/Gipfel/Pass/Treffer)
  const props = feat.properties || {};
  const stsName = String(props.STS || '').trim();
  // Harden: use '__none__' sentinel so empty-string filter doesn't accidentally match
  map.setFilter('sts-selected',['==',['get','STS'], stsName||'__none__']);
  _selSts = stsName; updateStsLabelFilter();   // B4: eigenen Gruppennamen ausblenden
  const visited = props.visited === 1;

  document.getElementById('pGroup').textContent = props.name_de || stsName;
  document.getElementById('pGegend').textContent = stsName + (props.CODICE?' · '+props.CODICE:'');
  document.getElementById('pYear').textContent = '';
  /* PRIV:START */
  document.getElementById('pYear').textContent = visited ? 'Besucht' : 'Noch nicht besucht';
  /* PRIV:END */

  document.getElementById('pAbout').innerHTML = steckbriefHtml(stsName, props);
  setTourTab(visited ? groupTourHtml(props) : '', visited ? _toursOf(props).length : 0);  // P2: „Touren (n)"
  showGroupPeaks(stsName);

  const _pnl=document.getElementById('panel');
  /* PRIV:START */
  // P2 Master-Detail: Desktop-Privat -> Steckbrief nimmt die Tourenlisten-Position ein
  // (as-cov, „← Touren"-Rückzeile). Vorher Scrollposition der Liste merken.
  const _cl=document.querySelector('#cov .cl'); _covScroll=_cl?_cl.scrollTop:0;
  const asCov = PRIV && window.innerWidth>640 && !_chronoOn;
  _pnl.classList.toggle('as-cov', asCov);
  _pnl.classList.toggle('has-back', !_chronoOn);   // „← Touren"-Rückzeile (nicht im Chronik-Modus)
  document.getElementById('cov').classList.remove('open');   // Liste einklappen (Steckbrief übernimmt)
  markChronoGroupYears(props);   // P1: Jahres-Chips dieses Gebiets markieren (Play-Cursor bleibt)
  if(asCov){ _pnl.style.top=''; }
  else {
  /* PRIV:END */
  // §1 (W4): Steckbrief unter der Title-Card andocken (kein Overlap der KPI-Zeile).
  const _tc=document.getElementById('title');
  if(_tc && window.innerWidth>640) _pnl.style.top=(_tc.getBoundingClientRect().bottom+10)+'px';
  else _pnl.style.top='';
  /* PRIV:START */
  }
  /* PRIV:END */
  _pnl.classList.add('open');
  /* PRIV:START */
  // P3b §7: die aufgeklappte Tour-Karte betonen (Icon+Track), andere im Gebiet dimmen.
  { const oc=document.querySelector('#pTour .tcard.open'); const eid=oc?+oc.dataset.tid:null;
    _selTourId=eid; markSelTourRow(); emphasizeTour(eid); }
  /* PRIV:END */
  // §6a (W4)/Fix2: 'nofly' -> nie fliegen (Chronik fliegt selbst); sonst ab z>=11 kein
  // Auto-flyTo bei Klick (Fehlklick-Schutz), 'force' (Suche) springt immer.
  if(camMode==='nofly') return;
  if(map.getZoom()>=11 && camMode!=='force') return;
  const bb=featBbox(feat);
  if(bb){ saveUndo(); map.fitBounds(bb,{padding:{top:80,bottom:80,left:320,right:80},
    pitch:18,bearing:0,maxZoom:10,duration:1200,essential:true}); showUndoChip(); }
}

// ── Toggle: group labels (fills always on) ────────────────────────────────────
// sts-fill / sts-line always visible; button toggles only the text labels.
// UX(1): Ebenen-Zustaende via localStorage persistieren (ueberleben Reload; auch Standalone).
let _restoring=false;
function persistToggles(){
  if(_restoring) return;
  try{ const _st={f:_farbungOn,n:_layersOn,b:_bordersOn,p:_peaksOn,h:_hutsOn,s:_passesOn,o:_placesOn,c:_cableOn};
    if(typeof _tracksOn!=='undefined') _st.t=_tracksOn;   // nur Privat (PRIV-Strip laesst _tracksOn im Public weg)
    localStorage.setItem('alpen_toggles', JSON.stringify(_st)); }catch(_){}
}
function restoreToggles(){
  let st; try{ st=JSON.parse(localStorage.getItem('alpen_toggles')||'null'); }catch(_){ st=null; }
  if(!st || _basemap==='topo') return;   // Topo hat eigene Sperren/Regeln -> nicht ueberschreiben
  _restoring=true;
  try{
    if(st.f===false && _farbungOn) toggleFarbung();
    if(st.n===true  && !_layersOn) toggleLayers();
    if(st.b===true  && !_bordersOn) toggleBorders();
    if(st.p===true  && !_peaksOn)  togglePeaks();
    if(st.h===true  && !_hutsOn)   toggleHuts();
    if(st.s===true  && !_passesOn) togglePasses();
    if(st.o===true  && !_placesOn) togglePlaces();
    if(st.c===true  && !_cableOn)  toggleCable();
    if(typeof _tracksOn!=='undefined' && st.t===false && _tracksOn) toggleTracks();
  } finally { _restoring=false; }
}

let _layersOn=false;
function toggleLayers(){
  _layersOn=!_layersOn;
  const v=_layersOn?'visible':'none';
  map.setLayoutProperty('sts-label',   'visibility',v);
  map.setLayoutProperty('sts-label-hl','visibility',v);
  document.getElementById('tglNamen').classList.toggle('on',_layersOn);
  persistToggles();
}

// ── Settore-Färbung an/aus (Fill; Fade bleibt beim Reinzoomen) ────────────────
let _farbungOn=true;
function toggleFarbung(){
  _farbungOn=!_farbungOn;
  const v=_farbungOn?'visible':'none';
  map.setLayoutProperty('sts-fill','visibility',v);
  /* PRIV:START */
  // Fix1: im Chronik-Modus die Chrono-Fuellungen mit ein-/ausblenden (Outlines bleiben).
  if(_chronoOn) ['chrono-past','chrono-cur'].forEach(l=>map.setLayoutProperty(l,'visibility',v));
  /* PRIV:END */
  document.getElementById('tglFarbung').classList.toggle('on',_farbungOn);
  persistToggles();
}
// ── Landesgrenzen an/aus ──────────────────────────────────────────────────────
let _bordersOn=false;
function toggleBorders(){
  _bordersOn=!_bordersOn;
  ['borders','country-labels'].forEach(l=>map.setLayoutProperty(l,'visibility',_bordersOn?'visible':'none'));
  document.getElementById('tglBorders').classList.toggle('on',_bordersOn);
  persistToggles();
}

// ── OSM overlays (zuschaltbar, zoom-gated) ────────────────────────────────────
// W1.1: Race-Guard — Toggle vor Layer-Init darf nicht crashen. setLayoutProperty
// nur auf existierende Layer; der Wunsch-Zustand (State-Var) wird nach Layer-Init
// via _syncPointToggles() nachgezogen. Betrifft alle Punkt-Layer (peaks..places/cable).
function _setVis(ids, v){ (Array.isArray(ids)?ids:[ids]).forEach(l=>{ if(map.getLayer(l)) map.setLayoutProperty(l,'visibility',v); }); }
function _syncPointToggles(){
  _setVis(['osm-peaks','osm-landmark-glow','osm-landmarks'], _peaksOn?'visible':'none');
  _setVis(['osm-huts-club','osm-huts-other','osm-huts-wild'], _hutsOn?'visible':'none');
  _setVis(['osm-passes','osm-passes-famous'], _passesOn?'visible':'none');
  _setVis(['places-sq','places-dot','places-label','places-village','places-village-label'], _placesOn?'visible':'none');
  _setVis(['cable-line-halo','cable-line','cable-icon'], _cableOn?'visible':'none');
}
let _peaksOn=false;
function togglePeaks(){
  _peaksOn=!_peaksOn; const v=_peaksOn?'visible':'none';
  _setVis(['osm-peaks','osm-peaks-gold','osm-landmark-glow','osm-landmarks'], v);
  _applyGroupPeaksVis();   // Punkt 3: Gruppen-Gipfel (inkl. Gold) mitschalten, wenn Gruppe gewaehlt
  document.getElementById('tglPeaks').classList.toggle('on',_peaksOn);
  persistToggles();
}
let _hutsOn=false;
function toggleHuts(){
  _hutsOn=!_hutsOn; const v=_hutsOn?'visible':'none';
  _setVis(['osm-huts-club','osm-huts-other','osm-huts-wild'], v);
  document.getElementById('tglHuts').classList.toggle('on',_hutsOn);
  persistToggles();
}
let _passesOn=false;
function togglePasses(){
  _passesOn=!_passesOn; const v=_passesOn?'visible':'none';
  _setVis(['osm-passes','osm-passes-famous'], v);
  document.getElementById('tglPasses').classList.toggle('on',_passesOn);
  persistToggles();
}
// Anreise-Toggles (Orte, Seilbahnen) — default aus, wie die anderen Punkte.
let _placesOn=false;
function togglePlaces(){
  _placesOn=!_placesOn; const v=_placesOn?'visible':'none';
  _setVis(['places-sq','places-dot','places-label','places-village','places-village-label'], v);
  document.getElementById('tglPlaces').classList.toggle('on',_placesOn);
  persistToggles();
}
let _cableOn=false;
function toggleCable(){
  _cableOn=!_cableOn; const v=_cableOn?'visible':'none';
  _setVis(['cable-line-halo','cable-line','cable-icon','chairlift-line','chairlift-ticks'], v);   // ein Toggle: Gondeln + Sessellifte
  document.getElementById('tglCable').classList.toggle('on',_cableOn);
  persistToggles();
}
/* PRIV:START */
// Touren-Tracks (rekonstruierte GPX-Linien) — default AN im Privat-Build.
let _tracksOn=true;
function toggleTracks(){
  _tracksOn=!_tracksOn; const v=_tracksOn?'visible':'none';
  _setVis(['trk-casing','trk-line'], v);
  document.getElementById('tglTracks').classList.toggle('on',_tracksOn);
  persistToggles();
}
/* PRIV:END */

// ── kurzlebiger Hinweis (Toast, kein Modal) ───────────────────────────────────
let _toastT=null;
function showToast(msg){
  const el=document.getElementById('toast'); if(!el) return;
  el.textContent=msg; el.classList.add('show');
  clearTimeout(_toastT); _toastT=setTimeout(()=>el.classList.remove('show'),2600);
}

// ── Basemap: Satellit ⇄ OpenTopoMap — Interim-Gate (SPEC_Vektor_Topo_Overlay) ──
// Topo ist ein Raster für die Draufsicht: nur ab Detail-Zoom, flach, ohne Farb-/
// Namens-Konkurrenz. Punkte + Highlight-Umrisse + Suche bleiben erlaubt.
let _basemap='sat';
let _savedToggles=null, _savedPitch=null;
let _bmPending=null, _bmWaiting=false, _bmLast=0;   // Race/Debounce-Zustand
let _topoFallbackPending=false;                    // W2: Gate-Auto-Rueckfall via once('idle')
function _lockStructureToggles(lock){
  ['tglFarbung','tglNamen'].forEach(id=>{ const el=document.getElementById(id); if(el) el.classList.toggle('locked',lock); });
}
// Öffentlicher Einstieg: Gate + Style-Guard + Debounce; der eigentliche Swap ist atomar.
function setBasemap(bm){
  const topo = bm==='topo';
  // Gate: Topo erst ab z11 aktivierbar — Klick darunter ignorieren + Hinweis.
  if(topo && bm!==_basemap && map.getZoom()<11){ showToast('Topo-Karte ab Detail-Zoom – hineinzoomen'); return; }
  // Race-Guard: Style noch nicht fertig (Klick während des Ladens) ODER Debounce
  // (schneller Mehrfach-Wechsel) -> Ziel merken, EINMAL nach 'idle'/Cooldown nachholen.
  // Verhindert Style-abhängige APIs (setPaintProperty/…) vor "Style is done loading".
  if(!map.isStyleLoaded() || (Date.now()-_bmLast < 300)){
    _bmPending=bm;
    if(!_bmWaiting){
      _bmWaiting=true;
      const retry=()=>{ _bmWaiting=false; const p=_bmPending; _bmPending=null; if(p!=null) setBasemap(p); };
      if(!map.isStyleLoaded()) map.once('idle', retry); else setTimeout(retry, 300);
    }
    return;
  }
  _bmLast=Date.now();
  _applyBasemap(bm, topo);
}
// Atomarer Swap: erst die Style-Ops, dann die dauerhaften Zustände; bei Fehler Rollback.
function _applyBasemap(bm, topo){
  const prev=_basemap, prevSaved=_savedToggles, prevPitch=_savedPitch, prevAuto=_autoPitch;
  try{
    // ── 1) Swap (Style-Ops) ──
    map.setLayoutProperty('sat','visibility',topo?'none':'visible');
    map.setLayoutProperty('topo','visibility',topo?'visible':'none');
    map.setPaintProperty('sts-fill','fill-opacity',
      topo ? ['interpolate',['linear'],['zoom'], 8,0.22, 10.5,0.08, 12,0]
           : ['interpolate',['linear'],['zoom'], 8,0.34, 10.5,0.12, 12,0]);
    map.setPaintProperty('hill','hillshade-exaggeration', topo?0.08:0.25);
    // Toggle-Zustände (ebenfalls Style-Ops) — nur beim echten Moduswechsel.
    if(topo && prev!=='topo'){
      // Färbung+Namen aus (+ gesperrt, s.u.). Punkte default aus, aber NICHT gesperrt.
      _savedToggles={farbung:_farbungOn, namen:_layersOn, peaks:_peaksOn, huts:_hutsOn, passes:_passesOn,
                     places:_placesOn, cable:_cableOn};
      if(_farbungOn) toggleFarbung();
      if(_layersOn)  toggleLayers();
      if(_peaksOn)   togglePeaks();
      if(_hutsOn)    toggleHuts();
      if(_passesOn)  togglePasses();
      if(_placesOn)  togglePlaces();
      if(_cableOn)   toggleCable();
    } else if(!topo && prev==='topo' && _savedToggles){
      if(_savedToggles.farbung && !_farbungOn) toggleFarbung();
      if(_savedToggles.namen  && !_layersOn)  toggleLayers();
      if(_savedToggles.peaks  && !_peaksOn)   togglePeaks();
      if(_savedToggles.huts   && !_hutsOn)    toggleHuts();
      if(_savedToggles.passes && !_passesOn)  togglePasses();
      if(_savedToggles.places && !_placesOn)  togglePlaces();
      if(_savedToggles.cable  && !_cableOn)   toggleCable();
      _savedToggles=null;
    }
    // ── 2) Erst NACH erfolgreichem Swap: dauerhafte Zustände ──
    _basemap=bm;
    _lockStructureToggles(topo);                                  // sperrt nur Färbung+Namen
    if(topo && prev!=='topo'){                                    // Ortho-Zwang
      _savedPitch=map.getPitch(); _autoPitch=false;
      if(map.getPitch()>0.5) map.easeTo({pitch:0, duration:500, essential:true});
    } else if(!topo && prev==='topo'){
      _autoPitch=true;
      if(_savedPitch!=null){ if(_savedPitch>0.5) map.easeTo({pitch:_savedPitch, duration:500, essential:true}); _savedPitch=null; }
    }
    setAttrib(topo);
    const bs=document.getElementById('bmSat'), bt=document.getElementById('bmTopo');
    if(bs) bs.classList.toggle('on',!topo);
    if(bt) bt.classList.toggle('on',topo);
    updateTopoGate();
    updateSky();                                    // §3: Topo -> Himmel aus, Sat -> ggf. an
    try{localStorage.setItem('alpen_basemap',bm);}catch(_){}
  }catch(e){
    console.warn('Basemap-Switch fehlgeschlagen -> Rollback:', e);
    // Best-effort Rollback der dauerhaften/sichtbaren Zustände auf prev.
    _basemap=prev; _savedToggles=prevSaved; _savedPitch=prevPitch; _autoPitch=prevAuto;
    try{
      map.setLayoutProperty('sat','visibility',prev==='topo'?'none':'visible');
      map.setLayoutProperty('topo','visibility',prev==='topo'?'visible':'none');
    }catch(_){}
    _lockStructureToggles(prev==='topo');
    const bs=document.getElementById('bmSat'), bt=document.getElementById('bmTopo');
    if(bs) bs.classList.toggle('on', prev!=='topo');
    if(bt) bt.classList.toggle('on', prev==='topo');
    try{ updateTopoGate(); }catch(_){}
    showToast('Kartenwechsel gerade nicht möglich – bitte erneut versuchen');
  }
}
// Live-Gate: Button unter z11 ausgegraut; im Topo-Modus unter z10 auto zurück zu Satellit.
function updateTopoGate(){
  const bt=document.getElementById('bmTopo'); if(!bt) return;
  const z=map.getZoom(), ok=z>=11;
  bt.classList.toggle('disabled', !ok && _basemap!=='topo');
  bt.title = ok ? '' : 'Topo-Karte ab Detail-Zoom';
  // W2 (Repro 2): Auto-Rueckfall unter z10 NICHT sofort mitten in der Zoom-Geste
  // (Gate-Uebertritt beim schnellen Rauszoomen) -> per once('idle') absichern, dann
  // Bedingung erneut pruefen. Verhindert „Style is not done loading"/Halbzustand.
  if(_basemap==='topo' && z<10 && !_topoFallbackPending){
    _topoFallbackPending=true;
    map.once('idle', ()=>{
      _topoFallbackPending=false;
      if(_basemap==='topo' && map.getZoom()<10){ setBasemap('sat'); showToast('Übersicht – zurück zu Satellit'); }
    });
  }
}

// ══ Suche: Gipfel/Hütten/Pässe/Gruppen + Koordinaten (keyless, client-seitig) ══
const SEARCH_IDX=[];
const SCAT={group:'▦',peak:'▲',hut:'\u{1F3E0}',pass:')(',coord:'\u{1F4CD}',place:'●'};
function sNorm(s){ return (s||'').toLowerCase()
  .replace(/ä/g,'ae').replace(/ö/g,'oe').replace(/ü/g,'ue').replace(/ß/g,'ss')
  .normalize('NFKD').replace(/[̀-ͯ]/g,'')
  // Review-Befund 1: Leerzeichen und alle Bindestrich-/Gedankenstrich-Varianten
  // auf EIN Leerzeichen kollabieren -> "franz senn" == "franz-senn" (Query UND Index).
  .replace(/[\s‐-―-]+/g,' ').trim(); }
function buildSearchIndex(){
  SOIUSA_STS.features.forEach(f=>{
    const p=f.properties, nm=p.name_de||p.STS;
    SEARCH_IDX.push({cat:'group', name:nm, sub:p.settore||'Gruppe', sts:p.STS,
      n:sNorm(nm+' '+(p.STS||'')), w:0, ele:0});
  });
  // Standalone: src ist bereits das GeoJSON-Objekt (kein fetch); sonst URL -> fetch.
  const add=(src,cat,w)=>{
    const use=fc=>{ (fc.features||[]).forEach(f=>{
        const p=f.properties||{}, c=f.geometry&&f.geometry.coordinates;
        if(!p.name||!c) return;
        SEARCH_IDX.push({cat, name:p.name, ele:+p.ele||0, lon:c[0], lat:c[1], n:sNorm(p.name), w}); }); };
    if(typeof src==='string') return fetch(src).then(r=>r.json()).then(use).catch(()=>{});
    if(src) use(src); return Promise.resolve();
  };
  add(OSM_PEAKS  || './soiusa_osm_peaks.geojson','peak',1);
  add(OSM_HUTS   || './soiusa_osm_huts.geojson','hut',2);
  add(OSM_PASSES || './soiusa_osm_passes.geojson','pass',3);
  add(OSM_PLACES || './soiusa_osm_places_v1.geojson','place',4);   // Anreise: Ortssuche (v1: nur city/town)
}
function parseCoord(q){
  q=(q||'').trim(); if(!q) return null;
  const dms=q.match(/(\d{1,3})[°º:\s]+(\d{1,2})['′:\s]*(\d{1,2}(?:\.\d+)?)?["″]?\s*([NSns])[,;\s]+(\d{1,3})[°º:\s]+(\d{1,2})['′:\s]*(\d{1,2}(?:\.\d+)?)?["″]?\s*([EWOewo])/);
  if(dms){
    let lat=(+dms[1])+(+dms[2])/60+(+(dms[3]||0))/3600;
    let lon=(+dms[5])+(+dms[6])/60+(+(dms[7]||0))/3600;
    if(/[sS]/.test(dms[4])) lat=-lat;
    if(/[wW]/.test(dms[8])) lon=-lon;
    return {lat,lon};
  }
  const cleaned=q.replace(/;/g,' ').replace(/(\d),(\d)/g,'$1.$2');
  const nums=cleaned.match(/-?\d+(?:\.\d+)?/g);
  if(nums&&nums.length>=2){
    const lat=parseFloat(nums[0]), lon=parseFloat(nums[1]);
    if(isFinite(lat)&&isFinite(lon)&&Math.abs(lat)<=90&&Math.abs(lon)<=180) return {lat,lon};
  }
  return null;
}
function searchQuery(q){
  const res=[], co=parseCoord(q);
  if(co) res.push({cat:'coord', name:co.lat.toFixed(4)+', '+co.lon.toFixed(4), lat:co.lat, lon:co.lon,
    sub:(co.lat>=43&&co.lat<=49&&co.lon>=4&&co.lon<=17)?'Koordinate':'außerhalb Alpenraum'});
  const qn=sNorm(q.trim());
  if(qn.length>=2){
    const hits=[];
    for(const it of SEARCH_IDX){
      const i=it.n.indexOf(qn); if(i<0) continue;
      hits.push({it, rank: it.n.startsWith(qn)?0:1});
    }
    hits.sort((a,b)=> a.rank-b.rank || a.it.w-b.it.w || (b.it.ele-a.it.ele)
      || a.it.name.localeCompare(b.it.name));
    for(const h of hits.slice(0, co?7:8)) res.push(h.it);
  }
  return res.slice(0,8);
}
// UI
let sCur=[], sSel=-1, _searchMarker=null, _sDeb=null;
const sBox=document.getElementById('search'), sInput=document.getElementById('sInput'),
      sRes=document.getElementById('sRes');
function toggleSearch(){ sBox.classList.contains('open')?closeSearch():openSearch(); }
function openSearch(){ sBox.classList.add('open'); sInput.focus(); }
function closeSearch(){ sBox.classList.remove('open'); sRes.style.display='none'; sRes.innerHTML='';
  sCur=[]; sSel=-1; }
function clearSearchMarker(){ if(_searchMarker){ _searchMarker.remove(); _searchMarker=null; } }
function renderResults(list){
  sCur=list; sSel=-1;
  if(!list.length){ sRes.style.display='none'; sRes.innerHTML=''; return; }
  sRes.innerHTML=list.map((r,i)=>{
    const sub = r.cat==='peak'||r.cat==='hut' ? (r.ele?r.ele+' m':'')
      : r.cat==='group' ? (r.sub||'Gruppe') : r.cat==='pass' ? 'Pass'
      : r.cat==='place' ? 'Ort' : (r.sub||'');
    return '<div class="sr" data-i="'+i+'"><span class="ic">'+(SCAT[r.cat]||'')+'</span>'+
      '<span class="nm">'+String(r.name||'').replace(/</g,'&lt;')+'</span>'+
      (sub?'<span class="sb">'+sub+'</span>':'')+'</div>';
  }).join('');
  sRes.style.display='block';
  [...sRes.children].forEach(el=>el.addEventListener('click',()=>pickResult(+el.dataset.i)));
}
function pickResult(i){
  const r=sCur[i]; if(!r) return;
  clearSearchMarker();
  if(r.cat==='group'){
    const f=SOIUSA_STS.features.find(x=>x.properties.STS===r.sts); if(f) openSts(f, 'force');
  } else if(r.cat==='coord'){
    _searchMarker=new maplibregl.Marker({color:'#5fd0c5'}).setLngLat([r.lon,r.lat]).addTo(map);
    saveUndo(); map.flyTo({center:[r.lon,r.lat], zoom:13, duration:1200, essential:true}); showUndoChip();
  } else if(r.cat==='hut'){
    // W1.4: Hütten-Treffer öffnet direkt das enrichte Hütten-Kärtchen (HUTS_WIKI/
    // HUT_VISITS/Seilbahn-Chip über den OSM-Namen), nicht nur flyTo.
    if(_basemap!=='topo' && !_hutsOn) toggleHuts();
    saveUndo(); map.flyTo({center:[r.lon,r.lat], zoom:12.5, duration:1200, essential:true}); showUndoChip();
    closeAllPopups();
    hutPopup.setLngLat([r.lon,r.lat]).setHTML(hutPopupHtml({name:r.name, ele:r.ele})).addTo(map);
  } else {
    // Fix7: Treffer-Kontext — passenden Punkt-Toggle aktivieren (Nachbargipfel/-huetten
    // sichtbar), NICHT im Topo-Modus (dort bleibt das Punkte-Verhalten wie es ist).
    if(_basemap!=='topo'){
      if(r.cat==='peak' && !_peaksOn) togglePeaks();
      else if(r.cat==='pass' && !_passesOn) togglePasses();
      else if(r.cat==='place' && !_placesOn) togglePlaces();
    }
    saveUndo(); map.flyTo({center:[r.lon,r.lat], zoom:12.5, duration:1200, essential:true}); showUndoChip();
    new maplibregl.Popup({offset:12, closeButton:true})
      .setLngLat([r.lon,r.lat])
      .setHTML('<div class="hp-n">'+String(r.name||'').replace(/</g,'&lt;')+'</div>'+
        (r.ele?'<div class="hp-s">'+r.ele+' m</div>':''))
      .addTo(map);
  }
  closeSearch();
}
function sHi(){ [...sRes.children].forEach((el,i)=>el.classList.toggle('sel',i===sSel));
  if(sRes.children[sSel]) sRes.children[sSel].scrollIntoView({block:'nearest'}); }
if(sInput){
  sInput.addEventListener('input',()=>{ clearTimeout(_sDeb);
    _sDeb=setTimeout(()=>renderResults(searchQuery(sInput.value)),150); });
  sInput.addEventListener('keydown',e=>{
    if(e.key==='Escape'){ closeSearch(); sInput.blur(); clearSearchMarker(); }
    else if(e.key==='ArrowDown'){ e.preventDefault(); sSel=Math.min(sSel+1,sCur.length-1); sHi(); }
    else if(e.key==='ArrowUp'){ e.preventDefault(); sSel=Math.max(sSel-1,0); sHi(); }
    else if(e.key==='Enter'){ e.preventDefault(); if(sCur.length) pickResult(sSel<0?0:sSel); }
  });
}

function closePanel(){
  stsPopup.remove();
  document.getElementById('panel').classList.remove('open');
  if(window.highlightTrack) highlightTrack(null);   // Track-Hervorhebung zuruecksetzen
  map.setFilter('sts-selected',['==',['get','STS'],'']);
  _selSts=''; updateStsLabelFilter();   // B4: Gruppennamen wieder alle einblenden
  resetGroupPeaks();
  /* PRIV:START */
  // P1/P2: Chronik-Auswahlrahmen räumen, Zeilen-Highlight zurück, Master-Detail-Klasse ab.
  // try/catch schützt vor TDZ, falls closePanel vor der Coverage-Block-Init einmal früh läuft.
  document.getElementById('panel').classList.remove('as-cov');
  document.getElementById('panel').classList.remove('has-back');
  try{ clearChronoSel(); _selTourId=null; markSelTourRow(); emphasizeTour(null); }catch(_){}
  /* PRIV:END */
}
function overview(){
  closePanel();
  _autoPitch=true;
  map.flyTo({...ALPS,duration:1200,essential:true});
}
// §6b (W4): „Letzte Ansicht"-Chip nach automatischem Kamerasprung (Gruppen-flyTo,
// Suchtreffer). Stellt die vorherige Kamera-Pose wieder her; verschwindet nach ~8 s
// oder bei Nutzer-Interaktion (movestart mit originalEvent).
let _undoPose=null, _undoT=null, _undoFadeT=null;
function saveUndo(){ _undoPose={center:map.getCenter(),zoom:map.getZoom(),bearing:map.getBearing(),pitch:map.getPitch()}; }
function _hideUndoChip(){
  const el=document.getElementById('undoChip'); if(!el) return;
  el.classList.remove('show');                       // Fade -> 0
  clearTimeout(_undoT); clearTimeout(_undoFadeT);
  _undoFadeT=setTimeout(()=>{ el.style.pointerEvents='none'; }, 300);  // erst NACH Fade klick-durchlaessig
}
function showUndoChip(){
  const el=document.getElementById('undoChip'); if(!el||!_undoPose) return;
  clearTimeout(_undoFadeT); el.style.pointerEvents='auto';
  el.classList.add('show'); clearTimeout(_undoT); _undoT=setTimeout(_hideUndoChip,12000);  // Fix6: 12 s
}
function restoreUndo(e){
  if(e) e.stopPropagation();                          // Fix6: kein Durchreichen zur Karte
  _hideUndoChip();
  if(_undoPose){ _autoPitch=false; map.easeTo({center:_undoPose.center,zoom:_undoPose.zoom,
    bearing:_undoPose.bearing,pitch:_undoPose.pitch,duration:800,essential:true}); _undoPose=null; }
}
map.on('movestart', e=>{ if(e && e.originalEvent){ _hideUndoChip(); _autoCollapseTitle(); } });   // P1.2: erste Interaktion klappt Title-Card ein
map.on('click', ()=>_autoCollapseTitle());

// ── Coverage list + Tour-Filter (private build only) ──────────────────────────
/* PRIV:START */
// SPEC_Personenfilter: EIN Zustand FILTER + EINE Filter-Funktion schaltet
// Liste (filtern, Jahre auf Treffer reduzieren) · Karte (Marker/Tracks dimmen) ·
// Kopf-Bilanz · Chronik konsistent. Kein localStorage, Default Alle/leer.
const _e = s => String(s==null?'':s).replace(/[<>&]/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;'}[c]));
function openGroup(sts){ const f=SOIUSA_STS.features.find(x=>x.properties.STS===sts); if(f) openSts(f); }
// Befund 3: Gipfel-Popup light (Name · Höhe · Zeile „<Gruppe> öffnen →").
function peakPopupHtml(name, ele, sts, gname){
  let h='<div class="pk-pop"><div class="pk-name">'+_e(name)+'</div>';
  if(ele) h+='<div class="pk-ele">'+_e(ele)+'</div>';
  if(sts) h+='<div class="pk-grp" onclick="peakOpenGroup(\''+sts+'\')">'+_e(gname||'Gebirgsgruppe')+' öffnen &rarr;</div>';
  return h+'</div>';
}
function peakOpenGroup(sts){ try{ document.querySelectorAll('.maplibregl-popup').forEach(el=>el.remove()); }catch(_){ } openGroup(sts); }
function _groupTourIds(g){ return typeof g.tour_ids==='string'?JSON.parse(g.tour_ids||'[]'):(g.tour_ids||[]); }

// Register-Lookup + Personen-Häufigkeit (alle teilnehmer_ids). Chip-Liste: nur
// filterbar!=false und Zähler>0, Häufigkeit absteigend (Tie-Break Name). Chip-Name
// = Register-name (kanonischer Anzeigename).
const PERSON_BY_ID={}; (PERSONEN.personen||[]).forEach(p=>{ PERSON_BY_ID[p.id]=p; });
const _personFreq={};
TOUREN.forEach(t=>(t.teilnehmer_ids||[]).forEach(id=>{ _personFreq[id]=(_personFreq[id]||0)+1; }));
const CHIP_PERSONS=Object.keys(_personFreq)
  .filter(id=>{ const p=PERSON_BY_ID[id]; return p && p.filterbar!==false && _personFreq[id]>0; })
  .map(id=>({id, name:PERSON_BY_ID[id].name, n:_personFreq[id]}))
  .sort((a,b)=> b.n-a.n || String(a.name).localeCompare(String(b.name)));

// Strang: fester Schnitt, EINMALIG abgeleitet aus kategorie.
function serieOf(t){ return __PT_STRANG_CATS__.includes(t.kategorie)?'brueder':'weitere'; }
const _strangCount={alle:TOUREN.length, brueder:0, weitere:0};
TOUREN.forEach(t=>{ _strangCount[serieOf(t)]++; });
{ const set=(id,v)=>{ const e=document.getElementById(id); if(e) e.textContent=v; };
  set('cntAlle',_strangCount.alle); set('cntBrueder',_strangCount.brueder); set('cntWeitere',_strangCount.weitere); }

// P3a: EIN Filterzustand F = Strang × Personen (UND) × Jahr [von–bis].
const YEAR_MIN=Math.min(...TOUREN.map(t=>jahrSort(t.jahr)).filter(v=>v!=null));
const YEAR_MAX=Math.max(...TOUREN.map(t=>jahrSort(t.jahr)).filter(v=>v!=null));
const FILTER={strang:'alle', personen:[], jahrVon:YEAR_MIN, jahrBis:YEAR_MAX};
let _filterIds=null;   // null = Filter inaktiv (Karte voll); sonst Treffer-tour_id-Liste
function jahrDefault(){ return FILTER.jahrVon<=YEAR_MIN && FILTER.jahrBis>=YEAR_MAX; }
function filterActive(){ return FILTER.strang!=='alle' || FILTER.personen.length>0 || !jahrDefault(); }
function matchedTours(){
  return TOUREN.filter(t=>{
    if(FILTER.strang!=='alle' && serieOf(t)!==FILTER.strang) return false;
    if(FILTER.personen.length){                        // Mehrfachauswahl = UND (gemeinsam unterwegs)
      const ids=t.teilnehmer_ids||[];
      if(!FILTER.personen.every(p=>ids.includes(p))) return false;
    }
    const y=jahrSort(t.jahr);
    if(y!=null && (y<FILTER.jahrVon || y>FILTER.jahrBis)) return false;   // Jahr-Range
    return true;
  });
}
// STS-Codes der Gebiete mit >=1 Treffer-Tour (für hl-line-Kontur).
function _matchedGroupSTS(idSet){
  const s=[]; visitedGroups.forEach(g=>{ if(_groupTourIds(g).some(id=>idSet.has(id))) s.push(g.STS); }); return s;
}
// ── Karte folgt F: Wanderer-Icons + Tracks ausgefilterter Touren AUSBLENDEN (setFilter),
// Besucht-Kontur (hl-line) nur für Gebiete mit Treffer; Flächen bleiben (gedimmt via fehlende Kontur). ──
// Marker-Filter = F (Treffer-ids) UND, bei z<9, „multi!=1" (Multi-Gebiets-Touren clustern).
function _markerFilter(ids, active){
  const parts=[];
  if(active) parts.push(['in',['get','id'],['literal',ids]]);
  try{ if(map && map.getZoom && map.getZoom()<9) parts.push(['!=',['get','multi'],1]); }catch(_){}
  return parts.length===0?null:(parts.length===1?parts[0]:['all',...parts]);
}
function _applyMapFilter(ids, active){
  try{
    if(!map || !map.getLayer) return;
    const mf = _markerFilter(ids, active);
    ['t-halo','t-badge','t-hit','t-dot','t-label'].forEach(l=>{ if(map.getLayer(l)) map.setFilter(l, mf); });
    const tf = active ? ['in',['get','tour_id'],['literal',ids]] : null;
    ['trk-line','trk-casing','trk-hit'].forEach(l=>{ if(map.getLayer(l)) map.setFilter(l, tf); });
    if(map.getLayer('hl-line')){
      const g = active ? _matchedGroupSTS(new Set(ids)) : null;
      map.setFilter('hl-line', g ? ['in',['get','parent_sts'],['literal',g]] : null);
    }
  }catch(_){}
}
function _trackBaseOpacity(which){ return which==='casing'?0.55:0.95; }   // F blendet aus (setFilter), kein Opazitäts-Dim mehr
// Filter-Persistenz (P3a.5): F wie die Ebenen-Toggles in localStorage.
function persistFilter(){ try{ localStorage.setItem('alpen_filter', JSON.stringify(FILTER)); }catch(_){} }
function restoreFilter(){ try{ const f=JSON.parse(localStorage.getItem('alpen_filter')||'null'); if(f){
    FILTER.strang = (f.strang==='brueder'||f.strang==='weitere')?f.strang:'alle';
    FILTER.personen = Array.isArray(f.personen)?f.personen.filter(id=>CHIP_PERSONS.some(p=>p.id===id)):[];
    FILTER.jahrVon = Math.max(YEAR_MIN, Math.min(+f.jahrVon||YEAR_MIN, YEAR_MAX));
    FILTER.jahrBis = Math.max(FILTER.jahrVon, Math.min(+f.jahrBis||YEAR_MAX, YEAR_MAX));
  } }catch(_){} }

// ── UI-Render: Chips, Badges, Liste, Kopf-Bilanz ──
function renderChips(){
  const wrap=document.getElementById('personChips'); if(!wrap) return;
  wrap.innerHTML=CHIP_PERSONS.map(p=>{
    const on=FILTER.personen.includes(p.id)?' on':'';
    return '<button class="tf-chip'+on+'" data-id="'+_e(p.id)+'" onclick="togglePerson(\''+_e(p.id)+'\')">'+
      _e(p.name)+' <span class="n">'+p.n+'</span></button>';
  }).join('');
}
// P3a: Filter-Bilanzzeile (Strang · Personen · Jahr-Range -> N Touren ✕); ✕ resettet F komplett.
// Beschreibung des aktiven Filters (Tourentyp · Personen · Jahre) — für Bilanzzeile
// UND die Chronik-Filter-Zeile (Befund 10).
function _filterLabelText(){
  const parts=[];
  if(FILTER.strang==='brueder') parts.push('Br&uuml;dertouren');
  else if(FILTER.strang==='weitere') parts.push('Weitere Touren');
  FILTER.personen.map(id=>PERSON_BY_ID[id]).filter(Boolean).forEach(p=>parts.push(_e(p.name)));
  if(!jahrDefault()) parts.push(FILTER.jahrVon===FILTER.jahrBis?String(FILTER.jahrVon):FILTER.jahrVon+'&ndash;'+FILTER.jahrBis);
  return parts.join(' &middot; ');
}
function renderBilanz(){
  const el=document.getElementById('filterBadges'); if(!el) return;
  if(!filterActive()){ el.innerHTML=''; return; }
  const n=matchedTours().length;
  el.innerHTML='<span class="tf-bilanz-txt">'+_filterLabelText()+' &rarr; '+n+(n===1?' Tour':' Touren')+'</span>'+
    '<button class="tf-reset" onclick="resetFilter()" title="Filter zur&uuml;cksetzen" aria-label="Zur&uuml;cksetzen">&times;</button>';
}
// ── Jahr-Range-Slider (Doppelgriff, YEAR_MIN..YEAR_MAX aus Daten, von=bis erlaubt) ──
function _yearSliderInit(){
  const von=document.getElementById('tfJahrVon'), bis=document.getElementById('tfJahrBis'); if(!von||!bis) return;
  [von,bis].forEach(s=>{ s.min=YEAR_MIN; s.max=YEAR_MAX; s.step=1; });
  _yearSliderSync();
  const upd=(from)=>{
    let a=+von.value, b=+bis.value;
    if(a>b){ if(from==='von'){ b=a; bis.value=b; } else { a=b; von.value=a; } }   // von=bis erlaubt
    FILTER.jahrVon=a; FILTER.jahrBis=b; applyTourFilter();
  };
  von.oninput=()=>upd('von'); bis.oninput=()=>upd('bis');
  _yearSliderPaint();
}
function _yearSliderSync(){   // Input-Werte aus FILTER (nach Reset/Restore)
  const von=document.getElementById('tfJahrVon'), bis=document.getElementById('tfJahrBis');
  if(von) von.value=FILTER.jahrVon; if(bis) bis.value=FILTER.jahrBis;
}
function _yearSliderPaint(){
  const fill=document.getElementById('tfJahrFill'), val=document.getElementById('tfJahrVal');
  const span=(YEAR_MAX-YEAR_MIN)||1;
  const l=(FILTER.jahrVon-YEAR_MIN)/span*100, r=(FILTER.jahrBis-YEAR_MIN)/span*100;
  if(fill){ fill.style.left=l+'%'; fill.style.width=Math.max(0,r-l)+'%'; }
  if(val) val.textContent=FILTER.jahrVon===FILTER.jahrBis?String(FILTER.jahrVon):FILTER.jahrVon+'–'+FILTER.jahrBis;
}
// P1: EINE Zeile pro Tour (chronologisch aufsteigend, Tie-Break gegend). Gebiete
// erscheinen mehrfach (Tagebuch-Logik). Strang/Personen-Chips filtern die Zeilen.
let _selTourId=null;    // im Steckbrief geöffnete Tour (Zeilen-Highlight)
let _pendingTour=null;  // P2: im Steckbrief aufzuklappende Tour-Karte
let _covScroll=0;       // P2: Scrollposition der Liste (für Rückkehr aus dem Steckbrief)
// P2: aus dem Steckbrief zurück zur Liste (Scrollposition + Filter bleiben erhalten).
function backToList(){
  const pnl=document.getElementById('panel'); if(!pnl.classList.contains('open')) return;
  const wasList=pnl.classList.contains('has-back');
  closePanel();
  if(wasList){
    const cov=document.getElementById('cov'); cov.classList.add('open'); sizeCov();
    const cl=cov.querySelector('.cl'); if(cl) cl.scrollTop=_covScroll||0;
  }
}
function renderCovList(){
  const cl=document.getElementById('covList'), empty=document.getElementById('covEmpty'); if(!cl) return;
  const active=filterActive();
  const tours=(active?matchedTours():TOUREN.slice())
    .sort((a,b)=> (jahrSort(a.jahr)||0)-(jahrSort(b.jahr)||0)
               || String(a.gegend||a.gebirge||'').localeCompare(String(b.gegend||b.gebirge||'')));
  cl.innerHTML=tours.map(t=>{
    const yr=_e(String(t.jahr||'')), geb=_e(t.gegend||t.gebirge||''), kat=_e(katOf(t));
    const kc=serieOf(t)==='brueder'?' br':'';
    const sel=t.id===_selTourId?' sel':'';
    return '<div class="trow'+sel+'" data-tid="'+t.id+'" onclick="openTourRow('+t.id+')">'+
      '<span class="tyr">'+yr+'</span><span class="tgeb">'+geb+'</span>'+
      '<span class="tkat'+kc+'">'+kat+'</span></div>';
  }).join('');
  if(empty){
    if(active && !tours.length){
      empty.innerHTML='Keine gemeinsame Tour mit dieser Auswahl. '+
        '<button class="tf-reset" onclick="resetFilter()">&times; Zur&uuml;cksetzen</button>';
      empty.style.display='';
    } else empty.style.display='none';
  }
}
// Zeilen-Klick: Steckbrief der SOIUSA-Gruppe dieser Tour öffnen (P2: mit Tour-Karte aufgeklappt).
function openTourRow(tid){
  const t=TOUREN.find(x=>x.id==tid); if(!t) return;
  _selTourId=tid; _pendingTour=tid; markSelTourRow();
  const f=_groupFeatureOfTour(tid);
  if(f) openSts(f);
  else { closeAllPopups(); if(t.lon!=null&&t.lat!=null){ saveUndo(); map.flyTo({center:[t.lon,t.lat],zoom:9,pitch:18,essential:true}); showUndoChip(); } }
}
function _groupFeatureOfTour(tid){
  return SOIUSA_STS.features.find(x=>{
    if(x.properties.visited!==1) return false;
    let ids=[]; try{ ids = typeof x.properties.tour_ids==='string'?JSON.parse(x.properties.tour_ids||'[]'):(x.properties.tour_ids||[]); }catch(_){}
    return ids.some(v=>String(v)===String(tid));
  });
}
function markSelTourRow(){
  document.querySelectorAll('#covList .trow').forEach(r=>r.classList.toggle('sel', +r.dataset.tid===_selTourId));
}
// P3b §7: selektierte (aufgeklappte) Tour betonen — ihr Icon+Track heller, andere
// Icons DESSELBEN Gebiets gedimmt. id=null hebt auf (Basis-Deckkraft).
function _selGroupTourIds(){
  if(!_selSts) return [];
  const f=SOIUSA_STS.features.find(x=>x.properties.STS===_selSts);
  return f?_groupTourIds(f.properties):[];
}
function emphasizeTour(id){
  try{
    if(!map||!map.getLayer||!map.getLayer('t-dot')) return;
    if(id==null){
      map.setPaintProperty('t-dot','icon-opacity',1);
      map.setPaintProperty('t-halo','circle-opacity',0.20);
      map.setPaintProperty('t-badge','circle-opacity',0.96);
      highlightTrack(null); return;
    }
    const others=_selGroupTourIds().filter(x=>x!==id);
    const dim=['in',['get','id'],['literal',others]], sel=['==',['get','id'],id];
    map.setPaintProperty('t-dot','icon-opacity',['case',sel,1,dim,0.22,1]);
    map.setPaintProperty('t-halo','circle-opacity',['case',sel,0.42,dim,0.05,0.20]);   // Glow auf selektierter
    map.setPaintProperty('t-badge','circle-opacity',['case',sel,1,dim,0.25,0.96]);
    highlightTrack(id);   // Track der selektierten Tour betont (0.25 für die übrigen)
  }catch(_){}
  // P2.7: bei z<9 das Cluster-Icon des offenen Gebiets betonen (weißer Rand, größer).
  try{ if(map.getLayer('t-cluster-badge')){
    const g=(id!=null&&_selSts)?_selSts:'__none__';
    map.setPaintProperty('t-cluster-badge','circle-stroke-color',['case',['==',['get','sts'],g],'#ffffff','#c76a1a']);
    map.setPaintProperty('t-cluster-badge','circle-stroke-width',['case',['==',['get','sts'],g],3,2]);
    map.setPaintProperty('t-cluster-halo','circle-opacity',['case',['==',['get','sts'],g],0.4,0.22]);
  } }catch(_){}
}

// P1: Personen-Chip-Grid ein-/ausklappen (Default zu; Zustand in localStorage; aktive
// Auswahl bleibt über die Badge-Zeile sichtbar/abwählbar).
function togglePersGrid(){
  const cov=document.getElementById('cov'); if(!cov) return;
  const open=cov.classList.toggle('pers-open');
  try{ localStorage.setItem('alpen_pers_open', open?'1':'0'); }catch(_){}
  sizeCov();
}
// Politur P1.4: Filter-Block als Ganzes ein-/ausklappen (Default offen; localStorage).
function toggleFilterBlock(){
  const cov=document.getElementById('cov'); if(!cov) return;
  const open=cov.classList.toggle('filter-open');
  try{ localStorage.setItem('alpen_filter_open', open?'1':'0'); }catch(_){}
  sizeCov();
}
// #cov-Kopf: auf-/zuklappen + Höhe neu messen.
function toggleCov(){
  const cov=document.getElementById('cov'); if(!cov) return;
  if(cov.classList.toggle('open')) sizeCov();
}
// Panel-Höhe bis knapp über die Chronoleiste (kein Overlap mit Title-Card) -> --cov-max.
function sizeCov(){
  const cov=document.getElementById('cov'); if(!cov) return;
  const phone=window.matchMedia && window.matchMedia('(max-width:640px)').matches;
  let avail;
  if(phone){ avail=Math.round(window.innerHeight*0.72); }
  else{
    const tc=document.getElementById('title');
    const top=(tc?tc.getBoundingClientRect().bottom:80)+12;
    const rowH=parseInt(getComputedStyle(document.documentElement).getPropertyValue('--row-h'))||32;
    avail=window.innerHeight-top-(rowH+104);   // Chrono-Button/-Caption + Ränder
  }
  cov.style.setProperty('--cov-max', Math.max(140, avail-44)+'px');   // 44 = Kopfzeile
}
window.addEventListener('resize', sizeCov);

// P1: Chronik-Sync — offenes Gebiet markiert seine Jahres-Chips (teal Ring, chsel),
// OHNE den Play-Cursor (.on) zu bewegen. Deselect/Esc räumt die Rahmen.
function clearChronoSel(){ document.querySelectorAll('#chronoChips .chip.chsel').forEach(c=>c.classList.remove('chsel')); }
function markChronoGroupYears(props){
  clearChronoSel(); if(!props) return;
  const yrs=new Set(_toursOf(props).map(t=>jahrSort(t.jahr)).filter(Boolean));
  document.querySelectorAll('#chronoChips .chip').forEach(c=>{
    const y=CHRONO.years[+c.dataset.i]; if(yrs.has(y)) c.classList.add('chsel');
  });
}
// Init: Chip-Grid + Filter-Block-Zustand aus localStorage; #cov-Höhe initial messen.
(function(){
  const cov=document.getElementById('cov'); if(!cov) return;
  let pv='0'; try{ pv=localStorage.getItem('alpen_pers_open')||'0'; }catch(_){}
  if(pv==='1') cov.classList.add('pers-open');
  let fv='1'; try{ const s=localStorage.getItem('alpen_filter_open'); if(s!==null) fv=s; }catch(_){}
  if(fv==='1') cov.classList.add('filter-open');   // Default: Filter-Block offen
})();
// P2: Esc-Kaskade — Steckbrief -> Liste (backToList), Liste -> Panel zu. Lightbox/Suche haben Vorrang.
document.addEventListener('keydown', e=>{
  if(e.key!=='Escape') return;
  const lb=document.getElementById('lightbox'); if(lb && lb.classList.contains('open')) return;
  const s=document.getElementById('search'); if(s && s.classList.contains('open')) return;
  const pnl=document.getElementById('panel');
  if(pnl && pnl.classList.contains('open')){
    if(pnl.classList.contains('has-back')) backToList(); else closePanel();
    return;
  }
  const cov=document.getElementById('cov');
  if(cov && cov.classList.contains('open')) cov.classList.remove('open');
});
function updateCovCount(tours){
  const el=document.getElementById('covCount'); if(!el) return;
  if(!filterActive()){
    el.textContent=SOIUSA_HIGHLIGHTS.features.length+' Gebiete · '+TOUREN.length+' Touren';
    return;
  }
  const idSet=new Set(tours.map(t=>t.id));
  let nGeb=0; visitedGroups.forEach(g=>{ if(_groupTourIds(g).some(id=>idSet.has(id))) nGeb++; });
  const word={brueder:'__PT_LBL_BRUEDER__', weitere:'__PT_LBL_WEITERE_S__'}[FILTER.strang];
  el.textContent=(word?word+' · ':'')+tours.length+' Touren · '+nGeb+' Gebiete';
}

// ── Die EINE Schaltfunktion: schaltet alle Sichten konsistent (F = Strang×Personen×Jahr) ──
function applyTourFilter(){
  const tours=matchedTours();
  const ids=tours.map(t=>t.id);
  const active=filterActive();
  _filterIds=active?ids:null;
  _applyMapFilter(ids, active);      // Karte: Icons/Tracks ausblenden, Kontur nur Treffer-Gebiete
  document.querySelectorAll('#strangSeg .tf-sbtn')
    .forEach(b=>b.classList.toggle('on', b.dataset.strang===FILTER.strang));
  renderChips(); renderBilanz(); _yearSliderPaint();
  renderCovList(); updateCovCount(tours);   // Liste = Ergebnisfläche (filtern), Kopf = Bilanz
  _chronoRefilter();                 // Chronik-Jahresleiste/Play folgt F (inkl. Jahr)
  persistFilter();
}
function setStrang(s){ FILTER.strang=s; applyTourFilter(); }
function togglePerson(id){
  const i=FILTER.personen.indexOf(id);
  if(i>=0) FILTER.personen.splice(i,1); else FILTER.personen.push(id);
  applyTourFilter();
}
function resetFilter(){
  FILTER.strang='alle'; FILTER.personen=[]; FILTER.jahrVon=YEAR_MIN; FILTER.jahrBis=YEAR_MAX;
  _yearSliderSync(); applyTourFilter();
}
// Chronik bei Filterwechsel neu ableiten: Jahresleiste/Färbung aus der gefilterten
// Menge, Chips neu; laufender Modus auf gültigen Jahr-Index geclamped
// (chrono-cur-Clamp-Altlast). Wird auch beim Initial-Render aufgerufen.
function _chronoRefilter(){
  CHRONO = buildChrono(matchedTours());
  chronoBuildChips();
  if(!_chronoOn) return;
  if(!CHRONO.years.length){                 // Auswahl ohne Jahre: Färbung/Caption leeren
    ['chrono-past','chrono-cur','chrono-cur-line','chrono-cur-name']
      .forEach(l=>{ try{ map.setFilter(l,['in',['get','STS'],['literal',[]]]); }catch(_){} });
    _chronoIdx=-1;
    const cap=document.getElementById('chronoCap');
    if(cap) cap.innerHTML='<div class="cc-t">Keine Tour in dieser Auswahl.</div>';
    return;
  }
  _chronoIdx=Math.min(Math.max(0,_chronoIdx), CHRONO.years.length-1);   // Clamp auf gültigen Index
  chronoSetYear(_chronoIdx,{fly:false});
}

// Initial-Render (applyTourFilter) erfolgt am Ende des Chronik-Blocks — erst dort ist
// CHRONO/_chronoOn initialisiert, sonst TDZ in _chronoRefilter.
/* PRIV:END */

// ══ Chronologie-Modus (nur Privat) — Stufe 1: Jahresleiste + kumulative Färbung ══
/* PRIV:START */
function jahrSort(j){ const m=String(j==null?'':j).match(/\d{4}/); return m?+m[0]:null; }
// buildChrono(tours): Jahresleiste + Färbung aus einer (ggf. gefilterten) Tour-Menge.
// stsYears = Treffer-Jahre je STS-Gruppe, geschnitten mit der Menge; years/yearTours nur
// Jahre mit Treffer. Bei Filterwechsel neu berechnet (_chronoRefilter).
function buildChrono(tours){
  const idSet=new Set(tours.map(t=>t.id));
  const tourById={}; tours.forEach(t=>{ tourById[t.id]=t; });
  // Färbung folgt der Gruppen-Zuordnung (tour_ids), geschnitten mit der gefilterten Menge.
  const stsYears={};
  SOIUSA_STS.features.forEach(f=>{
    const p=f.properties; if(p.visited!==1) return;
    let ids=[]; try{ ids = typeof p.tour_ids==='string'?JSON.parse(p.tour_ids||'[]'):(p.tour_ids||[]); }catch(_){}
    const ys=new Set();
    ids.forEach(id=>{ if(!idSet.has(id)) return; const t=tourById[id]; const y=t&&jahrSort(t.jahr); if(y) ys.add(y); });
    if(ys.size) stsYears[p.STS]=[...ys];
  });
  // Jahresleiste = Jahre der (gefilterten) Touren, auch wenn eine Tour (noch) keiner
  // STS-Gruppe zugeordnet ist -> Chip erscheint, Färbung ggf. leer.
  const yearMeta={}, yearTours={};
  tours.forEach(t=>{ const y=jahrSort(t.jahr); if(!y) return;
    if(!yearMeta[y]) yearMeta[y]={label:String(t.jahr), unsure:!!t.jahr_unsicher};
    if(t.jahr_unsicher) yearMeta[y].unsure=true;
    (yearTours[y]=yearTours[y]||[]).push(t); });
  const years=Object.keys(yearMeta).map(Number).sort((a,b)=>a-b);
  return {stsYears, years, yearMeta, yearTours};
}
let CHRONO = buildChrono(TOUREN);   // let: bei Filterwechsel neu zugewiesen

let _chronoOn=false, _chronoIdx=-1, _chronoSaved=null;
let _chronoPlaying=false, _chronoTimer=null, _chronoFallback=null, _pulseRAF=null;
// B1b: Play-Takt = dynamischer Flug (speed-basiert) + feste Lese-Pause nach Ankunft.
// Live kalibrierbar (schneller: SPEED hoch / DWELL runter).
const CHRONO_SPEED=1.5;        // flyTo-speed (Default 1.2; hoeher = zuegiger)
const CHRONO_DWELL=1300;       // ms Lese-Pause nach Ankunft, bevor das naechste Jahr laeuft
// Fix1: Chrono-Fuellungen zoom-interpoliert wie sts-fill (beim Reinzoomen freie Sicht),
// aktuelles Jahr kraeftiger als frueher besuchte.
const CHRONO_CUR_OP  = ['interpolate',['linear'],['zoom'], 8,0.62, 10.5,0.22, 12,0];
const CHRONO_PAST_OP = ['interpolate',['linear'],['zoom'], 8,0.30, 10.5,0.10, 12,0];
function _esc(s){ return String(s==null?'':s).replace(/[<>&]/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;'}[c])); }

// Caption: Jahr groß (Original-String) + datum · je Tour ort/gegend — Gipfel · Teilnehmer (kursiv).
function chronoCaption(Y){
  const cap=document.getElementById('chronoCap'); if(!cap) return;
  const meta=CHRONO.yearMeta[Y]||{}, ts=CHRONO.yearTours[Y]||[];
  const datums=[...new Set(ts.map(t=>t.datum).filter(Boolean))];
  let h='';
  // Befund 10: aktiver Filter dezent an der Caption (Mitte, ✕ wie Bilanzzeile).
  try{ if(typeof filterActive==='function' && filterActive())
    h+='<div class="cc-filter">Filter: '+_filterLabelText()+
       ' <button class="cc-fx" onclick="event.stopPropagation();resetFilter()" title="Filter zur&uuml;cksetzen" aria-label="Filter zur&uuml;cksetzen">&times;</button></div>'; }catch(_){}
  h+='<div class="cc-h"><span class="cc-y">'+_esc(meta.label||Y)+'</span>'+
        (datums.length?'<span class="cc-d">'+_esc(datums.join(' · '))+'</span>':'')+'</div>';
  h+=ts.map(t=>{
    const loc=_esc(t.ort||t.gegend||'');
    const gip=(Array.isArray(t.gipfel)?t.gipfel:[]).map(g=>_esc(g&&g.name)).filter(Boolean).join(', ');
    const parts=[]; if(loc) parts.push(loc); if(gip) parts.push(gip);
    const who=t.teilnehmer?' · <span class="cc-who">'+_esc(t.teilnehmer)+'</span>':'';
    // Stufe 3 / W1b: Memo-Vorschau (~100 Zeichen); „… mehr" -> Tour-Panel mit Volltext.
    const memo=(t.memo||'').trim();
    let mp='';
    if(memo){
      const trunc=memo.length>100;
      const prev=trunc?_esc(memo.slice(0,100).replace(/\s+\S*$/,'')):_esc(memo);
      mp='<div class="cc-memo" onclick="openTourPanel('+t.id+')">'+prev+
         (trunc?'&hellip; <span class="cc-more">mehr</span>':'')+'</div>';
    }
    // Foto-Thumb (erstes Foto) links neben der Memo-Vorschau; Tap -> Lightbox.
    const fs=Array.isArray(t.fotos)?t.fotos:[];
    const thumb = fs.length ? '<img class="cc-thumb" src="'+fs[0].src+'" loading="lazy" alt="" onclick="openLightbox('+t.id+',0)">' : '';
    const media = (thumb||mp) ? '<div class="cc-media">'+thumb+mp+'</div>' : '';
    const kat = '<span class="cc-kat">'+_esc(katOf(t))+'</span>';   // §5: Kategorie-Badge
    return '<div class="cc-t">'+kat+(parts.join(' &mdash; ')||'&nbsp;')+who+'</div>'+media;
  }).join('');
  cap.innerHTML=h;
}

// FlyTo je Jahr: eine Tour zentriert, mehrere gemeinsame BBox. Padding unten groß (Leiste/Caption).
function chronoFlyToYear(Y){
  const ts=(CHRONO.yearTours[Y]||[]).filter(t=>t.lon!=null&&t.lat!=null);
  if(!ts.length) return;
  const pad={top:80,bottom:190,left:80,right:80};
  if(ts.length===1){
    // B1b: speed-basiert statt fixe Dauer -> kurze Distanz = kurzer Flug (dynamisch).
    map.flyTo({center:[ts[0].lon,ts[0].lat], zoom:8.6, padding:pad, speed:CHRONO_SPEED, curve:1.5, essential:true});
  } else {
    let x0=180,y0=90,x1=-180,y1=-90;
    ts.forEach(t=>{x0=Math.min(x0,t.lon);x1=Math.max(x1,t.lon);y0=Math.min(y0,t.lat);y1=Math.max(y1,t.lat);});
    map.fitBounds([[x0,y0],[x1,y1]],{padding:pad, maxZoom:9, duration:1200, essential:true});
  }
}

// Einmalige Puls-Animation auf chrono-cur (auch bei Wiederbesuch).
function chronoPulse(){
  if(_pulseRAF) cancelAnimationFrame(_pulseRAF);
  const t0=performance.now(), peak=0.95, dur=680;
  (function step(now){
    const k=Math.min(1,(now-t0)/dur);
    if(k<1){ map.setPaintProperty('chrono-cur','fill-opacity', Math.max(0, peak*Math.sin(k*Math.PI)));  // kurzer Flash, >=0
      _pulseRAF=requestAnimationFrame(step); }
    else { map.setPaintProperty('chrono-cur','fill-opacity',CHRONO_CUR_OP); _pulseRAF=null; }  // zurueck zur Zoom-Kurve
  })(performance.now());
}

// Stand Jahr X: Gruppen mit Tour == X kräftig (chrono-cur), nur früher besuchte gedimmt (chrono-past).
function chronoSetYear(idx, opts){
  opts=opts||{};
  if(idx<0 || idx>=CHRONO.years.length) return;
  if(opts.manual && _chronoPlaying) chronoPause();      // manueller Chip-Tipp pausiert Play
  closeAllPopups();   // W1.3: kein Hütten-/Gipfel-Popup soll über die Zeitreise stehen bleiben
  _chronoIdx=idx; const Y=CHRONO.years[idx];
  const past=[], cur=[];
  Object.keys(CHRONO.stsYears).forEach(sts=>{
    const ys=CHRONO.stsYears[sts];
    if(ys.indexOf(Y)>=0) cur.push(sts);
    else if(ys.some(y=>y<Y)) past.push(sts);
  });
  map.setFilter('chrono-past',['in',['get','STS'],['literal',past]]);
  map.setFilter('chrono-cur', ['in',['get','STS'],['literal',cur]]);
  // W3: Mindestdarstellung folgt der aktiven Gruppe (Rahmen + verankerter Name).
  map.setFilter('chrono-cur-line',['in',['get','STS'],['literal',cur]]);
  map.setFilter('chrono-cur-name',['in',['get','STS'],['literal',cur]]);
  const chips=document.querySelectorAll('#chronoChips .chip');
  chips.forEach((c,i)=>c.classList.toggle('on',i===idx));
  if(chips[idx]) chips[idx].scrollIntoView({inline:'center',block:'nearest'});
  chronoCaption(Y);
  chronoPulse();
  // Fix2 + B1a: NUR bei manueller Jahr-Wahl den Steckbrief oeffnen (waehrend Play zaeh +
  // die Caption traegt die Info schon). Kein eigener Kamerasprung — die Chronik fliegt selbst.
  if(opts.manual && cur.length){ const gf=SOIUSA_STS.features.find(x=>x.properties.STS===cur[0]); if(gf) openSts(gf,'nofly'); }
  if(opts.fly!==false) chronoFlyToYear(Y);
}

// ── Play/Pause (~2,5 s/Jahr, kein Loop, stoppt am letzten Jahr) ──
function chronoPlayStep(){
  if(_chronoIdx>=CHRONO.years.length-1){ chronoFinale(); return; }   // kein Loop -> Abspann
  chronoSetYear(_chronoIdx+1);
  // B1b: naechstes Jahr erst nach Ankunft (moveend) + Lese-Pause -> dynamischer Takt.
  // Fallback, falls kein moveend feuert (Jahr ohne Koordinaten -> kein Flug).
  clearTimeout(_chronoFallback); let fired=false;
  const next=()=>{ if(fired||!_chronoPlaying) return; fired=true;
    clearTimeout(_chronoFallback); _chronoTimer=setTimeout(chronoPlayStep, CHRONO_DWELL); };
  map.once('moveend', next);
  _chronoFallback=setTimeout(next, 3500);
}
function chronoPlay(){
  if(!_chronoOn || _chronoPlaying) return;
  closeAllPopups();   // W1.3: Play-Start schließt offene Popups (Repro: klebte über die Zeitreise)
  if(_chronoIdx>=CHRONO.years.length-1) chronoSetYear(0,{fly:false});  // am Ende: von vorn
  _chronoPlaying=true;
  const b=document.getElementById('chronoPlay'); if(b){ b.textContent='⏸'; b.title='Pause'; b.classList.add('on'); }
  _chronoTimer=setTimeout(chronoPlayStep, 600);   // kurzer Vorlauf, dann dynamischer Takt
}
function chronoPause(){
  _chronoPlaying=false;
  if(_chronoTimer){ clearTimeout(_chronoTimer); _chronoTimer=null; }
  if(_chronoFallback){ clearTimeout(_chronoFallback); _chronoFallback=null; }
  const b=document.getElementById('chronoPlay'); if(b){ b.textContent='▶'; b.title='Abspielen'; b.classList.remove('on'); }
}
function chronoPlayToggle(){ _chronoPlaying?chronoPause():chronoPlay(); }

// §2: Abspann nach dem letzten Play-Schritt — Rückflug zur Übersicht + Bilanz-Caption.
// Zahlen aus den Daten berechnet (nicht hartkodiert). Bleibt bis zur Nutzer-Interaktion.
function chronoFinale(){
  chronoPause();                                         // Play-Button zurück auf ▶ (Neustart möglich)
  const all=Object.keys(CHRONO.stsYears);
  map.setFilter('chrono-cur', ['in',['get','STS'],['literal',[]]]);   // alle besuchten Gruppen
  map.setFilter('chrono-past',['in',['get','STS'],['literal',all]]);  //   einheitlich im Bild
  ['chrono-cur-line','chrono-cur-name'].forEach(l=>map.setFilter(l,['in',['get','STS'],['literal',[]]]));  // W3: kein Einzel-Rahmen im Abspann
  overview();                                            // zurück zur Gesamt-Übersicht (Home-Ausdehnung)
  const yrs=CHRONO.years, minY=yrs[0], maxY=yrs[yrs.length-1];
  const spanY=Math.max(0, maxY-minY);
  // Abspann-Bilanz zählt die GEFILTERTE Menge (Strang-Label · N Touren · M Gebiete).
  const nT=matchedTours().length;
  const word={brueder:'__PT_LBL_BRUEDER__', weitere:'__PT_LBL_WEITERE_L__'}[FILTER.strang] || 'Touren';
  const cap=document.getElementById('chronoCap');
  if(cap) cap.innerHTML =
    '<div class="cc-h"><span class="cc-y">'+minY+'&ndash;'+maxY+'</span>'+
    '<span class="cc-d">R&uuml;ckblick</span></div>'+
    '<div class="cc-t">'+spanY+' Jahre &middot; '+nT+' '+word+' &middot; '+
    all.length+' Gebiete</div>';
}

function chronoEnter(){
  if(_chronoOn || !CHRONO.years.length) return;
  _chronoOn=true;
  _chronoSaved={p:_peaksOn,h:_hutsOn,s:_passesOn,o:_placesOn,c:_cableOn};  // Punkt-Toggles merken + dezent aus
  if(_peaksOn) togglePeaks(); if(_hutsOn) toggleHuts(); if(_passesOn) togglePasses();
  if(_placesOn) togglePlaces(); if(_cableOn) toggleCable();
  ['hl-line','sts-label-hl'].forEach(l=>map.setLayoutProperty(l,'visibility','none'));  // „alle besucht" aus
  // Fix1: Chrono-Fuellungen folgen dem Faerbung-Toggle (aus -> ausgeblendet).
  const _cv=_farbungOn?'visible':'none';
  ['chrono-past','chrono-cur'].forEach(l=>map.setLayoutProperty(l,'visibility',_cv));
  // W3: Mindestdarstellung (Rahmen + Name) IMMER an — unabhängig von Färbung/Namen.
  ['chrono-cur-line','chrono-cur-name'].forEach(l=>map.setLayoutProperty(l,'visibility','visible'));
  map.setPaintProperty('chrono-cur','fill-opacity',CHRONO_CUR_OP);
  map.setPaintProperty('chrono-past','fill-opacity',CHRONO_PAST_OP);
  document.getElementById('cov').style.display='none';
  document.getElementById('chronoBar').classList.add('open');
  document.getElementById('chronoCap').classList.add('open');
  document.getElementById('chronoBtn').classList.add('active');
  document.body.classList.add('chrono');                 // Fix4: Scale-Bar ausblenden
  overview();
  chronoSetYear(0,{fly:false});                          // Beginn: frühestes Jahr, Übersicht halten
}
function chronoExit(){
  if(!_chronoOn) return; _chronoOn=false;
  chronoPause();
  if(_pulseRAF){ cancelAnimationFrame(_pulseRAF); _pulseRAF=null; }
  map.setPaintProperty('chrono-cur','fill-opacity',CHRONO_CUR_OP);
  ['chrono-past','chrono-cur','chrono-cur-line','chrono-cur-name'].forEach(l=>map.setLayoutProperty(l,'visibility','none'));  // W3 mit aus
  map.setLayoutProperty('hl-line','visibility','visible');
  map.setLayoutProperty('sts-label-hl','visibility', _layersOn?'visible':'none');   // Zustand restaurieren
  if(_chronoSaved){
    if(_chronoSaved.p && !_peaksOn) togglePeaks();
    if(_chronoSaved.h && !_hutsOn) toggleHuts();
    if(_chronoSaved.s && !_passesOn) togglePasses();
    if(_chronoSaved.o && !_placesOn) togglePlaces();
    if(_chronoSaved.c && !_cableOn) toggleCable();
    _chronoSaved=null;
  }
  document.getElementById('cov').style.display='';
  document.getElementById('chronoBar').classList.remove('open');
  document.getElementById('chronoCap').classList.remove('open');
  document.getElementById('chronoBtn').classList.remove('active');
  document.body.classList.remove('chrono');              // Fix4: Scale-Bar wieder zeigen
}
function chronoToggle(){ _chronoOn?chronoExit():chronoEnter(); }

// Jahres-Chips aus CHRONO.years (bei Filterwechsel neu). Ohne Jahre: Modus-Button aus.
function chronoBuildChips(){
  const wrap=document.getElementById('chronoChips'), btn=document.getElementById('chronoBtn');
  if(!wrap) return;
  if(!CHRONO.years.length){ wrap.innerHTML=''; if(btn) btn.style.display='none'; return; }
  if(btn) btn.style.display='';
  wrap.innerHTML=CHRONO.years.map((y,i)=>{
    const m=CHRONO.yearMeta[y]||{}; return '<button class="chip" data-i="'+i+'">'+(m.unsure?'~':'')+y+'</button>';
  }).join('');
  [...wrap.children].forEach(b=>b.addEventListener('click',()=>chronoSetYear(+b.dataset.i,{manual:true})));
}
chronoBuildChips();

// Initial-Render. Hier (nicht im Filter-Block), damit CHRONO/_chronoOn initialisiert sind.
restoreFilter();      // P3a.5: F aus localStorage (Bilanzzeile macht ihn sofort sichtbar)
_yearSliderInit();    // Jahr-Slider (YEAR_MIN..YEAR_MAX, Werte aus F)
applyTourFilter();
sizeCov();   // P1: #cov-Höhe initial messen (Title-Card-Layout steht am Script-Ende)
// P2.7: beim Überschreiten von z9 das Marker-Gate (Cluster <-> Einzel-Split) neu anwenden.
let _zoomGateLow=null;
map.on('zoomend', ()=>{ const low=map.getZoom()<9; if(low!==_zoomGateLow){ _zoomGateLow=low;
  try{ _applyMapFilter(matchedTours().map(t=>t.id), filterActive()); }catch(_){} } });
/* PRIV:END */
</script>
</body>
</html>
"""

html = TEMPLATE.replace("__TOUREN_GEOJSON__",        touren_json)
html = html.replace("__TRACKS_GEOJSON__",             tracks_json)
html = html.replace("__PERSONEN_JSON__",              personen_json)
html = html.replace("__SOIUSA_STS_GEOJSON__",         sts_json)
html = html.replace("__SOIUSA_HIGHLIGHTS_GEOJSON__",  highlights_json)
html = html.replace("__MASK_GEOJSON__",               mask_json)
html = html.replace("__SOIUSA_LBL_PTS_GEOJSON__",    lp_json)
html = html.replace("__SOIUSA_WIKI_JSON__",          wiki_json)
html = html.replace("__SOIUSA_HUTS_WIKI_JSON__",     huts_wiki_json)
html = html.replace("__TITEL__", TITEL).replace("__UNTER__", UNTER)
html = html.replace("__PRIV__", "false" if PUBLIC else "true")
html = html.replace("__KPI_GRUPPEN__",  str(kpi_gruppen))
html = html.replace("__KPI_SETTORI__",  str(kpi_settori))
html = html.replace("__KPI_HUETTEN__",  str(kpi_huetten))

# ── Modusabhaengig: Vendor-Libs, Glyphs, Inline-GeoJSONs (Standalone) ─────────
if STANDALONE:
    def _vend(p): return (HERE / "vendor" / p).read_text(encoding="utf-8")
    def _escs(s): return s.replace("</script>", "<\\/script>")
    # Fix0 v2: Standalone nutzt den CSP-Build. maplibre-gl-csp.js (Main) inline + das
    # SEPARATE, echte Worker-Bundle (maplibre-gl-csp-worker.js, inkl. geojson-vt) als
    # nicht-ausgefuehrtes text/plain-Script, daraus Blob-URL -> setWorkerUrl vor der Map.
    # (Frueher wurde faelschlich das Haupt-Bundle in den Worker gegeben -> Zugriff auf
    #  window/document -> Worker-Crash bei GeoJSON. contour blobt seinen Worker selbst.)
    csp_main   = _escs(_vend("maplibre-gl-csp-4.7.1.min.js"))
    csp_worker = _escs(_vend("maplibre-gl-csp-worker-4.7.1.min.js"))
    contour    = _escs(_vend("maplibre-contour-0.0.5.min.js"))
    _worker_setup = ("<script>maplibregl.setWorkerUrl(URL.createObjectURL(new Blob("
                     "[document.getElementById('mlworker').textContent],{type:'text/javascript'})));</script>")
    head_libs = ("<style>" + _vend("maplibre-gl-4.7.1.min.css") + "</style>\n"
                 "<script>" + csp_main + "</script>\n"
                 "<script id=\"mlworker\" type=\"text/plain\">" + csp_worker + "</script>\n"
                 + _worker_setup + "\n<script>" + contour + "</script>")
    # A4: Glyphs (nur „Noto Sans Bold", 4 Ranges) base64 inline -> glyphs://-Protokoll.
    import base64 as _b64g
    _gdir = HERE / "fonts" / "Noto Sans Bold"
    glyphs = "glyphs://fonts/{fontstack}/{range}.pbf"
    glyphs_data = json.dumps({p.stem: _b64g.b64encode(p.read_bytes()).decode("ascii")
                              for p in sorted(_gdir.glob("*.pbf"))}, separators=(",", ":"))
    osm_peaks  = load_compact("soiusa_osm_peaks.geojson")
    osm_huts   = load_compact("soiusa_osm_huts.geojson")
    osm_passes = load_compact("soiusa_osm_passes.geojson")
    osm_places = load_compact("soiusa_osm_places_v1.geojson")   # v1: nur city/town (schlank)
    osm_cable  = load_compact("soiusa_osm_cableways.geojson")
    osm_cable_lines = load_compact("soiusa_osm_cableways_lines.geojson")
    osm_chairlifts = load_compact("soiusa_osm_chairlifts.geojson")   # Sessellifte inline (file://-Pflicht)
    borders_gj = load_compact("soiusa_borders.geojson")
else:
    head_libs = ('<link href="./vendor/maplibre-gl-4.7.1.min.css" rel="stylesheet" />\n'
                 '<script src="./vendor/maplibre-gl-4.7.1.min.js"></script>\n'
                 '<script src="./vendor/maplibre-contour-0.0.5.min.js"></script>')
    glyphs = "./fonts/{fontstack}/{range}.pbf"
    glyphs_data = "null"
    osm_peaks = osm_huts = osm_passes = osm_places = osm_cable = borders_gj = "null"
    osm_cable_lines = "null"
    osm_chairlifts = "null"
html = html.replace("__GLYPHS_DATA__", glyphs_data)
html = html.replace("__GLYPHS__", glyphs)
html = html.replace("__OSM_PEAKS__",  osm_peaks)
html = html.replace("__OSM_HUTS__",   osm_huts)
html = html.replace("__OSM_PASSES__", osm_passes)
html = html.replace("__OSM_PLACES__", osm_places)
html = html.replace("__OSM_CABLE__",  osm_cable)
html = html.replace("__OSM_CABLE_LINES__", osm_cable_lines)
html = html.replace("__OSM_CHAIRLIFTS__", osm_chairlifts)
html = html.replace("__BORDERS__",    borders_gj)
html = html.replace("__GROUP_PEAKS__", group_peaks_json)
html = html.replace("__HUT_VISITS__", hut_visits_json)   # §1: Besuchsjahre je OSM-Hütte (Privat)
html = html.replace("__HEAD_LIBS__",  head_libs)   # zuletzt (Lib-Inhalt nicht rescannen)

# ── Symmetric marker stripping (E2 + E8) ──────────────────────────────────────
# PRIV blocks = private-only, removed in the public build (hard strip, no leak).
# PUB  blocks = public-only,  removed in the private build.
# HTML/CSS: <!-- X:START --> … <!-- X:END -->   ·   JS: /* X:START */ … /* X:END */
if PUBLIC:
    html = re.sub(r"<!-- PRIV:START -->.*?<!-- PRIV:END -->", "", html, flags=re.S)
    html = re.sub(r"/\* PRIV:START \*/.*?/\* PRIV:END \*/", "", html, flags=re.S)
else:
    html = re.sub(r"<!-- PUB:START -->.*?<!-- PUB:END -->", "", html, flags=re.S)
    html = re.sub(r"/\* PUB:START \*/.*?/\* PUB:END \*/", "", html, flags=re.S)
# Strip any surviving marker comments (the kept family's markers would linger).
for _m in ("<!-- PRIV:START -->", "<!-- PRIV:END -->", "<!-- PUB:START -->", "<!-- PUB:END -->",
           "/* PRIV:START */", "/* PRIV:END */", "/* PUB:START */", "/* PUB:END */"):
    html = html.replace(_m, "")

# Tab bar only in the private build (P2: „Touren (n)" / „Über die Gruppe").
PTABS = "" if PUBLIC else (
    '<div class="tabs" id="pTabs">'
    "<div class=\"tab\" id=\"tabTour\" onclick=\"showTab('tour')\">Touren</div>"
    "<div class=\"tab active\" id=\"tabAbout\" onclick=\"showTab('about')\">Über die Gruppe</div>"
    "</div>")
html = html.replace("__PTABS__", PTABS)

# Nachtjob P2: private Klartext-Tokens NUR im internen Build aus privat_template.py fuellen.
# Im oeffentlichen Build stehen diese Tokens ausschliesslich in PRIV-Bloecken und sind
# zu diesem Zeitpunkt bereits entfernt -> nichts zu ersetzen (die Tokens tauchen public nie auf).
if not PUBLIC and _PT is not None:
    html = html.replace("__PT_STRANG_CATS__", json.dumps(_PT.STRANG_CATS, ensure_ascii=False))
    html = html.replace("__PT_LBL_BRUEDER__",    _PT.LBL["brueder"])
    html = html.replace("__PT_LBL_WEITERE_S__",  _PT.LBL["weitere_short"])
    html = html.replace("__PT_LBL_WEITERE_L__",  _PT.LBL["weitere_long"])
    html = html.replace("__PT_LBL_PERSFILTER__", _PT.LBL["persfilter"])
    html = html.replace("__PT_LBL_BOOKSRC__",    _PT.LBL["book_source"])
    html = html.replace("__PT_ABOUT_INTRO__",    _PT.ABOUT_INTRO)   # N2

out = HERE / OUT
out.write_text(html, encoding="utf-8")
size_kb = out.stat().st_size / 1024
mode = "STANDALONE" if STANDALONE else ("public" if PUBLIC else "PRIVAT")
size_str = f"{size_kb/1024:.1f} MB" if size_kb > 1024 else f"{size_kb:.0f} KB"
print(f"{OUT} [{mode}]: {len(data['touren'])} Touren · {hl_count}/{sts_count} Untergruppen · {size_str}")
if STANDALONE and size_kb > 14 * 1024:   # Roadmap M0: Mitgabe-Ziel (WARN >14, FAIL >15 in check.py)
    print(f"WARN Standalone {size_str} > 14 MB (Mitgabe-Ziel) -- Fotos/Daten pruefen.")

# W7 (§6b): Standalone zusätzlich als „Alpentouren.html" ablegen — die file://-taugliche
# Mitgabe-Datei (gitignored). Erspart das manuelle Umbenennen vor der Mitgabe.
if STANDALONE:
    _mitgabe = HERE / "Alpentouren.html"
    _mitgabe.write_text(html, encoding="utf-8")
    print(f"  -> Mitgabe-Kopie: Alpentouren.html ({_mitgabe.stat().st_size//1024//1024} MB)")

# ── Backup-Hook (nur Privat-Build): sichert den gitignorierten Privat-Kanon ───
# (touren.json + _cowork_specs) nach OneDrive. Fehler brechen den Build nie ab.
if not PUBLIC:
    try:
        import backup_privat
        backup_privat.backup()
    except Exception as e:
        print(f"backup_privat: uebersprungen ({e})")
