#!/usr/bin/env python3
"""Sanity-check index.html auf alle kritischen Strings."""
import pathlib
import sys

html = (pathlib.Path(__file__).parent / "index.html").read_text(encoding="utf-8")

checks = [
    # Data constants
    ("SOIUSA_STS const",              "const SOIUSA_STS"),
    ("SOIUSA_HIGHLIGHTS const",       "const SOIUSA_HIGHLIGHTS"),
    ("SOIUSA_LBL_PTS const",         "const SOIUSA_LBL_PTS"),
    ("MASK const",                    "const MASK"),
    ("startup console.log",           "SOIUSA_STS.features.length"),
    # Layers
    ("mask-fill layer",               "id:'mask-fill'"),
    ("sts-fill layer",                "id:'sts-fill'"),
    ("sts-line layer",                "id:'sts-line'"),
    ("hl-line layer (always)",        "id:'hl-line'"),
    ("sts-lp source",                 "addSource('sts-lp'"),
    ("sts-label layer (non-visited)", "id:'sts-label'"),
    ("sts-label-hl layer (visited)",  "id:'sts-label-hl'"),
    ("sts-selected layer",            "id:'sts-selected'"),
    # Layer semantics
    ("fill_color coalesce",           "'fill-color': ['coalesce',['get','fill_color']"),
    ("fill fog-fade (top-level)",     "'fill-opacity': ['interpolate',['linear'],['zoom'], 8,0.34, 10.5,0.12, 12,0]"),
    ("Färbung toggle fn",             "function toggleFarbung"),
    ("Färbung toggle switch",         'id="tglFarbung"'),
    ("Ebenen panel",                  'id="ebenen"'),
    ("Landesgrenzen toggle",          'id="tglBorders"'),
    ("toggleBorders fn",              "function toggleBorders"),
    ("borders layer",                 "id:'borders'"),
    ("borders url source",            "./soiusa_borders.geojson"),
    ("country labels layer",          "id:'country-labels'"),
    ("home button",                   'id="home"'),
    ("auto-pitch fn",                 "function pitchForZoom"),
    ("auto-pitch on zoomend",         "map.on('zoomend'"),
    ("sts-line non-visited filter",   "filter:['==',['get','visited'],0]"),
    ("hl-line orange color",          "'line-color':'#ffb24d'"),
    ("hl-line always (no toggle)",    "id:'hl-line', type:'line'"),
    ("sts-label-hl visited filter",   "filter:['==',['get','visited'],1]"),
    ("sts-label non-visited filter",  "filter:['==',['get','visited'],0]"),
    ("sts-label minzoom 6.5",         "minzoom:6.5"),
    ("line-join round",               "'line-join':'round'"),
    # Functions
    ("openSts fn",                    "function openSts"),
    ("toggleLayers fn",               "function toggleLayers"),
    ("featBbox fn",                   "function featBbox"),
    ("featBbox GeometryCollection",   "GeometryCollection"),
    # Toggle behavior
    ("toggle controls sts-label",      "setLayoutProperty('sts-label'"),
    ("toggle controls sts-label-hl",  "setLayoutProperty('sts-label-hl'"),
    ("toggle starts OFF",             "_layersOn=false"),
    ("labels off by default",         "'visibility':'none'"),
    ("popup fn showStsPopup",         "function showStsPopup"),
    ("panel on sts click",            "openSts(e.features[0])"),
    ("popup closeOnClick false",      "closeOnClick:false"),
    # Phase 2c — two-tab panel + Steckbrief
    ("wiki const",                    "const WIKI"),
    ("priv flag (public=false)",      "const PRIV = false"),
    ("about pane",                    'id="pAbout"'),
    ("tour pane",                     'id="pTour"'),
    ("showTab fn",                    "function showTab"),
    ("steckbrief fn",                 "function steckbriefHtml"),
    ("steckbrief Hoechster Berg",     "Höchster Berg"),
    # Phase 2c — OSM overlays (peaks + huts)
    ("osm peaks url source",          "./soiusa_osm_peaks.geojson"),
    ("osm huts url source",           "./soiusa_osm_huts.geojson"),
    ("osm peaks layer",               "id:'osm-peaks'"),
    ("osm huts club layer",           "id:'osm-huts-club'"),
    ("osm huts other layer",          "id:'osm-huts-other'"),
    ("osm huts wild layer",           "id:'osm-huts-wild'"),
    ("peak triangle icon",            "map.addImage('peak'"),
    ("peak rank tiering by ele",      "'icon-opacity':['step',['zoom']"),
    ("peak tier icon match",          "'icon-image':['match',['get','tier']"),
    ("Mont Blanc star icon",          "'peak-star'"),
    ("landmark glow layer",           "id:'osm-landmark-glow'"),
    ("landmarks layer",               "id:'osm-landmarks'"),
    ("makeStar fn",                   "function makeStar"),
    ("passes url source",             "./soiusa_osm_passes.geojson"),
    ("passes famous layer",           "id:'osm-passes-famous'"),
    ("togglePasses fn",               "function togglePasses"),
    ("passes toggle switch",          'id="tglPasses"'),
    ("hut club icon",                 "'hut-club'"),
    # Erinnerungs-Feinschliff §3 — Seilbahn-nah-Chip (beide Builds)
    ("hut cable chip fn",             "function hutCableChip"),
    ("hut cable chip label",          "Seilbahn-nah"),
    # Orte v2 — pop-basierte Klassifizierung (beide Builds)
    ("places-sq K1 layer",            "id:'places-sq'"),
    ("city-square icon",              "map.addImage('citysq'"),
    ("pop-based place class",         "['coalesce',['get','pop'],0]"),
    # Nachtjob W2 — Orte Atlas-Rot (beide Builds)
    ("orte atlas-red",                "#cc3322"),
    # Nachtjob W5 — Vollbild-Button
    ("fullscreen button",             'id="btnFull"'),
    ("fullscreen fn",                 "function toggleFullscreen"),
    # Nachtjob W4 — Seilbahn-Linien + SDF-Gondel (beide Builds)
    ("cable line layer",              "id:'cable-line'"),
    ("cable lines source",            "./soiusa_osm_cableways_lines.geojson"),
    ("gondola SDF logo",              "gondolaIcon(), {sdf:true"),
    # Nachtjob W1 — Interaktions-Fixes
    ("compass pitch reset",           "visualizePitch:true"),
    ("attrib init fill",              "setAttrib(false)"),
    ("toggle race guard",             "function _setVis"),
    ("point toggle sync",             "function _syncPointToggles"),
    ("close-all-overlays fn",         "function closeAllOverlays"),
    ("hut search opens popup",        "hutPopupHtml({name:r.name"),
    # Mobile-Pass (Paket B) — Phone-Stufe + Touch-Gesten
    ("phone media query",             "(max-width: 480px) and (pointer: coarse)"),
    ("phone nav-control hidden",      ".maplibregl-ctrl-group{display:none"),
    ("title collapse css",            "#title.collapsed"),
    ("doubleClickZoom enabled",       "map.doubleClickZoom.enable()"),
    ("long-press zoom-out handler",   "setTimeout(begin, HOLD)"),
    # Phase 2c — Berge nach Klick
    ("peaks-in-group layer",          "id:'peaks-in-group'"),
    ("peaks-highest layer",           "id:'peaks-highest'"),
    ("showGroupPeaks fn",             "function showGroupPeaks"),
    ("within filter",                 "['within',geom]"),
    ("togglePeaks fn",                "function togglePeaks"),
    ("toggleHuts fn",                 "function toggleHuts"),
    ("peaks toggle switch",           'id="tglPeaks"'),
    ("huts toggle switch",            'id="tglHuts"'),
    ("OSM attribution ODbL",          "OpenStreetMap (ODbL)"),
    # Click/selection
    ("sts-selected filter on click",  "setFilter('sts-selected'"),
    ("closePanel resets sts-selected","setFilter('sts-selected',['=='"),
    ("fitBounds in openSts",          "map.fitBounds"),
    ("hl-line click handler",         "'click','hl-line'"),
    ("openSts sentinel __none__",     "__none__"),
    ("featBbox null guard",           "if(bb)"),
    # Instrumentation
    ("labels use Noto Sans Bold",       "'text-font':['Noto Sans Bold']"),
    ("local glyph path",               "glyphs:'./fonts/{fontstack}/{range}.pbf'"),
    # Bug fixes
    ("map.resize on load",            "map.resize()"),
    ("resize setTimeout",             "setTimeout(()=>map.resize()"),
    ("idle resize",                   "map.once('idle',()=>map.resize())"),
    # Public build hygiene (E8: neutral atlas)
    ("public atlas title",            "Alpen-Atlas"),
    # KPI (public: computed atlas stats) — T4: „Settori" -> „Sektoren"
    ("KPI Sektoren label",            "Sektoren"),
    ("KPI Vereinshütten label",       "Vereinsh&uuml;tten"),
    # Data integrity
    ("Silvretta / Verwall",           "Silvretta / Verwall"),
    ("Settore legend Nordwestalpen",  "Nordwestalpen"),
    ("popup uses settore",            "props.settore"),
    ("settore in feature props",      '"settore"'),
    # UI
    ("Info button",                   'id="btnInfo"'),
    ("About card",                    'id="about"'),
    # Search + basemap
    ("search input",                  'id="sInput"'),
    ("search index fn",               "function buildSearchIndex"),
    ("coord parser fn",               "function parseCoord"),
    ("search query fn",               "function searchQuery"),
    ("search diacritics norm",        "function sNorm"),
    ("basemap switch fn",             "function setBasemap"),
    ("basemap segmented Topo",        'id="bmTopo"'),
    ("topo raster layer",             "id:'topo'"),
    ("OpenTopoMap tiles",             "opentopomap.org"),
    ("OTM attribution CC-BY-SA",      "OpenTopoMap (CC-BY-SA)"),
    ("basemap localStorage",          "alpen_basemap"),
    ("toggleAbout fn",                "function toggleAbout"),
    ("hover tooltip popup",           "const hoverPop"),
    ("hover on sts-hit mousemove",    "map.on('mousemove','sts-hit'"),
    # Map setup
    ("overflow hidden",               "overflow:hidden"),
    ("maxBounds",                     "maxBounds"),
    ("minZoom 5.0",                   "minZoom: 5.0"),
    ("pitch 0 default",               "pitch:0"),
    ("pixelRatio",                    "pixelRatio"),
    ("sat raster-opacity 0.95",       "'raster-opacity':0.95"),
    ("hillshade-exaggeration 0.25",   "'hillshade-exaggeration':0.25"),
    ("terrain exaggeration 1.0",      "exaggeration:1.0"),
    ("SOIUSA attribution",            "Arpa Piemonte"),
]

