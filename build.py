#!/usr/bin/env python3
"""Build a standalone index.html.

Pipeline: fetch_soiusa.py -> simplify_sts.py -> assign_countries.py -> build.py

Run:  python build.py
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).parent

# ── Build mode: public (default, deployed) vs private (--private, local only) ──
PUBLIC = "--private" not in sys.argv
SRC   = "touren_public.json" if PUBLIC else "touren.json"
OUT   = "index.html" if PUBLIC else "index_privat.html"
TITEL = "Alpentouren — wo ich war" if PUBLIC else "Alpentouren mit Papa"
UNTER = ("SOIUSA-Untergruppen nach Alpen-Struktur (Settori) — Orange = besucht. Fläche anklicken."
         if PUBLIC else
         "SOIUSA-Untergruppen nach Alpen-Struktur — Orange = besucht. Fläche anklicken.")


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
_raw = (HERE / SRC).read_text(encoding="utf-8").replace("\x00", "").strip()
data = json.loads(_raw)
for t in data["touren"]:
    for k in ("gebirge", "gegend"):
        if t.get(k): t[k] = normalize_label(t[k])
touren_json = json.dumps(data["touren"], ensure_ascii=False)

sts_json        = load_compact("soiusa_sts_colored.geojson")
highlights_json = load_compact("soiusa_highlights_clean.geojson")
lp_json         = load_compact("soiusa_sts_label_points.geojson")
mask_json       = load_compact("soiusa_mask.geojson")
try:
    wiki_json = load_compact("soiusa_wiki.json")
except FileNotFoundError:
    wiki_json = '{"gruppen":{}}'

sts_count = len(json.loads(sts_json)["features"])
hl_count  = len(json.loads(highlights_json)["features"])

TEMPLATE = r"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>__TITEL__</title>
<link href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css" rel="stylesheet" />
<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
<style>
  :root{
    --bg:#0a0e14; --panel:rgba(14,20,28,.93); --line:rgba(255,255,255,.12);
    --txt:#e8edf2; --muted:#9fb0c0; --accent:#ffb24d; --accent2:#5fd0c5;
  }
  *{box-sizing:border-box}
  html,body{margin:0;height:100%;overflow:hidden;
    font-family:"Inter",system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
    background:var(--bg);color:var(--txt)}
  #map{position:absolute;inset:0}
  .maplibregl-ctrl-attrib{font-size:10px}

  /* ── Title card ── */
  #title{position:absolute;top:16px;left:16px;z-index:5;max-width:310px;
    background:var(--panel);backdrop-filter:blur(8px);border:1px solid var(--line);
    border-radius:14px;padding:13px 15px;box-shadow:0 8px 30px rgba(0,0,0,.5)}
  #title h1{margin:0;font-size:16px;letter-spacing:.2px}
  #title p{margin:5px 0 0;font-size:11.5px;color:var(--muted);line-height:1.4}
  #title .kpi{margin-top:8px;display:flex;gap:12px}
  #title .kpi b{display:block;font-size:18px;color:var(--accent)}
  #title .kpi span{font-size:10px;color:var(--muted)}
  #title .leg{margin-top:7px;display:flex;gap:10px;flex-wrap:wrap}
  #title .leg-item{display:flex;align-items:center;gap:4px;font-size:10px;color:var(--muted)}
  .sw-hl{display:inline-block;width:10px;height:10px;border:2px solid #ffb24d;
    border-radius:2px;flex-shrink:0}
  .sw-sw{display:inline-block;width:10px;height:10px;background:#c25a68;border-radius:2px;flex-shrink:0}
  .sw-nw{display:inline-block;width:10px;height:10px;background:#2f6fed;border-radius:2px;flex-shrink:0}
  .sw-no{display:inline-block;width:10px;height:10px;background:#16a34a;border-radius:2px;flex-shrink:0}
  .sw-zo{display:inline-block;width:10px;height:10px;background:#8b5cf6;border-radius:2px;flex-shrink:0}
  .sw-so{display:inline-block;width:10px;height:10px;background:#0ea5b5;border-radius:2px;flex-shrink:0}

  /* ── Controls (stacked below title card) ── */
  #controls{position:absolute;top:196px;left:16px;z-index:5;
    display:flex;flex-direction:column;gap:6px}
  .btn{background:var(--panel);border:1px solid var(--line);
    color:var(--txt);border-radius:10px;padding:7px 12px;font-size:11.5px;
    cursor:pointer;backdrop-filter:blur(8px);white-space:nowrap}
  .btn.active{border-color:var(--accent2);color:var(--accent2)}
  .btn:hover{border-color:rgba(255,255,255,.3)}

  /* ── Detail panel ── */
  #panel{position:absolute;top:16px;right:16px;z-index:5;width:285px;
    background:var(--panel);backdrop-filter:blur(8px);border:1px solid var(--line);
    border-radius:14px;padding:0;box-shadow:0 8px 30px rgba(0,0,0,.5);
    transform:translateX(120%);transition:transform .35s cubic-bezier(.2,.8,.2,1);overflow:hidden}
  #panel.open{transform:translateX(0)}
  #panel .ph{padding:13px 13px 10px;border-bottom:1px solid var(--line)}
  #panel .yr{font-size:11px;color:var(--accent2);font-weight:600;letter-spacing:.5px}
  #panel h2{margin:3px 0 2px;font-size:16px;line-height:1.2}
  #panel .gegend{font-size:10.5px;color:var(--muted)}
  #panel .body{padding:11px 13px 13px;font-size:12.5px;line-height:1.5;max-height:60vh;overflow-y:auto}
  #panel .sec{margin:0 0 10px}
  #panel .sec h3{margin:0 0 4px;font-size:9.5px;text-transform:uppercase;letter-spacing:1px;color:var(--muted)}
  #panel ul{margin:0;padding-left:0;list-style:none}
  #panel li{padding:2px 0;display:flex;justify-content:space-between;gap:8px;
    border-bottom:1px dotted rgba(255,255,255,.08)}
  #panel li b{color:var(--accent);font-variant-numeric:tabular-nums;white-space:nowrap}
  #panel .notiz{font-size:11px;color:var(--muted);margin-top:3px;line-height:1.4}
  #panel .x{position:absolute;top:10px;right:10px;cursor:pointer;color:var(--muted);
    width:22px;height:22px;border-radius:7px;display:grid;place-items:center;font-size:15px}
  #panel .x:hover{background:rgba(255,255,255,.08);color:#fff}
  /* Tabs + Steckbrief */
  #panel .tabs{display:flex;border-bottom:1px solid var(--line)}
  #panel .tab{flex:1;padding:8px 10px;font-size:11px;text-align:center;cursor:pointer;
    color:var(--muted);border-bottom:2px solid transparent;user-select:none}
  #panel .tab.active{color:var(--accent2);border-bottom-color:var(--accent2)}
  #panel .pane{display:none}
  #panel .pane.active{display:block}
  #panel .sb-row{display:flex;justify-content:space-between;gap:10px;padding:4px 0;
    border-bottom:1px dotted rgba(255,255,255,.08);font-size:12px}
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
  #cov{position:absolute;bottom:16px;left:16px;z-index:5;width:270px;max-height:42vh;
    background:var(--panel);backdrop-filter:blur(8px);border:1px solid var(--line);
    border-radius:14px;box-shadow:0 8px 30px rgba(0,0,0,.45);overflow:hidden}
  #cov .ch{padding:10px 12px;font-size:12px;font-weight:600;cursor:pointer;
    display:flex;justify-content:space-between;align-items:center;user-select:none}
  #cov .ch span{color:var(--muted);font-weight:400;font-size:11px}
  #cov .cl{max-height:0;overflow-y:auto;transition:max-height .3s ease}
  #cov.open .cl{max-height:34vh}
  #cov .row{padding:6px 12px;font-size:11.5px;cursor:pointer;
    display:flex;justify-content:space-between;gap:8px;
    border-top:1px solid rgba(255,255,255,.06)}
  #cov .row:hover{background:rgba(255,178,77,.10)}
  #cov .row .yr{color:var(--muted);font-variant-numeric:tabular-nums}

  /* ── STS group popup ── */
  .maplibregl-popup-content{
    background:rgba(14,20,28,.95);border:1px solid rgba(255,255,255,.14);
    border-radius:9px;padding:7px 11px;box-shadow:0 6px 20px rgba(0,0,0,.55);
    min-width:120px}
  .maplibregl-popup-tip{display:none}
  .maplibregl-popup-close-button{color:#9fb0c0;font-size:15px;right:5px;top:3px;
    line-height:1;background:none}
  .sp-name{font:600 13px/1.3 Inter,system-ui,sans-serif;color:#e8edf2}
  .sp-sub{font-size:10.5px;color:#9fb0c0;margin-top:2px}

  @media(max-width:640px){
    #title{max-width:none;right:16px}
    #controls{top:auto;bottom:60px;left:16px}
    #panel{width:auto;left:16px;right:16px;top:auto;bottom:16px}
    #cov{display:none}
  }
</style>
</head>
<body>
<div id="map"></div>

<div id="title">
  <h1>__TITEL__</h1>
  <p>__UNTER__</p>
  <div class="kpi">
    <div><b id="kTours">–</b><span>Touren</span></div>
    <div><b id="kGroups">–</b><span>SOIUSA-Gruppen</span></div>
    <div><b id="kYears">–</b><span>Jahre</span></div>
  </div>
  <div class="leg">
    <span class="leg-item"><span class="sw-hl"></span>besucht</span>
    <span class="leg-item"><span class="sw-nw"></span>Nordwestalpen</span>
    <span class="leg-item"><span class="sw-sw"></span>S&uuml;dwestalpen</span>
    <span class="leg-item"><span class="sw-no"></span>Nordostalpen</span>
    <span class="leg-item"><span class="sw-zo"></span>Zentralostalpen</span>
    <span class="leg-item"><span class="sw-so"></span>S&uuml;dostalpen</span>
  </div>
</div>

<div id="controls">
  <button id="toggleLayers" class="btn" onclick="toggleLayers()">Namen</button>
  <button class="btn" onclick="overview()">Alpen&uuml;berblick</button>
</div>

<div id="panel">
  <div class="x" onclick="closePanel()">&times;</div>
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

<div id="cov">
  <div class="ch" onclick="document.getElementById('cov').classList.toggle('open')">
    Besuchte Gebiete <span id="covCount"></span>
  </div>
  <div class="cl" id="covList"></div>
</div>

<script>
const TOUREN = __TOUREN_GEOJSON__;
const SOIUSA_STS = __SOIUSA_STS_GEOJSON__;
const SOIUSA_HIGHLIGHTS = __SOIUSA_HIGHLIGHTS_GEOJSON__;
const SOIUSA_LBL_PTS    = __SOIUSA_LBL_PTS_GEOJSON__;
const MASK = __MASK_GEOJSON__;
const WIKI = __SOIUSA_WIKI_JSON__;
const PRIV = __PRIV__;
const CNAMES = {AT:'Österreich',CH:'Schweiz',DE:'Deutschland',
  FR:'Frankreich',IT:'Italien',SI:'Slowenien',LI:'Liechtenstein'};

console.log('SOIUSA:', SOIUSA_STS.features.length, 'Untergruppen,',
            SOIUSA_HIGHLIGHTS.features.length, 'Highlights');

// ── Coverage ─────────────────────────────────────────────────────────────────
const groups = {};
TOUREN.forEach(t=>{
  const k=t.gebirge;
  if(!groups[k]) groups[k]={name:k, years:[], land:t.land};
  groups[k].years.push(t.jahr);
});
const groupList = Object.values(groups).sort((a,b)=>a.name.localeCompare(b.name));
const years = TOUREN.map(t=>parseInt(String(t.jahr).replace(/[^0-9]/g,'').slice(0,4))).filter(Boolean);

document.getElementById('kTours').textContent  = TOUREN.length;
document.getElementById('kGroups').textContent = SOIUSA_HIGHLIGHTS.features.length+'/'+SOIUSA_STS.features.length;
document.getElementById('kYears').textContent  = Math.min(...years)+'–'+Math.max(...years);
document.getElementById('covCount').textContent = groupList.length;

// ── GeoJSON point features ────────────────────────────────────────────────────
const fc = {type:'FeatureCollection', features: TOUREN.map(t=>({
  type:'Feature',
  geometry:{type:'Point', coordinates:[t.lon, t.lat]},
  properties:{id:t.id, jahr:t.jahr, gegend:t.gegend, gebirge:t.gebirge,
              land:t.land, verifiziert:t.verifiziert?1:0}
}))};

// ── Default camera: full Alpine view, slightly SW-biased ──────────────────────
const ALPS = {center:[10.2,46.1], zoom:5.3, pitch:0, bearing:0};

const map = new maplibregl.Map({
  container:'map',
  pixelRatio: window.devicePixelRatio || 2,
  minZoom: 5.0,
  maxBounds: [[3.5,42.5],[18.5,49.5]],
  style:{
    version:8,
    glyphs:'./fonts/{fontstack}/{range}.pbf',
    sources:{
      sat:{type:'raster', tileSize:256,
        tiles:['https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
        attribution:'Imagery © Esri, Maxar, Earthstar Geographics'},
      dem:{type:'raster-dem', tileSize:256, encoding:'terrarium', maxzoom:14,
        tiles:['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'],
        attribution:'Elevation: Mapzen Terrain Tiles / AWS Open Data'}
    },
    layers:[
      {id:'bg',  type:'background', paint:{'background-color':'#0a0e14'}},
      {id:'sat', type:'raster', source:'sat', paint:{'raster-opacity':0.95}},
      {id:'hill',type:'hillshade', source:'dem',
        paint:{'hillshade-exaggeration':0.25,'hillshade-shadow-color':'#1a2840'}}
    ]
  },
  center:ALPS.center, zoom:ALPS.zoom, pitch:ALPS.pitch, bearing:ALPS.bearing,
  maxPitch:70, hash:true,
  attributionControl:{compact:true,
    customAttribution:'SOIUSA © Arpa Piemonte · Marazzi et al. · Accorsi'}
});
map.addControl(new maplibregl.NavigationControl({visualizePitch:true}), 'bottom-right');

// ── Group name popup — shown on every STS click ───────────────────────────────
// closeOnClick:false — sonst schließt MapLibre den im selben Klick geöffneten Popup
// wieder (Name erst beim 2. Klick). Schließen via X / closePanel / Leer-Klick unten.
const stsPopup = new maplibregl.Popup({
  closeButton:true, closeOnClick:false, offset:10, maxWidth:'260px'});
function showStsPopup(lngLat, props){
  const name = props.name_de || props.STS || '—';
  const sub  = props.visited!==1 && props.settore && props.settore!=='—'
    ? '<div class="sp-sub">'+props.settore+'</div>' : '';
  stsPopup.setLngLat(lngLat)
    .setHTML('<div class="sp-name">'+name+'</div>'+sub)
    .addTo(map);
}

map.on('load',()=>{
  map.setTerrain({source:'dem', exaggeration:1.0});
  try{map.setSky({'sky-color':'#0b1f3a','horizon-color':'#7a92ad','fog-color':'#c8d6e5',
    'sky-horizon-blend':0.6,'horizon-fog-blend':0.5,'fog-ground-blend':0.4,
    'atmosphere-blend':0.4});}catch(e){}

  // ── Sources ──────────────────────────────────────────────────────────────
  map.addSource('mask',       {type:'geojson', data:MASK});
  map.addSource('sts',        {type:'geojson', data:SOIUSA_STS});
  map.addSource('highlights', {type:'geojson', data:SOIUSA_HIGHLIGHTS});
  map.addSource('sts-lp',    {type:'geojson', data:SOIUSA_LBL_PTS});
  map.addSource('tours',     {type:'geojson', data:fc});

  // ── Non-Alpine mask — always on ───────────────────────────────────────────
  map.addLayer({id:'mask-fill', type:'fill', source:'mask',
    paint:{'fill-color':'#000816','fill-opacity':0.42}});

  // ── STS mosaic fill — toggle-controlled ──────────────────────────────────
  // 'coalesce' prevents MapLibre crash when fill_color is undefined on a feature.
  // Opacity higher for visited groups.
  map.addLayer({id:'sts-fill', type:'fill', source:'sts',
    paint:{
      'fill-color': ['coalesce',['get','fill_color'],'#888888'],
      'fill-opacity': ['case',['==',['get','visited'],1],0.55,0.34]
    }});

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
      'text-allow-overlap':false,'text-optional':true,'text-anchor':'center'},
    paint:{'text-color':'rgba(232,240,255,0.95)',
           'text-halo-color':'#06101a','text-halo-width':1.8,'text-halo-blur':0.2}});

  // ── German labels for visited — toggle-controlled, off by default ───────────
  // Font: 'Noto Sans Bold' — PBFs self-hosted under fonts/Noto Sans Bold/ (fetch_fonts.py).
  // Source: sts-lp → one label per visited group, no duplicates.
  map.addLayer({id:'sts-label-hl', type:'symbol', source:'sts-lp',
    filter:['==',['get','visited'],1],
    layout:{'visibility':'none',
      'text-field':['get','name_de'],'text-font':['Noto Sans Bold'],
      'text-size':13,'text-allow-overlap':false,'text-optional':true,'text-anchor':'center'},
    paint:{'text-color':'#ffd47a',
           'text-halo-color':'#06101a','text-halo-width':2.0,'text-halo-blur':0.2}});

  // ── Selection ring — filter-driven, initially empty ───────────────────────
  map.addLayer({id:'sts-selected', type:'line', source:'sts',
    filter:['==',['get','STS'],''],
    layout:{'line-join':'round'},
    paint:{'line-color':'#ffffff','line-width':3.2,'line-opacity':0.95}});

  // ── Tour markers ─────────────────────────────────────────────────────────
  map.addLayer({id:'t-halo', type:'circle', source:'tours',
    paint:{'circle-radius':13,'circle-color':'#ffb24d',
           'circle-opacity':0.18,'circle-blur':0.4}});
  map.addLayer({id:'t-dot', type:'circle', source:'tours',
    paint:{'circle-radius':6.5,
      'circle-color':['case',['==',['get','verifiziert'],1],'#ffb24d','#5fd0c5'],
      'circle-stroke-width':2,'circle-stroke-color':'#0a0e14'}});
  // ── Tour marker events ────────────────────────────────────────────────────
  const pop = new maplibregl.Popup({closeButton:false,closeOnClick:false,offset:12});
  map.on('mouseenter','t-dot',e=>{
    map.getCanvas().style.cursor='pointer';
    const p=e.features[0].properties;
    pop.setLngLat(e.features[0].geometry.coordinates)
       .setHTML('<b>'+p.gebirge+'</b> · '+p.jahr).addTo(map);
  });
  map.on('mouseleave','t-dot',()=>{map.getCanvas().style.cursor='';pop.remove();});
  map.on('click','t-dot',e=>openTour(e.features[0].properties.id));

  // ── STS fill click — popup always; panel only for visited groups ─────────
  map.on('mouseenter','sts-fill',()=>map.getCanvas().style.cursor='pointer');
  map.on('mouseleave','sts-fill',()=>map.getCanvas().style.cursor='');
  map.on('click','sts-fill',e=>{
    if(map.queryRenderedFeatures(e.point,{layers:['t-dot']}).length) return;
    const feat=e.features[0];
    const props=feat.properties||{};
    showStsPopup(e.lngLat, props);
    if(props.visited===1){
      openSts(feat);
    } else {
      map.setFilter('sts-selected',['==',['get','STS'],props.STS||'__none__']);
      document.getElementById('panel').classList.remove('open');
    }
  });

  // ── HL-line click — fallback when fill is toggled off ────────────────────
  // Skip if sts-fill rendered features are present (sts-fill click takes priority).
  map.on('mouseenter','hl-line',()=>map.getCanvas().style.cursor='pointer');
  map.on('mouseleave','hl-line',()=>map.getCanvas().style.cursor='');
  map.on('click','hl-line',e=>{
    if(map.queryRenderedFeatures(e.point,{layers:['t-dot','sts-fill']}).length) return;
    const hp = e.features[0].properties;
    const matchName = (hp.match_field==='STS') ? hp.soiusa_name : (hp.parent_sts||'');
    const stsFeat = SOIUSA_STS.features.find(f=>f.properties.STS===matchName);
    if(stsFeat){
      showStsPopup(e.lngLat, stsFeat.properties||{});
      openSts(stsFeat);
    }
  });

  // ── Click on empty map (no feature) closes the popup ──────────────────────
  map.on('click', e=>{
    if(!map.queryRenderedFeatures(e.point,{layers:['sts-fill','hl-line','t-dot']}).length)
      stsPopup.remove();
  });

  // ── Fix blank canvas — map.resize() is more reliable than triggerRepaint ──
  map.resize();
  setTimeout(()=>map.resize(), 150);
  map.once('idle',()=>map.resize());
});

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
function setTourTab(html){
  const el=document.getElementById('pTour');
  const tabs=document.getElementById('pTabs');
  const show = PRIV && !!html;
  if(el) el.innerHTML = show ? html : '';
  if(tabs) tabs.style.display = show ? 'flex' : 'none';
  showTab(show ? 'tour' : 'about');
}

// ── Gipfel list markup (shared) ───────────────────────────────────────────────
function gipfelUl(gipfel){
  if(!gipfel||!gipfel.length) return '';
  return '<ul>'+gipfel.map(g=>'<li><span>'+g.name+
    (g.hinweis?' <i style="color:var(--muted)">('+g.hinweis+')</i>':'')+
    '</span>'+(g.hoehe_m?'<b>'+g.hoehe_m+' m</b>':'')+'</li>').join('')+'</ul>';
}

// ── Open: tour marker ─────────────────────────────────────────────────────────
function openTour(id){
  const t=TOUREN.find(x=>x.id==id); if(!t) return;
  map.setFilter('sts-selected',['==',['get','STS'],'']);
  document.getElementById('pYear').textContent=(t.land?t.land+' · ':'')+t.jahr;
  document.getElementById('pGroup').textContent=t.gebirge;
  document.getElementById('pGegend').textContent=t.gegend||'';
  // About pane: impersonal facts (Gipfel)
  let about='';
  if(t.gipfel&&t.gipfel.length) about+='<div class="sec"><h3>Gipfel</h3>'+gipfelUl(t.gipfel)+'</div>';
  document.getElementById('pAbout').innerHTML = about || '<div class="sb-open">—</div>';
  // Tour pane: private only (Hütten + Notiz)
  let tour='';
  if(t.huetten) tour+='<div class="sec"><h3>Hütten / Stationen</h3>'+t.huetten+'</div>';
  if(t.bemerkung) tour+='<div class="sec"><h3>Notiz</h3>'+t.bemerkung+'</div>';
  setTourTab(tour);
  document.getElementById('panel').classList.add('open');
  map.flyTo({center:[t.lon,t.lat],zoom:9.5,pitch:20,bearing:0,duration:1200,essential:true});
}

// ── Steckbrief markup (public-safe, from soiusa_wiki.json) ────────────────────
function steckbriefHtml(stsName, props){
  const w = (WIKI.gruppen||{})[stsName] || null;
  const settore = props.settore || '';
  const rows = [];
  if(w && w.hoechster_berg)
    rows.push(['Höchster Berg','<b>'+w.hoechster_berg+'</b>'+(w.hoehe_m?' · '+w.hoehe_m+' m':'')]);
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

// ── Tour markup for a visited group (private build only) ──────────────────────
function groupTourHtml(props){
  const tourIds = typeof props.tour_ids==='string'
    ? JSON.parse(props.tour_ids) : (Array.isArray(props.tour_ids)?props.tour_ids:[]);
  const tours = tourIds.map(id=>TOUREN.find(t=>t.id==id)).filter(Boolean);
  if(!tours.length) return '';
  let html='';
  const gebs=[...new Set(tours.map(t=>t.gebirge))];
  if(gebs.length>1) html+='<div class="notiz" style="margin:0 0 9px">SOIUSA fasst '+
    gebs.join(' &amp; ')+' zu einer Untergruppe zusammen ('+tours.length+' Touren).</div>';
  tours.forEach(t=>{
    html+='<div class="sec">';
    if(tours.length>1) html+='<h3>'+t.gebirge+(t.jahr?' — '+t.jahr:'')+'</h3>';
    html+=gipfelUl(t.gipfel);
    if(t.huetten) html+='<div class="notiz"><b style="color:var(--muted)">Hütten:</b> '+t.huetten+'</div>';
    if(t.bemerkung) html+='<div class="notiz">'+t.bemerkung+'</div>';
    html+='</div>';
  });
  return html;
}

// ── Open: STS polygon (visited or not) ───────────────────────────────────────
function openSts(feat){
  const props = feat.properties || {};
  const stsName = String(props.STS || '').trim();
  // Harden: use '__none__' sentinel so empty-string filter doesn't accidentally match
  map.setFilter('sts-selected',['==',['get','STS'], stsName||'__none__']);
  const visited = props.visited === 1;

  document.getElementById('pGroup').textContent = props.name_de || stsName;
  document.getElementById('pGegend').textContent = stsName + (props.CODICE?' · '+props.CODICE:'');
  document.getElementById('pYear').textContent = visited ? 'Besucht' : 'Noch nicht besucht';

  document.getElementById('pAbout').innerHTML = steckbriefHtml(stsName, props);
  setTourTab(visited ? groupTourHtml(props) : '');

  document.getElementById('panel').classList.add('open');
  const bb=featBbox(feat);
  if(bb) map.fitBounds(bb,{padding:{top:80,bottom:80,left:80,right:310},
    pitch:18,bearing:0,maxZoom:10,duration:1200,essential:true});
}

// ── Toggle: group labels (fills always on) ────────────────────────────────────
// sts-fill / sts-line always visible; button toggles only the text labels.
let _layersOn=false;
function toggleLayers(){
  _layersOn=!_layersOn;
  const v=_layersOn?'visible':'none';
  map.setLayoutProperty('sts-label',   'visibility',v);
  map.setLayoutProperty('sts-label-hl','visibility',v);
  document.getElementById('toggleLayers').classList.toggle('active',_layersOn);
}

function closePanel(){
  stsPopup.remove();
  document.getElementById('panel').classList.remove('open');
  map.setFilter('sts-selected',['==',['get','STS'],'']);
}
function overview(){
  closePanel();
  map.flyTo({...ALPS,duration:1200,essential:true});
}

// ── Coverage list ─────────────────────────────────────────────────────────────
const cl=document.getElementById('covList');
cl.innerHTML=groupList.map(g=>{
  const t=TOUREN.find(x=>x.gebirge===g.name);
  return '<div class="row" onclick="openTour('+t.id+')"><span>'+g.name+'</span>'+
    '<span class="yr">'+g.years.join(', ')+'</span></div>';
}).join('');
</script>
</body>
</html>
"""

