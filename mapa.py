import pandas as pd
import json
import os
import numpy as np
from sklearn.cluster import DBSCAN

SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS4iQ9hd5u1hkC7Uy-jmAEx-QSme-jp7W7bQuQim5rWvxKBqBR-kEuGZnoVD4ief-5c8MdcJsibOn4A/pub?output=csv"
OUTPUT_FILE = "docs/index.html"

MESES = {1:'Enero',2:'Febrero',3:'Marzo',4:'Abril',5:'Mayo',6:'Junio',
         7:'Julio',8:'Agosto',9:'Septiembre',10:'Octubre',11:'Noviembre',12:'Diciembre'}
COLOR_MAP = {'Con Muertos':'#E63946','Con Heridos':'#F4A261','Solo Daños':'#2A9D8F'}
CLUSTER_COLORS = ['#FF6B6B','#4ECDC4','#45B7D1','#96CEB4','#FFEAA7','#DDA0DD','#98D8C8']

AMENITY_CONFIG = {
    'school':       {'label':'Institución educativa', 'color':'#3B82F6', 'icon':'🏫'},
    'hospital':     {'label':'Hospital',              'color':'#EF4444', 'icon':'🏥'},
    'clinic':       {'label':'Centro de salud',       'color':'#F97316', 'icon':'🏥'},
    'pharmacy':     {'label':'Farmacia',              'color':'#22C55E', 'icon':'💊'},
    'police':       {'label':'Policía',               'color':'#1E3A5F', 'icon':'👮'},
    'fire_station': {'label':'Bomberos',              'color':'#DC2626', 'icon':'🚒'},
    'park':         {'label':'Parque',                'color':'#16A34A', 'icon':'🌳'},
}

def limpiar_coord(v):
    try: return float(str(v).strip().replace(",","."))
    except: return None

def cargar_datos(url):
    df = pd.read_csv(url)
    lat_col = next((c for c in df.columns if 'latitud' in c.lower()), None)
    lon_col = next((c for c in df.columns if 'longitud' in c.lower()), None)
    df['lat'] = df[lat_col].apply(limpiar_coord)
    df['lon'] = df[lon_col].apply(limpiar_coord)
    df = df.dropna(subset=['lat','lon'])
    df = df[df['lat'].between(-5,15) & df['lon'].between(-82,-65)]
    fecha_col = next((c for c in df.columns if 'fecha' in c.lower()), None)
    if fecha_col:
        df['FechaHecho'] = pd.to_datetime(df[fecha_col], errors='coerce', dayfirst=True)
        df['Anio'] = df['FechaHecho'].dt.year.fillna(0).astype(int)
        df['Mes'] = df['FechaHecho'].dt.month.fillna(0).astype(int)
    muertos_col = next((c for c in df.columns if 'muerto' in c.lower()), None)
    heridos_col = next((c for c in df.columns if 'herido' in c.lower()), None)
    if muertos_col:
        df[muertos_col] = pd.to_numeric(df[muertos_col], errors='coerce').fillna(0).astype(int)
    if heridos_col:
        df[heridos_col] = pd.to_numeric(df[heridos_col], errors='coerce').fillna(0).astype(int)
    return df

def calcular_dbscan(df):
    coords = df[['lat','lon']].values
    db = DBSCAN(eps=0.001, min_samples=2, metric='euclidean').fit(coords)
    df['cluster'] = db.labels_
    cluster_info = []
    for cid in sorted(set(db.labels_)):
        if cid == -1:
            continue
        mask = df['cluster'] == cid
        sub = df[mask]
        muertos_col = next((c for c in df.columns if 'muerto' in c.lower()), None)
        heridos_col = next((c for c in df.columns if 'herido' in c.lower()), None)
        cluster_info.append({
            'id': int(cid),
            'lat': float(sub['lat'].mean()),
            'lon': float(sub['lon'].mean()),
            'size': int(mask.sum()),
            'muertos': int(sub[muertos_col].sum()) if muertos_col else 0,
            'heridos': int(sub[heridos_col].sum()) if heridos_col else 0,
            'color': CLUSTER_COLORS[cid % len(CLUSTER_COLORS)]
        })
    return df, cluster_info

