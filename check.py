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
    ("fill fog-fade (top-level)",     "'fill-opacity': ['interpolate',['linear'],['zoom'], 8,0.34, 11.5,0]"),
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
    ("popup on sts click",            "showStsPopup(e.lngLat"),
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
    # KPI (public: computed atlas stats)
    ("KPI Settori label",             "Settori"),
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
    ("hover on sts-fill mousemove",   "map.on('mousemove','sts-fill'"),
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
                   ("PRIV:START", "PRIV start marker"),
                   ("PRIV:END", "PRIV end marker"),
                   ("PUB:START", "PUB start marker (must be stripped)"),
                   ('"jahr"', "year field"),
                   ("function openTour", "tour-marker function"),
                   ('id="kYears"', "years KPI"),
                   ('"visited":1', "visited=1 data (E8)"),
                   ('"tour_ids":', "tour_ids data (E8)"),
                   ("Touren ansehen", "coverage button (E8)")]:
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

print()
if errors:
    print(f"FEHLER: {len(errors)} Check(s) fehlgeschlagen:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print(f"Alle {len(checks)} Checks OK -- {len(html)//1024} KB")
