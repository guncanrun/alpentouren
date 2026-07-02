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

# ── Build mode: public (default, deployed) vs private (--private, local only) ──
PUBLIC = "--private" not in sys.argv
SRC   = "touren.json"   # only the private build reads tour data (E8)
OUT   = "index.html" if PUBLIC else "index_privat.html"
TITEL = "Alpen-Atlas" if PUBLIC else "Alpentouren mit Papa"
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
else:
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
<link href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css" rel="stylesheet" />
<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
<style>
  :root{
    --bg:#0a0e14; --panel:rgba(14,20,28,.93); --line:rgba(255,255,255,.12);
    --txt:#e8edf2; --muted:#9fb0c0; --accent:#ffb24d; --accent2:#5fd0c5;
    /* Dichte: kompakte Desktop-Basis (fein-Zeiger). Touch ueberschreibt unten. */
    --row-h:32px; --fs-ui:13.5px; --fs-popup:14px;
    --ctl:32px;        /* Zeilen-Controls / Schliessen-X */
    --ctl-round:40px;  /* runde Aktions-Icons (Info/Home/Suche): Maus-freundlich */
  }
  /* Touch (Tablet/Handy): grosse, komfortable Ziele. Desktop bleibt kompakt. */
  @media (pointer: coarse){
    :root{ --row-h:44px; --fs-ui:16px; --fs-popup:16px; --ctl:44px; --ctl-round:44px; }
  }
  /* Grosse Screens (27"+, feiner Zeiger): kompakte Desktop-Basis wirkt dort zu klein.
     Groessere Schrift/Controls + ~20% breitere Panels/Karten/Title. 16" (<2200px) und
     Touch (coarse) bleiben unveraendert. */
  @media (min-width: 2200px) and (pointer: fine){
    :root{ --row-h:38px; --fs-ui:15.5px; --fs-popup:15.5px; --ctl:36px; --ctl-round:46px; }
    #title{max-width:372px}
    #title h1{font-size:24px}
    #title p{font-size:15.5px}
    #title .kpi b{font-size:26px}
    #panel{width:342px}
    #ebenen{width:278px}
    #legend{width:224px}
    #cov{width:324px}
    #about{width:min(432px,calc(100vw - 32px))}
    .hut-pop{max-width:276px}
  }
  *{box-sizing:border-box}
  html,body{margin:0;height:100%;overflow:hidden;
    font-family:"Inter",system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
    background:var(--bg);color:var(--txt)}
  #map{position:absolute;inset:0}
  .maplibregl-ctrl-attrib{font-size:10px}
  /* MapLibre zoom/compass buttons: kompakt am Desktop, >=44px auf Touch (var) */
  .maplibregl-ctrl-group button{width:var(--ctl);height:var(--ctl);touch-action:manipulation}
  .maplibregl-ctrl-group button .maplibregl-ctrl-icon{transform:scale(1.15)}

  /* ── Title card ── */
  #title{position:absolute;top:16px;left:16px;z-index:5;max-width:310px;
    background:var(--panel);backdrop-filter:blur(8px);border:1px solid var(--line);
    border-radius:14px;padding:13px 15px;box-shadow:0 8px 30px rgba(0,0,0,.5)}
  #title h1{margin:0;font-size:20px;letter-spacing:.2px}
  #title p{margin:6px 0 0;font-size:13px;color:var(--muted);line-height:1.45}
  #title .kpi{margin-top:10px;display:flex;gap:16px}
  #title .kpi b{display:block;font-size:22px;color:var(--accent)}
  #title .kpi span{font-size:11px;color:var(--muted)}
  /* ── Legend box (bottom-right, collapsible) ── */
  #legend{position:absolute;bottom:150px;right:16px;z-index:5;width:186px;
    background:var(--panel);backdrop-filter:blur(8px);border:1px solid var(--line);
    border-radius:12px;box-shadow:0 8px 30px rgba(0,0,0,.45);overflow:hidden}
  #legend .lh{padding:9px 12px;font-size:12px;font-weight:600;cursor:pointer;
    display:flex;justify-content:space-between;align-items:center;user-select:none}
  #legend .lh::after{content:'▾';color:var(--muted);transition:transform .3s}
  #legend.open .lh::after{transform:rotate(180deg)}
  #legend .ll{max-height:0;overflow:hidden;transition:max-height .3s ease}
  #legend.open .ll{max-height:240px}
  #legend .lrow{display:flex;align-items:center;gap:8px;padding:4px 12px 4px;
    font-size:11.5px;color:var(--txt)}
  #legend .lrow:last-child{padding-bottom:10px}
  #legend .lsep{height:1px;background:var(--line);margin:6px 12px}
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
  #panel{position:absolute;top:174px;left:16px;z-index:7;width:285px;
    background:var(--panel);backdrop-filter:blur(8px);border:1px solid var(--line);
    border-radius:14px;padding:0;box-shadow:0 8px 30px rgba(0,0,0,.5);
    transform:translateX(-120%);transition:transform .35s cubic-bezier(.2,.8,.2,1);overflow:hidden}
  #panel.open{transform:translateX(0)}
  #panel .ph{padding:13px 13px 10px;border-bottom:1px solid var(--line)}
  #panel .yr{font-size:11px;color:var(--accent2);font-weight:600;letter-spacing:.5px}
  #panel h2{margin:3px 0 2px;font-size:16px;line-height:1.2}
  #panel .gegend{font-size:10.5px;color:var(--muted)}
  #panel .body{padding:11px 14px 14px;font-size:14px;line-height:1.55;max-height:58vh;overflow-y:auto;
    -webkit-overflow-scrolling:touch}
  #panel .sec{margin:0 0 10px}
  #panel .sec h3{margin:0 0 4px;font-size:9.5px;text-transform:uppercase;letter-spacing:1px;color:var(--muted)}
  #panel ul{margin:0;padding-left:0;list-style:none}
  #panel li{padding:2px 0;display:flex;justify-content:space-between;gap:8px;
    border-bottom:1px dotted rgba(255,255,255,.08)}
  #panel li b{color:var(--accent);font-variant-numeric:tabular-nums;white-space:nowrap}
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
  #cov{position:absolute;bottom:74px;left:16px;z-index:5;width:270px;max-height:42vh;
    background:var(--panel);backdrop-filter:blur(8px);border:1px solid var(--line);
    border-radius:14px;box-shadow:0 8px 30px rgba(0,0,0,.45);overflow:hidden}
  #cov .ch{padding:9px 14px;font-size:var(--fs-ui);font-weight:600;cursor:pointer;min-height:var(--row-h);
    display:flex;justify-content:space-between;align-items:center;user-select:none;touch-action:manipulation}
  #cov .ch span{color:var(--muted);font-weight:400;font-size:11px}
  #cov .cl{max-height:0;overflow-y:auto;transition:max-height .3s ease}
  #cov.open .cl{max-height:34vh}
  #cov .row{padding:8px 14px;font-size:var(--fs-ui);cursor:pointer;min-height:var(--row-h);box-sizing:border-box;
    display:flex;justify-content:space-between;align-items:center;gap:8px;
    border-top:1px solid rgba(255,255,255,.06);touch-action:manipulation}
  #cov .row:hover{background:rgba(255,178,77,.10)}
  #cov .row .yr{color:var(--muted);font-variant-numeric:tabular-nums}

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

  /* ── About / Info card ── */
  #about{position:absolute;top:16px;left:50%;transform:translateX(-50%);z-index:10;
    width:min(360px,calc(100vw - 32px));background:var(--panel);backdrop-filter:blur(8px);
    border:1px solid var(--line);border-radius:14px;padding:14px 16px;
    box-shadow:0 8px 30px rgba(0,0,0,.55);display:none}
  #about.open{display:block}
  #about h3{margin:10px 0 6px;font-size:15px}
  #about h3:first-of-type{margin-top:0}
  #about p{margin:5px 0;font-size:13px;color:var(--muted);line-height:1.55}
  #about b{color:var(--txt)}
  #about .x{position:absolute;top:5px;right:5px;cursor:pointer;color:var(--muted);font-size:22px;
    width:var(--ctl);height:var(--ctl);display:grid;place-items:center;border-radius:10px;touch-action:manipulation}
  #about .x:hover{background:rgba(255,255,255,.08);color:#fff}
  #about a{color:var(--accent2);text-decoration:none}

  /* ── Ebenen-Panel (Toggle-Switches + Legende) ── */
  #ebenen{position:absolute;top:64px;right:16px;z-index:6;width:232px;
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
  #home{position:absolute;bottom:150px;right:16px;z-index:6;width:var(--ctl-round);height:var(--ctl-round);
    border-radius:11px;background:var(--panel);border:1px solid var(--line);color:var(--txt);
    font-size:19px;cursor:pointer;backdrop-filter:blur(8px);touch-action:manipulation}
  #home:hover{border-color:var(--accent2);color:var(--accent2)}
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
  .seg{display:flex;gap:6px;margin:2px 0 2px}
  .seg button{flex:1;min-height:var(--row-h);padding:6px;border:1px solid var(--line);border-radius:9px;
    background:rgba(255,255,255,.04);color:var(--muted);font-size:var(--fs-ui);cursor:pointer;
    font-family:inherit;touch-action:manipulation}
  .seg button.on{background:rgba(95,208,197,.16);border-color:var(--accent2);color:var(--txt);font-weight:600}

  /* PRIV:START */
  /* ── Chronologie-Modus (nur Privat-Build) ── */
  #chronoBtn{position:absolute;left:16px;bottom:16px;z-index:8;
    width:var(--ctl-round);height:var(--ctl-round);border-radius:50%;
    background:var(--panel);border:1px solid var(--line);color:var(--txt);
    font-size:18px;cursor:pointer;backdrop-filter:blur(8px);touch-action:manipulation}
  #chronoBtn:hover{border-color:var(--accent2);color:var(--accent2)}
  #chronoBtn.active{border-color:var(--accent);color:var(--accent);background:rgba(255,178,77,.14)}
  #chronoBar{position:absolute;left:74px;right:64px;bottom:16px;z-index:7;display:none;
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
  #chronoCap{position:absolute;left:74px;bottom:76px;z-index:7;display:none;
    max-width:min(52vw,420px);background:var(--panel);backdrop-filter:blur(8px);
    border:1px solid var(--line);border-radius:14px;padding:9px 13px;
    box-shadow:0 8px 30px rgba(0,0,0,.45)}
  #chronoCap.open{display:block}
  .cc-h{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
  .cc-y{font-size:22px;font-weight:700;color:var(--accent);line-height:1.1}
  .cc-d{font-size:12px;color:var(--muted)}
  .cc-t{font-size:13px;color:var(--txt);line-height:1.45;margin-top:3px}
  .cc-who{font-style:italic;color:var(--muted)}
  .cc-memo{font-size:11.5px;color:var(--muted);line-height:1.4;margin-top:1px;
    border-left:2px solid rgba(255,178,77,.5);padding-left:7px}
  /* PRIV:END */

  @media(max-width:640px){
    #title{max-width:calc(100vw - 90px)}
    #panel{width:auto;left:16px;right:16px;top:auto;bottom:16px;z-index:9}
    #ebenen{max-width:calc(100vw - 32px)}
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
    <!-- PUB:START --><div><b>__KPI_GRUPPEN__</b><span>Gruppen</span></div><div><b>__KPI_SETTORI__</b><span>Settori</span></div><div><b>__KPI_HUETTEN__</b><span>Vereinsh&uuml;tten</span></div><!-- PUB:END -->
    <!-- PRIV:START --><div><b id="kTours">–</b><span>Touren</span></div><div><b id="kGroups">–</b><span>SOIUSA-Gruppen</span></div><div><b id="kYears">–</b><span>Jahre</span></div><!-- PRIV:END -->
  </div>
</div>

<button id="btnInfo" onclick="toggleAbout()" title="Info &amp; Anleitung">?</button>
<button id="home" onclick="overview()" title="Standardansicht">&#8962;</button>

<div id="search">
  <button id="sToggle" onclick="toggleSearch()" title="Suche" aria-label="Suche">&#128269;</button>
  <input id="sInput" type="text" autocomplete="off" spellcheck="false"
    placeholder="Gipfel, H&uuml;tte, Pass, Gruppe, Koordinate&hellip;" />
  <div id="sRes"></div>
</div>

<div id="about">
  <div class="x" onclick="toggleAbout()">&times;</div>
  <h3>So bedienst du die Karte</h3>
  <!-- PUB:START --><p>Auf eine <b>farbige Fl&auml;che tippen</b> &rarr; Steckbrief der Gruppe
     (h&ouml;chster Berg, Lage, Land). Rechts im Panel <b>„Ebenen"</b> schaltest du
     F&auml;rbung, Namen, Landesgrenzen, Gipfel, H&uuml;tten &amp; P&auml;sse; das Haus-Icon
     setzt die <b>Standardansicht</b> zur&uuml;ck.</p><!-- PUB:END -->
  <!-- PRIV:START --><p>Auf eine <b>farbige Fl&auml;che tippen</b> &rarr; Steckbrief &amp; besuchte Touren. Rechts im
     Panel <b>„Ebenen"</b> schaltest du F&auml;rbung, Namen, Gipfel, H&uuml;tten &amp; P&auml;sse.
     Unten links <b>„Touren ansehen"</b> f&uuml;hrt zu den besuchten Gebieten; das Haus-Icon
     setzt die <b>Standardansicht</b> zur&uuml;ck.</p><!-- PRIV:END -->
  <h3>&Uuml;ber diese Karte</h3>
  <!-- PUB:START --><p>Ein interaktiver <b>Alpen-Atlas</b> nach <b>SOIUSA</b>, der internationalen
     Gliederung der Alpen (italienischer Standard von 2005): alle 131 Gebirgsgruppen, geb&uuml;ndelt
     in f&uuml;nf Gro&szlig;sektoren (<b>Grandi Settori</b>), dazu Gipfel, H&uuml;tten und P&auml;sse
     aus OpenStreetMap.</p>
  <p><a href="https://de.wikipedia.org/wiki/SOIUSA" target="_blank" rel="noopener">SOIUSA auf Wikipedia &rarr;</a></p><!-- PUB:END -->
  <!-- PRIV:START --><p>Interaktive 3D-Karte der Alpen: welche <b>SOIUSA-Untergruppen</b> ich besucht habe,
     eingebettet in die Gesamtstruktur des Gebirges.</p><!-- PRIV:END -->
  <p><b>Tech:</b> Datenaufbereitung in <b>Python</b>, Rendering mit <b>MapLibre GL JS</b>,
     3D-Terrain aus offenem DEM. Komplett <b>statisch &amp; keyless</b> auf GitHub Pages
     (kein Server, kein API-Key).</p>
  <p><b>Daten:</b> SOIUSA (ARPA Piemonte) &middot; OpenStreetMap &ndash; Gipfel/H&uuml;tten (ODbL)
     &middot; Wikipedia/Wikidata &ndash; Steckbriefe (CC BY-SA) &middot; Natural Earth
     &middot; Esri World Imagery.</p>
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

<!-- PRIV:START -->
<div id="cov">
  <div class="ch" onclick="document.getElementById('cov').classList.toggle('open')">
Touren ansehen <span id="covCount"></span>
  </div>
  <div class="cl" id="covList"></div>
</div>
<!-- Chronologie-Modus: runder Toggle unten links + Caption + Jahresleiste (Play) -->
<button id="chronoBtn" onclick="chronoToggle()" title="Chronologie &ndash; Jahre durchgehen">&#128344;</button>
<div id="chronoCap"></div>
<div id="chronoBar">
  <button id="chronoPlay" onclick="chronoPlayToggle()" title="Abspielen" aria-label="Abspielen">&#9654;</button>
  <div id="chronoChips"></div>
</div>
<!-- PRIV:END -->

<div id="ebenen" class="open">
  <div class="eh" onclick="document.getElementById('ebenen').classList.toggle('open')">Ebenen</div>
  <div class="eb"><div class="eb-in">
    <div class="grp">Karte</div>
    <div class="seg">
      <button id="bmSat" class="on" onclick="setBasemap('sat')">Satellit</button>
      <button id="bmTopo" onclick="setBasemap('topo')">Topo</button>
    </div>
    <div class="grp">Struktur</div>
    <div id="tglFarbung" class="tgl on" onclick="toggleFarbung()"><span>F&auml;rbung</span><span class="sw"></span></div>
    <div id="tglNamen" class="tgl" onclick="toggleLayers()"><span>Namen</span><span class="sw"></span></div>
    <div id="tglBorders" class="tgl" onclick="toggleBorders()"><span>Landesgrenzen</span><span class="sw"></span></div>
    <div class="grp">Punkte</div>
    <div id="tglPeaks" class="tgl" onclick="togglePeaks()"><span>Gipfel</span><span class="sw"></span></div>
    <div id="tglHuts" class="tgl" onclick="toggleHuts()"><span>H&uuml;tten</span><span class="sw"></span></div>
    <div id="tglPasses" class="tgl" onclick="togglePasses()"><span>P&auml;sse</span><span class="sw"></span></div>
    <div class="grp" title="Settori = die f&uuml;nf Gro&szlig;sektoren der Alpen (SOIUSA)">Farben (Settori)</div>
    <div class="lrow"><span class="sw-nw"></span>Nordwestalpen</div>
    <div class="lrow"><span class="sw-sw"></span>S&uuml;dwestalpen</div>
    <div class="lrow"><span class="sw-zo"></span>Zentralostalpen</div>
    <div class="lrow"><span class="sw-no"></span>Nordostalpen</div>
    <div class="lrow"><span class="sw-so"></span>S&uuml;dostalpen</div>
    <!-- PRIV:START --><div class="lsep"></div>
    <div class="lrow"><span class="sw-hl"></span>besucht</div><!-- PRIV:END -->
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
const PRIV = __PRIV__;
const TOUR_LAYERS = PRIV ? ['t-dot'] : [];   // tour markers only exist in the private build
const CNAMES = {AT:'Österreich',CH:'Schweiz',DE:'Deutschland',
  FR:'Frankreich',IT:'Italien',SI:'Slowenien',LI:'Liechtenstein'};

console.log('SOIUSA:', SOIUSA_STS.features.length, 'Untergruppen,',
            SOIUSA_HIGHLIGHTS.features.length, 'Highlights');

// ── Coverage (private build only — visited groups + years) ────────────────────
/* PRIV:START */
const visitedGroups = SOIUSA_STS.features.filter(f=>f.properties.visited===1)
  .map(f=>f.properties)
  .sort((a,b)=>String(a.name_de||a.STS).localeCompare(String(b.name_de||b.STS)));
document.getElementById('kGroups').textContent = SOIUSA_HIGHLIGHTS.features.length+'/'+SOIUSA_STS.features.length;
document.getElementById('kTours').textContent = TOUREN.length;
document.getElementById('covCount').textContent =
  SOIUSA_HIGHLIGHTS.features.length + ' Gebiete · ' + TOUREN.length + ' Touren';
{ const ys=TOUREN.map(t=>parseInt(String(t.jahr||'').replace(/[^0-9]/g,'').slice(0,4))).filter(Boolean);
  if(ys.length) document.getElementById('kYears').textContent = Math.min(...ys)+'–'+Math.max(...ys); }
/* PRIV:END */

// ── Tour point markers (privat only — public JSON has no coordinates) ─────────
/* PRIV:START */
const fc = {type:'FeatureCollection', features: TOUREN.map(t=>({
  type:'Feature',
  geometry:{type:'Point', coordinates:[t.lon, t.lat]},
  properties:{id:t.id, jahr:t.jahr, gegend:t.gegend, gebirge:t.gebirge,
              land:t.land, verifiziert:t.verifiziert?1:0}
}))};
/* PRIV:END */

// ── Default camera: full Alpine view, slightly SW-biased ──────────────────────
const ALPS = {center:[10.2,46.1], zoom:5.3, pitch:0, bearing:0};

// Große-Screen-Stufe (27"+, feiner Zeiger): spiegelt die CSS-Media-Query. Steuert
// Popup-Breiten und einen leichten Karten-Label-Boost (initialer Viewport-Check).
const _bigScr = !!(window.matchMedia && window.matchMedia('(min-width: 2200px) and (pointer: fine)').matches);
const LB = _bigScr ? 1.5 : 0;   // Label-Zuschlag (px) für Gipfel/Hütten/Pässe

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
  attributionControl:false   // custom control, rebuilt on basemap switch (setAttrib)
});
// ── Attribution (dynamic per basemap) ─────────────────────────────────────────
const ATTRIB = {
  sat:'Imagery © Esri, Maxar, Earthstar · Höhen: Mapzen/AWS · SOIUSA © Arpa Piemonte · '+
      'Gipfel/Hütten/Pässe © OpenStreetMap (ODbL)',
  topo:'© OpenStreetMap-Mitwirkende, SRTM · Kartendarstellung © OpenTopoMap (CC-BY-SA) · '+
       'Höhen: Mapzen/AWS · SOIUSA © Arpa Piemonte'
};
let _attribCtl=null;
function setAttrib(topo){
  if(_attribCtl) map.removeControl(_attribCtl);
  _attribCtl=new maplibregl.AttributionControl({compact:true, customAttribution:topo?ATTRIB.topo:ATTRIB.sat});
  map.addControl(_attribCtl,'bottom-right');
}
map.addControl(new maplibregl.NavigationControl({visualizePitch:true}), 'bottom-right');

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