def descargar_equipamientos(center_lat, center_lon, dist=2000):
    """Descarga equipamientos urbanos desde OpenStreetMap."""
    amenities = []
    try:
        import osmnx as ox
        tags = {
            'amenity': ['school', 'hospital', 'clinic', 'police',
                        'fire_station', 'pharmacy'],
            'leisure': ['park']
        }
        gdf = ox.features_from_point((center_lat, center_lon), tags=tags, dist=dist)
        for _, row in gdf.iterrows():
            amenity_type = str(row.get('amenity', row.get('leisure', 'other')))
            if amenity_type not in AMENITY_CONFIG:
                continue
            cfg = AMENITY_CONFIG[amenity_type]
            # Get coordinates
            try:
                geom = row.geometry
                if geom.geom_type == 'Point':
                    lat, lon = geom.y, geom.x
                else:
                    lat, lon = geom.centroid.y, geom.centroid.x
            except:
                continue
            name = str(row.get('name', cfg['label']))
            if name == 'nan':
                name = cfg['label']
            amenities.append({
                'lat': float(lat), 'lon': float(lon),
                'type': amenity_type,
                'name': name,
                'label': cfg['label'],
                'color': cfg['color'],
                'icon': cfg['icon']
            })
        print(f"✓ {len(amenities)} equipamientos descargados desde OSM")
    except Exception as e:
        print(f"⚠ No se pudieron descargar equipamientos: {e}")
    return amenities

def generar_html(df, cluster_info, amenities):
    gravedad_col = next((c for c in df.columns if 'gravedad' in c.lower()), None)
    clase_col    = next((c for c in df.columns if 'clase' in c.lower() and 'acc' in c.lower()), None)
    dir_col      = next((c for c in df.columns if 'direcc' in c.lower()), None)
    hora_col     = next((c for c in df.columns if 'hora' in c.lower()), None)
    muertos_col  = next((c for c in df.columns if 'muerto' in c.lower()), None)
    heridos_col  = next((c for c in df.columns if 'herido' in c.lower()), None)
    cod_col      = next((c for c in df.columns if 'codrot' in c.lower() or 'ipat' in c.lower()), None)

    points_data = []
    for _, row in df.iterrows():
        g = str(row[gravedad_col]) if gravedad_col else 'N/D'
        fecha = str(row['FechaHecho'].date()) if 'FechaHecho' in df.columns and pd.notna(row['FechaHecho']) else 'N/D'
        cl = int(row['cluster'])
        points_data.append({
            'lat': float(row['lat']), 'lon': float(row['lon']),
            'gravedad': g, 'color': COLOR_MAP.get(g,'#888'),
            'codrot': str(row[cod_col]) if cod_col else 'N/D',
            'direccion': str(row[dir_col]) if dir_col else 'N/D',
            'fecha': fecha,
            'hora': str(row[hora_col]) if hora_col else 'N/D',
            'clase': str(row[clase_col]) if clase_col else 'N/D',
            'muertos': int(row[muertos_col]) if muertos_col else 0,
            'heridos': int(row[heridos_col]) if heridos_col else 0,
            'anio': int(row.get('Anio', 0)),
            'mes': int(row.get('Mes', 0)),
            'cluster': cl,
            'zona': f"Zona crítica {cl+1}" if cl >= 0 else "Siniestro aislado"
        })

    center_lat = df['lat'].mean()
    center_lon = df['lon'].mean()
    anios = sorted([a for a in df['Anio'].unique() if a > 0]) if 'Anio' in df.columns else []
    meses_disp = sorted([m for m in df['Mes'].unique() if m > 0]) if 'Mes' in df.columns else []
    points_json = json.dumps(points_data, ensure_ascii=False)
    clusters_json = json.dumps(cluster_info, ensure_ascii=False)
    cluster_colors_json = json.dumps(CLUSTER_COLORS)
    amenities_json = json.dumps(amenities, ensure_ascii=False)
    anios_opts = ''.join(f'<option value="{a}">{a}</option>' for a in anios)
    meses_opts = ''.join(f'<option value="{m}">{MESES.get(m,"Mes "+str(m))}</option>' for m in meses_disp)

    amenity_legend = ''

    html = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Análisis Espacial — Siniestros Viales Aguazul</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.heat@0.2.0/dist/leaflet-heat.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',Arial,sans-serif;background:#f0f0f0}