errors = []
for name, marker in checks:
    ok = marker in html
    print(f"{'OK  ' if ok else 'FAIL'} {name}")
    if not ok:
        errors.append(name)

# ── Public-hygiene negative guards (SPEC_Build_Teilung E1/E2 + E8 atlas) ──────
# The public index.html must carry NO private markers, NO year fields, NO
# private-only functions/KPIs, and (E8) NO visited/tour layer whatsoever.
for bad, label in [("Tour mit Papa", "private tab label"),
                   # Politur: privater Familien-Titel darf nicht in den Public. NICHT bare
                   # "Günther" — false-positive auf die OSM-Hütte „Alois-Günther-Haus"
                   # (neutrale Geodaten, unbeteiligte Person). Spezifisch der Titel:
                   ("Günther-Alpenchronik", "private family title (Politur, privat-only)"),
                   ("PRIV:START", "PRIV start marker"),
                   ("PRIV:END", "PRIV end marker"),
                   ("PUB:START", "PUB start marker (must be stripped)"),
                   ('"jahr"', "year field"),
                   ("function openTour", "tour-marker function"),
                   ('id="kYears"', "years KPI"),
                   ('"visited":1', "visited=1 data (E8)"),
                   ('"tour_ids":', "tour_ids data (E8)"),
                   ("Touren ansehen", "coverage button (E8)"),
                   ("chronoBar", "chronology bar (privat-only)"),
                   ("chrono-past", "chronology fill layer (privat-only)"),
                   ("function chronoSetYear", "chronology fn (privat-only)"),
                   ("const CHRONO", "chronology data (privat-only)"),
                   ("jahr_unsicher", "year-uncertainty field (privat-only)"),
                   ("privat_assets", "private photo asset path (privat-only)"),
                   ("openLightbox", "photo lightbox fn (privat-only)"),
                   ("Ihr wart hier", "hut visit badge (privat-only, §1)"),
                   ("const HUT_VISITS", "hut visit map (privat-only, §1)"),
                   ("const TRACKS", "GPX track data (privat-only, SPEC_GPX_Tracks)"),
                   ("trk-line", "GPX track layer (privat-only)"),
                   ('"tour_id"', "track tour_id prop (privat-only)"),
                   ("tglTracks", "tracks toggle (privat-only)"),
                   ("track_km", "track km field (privat-only)"),
                   # Personenfilter (SPEC_Personenfilter, privat-only, E8). NICHT bare
                   # "personen" prüfen — false-positive auf "Personen-Seilbahn" (hutCableChip,
                   # bewusst in beiden Builds). Nur diese spezifischen Marker:
                   ("personen.json", "personen register file ref (privat-only)"),
                   ("const PERSONEN", "personen register const (privat-only)"),
                   ("__PERSONEN_JSON__", "personen json token (must be replaced/stripped)"),
                   ("teilnehmer_ids", "teilnehmer ids data (privat-only)"),
                   ("applyTourFilter", "tour filter fn (privat-only)"),
                   ("tf-chip", "person chip class (privat-only)"),
                   ("Brüdertouren (", "strang segment markup (privat-only)")]:
    if bad in html:
        print(f"FAIL public leak: '{bad}' ({label}) present in index.html")
        errors.append(f"public leak: {bad}")
    else:
        print(f"OK   public free of '{bad}'")

