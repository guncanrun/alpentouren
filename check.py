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
    ("fill fog-fade to z12",          "10.5,0.35, 12,0"),
    ("auto-pitch fn",                 "function pitchForZoom"),
    ("sts-line non-visited filter",   "filter:['==',['get','visited'],0]"),
    ("hl-line orange color",          "'line-color':'#ffb24d'"),
    ("hl-line always (no toggle)",    "id:'hl-line', type:'line'"),
    ("sts-label-hl visited filter",   "filter:['==',['get','visited'],1]"),
    ("sts-label non-visited filter",  "filter:['==',['get','visited'],0]"),
    ("sts-label minzoom 6.5",         "minzoom:6.5"),
    ("line-join round",               "'line-join':'round'"),
    # Functions
    ("openSts fn",                    "function openSts"),
    ("openTour fn",                   "function openTour"),
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
    ("peak triangle icon",            "map.addImage('peak'"),
    ("hut club icon",                 "'hut-club'"),
    # Phase 2c — Berge nach Klick
    ("peaks-in-group layer",          "id:'peaks-in-group'"),
    ("peaks-highest layer",           "id:'peaks-highest'"),
    ("showGroupPeaks fn",             "function showGroupPeaks"),
    ("within filter",                 "['within',geom]"),
    ("togglePeaks fn",                "function togglePeaks"),
    ("toggleHuts fn",                 "function toggleHuts"),
    ("peaks button",                  'id="btnPeaks"'),
    ("huts button",                   'id="btnHuts"'),
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
    # Public build hygiene
    ("public neutral title",          "Alpentouren — wo ich war"),
    # KPI
    ("KPI dynamic total",             "features.length+'/'+SOIUSA_STS.features.length"),
    ("tour_ids JSON.parse",           "JSON.parse(props.tour_ids)"),
    # Data integrity
    ("Silvretta / Verwall",           "Silvretta / Verwall"),
    ("Settore legend Nordwestalpen",  "Nordwestalpen"),
    ("popup uses settore",            "props.settore"),
    ("settore in feature props",      '"settore"'),
    # UI
    ("controls div",                  'id="controls"'),
    ("cov default collapsed",         '<div id="cov">'),
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

# Negative guard: the public build must NOT carry the private tab label.
if "Tour mit Papa" in html:
    print("FAIL public leak: 'Tour mit Papa' present in index.html")
    errors.append("public leak: 'Tour mit Papa' in index.html")
else:
    print("OK   public build free of 'Tour mit Papa'")

print()
if errors:
    print(f"FEHLER: {len(errors)} Check(s) fehlgeschlagen:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print(f"Alle {len(checks)} Checks OK -- {len(html)//1024} KB")