#map{position:fixed;top:0;left:360px;right:0;bottom:0;z-index:1}
#sidebar{position:fixed;top:0;left:0;width:360px;height:100vh;background:#FFFFFF;color:#1a1a2e;z-index:10;display:flex;flex-direction:column;overflow:hidden;box-shadow:4px 0 20px rgba(0,0,0,0.15)}
#header{background:linear-gradient(135deg,#2d6a4f,#1b4332);padding:14px 18px;flex-shrink:0}
#header h2{font-size:14px;color:#fff;font-weight:700;line-height:1.4}
#header p{font-size:11px;color:#a8d5c2;margin-top:3px}
#scroll{flex:1;overflow-y:auto;padding:14px}
#scroll::-webkit-scrollbar{width:4px}
#scroll::-webkit-scrollbar-thumb{background:#ccc;border-radius:4px}
.stitle{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#2d6a4f;margin:14px 0 8px}
.stitle:first-child{margin-top:0}
.fg{margin-bottom:8px}
.fg label{font-size:11px;color:#666;display:block;margin-bottom:3px}
.fg select{width:100%;padding:7px 10px;border-radius:7px;border:1px solid #ddd;background:#f8f8f8;color:#1a1a2e;font-size:12px;cursor:pointer;outline:none}
.fg select:hover{border-color:#2d6a4f}
.grav-filters{display:flex;flex-direction:column;gap:6px}
.gitem{display:flex;align-items:center;gap:8px;background:#f3f4f6;border-radius:7px;padding:7px 10px;cursor:pointer;border:1px solid #e5e7eb;transition:all 0.2s;user-select:none}
.gitem:hover{border-color:#2d6a4f}
.gdot{width:12px;height:12px;border-radius:50%;background:var(--c);flex-shrink:0;box-shadow:0 0 5px var(--c)}
.glabel{font-size:12px;color:#333;flex:1}
.gcnt{font-size:11px;font-weight:700;color:var(--c);background:rgba(255,255,255,0.05);padding:2px 7px;border-radius:20px}
.gitem.off{opacity:0.3}
.sgrid{display:grid;grid-template-columns:1fr 1fr;gap:6px}
.scard{background:#f3f4f6;border-radius:8px;padding:10px;border:1px solid #e5e7eb;text-align:center}
.scard.full{grid-column:1/-1}
.snum{font-size:24px;font-weight:700;color:#1a1a2e;line-height:1}
.snum.r{color:#E63946}.snum.o{color:#F4A261}.snum.t{color:#2A9D8F}.snum.y{color:#F9C74F}
.slbl{font-size:9px;color:#888;margin-top:2px;text-transform:uppercase;letter-spacing:0.5px;line-height:1.2}
.tbtn{flex:1;padding:7px;border-radius:7px;border:1px solid #ddd;background:#f3f4f6;color:#333;font-size:11px;cursor:pointer;transition:all 0.2s;text-align:center}
.tbtn:hover{background:#e5e7eb;border-color:#2d6a4f}
.tbtn.on{background:#2d6a4f;border-color:#2d6a4f;color:#fff}
.trow{display:flex;gap:6px;margin-bottom:8px}
.trow2{display:flex;gap:6px;margin-bottom:8px}
.zcard{background:#f3f4f6;border-radius:8px;padding:10px;border:1px solid #e5e7eb;margin-bottom:6px;cursor:pointer;transition:all 0.2s}
.zcard:hover{border-color:#2d6a4f;background:#e5e7eb}
.zcard-top{display:flex;align-items:center;gap:8px;margin-bottom:4px}
.zdot{width:14px;height:14px;border-radius:50%;flex-shrink:0}
.ztitle{font-size:12px;font-weight:600;color:#1a1a2e;flex:1}
.zbadge{font-size:10px;background:#e5e7eb;color:#555;padding:2px 7px;border-radius:10px}
.zstats{display:flex;gap:8px;font-size:11px;color:#666}

#footer{padding:8px 14px;border-top:1px solid #e5e7eb;font-size:10px;color:#888;text-align:center;flex-shrink:0}
.leaflet-control-attribution{font-size:9px}
</style>
</head>
<body>
<div id="sidebar">
  <div id="header">
    <h2>🚦 Análisis Espacial de Siniestros Viales<br>Aguazul, Casanare</h2>
    <p>Observatorio Territorial de Seguridad Vial · ROT ANSV</p>
  </div>
  <div id="scroll">
    <div class="stitle">🔍 Filtros</div>
    <div class="fg"><label>Año</label>
      <select id="fa" onchange="filtrar()">
        <option value="t">Todos los años</option>ANIOS_OPTS
      </select>
    </div>
    <div class="fg"><label>Mes</label>
      <select id="fm" onchange="filtrar()">
        <option value="t">Todos los meses</option>MESES_OPTS
      </select>
    </div>
    <div class="stitle">⚠ Gravedad</div>
    <div class="grav-filters">
      <div class="gitem active" id="gM" style="--c:#E63946" onclick="tg('Con Muertos')">
        <div class="gdot"></div><span class="glabel">Con Muertos</span>
        <span class="gcnt" id="cM">0</span>
      </div>
      <div class="gitem active" id="gH" style="--c:#F4A261" onclick="tg('Con Heridos')">
        <div class="gdot"></div><span class="glabel">Con Heridos</span>
        <span class="gcnt" id="cH">0</span>
      </div>
      <div class="gitem active" id="gD" style="--c:#2A9D8F" onclick="tg('Solo Daños')">
        <div class="gdot"></div><span class="glabel">Solo Daños</span>
        <span class="gcnt" id="cD">0</span>
      </div>
    </div>
    <div class="stitle">📊 Resumen de siniestros</div>
    <div class="sgrid">
      <div class="scard full"><div class="snum" id="sT">0</div><div class="slbl">Total Siniestros</div></div>
      <div class="scard"><div class="snum r" id="sSM">0</div><div class="slbl">Siniestros<br>con Muertos</div></div>
      <div class="scard"><div class="snum o" id="sSH">0</div><div class="slbl">Siniestros<br>con Heridos</div></div>
      <div class="scard"><div class="snum t" id="sSD">0</div><div class="slbl">Siniestros<br>Solo Daños</div></div>
    </div>
    <div class="stitle">🏥 Víctimas</div>
    <div class="sgrid">
      <div class="scard"><div class="snum r" id="sPM">0</div><div class="slbl">Personas<br>Fallecidas</div></div>
      <div class="scard"><div class="snum o" id="sPH">0</div><div class="slbl">Personas<br>Heridas</div></div>
      <div class="scard full"><div class="snum y" id="sTV">0</div><div class="slbl">Total Víctimas</div></div>
    </div>
    <div class="stitle">🗺 Capas del mapa</div>
    <div class="trow">
      <button class="tbtn on" id="bC" onclick="tCal()">🔥 Calor</button>
      <button class="tbtn on" id="bP" onclick="tPts()">📍 Puntos</button>
      <button class="tbtn on" id="bZ" onclick="tZon()">🎯 Zonas</button>
      <button class="tbtn on" id="bB" onclick="tBuf()">⭕ Buffers</button>
    </div>

    <div class="stitle">🎯 Zonas críticas identificadas</div>
    <div id="zonas-list"></div>
  </div>
  <div id="footer">Actualización automática diaria · ROT Aguazul</div>
</div>
<div id="map"></div>
<script>
const PUNTOS = POINTS_JSON;
const CLUSTERS = CLUSTERS_JSON;
const CLUSTER_COLORS = CLUSTER_COLORS_JSON;
const AMENITIES = AMENITIES_JSON;
const map = L.map('map').setView([CENTER_LAT, CENTER_LON], 14);
const bases = {
  'Calles (OpenStreetMap)': L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OSM'}),
  'Satélite (Esri)': L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',{attribution:'© Esri'}),
  'Calles detalladas': L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',{attribution:'© Esri'})
};
bases['Calles (OpenStreetMap)'].addTo(map);
L.control.layers(bases,{},{position:'topright'}).addTo(map);
let mLyr=L.layerGroup().addTo(map);
let zLyr=L.layerGroup().addTo(map);
let bLyr=L.layerGroup().addTo(map);
let aLyr=L.layerGroup().addTo(map);
let hLyr=null;
let showCal=true,showPts=true,showZon=true,showBuf=true,showAmen=true;
let gravActivas=new Set(['Con Muertos','Con Heridos','Solo Daños']);

// Build zones list
const zonasList=document.getElementById('zonas-list');
CLUSTERS.forEach(c=>{
  const d=document.createElement('div');
  d.className='zcard';
  d.innerHTML=`<div class="zcard-top"><div class="zdot" style="background:${c.color}"></div><span class="ztitle">Zona crítica ${c.id+1}</span><span class="zbadge">${c.size} siniestros</span></div><div class="zstats"><div>🔴 ${c.muertos} fallecidos</div><div>🟠 ${c.heridos} heridos</div></div>`;
  d.onclick=()=>map.setView([c.lat,c.lon],17);
  zonasList.appendChild(d);
});

// Draw amenities
function dibujarAmenities(){
  aLyr.clearLayers();
  if(!showAmen) return;
  AMENITIES.forEach(a=>{
    const icon = L.divIcon({
      html:`<div style="background:${a.color};color:white;border-radius:50%;width:28px;height:28px;display:flex;align-items:center;justify-content:center;font-size:14px;border:2px solid white;box-shadow:0 2px 4px rgba(0,0,0,0.3)">${a.icon}</div>`,
      iconSize:[28,28], iconAnchor:[14,14], className:''
    });
    const m = L.marker([a.lat,a.lon],{icon});
    m.bindPopup(`
      <div style="font-family:'Segoe UI';font-size:13px;min-width:180px">
        <div style="background:${a.color};color:white;padding:8px 12px;margin:-1px -1px 8px;border-radius:4px 4px 0 0">
          <b>${a.icon} ${a.label}</b>
        </div>
        <div style="padding:0 4px 4px">
          <b>${a.name}</b><br>
          <a href="https://www.google.com/maps?q=${a.lat},${a.lon}" target="_blank" style="color:#1a73e8;font-size:12px">📍 Ver en Google Maps</a>
        </div>
      </div>`,{maxWidth:240});
    m.bindTooltip(`${a.icon} ${a.name}`,{sticky:true});
    m.addTo(aLyr);
  });
}

function crearHeat(datos){
  if(hLyr)map.removeLayer(hLyr);
  if(!datos.length)return;
  hLyr=L.heatLayer(datos.map(p=>[p.lat,p.lon,1]),{radius:25,blur:15,maxZoom:16,gradient:{0.2:'yellow',0.5:'orange',0.8:'red',1.0:'darkred'}});
  if(showCal)hLyr.addTo(map);
}

function dibujarZonas(datos){
  zLyr.clearLayers();bLyr.clearLayers();
  CLUSTERS.forEach(c=>{
    const pf=datos.filter(p=>p.cluster===c.id);
    if(!pf.length)return;
    const zm=L.circleMarker([c.lat,c.lon],{radius:10+c.size*2,color:c.color,weight:4,fill:true,fillColor:c.color,fillOpacity:0.25});
    zm.bindPopup(`<div style="font-family:'Segoe UI';font-size:13px;min-width:220px"><div style="background:${c.color};color:white;padding:8px 12px;margin:-1px -1px 8px;border-radius:4px 4px 0 0"><b>🎯 Zona crítica ${c.id+1}</b></div><b>Siniestros:</b> ${c.size}<br><b>Fallecidos:</b> ${c.muertos}<br><b>Heridos:</b> ${c.heridos}<br><b>Radio:</b> ~100 metros</div>`,{maxWidth:260});
    if(showZon)zm.addTo(zLyr);
    const darkColor = c.color.replace('#FF6B6B','#CC0000').replace('#4ECDC4','#007A73').replace('#45B7D1','#005F8A').replace('#96CEB4','#2D6A4F').replace('#FFEAA7','#B8860B').replace('#DDA0DD','#7B2D8B').replace('#98D8C8','#1A6B5A');
    const buf=L.circle([c.lat,c.lon],{radius:150,color:darkColor,weight:3,fill:true,fillColor:darkColor,fillOpacity:0.15,dashArray:'8,5'});
    buf.bindTooltip(`Zona crítica ${c.id+1} · Radio 150m`,{sticky:true});
    if(showBuf)buf.addTo(bLyr);
  });
}

function filtrar(){
  const anio=document.getElementById('fa').value;
  const mes=document.getElementById('fm').value;
  const fil=PUNTOS.filter(p=>(anio==='t'||p.anio==anio)&&(mes==='t'||p.mes==mes)&&gravActivas.has(p.gravedad));
  mLyr.clearLayers();
  fil.forEach(p=>{
    const c=L.circleMarker([p.lat,p.lon],{radius:p.cluster>=0?4:3,color:'white',weight:1.5,fillColor:p.color,fillOpacity:0.9});
    c.bindPopup(`<div style="font-family:'Segoe UI';font-size:13px;min-width:230px"><div style="background:${p.color};color:white;padding:8px 12px;margin:-1px -1px 8px;border-radius:4px 4px 0 0"><b>⚠ ${p.gravedad}</b>${p.cluster>=0?`<span style="float:right;font-size:10px;opacity:0.9">🎯 Zona ${p.cluster+1}</span>`:''}</div><div style="padding:0 4px 4px"><b>Código:</b> ${p.codrot}<br><b>Dirección:</b> ${p.direccion}<br><b>Fecha:</b> ${p.fecha} <b>Hora:</b> ${p.hora}<br><b>Clase:</b> ${p.clase}<br><b>Fallecidos:</b> ${p.muertos} <b>Heridos:</b> ${p.heridos}<br><hr style="margin:6px 0"><a href="https://www.google.com/maps?q=${p.lat},${p.lon}" target="_blank" style="color:#1a73e8;font-size:12px">📍 Ver en Google Maps / Street View</a></div></div>`,{maxWidth:280});
    c.bindTooltip(`<b>${p.gravedad}</b> · ${p.zona}<br>${p.direccion}`,{sticky:true});
    c.addTo(mLyr);
  });
  crearHeat(fil);
  dibujarZonas(fil);
  dibujarAmenities();
  const sM=fil.filter(p=>p.gravedad==='Con Muertos').length;
  const sH=fil.filter(p=>p.gravedad==='Con Heridos').length;
  const sD=fil.filter(p=>p.gravedad==='Solo Daños').length;
  const pM=fil.reduce((s,p)=>s+p.muertos,0);
  const pH=fil.reduce((s,p)=>s+p.heridos,0);
  document.getElementById('sT').textContent=fil.length;
  document.getElementById('sSM').textContent=sM;
  document.getElementById('sSH').textContent=sH;
  document.getElementById('sSD').textContent=sD;
  document.getElementById('sPM').textContent=pM;
  document.getElementById('sPH').textContent=pH;
  document.getElementById('sTV').textContent=pM+pH;
  document.getElementById('cM').textContent=sM;
  document.getElementById('cH').textContent=sH;
  document.getElementById('cD').textContent=sD;
}

function tg(g){const ids={'Con Muertos':'gM','Con Heridos':'gH','Solo Daños':'gD'};const el=document.getElementById(ids[g]);if(gravActivas.has(g)){gravActivas.delete(g);el.classList.add('off');}else{gravActivas.add(g);el.classList.remove('off');}filtrar();}
function tCal(){showCal=!showCal;const b=document.getElementById('bC');if(showCal){if(hLyr)hLyr.addTo(map);b.classList.add('on');}else{if(hLyr)map.removeLayer(hLyr);b.classList.remove('on');}}
function tPts(){showPts=!showPts;const b=document.getElementById('bP');if(showPts){mLyr.addTo(map);b.classList.add('on');}else{map.removeLayer(mLyr);b.classList.remove('on');}}
function tZon(){showZon=!showZon;const b=document.getElementById('bZ');if(showZon){zLyr.addTo(map);b.classList.add('on');}else{map.removeLayer(zLyr);b.classList.remove('on');}}
function tBuf(){showBuf=!showBuf;const b=document.getElementById('bB');if(showBuf){bLyr.addTo(map);b.classList.add('on');}else{map.removeLayer(bLyr);b.classList.remove('on');}}
function tAmen(){showAmen=!showAmen;const b=document.getElementById('bA');if(showAmen){aLyr.addTo(map);b.classList.add('on');}else{map.removeLayer(aLyr);b.classList.remove('on');}dibujarAmenities();}
filtrar();
</script>
</body>
</html>"""

    html = html.replace('ANIOS_OPTS', anios_opts)
    html = html.replace('MESES_OPTS', meses_opts)
    html = html.replace('POINTS_JSON', points_json)
    html = html.replace('CLUSTERS_JSON', clusters_json)
    html = html.replace('CLUSTER_COLORS_JSON', cluster_colors_json)
    html = html.replace('AMENITIES_JSON', amenities_json)
    html = html.replace('CENTER_LAT', str(center_lat))
    html = html.replace('CENTER_LON', str(center_lon))
    html = html.replace('AMENITY_LEGEND', amenity_legend)
    return html

if __name__ == "__main__":
    os.makedirs("docs", exist_ok=True)
    print("Cargando datos desde Google Sheets...")
    df = cargar_datos(SHEET_URL)
    print(f"✓ {len(df)} siniestros cargados")
    print("Calculando zonas críticas (DBSCAN)...")
    df, cluster_info = calcular_dbscan(df)
    print(f"✓ {len(cluster_info)} zonas críticas identificadas")
    print("Descargando equipamientos urbanos (OSM)...")
    center_lat = df['lat'].mean()
    center_lon = df['lon'].mean()
    amenities = descargar_equipamientos(center_lat, center_lon)
    print("Generando mapa...")
    html = generar_html(df, cluster_info, amenities)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✓ Mapa guardado en {OUTPUT_FILE}")
    print(f"✓ {len(amenities)} equipamientos incluidos")