// ── Group name popup — shown on every STS click ───────────────────────────────
// closeOnClick:false — sonst schließt MapLibre den im selben Klick geöffneten Popup
// wieder (Name erst beim 2. Klick). Schließen via X / closePanel / Leer-Klick unten.
const stsPopup = new maplibregl.Popup({
  closeButton:true, closeOnClick:false, offset:10, maxWidth:_bigScr?'320px':'260px'});
const hoverPop = new maplibregl.Popup({closeButton:false, closeOnClick:false, offset:8});
const hutPopup = new maplibregl.Popup({closeButton:true, closeOnClick:false, offset:12, maxWidth:_bigScr?'300px':'250px'});
let _hoverTimer=null;
function toggleAbout(){ document.getElementById('about').classList.toggle('open'); }
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
  try{map.setSky({'sky-color':'#0b1f3a','horizon-color':'#7a92ad','fog-color':'#c8d6e5',
    'sky-horizon-blend':0.6,'horizon-fog-blend':0.5,'fog-ground-blend':0.4,
    'atmosphere-blend':0.4});}catch(e){}

  // ── Sources ──────────────────────────────────────────────────────────────
  map.addSource('mask',       {type:'geojson', data:MASK});
  map.addSource('sts',        {type:'geojson', data:SOIUSA_STS});
  map.addSource('highlights', {type:'geojson', data:SOIUSA_HIGHLIGHTS});
  map.addSource('sts-lp',    {type:'geojson', data:SOIUSA_LBL_PTS});
  /* PRIV:START */
  map.addSource('tours',     {type:'geojson', data:fc});
  /* PRIV:END */
  // OSM overlays as URL sources (not inlined) — keeps index.html small.
  map.addSource('osm-peaks', {type:'geojson', data:'./soiusa_osm_peaks.geojson'});
  map.addSource('osm-huts',  {type:'geojson', data:'./soiusa_osm_huts.geojson'});
  map.addSource('osm-passes',{type:'geojson', data:'./soiusa_osm_passes.geojson'});

  // ── Non-Alpine mask — always on ───────────────────────────────────────────
  map.addLayer({id:'mask-fill', type:'fill', source:'mask',
    paint:{'fill-color':'#000816','fill-opacity':0.42}});
  map.addSource('borders', {type:'geojson', data:'./soiusa_borders.geojson'});
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
      // Settore-Fill als "Nebel": voll bis z8, linear auf 0 bis z11.5 (freie Sicht beim
      // Reinzoomen). Zoom MUSS top-level stehen (nicht in * / case verschachteln).
      'fill-opacity': ['interpolate',['linear'],['zoom'], 8,0.34, 11.5,0]
    }});

  /* PRIV:START */
  // ── Chronologie-Füllungen (nur Privat): kumulativ gedimmt (≤ Jahr) + aktuelles
  //    Jahr kräftig. Filter werden je Jahr aus JS gesetzt; standardmäßig aus. ──
  map.addLayer({id:'chrono-past', type:'fill', source:'sts',
    filter:['in',['get','STS'],['literal',[]]],
    layout:{'visibility':'none'},
    paint:{'fill-color':'#ffb24d','fill-opacity':0.30}});
  map.addLayer({id:'chrono-cur', type:'fill', source:'sts',
    filter:['in',['get','STS'],['literal',[]]],
    layout:{'visibility':'none'},
    paint:{'fill-color':'#ffb24d','fill-opacity':0.62}});
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
      'text-allow-overlap':true,'text-optional':false,'text-anchor':'center','symbol-sort-key':0},
    paint:{'text-color':'rgba(232,240,255,0.95)',
           'text-halo-color':'#06101a','text-halo-width':1.8,'text-halo-blur':0.2}});

  // ── German labels for visited — toggle-controlled, off by default ───────────
  // Font: 'Noto Sans Bold' — PBFs self-hosted under fonts/Noto Sans Bold/ (fetch_fonts.py).
  // Source: sts-lp → one label per visited group, no duplicates.
  map.addLayer({id:'sts-label-hl', type:'symbol', source:'sts-lp',
    filter:['==',['get','visited'],1],
    layout:{'visibility':'none',
      'text-field':['get','name_de'],'text-font':['Noto Sans Bold'],
      'text-size':13,'text-allow-overlap':true,'text-optional':false,'text-anchor':'center','symbol-sort-key':0},
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

  // Peaks — black triangle, name+height label from higher zoom
  // Landmark-Glow (hinter den Gipfeln)
  map.addLayer({id:'osm-landmark-glow', type:'circle', source:'osm-peaks', minzoom:5,
    filter:['==',['get','landmark'],1],
    layout:{'visibility':'none'},
    paint:{'circle-radius':['interpolate',['linear'],['zoom'], 6,7, 12,16],
      'circle-color':'#ffd24d','circle-opacity':0.28,'circle-blur':0.9}});
  map.addLayer({id:'osm-peaks', type:'symbol', source:'osm-peaks', minzoom:5,
    filter:['!=',['get','landmark'],1],
    layout:{'visibility':'none','icon-anchor':'bottom','icon-allow-overlap':false,
      // Tier 0 = Mont Blanc (Stern), 1 = Länder-Höchste (Gold-Dreieck), 2-4 = Höhenbänder.
      'icon-image':['match',['get','tier'], 0,'peak-star', 1,'peak-hi', 'peak'],
      'icon-size':['match',['get','tier'], 0,1.9, 1,1.35, 2,1.05, 3,0.82, 0.62],
      // Labels tier-/zoom-gestaffelt: Mont Blanc immer, Länder ab z8, 4000er z10, 3000er z11, alle z12.
      'text-field':['step',['zoom'],
        ['case',['==',['get','tier'],0],['concat',['get','name'],'\n',['to-string',['get','ele']],' m'],''],
        8, ['case',['<=',['get','tier'],1],['concat',['get','name'],'\n',['to-string',['get','ele']],' m'],''],
        10,['case',['<=',['get','tier'],2],['concat',['get','name'],'\n',['to-string',['get','ele']],' m'],''],
        11,['case',['<=',['get','tier'],3],['concat',['get','name'],'\n',['to-string',['get','ele']],' m'],''],
        12,['concat',['get','name'],'\n',['to-string',['get','ele']],' m']],
      'text-font':['Noto Sans Bold'],'text-size':['match',['get','tier'], 0,12+LB, 1,11+LB, 9.5+LB],
      'text-offset':[0,0.3],'text-anchor':'top','text-optional':true,'text-allow-overlap':false},
    paint:{'text-color':['match',['get','tier'], 0,'#ffe08a', 1,'#ffd24d', '#dbe7ff'],
      'text-halo-color':'#06101a','text-halo-width':1.4,
      // Sichtbarkeit tier-/zoom-gestaffelt: Tier0-2 (bis 4000er) früh, 3000er ab z8, alle ab z11.
      'icon-opacity':['step',['zoom'],
        ['case',['<=',['get','tier'],2],1,0],
        8, ['case',['<=',['get','tier'],3],1,0],
        11, 1]}});

  // Landmark-Gipfel: eigener Rang — Icon nach Tier, Label immer, ab Übersicht sichtbar.
  map.addLayer({id:'osm-landmarks', type:'symbol', source:'osm-peaks', minzoom:5,
    filter:['==',['get','landmark'],1],
    layout:{'visibility':'none','icon-anchor':'bottom','icon-allow-overlap':true,
      'icon-image':['match',['get','tier'], 0,'peak-star', 1,'peak-hi', 'peak'],
      'icon-size':['match',['get','tier'], 0,1.95, 1,1.4, 1.15],
      'text-field':['concat',['get','name'],'\n',['to-string',['get','ele']],' m'],
      'text-font':['Noto Sans Bold'],'text-size':11,'text-offset':[0,0.3],
      'text-anchor':'top','text-optional':true,'text-allow-overlap':false},
    paint:{'text-color':'#ffe6a0','text-halo-color':'#06101a','text-halo-width':1.8}});

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

  // ── Pässe (toggle): berühmte früh, restliche erst bei hohem Zoom ───────────
  map.addLayer({id:'osm-passes', type:'symbol', source:'osm-passes', minzoom:10.5,
    filter:['==',['get','famous'],0],
    layout:{'visibility':'none','icon-image':'pass','icon-allow-overlap':false,'icon-size':0.8,
      'text-field':['step',['zoom'], '', 12, ['get','name']],'text-font':['Noto Sans Bold'],
      'text-size':8.5+LB,'text-offset':[0,0.6],'text-anchor':'top','text-optional':true,'text-allow-overlap':false},
    paint:{'text-color':'#e8d9a0','text-halo-color':'#06101a','text-halo-width':1.2}});
  map.addLayer({id:'osm-passes-famous', type:'symbol', source:'osm-passes', minzoom:6.5,
    filter:['==',['get','famous'],1],
    layout:{'visibility':'none','icon-image':'pass','icon-allow-overlap':false,'icon-size':1.05,
      'text-field':['step',['zoom'], '', 8, ['get','name']],'text-font':['Noto Sans Bold'],
      'text-size':10+LB,'text-offset':[0,0.6],'text-anchor':'top','text-optional':true,'text-allow-overlap':false},
    paint:{'text-color':'#f0dfa0','text-halo-color':'#06101a','text-halo-width':1.5}});

  // ── Peaks of the clicked group (within-filter, reuse peak icon) ────────────
  map.addLayer({id:'peaks-in-group', type:'symbol', source:'osm-peaks', minzoom:5,
    filter:['==',['get','name'],'__none__'],
    layout:{'visibility':'none','icon-image':'peak','icon-anchor':'bottom','icon-allow-overlap':false,
      'icon-size':['match',['get','tier'], 2,1.0, 3,0.82, 0.64],
      // gleiche Rang-/Zoom-Staffelung wie die Basis-Gipfel: nur prominente bei mittlerem Zoom.
      'text-field':['step',['zoom'],
        ['case',['<=',['get','tier'],2],['concat',['get','name'],'\n',['to-string',['get','ele']],' m'],''],
        11,['case',['<=',['get','tier'],3],['concat',['get','name'],'\n',['to-string',['get','ele']],' m'],''],
        12,['concat',['get','name'],'\n',['to-string',['get','ele']],' m']],
      'text-font':['Noto Sans Bold'],'text-size':9.5,'text-offset':[0,0.4],
      'text-anchor':'top','text-optional':true,'text-allow-overlap':false},
    paint:{'text-color':'#eaf1ff','text-halo-color':'#06101a','text-halo-width':1.5,
      'icon-opacity':['step',['zoom'],
        ['case',['<=',['get','tier'],2],1,0],
        10,['case',['<=',['get','tier'],3],1,0],
        12,1]}});
  // Highlight: the group's highest peak (bigger triangle + bold gold label)
  map.addLayer({id:'peaks-highest', type:'symbol', source:'osm-peaks',
    filter:['==',['get','name'],'__none__'],
    layout:{'visibility':'none','icon-image':'peak','icon-anchor':'bottom','icon-allow-overlap':true,'icon-size':1.5,
      'text-field':['concat',['get','name'],'  ',['to-string',['get','ele']],' m'],
      'text-font':['Noto Sans Bold'],'text-size':12,'text-offset':[0,0.5],
      'text-anchor':'top','text-allow-overlap':true},
    paint:{'text-color':'#ffd47a','text-halo-color':'#06101a','text-halo-width':2}});

  // ── Selection ring — filter-driven, initially empty ───────────────────────
  map.addLayer({id:'sts-selected', type:'line', source:'sts',
    filter:['==',['get','STS'],''],
    layout:{'line-join':'round'},
    paint:{'line-color':'#ffffff','line-width':3.2,'line-opacity':0.95}});

  /* PRIV:START */
  // ── Tour markers (privat only — reveals "wann/wo" per point) ──────────────
  map.addLayer({id:'t-halo', type:'circle', source:'tours',
    paint:{'circle-radius':13,'circle-color':'#ffb24d',
           'circle-opacity':0.18,'circle-blur':0.4}});
  map.addLayer({id:'t-dot', type:'circle', source:'tours',
    paint:{'circle-radius':6.5,
      'circle-color':['case',['==',['get','verifiziert'],1],'#ffb24d','#5fd0c5'],
      'circle-stroke-width':2,'circle-stroke-color':'#0a0e14'}});
  const pop = new maplibregl.Popup({closeButton:false,closeOnClick:false,offset:12});
  map.on('mouseenter','t-dot',e=>{
    map.getCanvas().style.cursor='pointer';
    const p=e.features[0].properties;
    pop.setLngLat(e.features[0].geometry.coordinates)
       .setHTML('<b>'+p.gebirge+'</b> · '+p.jahr).addTo(map);
  });
  map.on('mouseleave','t-dot',()=>{map.getCanvas().style.cursor='';pop.remove();});
  map.on('click','t-dot',e=>openTour(e.features[0].properties.id));
  /* PRIV:END */

  // ── STS fill click — popup always; panel only for visited groups ─────────
  map.on('mouseenter','sts-fill',()=>map.getCanvas().style.cursor='pointer');
  map.on('mousemove','sts-fill',e=>{
    if(document.getElementById('panel').classList.contains('open')) return;  // kein Doppel-Popup
    clearTimeout(_hoverTimer);                                               // Dwell: erst nach 700 ms Ruhe
    const p=e.features[0].properties, ll=e.lngLat, nm=p.name_de||p.STS||'';
    let sub=p.settore||'';
    /* PRIV:START */
    if(p.visited===1){ try{const n=JSON.parse(p.tour_ids||'[]').length; sub=n+(n===1?' Tour':' Touren');}catch(_){} }
    /* PRIV:END */
    _hoverTimer=setTimeout(()=>{
      hoverPop.setLngLat(ll)
        .setHTML('<div class="hp-n">'+nm+'</div>'+(sub?'<div class="hp-s">'+sub+'</div>':''))
        .addTo(map);
    }, 700);
  });
  map.on('mouseleave','sts-fill',()=>{map.getCanvas().style.cursor='';clearTimeout(_hoverTimer);hoverPop.remove();});
  map.on('click','sts-fill',e=>{
    if(TOUR_LAYERS.length && map.queryRenderedFeatures(e.point,{layers:TOUR_LAYERS}).length) return;
    if(map.queryRenderedFeatures(e.point,{layers:HUT_LAYERS}).length) return;  // Hütte hat Vorrang
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
    if(map.queryRenderedFeatures(e.point,{layers:['sts-fill'].concat(TOUR_LAYERS)}).length) return;
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
    if(!map.queryRenderedFeatures(e.point,{layers:HUT_LAYERS}).length) hutPopup.remove();
    if(!map.queryRenderedFeatures(e.point,{layers:['sts-fill','hl-line'].concat(TOUR_LAYERS)}).length)
      stsPopup.remove();
  });

  // ── Basemap init (localStorage) + attribution ─────────────────────────────
  let _bm='sat';
  try{ if(localStorage.getItem('alpen_basemap')==='topo') _bm='topo'; }catch(_){}
  setBasemap(_bm);

  // ── Build the search index (groups now; OSM points fetched async) ──────────
  buildSearchIndex();

  // ── Fix blank canvas — map.resize() is more reliable than triggerRepaint ──
  map.resize();
  setTimeout(()=>map.resize(), 150);
  map.once('idle',()=>map.resize());
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
// Unbewirtschaftet / Refugio / Biwak: hollow house (outline only), muted.
function houseOutline(color){
  return makeIcon(20,(x,s)=>{
    x.strokeStyle=color; x.lineWidth=1.8; x.lineJoin='round'; x.fillStyle='rgba(10,14,20,0.5)';
    x.beginPath(); x.moveTo(s*0.5,s*0.16); x.lineTo(s*0.86,s*0.5); x.lineTo(s*0.14,s*0.5); x.closePath(); x.fill(); x.stroke();
    x.beginPath(); x.rect(s*0.27,s*0.5,s*0.46,s*0.34); x.fill(); x.stroke();
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
  // immer zeigen — unabhängig vom "Gipfel"-Toggle (der Steckbrief nennt den höchsten Berg)
  map.setLayoutProperty('peaks-in-group','visibility','visible');
  map.setLayoutProperty('peaks-highest','visibility','visible');
}
function resetGroupPeaks(){
  map.setFilter('peaks-in-group', ['==',['get','name'],'__none__']);
  map.setFilter('peaks-highest',  ['==',['get','name'],'__none__']);
  map.setLayoutProperty('peaks-in-group','visibility','none');
  map.setLayoutProperty('peaks-highest','visibility','none');
}

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

// ── Open: tour marker (privat only) ───────────────────────────────────────────
/* PRIV:START */
function openTour(id){
  const t=TOUREN.find(x=>x.id==id); if(!t) return;
  map.setFilter('sts-selected',['==',['get','STS'],'']);
  resetGroupPeaks();
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
/* PRIV:END */

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

// ── Hütten-Popup (beide Builds; Daten = HUTS_WIKI, Key = OSM properties.name) ──
// Fehlt ein Feld -> weglassen. Ohne Eintrag / nur sb_* -> schlichtes Popup (Name+ele+kat).
// sb_* werden NICHT gerendert (Datenfelder fuer spaeteren Familien-Filter, G2).
const HUT_KAT = {club:'Verbandshütte', hut:'Hütte', wild:'Unbewirtschaftet'};
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

// ── Tour markup for a visited group (private build only) ──────────────────────
/* PRIV:START */
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
/* PRIV:END */

// ── Open: STS polygon (visited or not) ───────────────────────────────────────
function openSts(feat){
  const props = feat.properties || {};
  const stsName = String(props.STS || '').trim();
  // Harden: use '__none__' sentinel so empty-string filter doesn't accidentally match
  map.setFilter('sts-selected',['==',['get','STS'], stsName||'__none__']);
  const visited = props.visited === 1;

  document.getElementById('pGroup').textContent = props.name_de || stsName;
  document.getElementById('pGegend').textContent = stsName + (props.CODICE?' · '+props.CODICE:'');
  document.getElementById('pYear').textContent = '';
  /* PRIV:START */
  document.getElementById('pYear').textContent = visited ? 'Besucht' : 'Noch nicht besucht';
  /* PRIV:END */

  document.getElementById('pAbout').innerHTML = steckbriefHtml(stsName, props);
  setTourTab(visited ? groupTourHtml(props) : '');
  showGroupPeaks(stsName);

  /* PRIV:START */
  document.getElementById('cov').classList.remove('open');   // Touren-Liste einklappen (kein Overlap)
  /* PRIV:END */
  document.getElementById('panel').classList.add('open');
  const bb=featBbox(feat);
  if(bb) map.fitBounds(bb,{padding:{top:80,bottom:80,left:320,right:80},
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
  document.getElementById('tglNamen').classList.toggle('on',_layersOn);
}

// ── Settore-Färbung an/aus (Fill; Fade bleibt beim Reinzoomen) ────────────────
let _farbungOn=true;
function toggleFarbung(){
  _farbungOn=!_farbungOn;
  map.setLayoutProperty('sts-fill','visibility',_farbungOn?'visible':'none');
  document.getElementById('tglFarbung').classList.toggle('on',_farbungOn);
}
// ── Landesgrenzen an/aus ──────────────────────────────────────────────────────
let _bordersOn=false;
function toggleBorders(){
  _bordersOn=!_bordersOn;
  ['borders','country-labels'].forEach(l=>map.setLayoutProperty(l,'visibility',_bordersOn?'visible':'none'));
  document.getElementById('tglBorders').classList.toggle('on',_bordersOn);
}

// ── OSM overlays (zuschaltbar, zoom-gated) ────────────────────────────────────
let _peaksOn=false;
function togglePeaks(){
  _peaksOn=!_peaksOn; const v=_peaksOn?'visible':'none';
  ['osm-peaks','osm-landmark-glow','osm-landmarks']
    .forEach(l=>map.setLayoutProperty(l,'visibility',v));
  document.getElementById('tglPeaks').classList.toggle('on',_peaksOn);
}
let _hutsOn=false;
function toggleHuts(){
  _hutsOn=!_hutsOn; const v=_hutsOn?'visible':'none';
  ['osm-huts-club','osm-huts-other','osm-huts-wild'].forEach(l=>map.setLayoutProperty(l,'visibility',v));
  document.getElementById('tglHuts').classList.toggle('on',_hutsOn);
}
let _passesOn=false;
function togglePasses(){
  _passesOn=!_passesOn; const v=_passesOn?'visible':'none';
  ['osm-passes','osm-passes-famous'].forEach(l=>map.setLayoutProperty(l,'visibility',v));
  document.getElementById('tglPasses').classList.toggle('on',_passesOn);
}

// ── Basemap: Satellit ⇄ OpenTopoMap (Redundanz-Regel + localStorage) ──────────
let _basemap='sat';
let _savedPts=null;
function setBasemap(bm){
  const topo = bm==='topo';
  if(topo && _basemap!=='topo'){
    // OTM bakes in peak/hut/pass labels -> switch our own point layers OFF, remember state.
    _savedPts={p:_peaksOn,h:_hutsOn,s:_passesOn};
    if(_peaksOn) togglePeaks();
    if(_hutsOn) toggleHuts();
    if(_passesOn) togglePasses();
  } else if(!topo && _basemap==='topo' && _savedPts){
    if(_savedPts.p && !_peaksOn) togglePeaks();
    if(_savedPts.h && !_hutsOn) toggleHuts();
    if(_savedPts.s && !_passesOn) togglePasses();
    _savedPts=null;
  }
  _basemap=bm;
  map.setLayoutProperty('sat','visibility',topo?'none':'visible');
  map.setLayoutProperty('topo','visibility',topo?'visible':'none');
  // Settori fill a touch softer over the busy topo sheet; hillshade lighter (OTM shades itself).
  map.setPaintProperty('sts-fill','fill-opacity',
    topo ? ['interpolate',['linear'],['zoom'], 8,0.22, 11.5,0]
         : ['interpolate',['linear'],['zoom'], 8,0.34, 11.5,0]);
  map.setPaintProperty('hill','hillshade-exaggeration', topo?0.08:0.25);
  setAttrib(topo);
  const bs=document.getElementById('bmSat'), bt=document.getElementById('bmTopo');
  if(bs) bs.classList.toggle('on',!topo);
  if(bt) bt.classList.toggle('on',topo);
  try{localStorage.setItem('alpen_basemap',bm);}catch(_){}
}

// ══ Suche: Gipfel/Hütten/Pässe/Gruppen + Koordinaten (keyless, client-seitig) ══
const SEARCH_IDX=[];
const SCAT={group:'▦',peak:'▲',hut:'\u{1F3E0}',pass:')(',coord:'\u{1F4CD}'};
function sNorm(s){ return (s||'').toLowerCase()
  .replace(/ä/g,'ae').replace(/ö/g,'oe').replace(/ü/g,'ue').replace(/ß/g,'ss')
  .normalize('NFKD').replace(/[̀-ͯ]/g,''); }
function buildSearchIndex(){
  SOIUSA_STS.features.forEach(f=>{
    const p=f.properties, nm=p.name_de||p.STS;
    SEARCH_IDX.push({cat:'group', name:nm, sub:p.settore||'Gruppe', sts:p.STS,
      n:sNorm(nm+' '+(p.STS||'')), w:0, ele:0});
  });
  const add=(url,cat,w)=>fetch(url).then(r=>r.json()).then(fc=>{
    (fc.features||[]).forEach(f=>{
      const p=f.properties||{}, c=f.geometry&&f.geometry.coordinates;
      if(!p.name||!c) return;
      SEARCH_IDX.push({cat, name:p.name, ele:+p.ele||0, lon:c[0], lat:c[1], n:sNorm(p.name), w});
    });
  }).catch(()=>{});
  add('./soiusa_osm_peaks.geojson','peak',1);
  add('./soiusa_osm_huts.geojson','hut',2);
  add('./soiusa_osm_passes.geojson','pass',3);
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
      : r.cat==='group' ? (r.sub||'Gruppe') : r.cat==='pass' ? 'Pass' : (r.sub||'');
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
    const f=SOIUSA_STS.features.find(x=>x.properties.STS===r.sts); if(f) openSts(f);
  } else if(r.cat==='coord'){
    _searchMarker=new maplibregl.Marker({color:'#5fd0c5'}).setLngLat([r.lon,r.lat]).addTo(map);
    map.flyTo({center:[r.lon,r.lat], zoom:13, duration:1200, essential:true});
  } else {
    map.flyTo({center:[r.lon,r.lat], zoom:12.5, duration:1200, essential:true});
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
  map.setFilter('sts-selected',['==',['get','STS'],'']);
  resetGroupPeaks();
}
function overview(){
  closePanel();
  _autoPitch=true;
  map.flyTo({...ALPS,duration:1200,essential:true});
}

// ── Coverage list (private build only; click flies to the group) ──────────────
/* PRIV:START */
function openGroup(sts){ const f=SOIUSA_STS.features.find(x=>x.properties.STS===sts); if(f) openSts(f); }
const cl=document.getElementById('covList');
cl.innerHTML=visitedGroups.map(g=>{
  const nm=(g.name_de||g.STS||'').replace(/</g,'&lt;');
  const key=String(g.STS||'').replace(/\\/g,'\\\\').replace(/'/g,"\\'");
  return '<div class="row" onclick="openGroup(\''+key+'\')"><span>'+nm+'</span><span class="yr"></span></div>';
}).join('');
[...cl.children].forEach((row,i)=>{
  const g=visitedGroups[i]; if(!g) return;
  const ids = typeof g.tour_ids==='string'?JSON.parse(g.tour_ids||'[]'):(g.tour_ids||[]);
  const yrs = ids.map(id=>{const t=TOUREN.find(x=>x.id==id);return t&&t.jahr;}).filter(Boolean);
  const sp=row.querySelector('.yr'); if(sp) sp.textContent=yrs.join(', ');
});
/* PRIV:END */

// ══ Chronologie-Modus (nur Privat) — Stufe 1: Jahresleiste + kumulative Färbung ══
/* PRIV:START */
function jahrSort(j){ const m=String(j==null?'':j).match(/\d{4}/); return m?+m[0]:null; }
// Pro STS-Gruppe die Besuchsjahre + globale Jahresliste (nur Jahre mit Touren).
const CHRONO = (function(){
  const tourById={}; TOUREN.forEach(t=>{ tourById[t.id]=t; });
  // Färbung folgt der Gruppen-Zuordnung (tour_ids) — konsistent mit der besucht-Logik.
  const stsYears={};
  SOIUSA_STS.features.forEach(f=>{
    const p=f.properties; if(p.visited!==1) return;
    let ids=[]; try{ ids = typeof p.tour_ids==='string'?JSON.parse(p.tour_ids||'[]'):(p.tour_ids||[]); }catch(_){}
    const ys=new Set();
    ids.forEach(id=>{ const t=tourById[id]; const y=t&&jahrSort(t.jahr); if(y) ys.add(y); });
    if(ys.size) stsYears[p.STS]=[...ys];
  });
  // Jahresleiste = ALLE Touren-Jahre (Spec: „nur Jahre mit Touren"), auch wenn eine
  // Tour (noch) keiner STS-Gruppe zugeordnet ist -> Chip erscheint, Färbung ggf. leer.
  const yearMeta={}, yearTours={};
  TOUREN.forEach(t=>{ const y=jahrSort(t.jahr); if(!y) return;
    if(!yearMeta[y]) yearMeta[y]={label:String(t.jahr), unsure:!!t.jahr_unsicher};
    if(t.jahr_unsicher) yearMeta[y].unsure=true;
    (yearTours[y]=yearTours[y]||[]).push(t); });
  const years=Object.keys(yearMeta).map(Number).sort((a,b)=>a-b);
  return {stsYears, years, yearMeta, yearTours};
})();

let _chronoOn=false, _chronoIdx=-1, _chronoSaved=null;
let _chronoPlaying=false, _chronoTimer=null, _pulseRAF=null;
const CHRONO_STEP=2500;        // ms pro Jahr (Play)
const CHRONO_CUR_OP=0.62;      // Basis-Deckkraft aktuelles Jahr (= chrono-cur Layer-Paint)
function _esc(s){ return String(s==null?'':s).replace(/[<>&]/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;'}[c])); }

// Caption: Jahr groß (Original-String) + datum · je Tour ort/gegend — Gipfel · Teilnehmer (kursiv).
function chronoCaption(Y){
  const cap=document.getElementById('chronoCap'); if(!cap) return;
  const meta=CHRONO.yearMeta[Y]||{}, ts=CHRONO.yearTours[Y]||[];
  const datums=[...new Set(ts.map(t=>t.datum).filter(Boolean))];
  let h='<div class="cc-h"><span class="cc-y">'+_esc(meta.label||Y)+'</span>'+
        (datums.length?'<span class="cc-d">'+_esc(datums.join(' · '))+'</span>':'')+'</div>';
  h+=ts.map(t=>{
    const loc=_esc(t.ort||t.gegend||'');
    const gip=(Array.isArray(t.gipfel)?t.gipfel:[]).map(g=>_esc(g&&g.name)).filter(Boolean).join(', ');
    const parts=[]; if(loc) parts.push(loc); if(gip) parts.push(gip);
    const who=t.teilnehmer?' · <span class="cc-who">'+_esc(t.teilnehmer)+'</span>':'';
    // Stufe 3: Memo-Vorschau (~100 Zeichen, an Wortgrenze) wenn befüllt.
    const memo=(t.memo||'').trim();
    const mp = memo ? '<div class="cc-memo">'+_esc(memo.length>100?memo.slice(0,100).replace(/\s+\S*$/,'')+'…':memo)+'</div>' : '';
    return '<div class="cc-t">'+(parts.join(' &mdash; ')||'&nbsp;')+who+'</div>'+mp;
  }).join('');
  cap.innerHTML=h;
}

// FlyTo je Jahr: eine Tour zentriert, mehrere gemeinsame BBox. Padding unten groß (Leiste/Caption).
function chronoFlyToYear(Y){
  const ts=(CHRONO.yearTours[Y]||[]).filter(t=>t.lon!=null&&t.lat!=null);
  if(!ts.length) return;
  const pad={top:80,bottom:190,left:80,right:80};
  if(ts.length===1){
    map.flyTo({center:[ts[0].lon,ts[0].lat], zoom:8.6, padding:pad, duration:1600, essential:true});
  } else {
    let x0=180,y0=90,x1=-180,y1=-90;
    ts.forEach(t=>{x0=Math.min(x0,t.lon);x1=Math.max(x1,t.lon);y0=Math.min(y0,t.lat);y1=Math.max(y1,t.lat);});
    map.fitBounds([[x0,y0],[x1,y1]],{padding:pad, maxZoom:9, duration:1600, essential:true});
  }
}

// Einmalige Puls-Animation auf chrono-cur (auch bei Wiederbesuch).
function chronoPulse(){
  if(_pulseRAF) cancelAnimationFrame(_pulseRAF);
  const t0=performance.now(), peak=0.95, dur=680;
  (function step(now){
    const k=Math.min(1,(now-t0)/dur);
    map.setPaintProperty('chrono-cur','fill-opacity', CHRONO_CUR_OP+(peak-CHRONO_CUR_OP)*Math.sin(k*Math.PI));
    if(k<1) _pulseRAF=requestAnimationFrame(step);
    else { map.setPaintProperty('chrono-cur','fill-opacity',CHRONO_CUR_OP); _pulseRAF=null; }
  })(performance.now());
}

// Stand Jahr X: Gruppen mit Tour == X kräftig (chrono-cur), nur früher besuchte gedimmt (chrono-past).
function chronoSetYear(idx, opts){
  opts=opts||{};
  if(idx<0 || idx>=CHRONO.years.length) return;
  if(opts.manual && _chronoPlaying) chronoPause();      // manueller Chip-Tipp pausiert Play
  _chronoIdx=idx; const Y=CHRONO.years[idx];
  const past=[], cur=[];
  Object.keys(CHRONO.stsYears).forEach(sts=>{
    const ys=CHRONO.stsYears[sts];
    if(ys.indexOf(Y)>=0) cur.push(sts);
    else if(ys.some(y=>y<Y)) past.push(sts);
  });
  map.setFilter('chrono-past',['in',['get','STS'],['literal',past]]);
  map.setFilter('chrono-cur', ['in',['get','STS'],['literal',cur]]);
  const chips=document.querySelectorAll('#chronoChips .chip');
  chips.forEach((c,i)=>c.classList.toggle('on',i===idx));
  if(chips[idx]) chips[idx].scrollIntoView({inline:'center',block:'nearest'});
  chronoCaption(Y);
  chronoPulse();
  if(opts.fly!==false) chronoFlyToYear(Y);
}

// ── Play/Pause (~2,5 s/Jahr, kein Loop, stoppt am letzten Jahr) ──
function chronoPlayStep(){
  if(_chronoIdx>=CHRONO.years.length-1){ chronoPause(); return; }   // kein Loop
  chronoSetYear(_chronoIdx+1);
  _chronoTimer=setTimeout(chronoPlayStep, CHRONO_STEP);
}
function chronoPlay(){
  if(!_chronoOn || _chronoPlaying) return;
  if(_chronoIdx>=CHRONO.years.length-1) chronoSetYear(0,{fly:false});  // am Ende: von vorn
  _chronoPlaying=true;
  const b=document.getElementById('chronoPlay'); if(b){ b.textContent='⏸'; b.classList.add('on'); }
  _chronoTimer=setTimeout(chronoPlayStep, CHRONO_STEP);
}
function chronoPause(){
  _chronoPlaying=false;
  if(_chronoTimer){ clearTimeout(_chronoTimer); _chronoTimer=null; }
  const b=document.getElementById('chronoPlay'); if(b){ b.textContent='▶'; b.classList.remove('on'); }
}
function chronoPlayToggle(){ _chronoPlaying?chronoPause():chronoPlay(); }

function chronoEnter(){
  if(_chronoOn || !CHRONO.years.length) return;
  _chronoOn=true;
  _chronoSaved={p:_peaksOn,h:_hutsOn,s:_passesOn};       // Punkt-Toggles merken + dezent aus
  if(_peaksOn) togglePeaks(); if(_hutsOn) toggleHuts(); if(_passesOn) togglePasses();
  ['hl-line','sts-label-hl'].forEach(l=>map.setLayoutProperty(l,'visibility','none'));  // „alle besucht" aus
  ['chrono-past','chrono-cur'].forEach(l=>map.setLayoutProperty(l,'visibility','visible'));
  map.setPaintProperty('chrono-cur','fill-opacity',CHRONO_CUR_OP);
  document.getElementById('cov').style.display='none';
  document.getElementById('chronoBar').classList.add('open');
  document.getElementById('chronoCap').classList.add('open');
  document.getElementById('chronoBtn').classList.add('active');
  overview();
  chronoSetYear(0,{fly:false});                          // Beginn: frühestes Jahr, Übersicht halten
}
function chronoExit(){
  if(!_chronoOn) return; _chronoOn=false;
  chronoPause();
  if(_pulseRAF){ cancelAnimationFrame(_pulseRAF); _pulseRAF=null; }
  map.setPaintProperty('chrono-cur','fill-opacity',CHRONO_CUR_OP);
  ['chrono-past','chrono-cur'].forEach(l=>map.setLayoutProperty(l,'visibility','none'));
  map.setLayoutProperty('hl-line','visibility','visible');
  map.setLayoutProperty('sts-label-hl','visibility', _layersOn?'visible':'none');   // Zustand restaurieren
  if(_chronoSaved){
    if(_chronoSaved.p && !_peaksOn) togglePeaks();
    if(_chronoSaved.h && !_hutsOn) toggleHuts();
    if(_chronoSaved.s && !_passesOn) togglePasses();
    _chronoSaved=null;
  }
  document.getElementById('cov').style.display='';
  document.getElementById('chronoBar').classList.remove('open');
  document.getElementById('chronoCap').classList.remove('open');
  document.getElementById('chronoBtn').classList.remove('active');
}
function chronoToggle(){ _chronoOn?chronoExit():chronoEnter(); }

// Jahres-Chips (nur Jahre mit Touren). Ohne Jahre: Modus ausblenden.
(function(){
  const wrap=document.getElementById('chronoChips'), btn=document.getElementById('chronoBtn');
  if(!wrap) return;
  if(!CHRONO.years.length){ if(btn) btn.style.display='none'; return; }
  wrap.innerHTML=CHRONO.years.map((y,i)=>{
    const m=CHRONO.yearMeta[y]||{}; return '<button class="chip" data-i="'+i+'">'+(m.unsure?'~':'')+y+'</button>';
  }).join('');
  [...wrap.children].forEach(b=>b.addEventListener('click',()=>chronoSetYear(+b.dataset.i,{manual:true})));
})();
/* PRIV:END */
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
html = html.replace("__SOIUSA_HUTS_WIKI_JSON__",     huts_wiki_json)
html = html.replace("__TITEL__", TITEL).replace("__UNTER__", UNTER)
html = html.replace("__PRIV__", "false" if PUBLIC else "true")
html = html.replace("__KPI_GRUPPEN__",  str(kpi_gruppen))
html = html.replace("__KPI_SETTORI__",  str(kpi_settori))
html = html.replace("__KPI_HUETTEN__",  str(kpi_huetten))

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

# ── Backup-Hook (nur Privat-Build): sichert den gitignorierten Privat-Kanon ───
# (touren.json + _cowork_specs) nach OneDrive. Fehler brechen den Build nie ab.
if not PUBLIC:
    try:
        import backup_privat
        backup_privat.backup()
    except Exception as e:
        print(f"backup_privat: uebersprungen ({e})")