# E8: the word "besucht" (any case) must not appear in the public atlas.
if "besucht" in html.lower():
    print("FAIL public leak: 'besucht' present in index.html (E8)")
    errors.append("public leak: besucht")
else:
    print("OK   public free of 'besucht' (E8)")

# ── Fotos (Paket A): Privat-Build referenziert privat_assets/web/… ─────────────
# Warnungen (kein Fehler): fehlende Dateien / >400 KB. touren.json ist gitignored
# und nur lokal vorhanden -> saubere Skip, wenn nicht da.
import json as _jf
_tj = pathlib.Path(__file__).parent / "touren.json"
if _tj.exists():
    _root = pathlib.Path(__file__).parent
    _miss, _big = [], []
    for _t in _jf.loads(_tj.read_text(encoding="utf-8")).get("touren", []):
        for _f in (_t.get("fotos") or []):
            _src = _f.get("src", "")
            if not _src:
                continue
            _p = _root / _src
            if not _p.exists():
                _miss.append(_src)
            elif _p.stat().st_size > 400 * 1024:
                _big.append((_src, _p.stat().st_size // 1024))
    if _miss:
        print(f"WARN {len(_miss)} fotos[].src fehlen auf Platte: {_miss[:3]}")
    else:
        print("OK   alle fotos[].src existieren")
    for _src, _kb in _big:
        print(f"WARN Foto > 400 KB: {_src} ({_kb} KB) -> Qualitaet senken")

# ── Personenfilter (SPEC_Personenfilter): teilnehmer_ids ↔ personen.json ──────
# Beide Dateien sind gitignored (nur lokal). Skip, wenn eine fehlt. Unbekannte id
# in irgendeiner Tour -> FAIL (Register-Integrität, spiegelt den build.py-WARN).
_tjp = pathlib.Path(__file__).parent / "touren.json"
_pjp = pathlib.Path(__file__).parent / "personen.json"
if _tjp.exists() and _pjp.exists():
    _known = {p.get("id") for p in _jf.loads(_pjp.read_text(encoding="utf-8")).get("personen", [])}
    _unknown = []
    for _t in _jf.loads(_tjp.read_text(encoding="utf-8")).get("touren", []):
        for _pid in (_t.get("teilnehmer_ids") or []):
            if _pid not in _known:
                _unknown.append((_t.get("id"), _pid))
    if _unknown:
        print(f"FAIL personen: unbekannte teilnehmer_ids (nicht im Register): {_unknown[:5]}")
        errors.append(f"personen: unknown teilnehmer_ids {_unknown[:5]}")
    else:
        print("OK   personen: alle teilnehmer_ids im Register")
else:
    print("SKIP personen-Register-Check (touren.json/personen.json nicht vorhanden)")

# ── Standalone-Build (Paket B, SPEC §6): file://-Tauglichkeit + Groesse ────────
# Standalone ist privat/gitignored -> Skip, wenn nicht gebaut.
_sa = pathlib.Path(__file__).parent / "index_privat_standalone.html"
if _sa.exists():
    _sah = _sa.read_text(encoding="utf-8")
    _samb = _sa.stat().st_size / (1024 * 1024)
    for _bad, _lbl in [("fetch('./", "relativer fetch"), ("data:'./", "relative Source-URL"),
                       ("'./fonts", "relative Glyphs"), ("unpkg.com", "CDN unpkg")]:
        if _bad in _sah:
            print(f"FAIL standalone: '{_bad}' ({_lbl}) im Output")
            errors.append(f"standalone: {_bad}")
        else:
            print(f"OK   standalone frei von '{_bad}'")
    _cmiss = [c for c in ("const OSM_PEAKS", "const OSM_HUTS", "const OSM_PASSES", "const BORDERS_GJ")
              if c not in _sah]
    if _cmiss or "Piz Linard" not in _sah:
        print(f"FAIL standalone: Daten-Konstanten/Stichprobe fehlen: {_cmiss or 'Piz Linard'}")
        errors.append("standalone: inline data missing")
    else:
        print("OK   standalone: 4 Daten-Konstanten + 'Piz Linard' inline")
    # Personenfilter (SPEC_Personenfilter): Privat-Positiv-Checks (Register + Filter-Logik inline).
    _pf_pos = [c for c in ("const PERSONEN", "function serieOf", "function applyTourFilter",
                           'class="tf-chip', 'id="strangSeg"') if c not in _sah]
    if _pf_pos:
        print(f"FAIL standalone: Personenfilter-Marker fehlen: {_pf_pos}")
        errors.append(f"standalone: personenfilter missing {_pf_pos}")
    else:
        print("OK   standalone: Personenfilter inline (PERSONEN/serieOf/applyTourFilter/tf-chip/strangSeg)")
    # Fix0 v2: echtes CSP-Worker-Bundle via Blob + setWorkerUrl (sonst kein GeoJSON).
    if 'id="mlworker"' in _sah and "setWorkerUrl(URL.createObjectURL" in _sah:
        print("OK   standalone: CSP-Worker-Bundle inline + setWorkerUrl")
    else:
        print("FAIL standalone: Worker-Setup (mlworker/setWorkerUrl) fehlt -> GeoJSON bleibt leer")
        errors.append("standalone: worker setup missing")
    # A4: Glyphs base64 inline (glyphs://-Protokoll), keine Font-Requests ans Netz.
    if "glyphs://" in _sah and "const GLYPHS_DATA = {" in _sah and "github.io/alpentouren/fonts" not in _sah:
        print("OK   standalone: Glyphs base64 inline (glyphs://), keine externe Font-URL")
    else:
        print("FAIL standalone: Glyphs nicht inline (glyphs://-Protokoll/GLYPHS_DATA fehlt)")
        errors.append("standalone: glyphs not inlined")
    if _samb > 20:
        print(f"FAIL standalone {_samb:.1f} MB > 20 MB")
        errors.append("standalone >20MB")
    elif _samb > 15:
        print(f"WARN standalone {_samb:.1f} MB > 15 MB (E-Mail-Grenze)")
    else:
        print(f"OK   standalone Groesse {_samb:.1f} MB (<=15 MB)")
else:
    print("SKIP standalone-Checks (index_privat_standalone.html nicht gebaut)")

# Whitelist guard: touren_public.json may only contain gruppe/besucht.
import json as _json
tp = pathlib.Path(__file__).parent / "touren_public.json"
if tp.exists():
    _keys = {k for t in _json.loads(tp.read_text(encoding="utf-8")).get("touren", []) for k in t}
    _extra = _keys - {"gruppe", "besucht"}
    if _extra:
        print(f"FAIL touren_public.json has non-whitelist keys: {_extra}")
        errors.append(f"public json non-whitelist keys: {_extra}")
    else:
        print("OK   touren_public.json whitelist (gruppe/besucht only)")

# ── HR-Clip guard: no STS vertex may fall inside Croatia (shrunk by ~300 m) ───
# The source clip in assign_countries.py removes the Sotla/Sutla overspill of
# "Prealpi Slovene orientali" (and any STS touching HR). Verify the DERIVED
# soiusa_sts_colored.geojson carries no vertices inside HR. Do NOT test HU
# (Styrian pre-Alps are SOIUSA-correct to Kőszeg/Sopron) or SK. Skips
# gracefully if the NE-10m cache is absent (nothing to derive HR from).
_here = pathlib.Path(__file__).parent
_ne10c = _here / "ne_10m_countries.geojson"
_colored = _here / "soiusa_sts_colored.geojson"
if not _ne10c.exists():
    print("SKIP HR-Clip guard (ne_10m_countries.geojson fehlt -- assign_countries zuerst laufen lassen)")
else:
    try:
        from shapely.geometry import shape as _shape
        from shapely.ops import unary_union as _uu
        from shapely.prepared import prep as _prep

        _hr_geoms = []
        for _f in _json.loads(_ne10c.read_text(encoding="utf-8"))["features"]:
            _p = _f["properties"]
            if _p.get("ADM0_A3") == "HRV" or _p.get("ADMIN") == "Croatia":
                _g = _shape(_f["geometry"])
                if not _g.is_valid:
                    _g = _g.buffer(0)
                if _g and not _g.is_empty:
                    _hr_geoms.append(_g)
        _hr = _uu(_hr_geoms) if len(_hr_geoms) > 1 else (_hr_geoms[0] if _hr_geoms else None)
        if _hr is None:
            print("SKIP HR-Clip guard (Kroatien-Polygon nicht gefunden)")
        else:
            _hr_shrunk = _prep(_hr.buffer(-0.003))  # ~300 m inside the border

            def _coords(geom):
                t = geom["type"]
                c = geom["coordinates"]
                if t == "Point":
                    yield c
                elif t in ("LineString", "MultiPoint"):
                    yield from c
                elif t in ("Polygon", "MultiLineString"):
                    for ring in c:
                        yield from ring
                elif t == "MultiPolygon":
                    for poly in c:
                        for ring in poly:
                            yield from ring
                elif t == "GeometryCollection":
                    for gg in geom.get("geometries", []):
                        yield from _coords(gg)

            from shapely.geometry import Point as _Point
            _hits = 0
            for _feat in _json.loads(_colored.read_text(encoding="utf-8"))["features"]:
                for _xy in _coords(_feat["geometry"]):
                    if _hr_shrunk.contains(_Point(_xy[0], _xy[1])):
                        _hits += 1
            if _hits == 0:
                print("OK   HR-Clip guard: 0 STS-Vertices in Kroatien (geschrumpft)")
            else:
                print(f"FAIL HR-Clip guard: {_hits} STS-Vertices in Kroatien (geschrumpft)")
                errors.append(f"HR-Clip: {_hits} vertices in Croatia")
    except ImportError:
        print("SKIP HR-Clip guard (shapely fehlt)")

# ── Nachtjob P1: Besuchsmuster raus aus dem Tracking ──────────────────────────
# Getrackte SOIUSA-GeoJSONs muessen neutral sein (visited:0, tour_ids leer); das
# Besuchsmuster liegt gitignored in visited_overlay.json (Privat-Merge in build.py).
import re as _rep1
for _fn in ("soiusa_sts_colored.geojson", "soiusa_sts_label_points.geojson"):
    _p = pathlib.Path(__file__).parent / _fn
    if not _p.exists():
        continue
    _txt = _p.read_text(encoding="utf-8")
    if '"visited": 1' in _txt or '"visited":1' in _txt:
        print(f"FAIL privacy: '{_fn}' enthaelt visited:1 (Besuchsmuster gehoert ins Overlay)")
        errors.append(f"privacy: {_fn} visited:1")
    else:
        print(f"OK   {_fn}: 0x visited:1")
    _bad = _rep1.findall(r'"tour_ids":\s*"\[[^\]]+\]"', _txt) + _rep1.findall(r'"tour_ids":\s*\[[^\]]+\]', _txt)
    if _bad:
        print(f"FAIL privacy: '{_fn}' enthaelt nicht-leere tour_ids ({_bad[:2]})")
        errors.append(f"privacy: {_fn} tour_ids")
    else:
        print(f"OK   {_fn}: tour_ids leer")

# Besuchsmuster-Dateien (highlights / overlay) duerfen NICHT getrackt sein.
import subprocess as _sp1
try:
    _tracked = _sp1.run(["git", "ls-files"], capture_output=True, text=True,
                        cwd=str(pathlib.Path(__file__).parent)).stdout
    _leak = [l for l in _tracked.splitlines() if "highlights" in l or l == "visited_overlay.json"]
    if _leak:
        print(f"FAIL privacy: Besuchsmuster-Dateien noch getrackt: {_leak}")
        errors.append(f"privacy: tracked {_leak}")
    else:
        print("OK   highlights/overlay nicht getrackt (git ls-files)")
except Exception as _e:
    print(f"SKIP git ls-files check ({_e})")

print()
if errors:
    print(f"FEHLER: {len(errors)} Check(s) fehlgeschlagen:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print(f"Alle {len(checks)} Checks OK -- {len(html)//1024} KB")