html = TEMPLATE.replace("__TOUREN_GEOJSON__",        touren_json)
html = html.replace("__SOIUSA_STS_GEOJSON__",         sts_json)
html = html.replace("__SOIUSA_HIGHLIGHTS_GEOJSON__",  highlights_json)
html = html.replace("__MASK_GEOJSON__",               mask_json)
html = html.replace("__SOIUSA_LBL_PTS_GEOJSON__",    lp_json)
html = html.replace("__SOIUSA_WIKI_JSON__",          wiki_json)
html = html.replace("__TITEL__", TITEL).replace("__UNTER__", UNTER)
html = html.replace("__PRIV__", "false" if PUBLIC else "true")

# Tab bar only in the private build — keeps the string "Tour mit Papa" out of public HTML.
PTABS = "" if PUBLIC else (
    '<div class="tabs" id="pTabs">'
    "<div class=\"tab\" id=\"tabTour\" onclick=\"showTab('tour')\">Tour mit Papa</div>"
    "<div class=\"tab active\" id=\"tabAbout\" onclick=\"showTab('about')\">Über die Gruppe</div>"
    "</div>")
html = html.replace("__PTABS__", PTABS)

out = HERE / OUT
out.write_text(html, encoding="utf-8")
size_kb = out.stat().st_size / 1024
mode = "public" if PUBLIC else "PRIVAT"
print(f"{OUT} [{mode}]: {len(data['touren'])} Touren · {hl_count}/{sts_count} Untergruppen · {size_kb:.0f} KB")
