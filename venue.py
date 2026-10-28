"""Venue proximity monitoring, tolerant NEA observation parsing and route support."""
import io, math, zipfile, xml.etree.ElementTree as ET
from datetime import datetime
import pandas as pd
from backend import fetch, parse_time, now

VENUES={
 'Marina Bay / F1 Pit Building':(1.2914,103.8639,5),
 'Padang / Connaught Drive':(1.2898,103.8534,5),
 'East Coast Park (central reference)':(1.3008,103.9122,10),
 'Punggol Digital District':(1.4055,103.9118,5),
 'Singapore Sports Hub':(1.3040,103.8748,5),
 'Bayfront Event Space (approximate)':(1.2818,103.8590,5),
 'Marina Promontory':(1.2797,103.8540,5),
 'Marina Barrage':(1.2806,103.8703,5),
}
# Reference points, not surveyed site boundaries. Users may override coordinates.
FEEDS={'Rainfall':'rainfall','Lightning':'lightning','Wind direction':'wind-direction','Wind speed':'wind-speed','2-hour forecast':'two-hr-forecast'}

def km(lat1,lon1,lat2,lon2):
    a,b,c,d=map(math.radians,[lat1,lon1,lat2,lon2]); delta=a-c; dl=b-d
    return 6371.0088*2*math.asin(min(1,math.sqrt(math.sin(delta/2)**2+math.cos(a)*math.cos(c)*math.sin(dl/2)**2)))

def number(x):
    try:
        if isinstance(x,bool) or x is None:return None
        v=float(x)
        return v if math.isfinite(v) else None
    except (ValueError,TypeError):return None

def location(p):
    if not isinstance(p,dict):return None
    q=p.get('location') or p.get('coordinates') or p
    if isinstance(q,dict):
        a=number(q.get('latitude',q.get('lat'))); b=number(q.get('longitude',q.get('lng',q.get('lon'))))
    elif isinstance(q,(list,tuple)) and len(q)>=2:
        # GeoJSON coordinates [longitude,latitude]
        b,a=number(q[0]),number(q[1])
    else:return None
    return (a,b) if a is not None and b is not None and -90<=a<=90 and -180<=b<=180 else None

def stations(data):
    out={}
    for s in data.get('stations',[]) or []:
        if not isinstance(s,dict):continue
        point=location(s)
        if point:out[str(s.get('id',s.get('stationId',s.get('name',''))))]={'lat':point[0],'lon':point[1],'name':s.get('name') or s.get('id') or 'Station'}
    return out

def readings(data):
    """Return latest station readings, supporting common data.gov.sg envelope shapes."""
    stations_by_id=stations(data); out=[]
    for item in data.get('items',[]) or []:
        if not isinstance(item,dict):continue
        stamp=parse_time(item.get('timestamp') or item.get('updatedTimestamp'))
        for r in item.get('readings',[]) or []:
            if not isinstance(r,dict):continue
            ident=str(r.get('stationId',r.get('station_id',r.get('id',''))))
            s=stations_by_id.get(ident)
            if not s:continue
            value=number(r.get('value'))
            if value is not None:out.append(dict(**s,value=value,timestamp=stamp))
    return out

def lightning_points(data):
    """Only use observations with explicit coordinates; do not infer strikes from area forecasts."""
    result=[]
    for item in data.get('items',[]) or []:
        if not isinstance(item,dict):continue
        ts=parse_time(item.get('timestamp') or item.get('updatedTimestamp'))
        candidates=item.get('readings') or item.get('locations') or item.get('observations') or []
        if isinstance(candidates,dict):candidates=candidates.get('locations') or candidates.get('readings') or []
        for r in candidates:
            p=location(r)
            if p:result.append({'lat':p[0],'lon':p[1],'timestamp':parse_time(r.get('timestamp')) or ts})
    return result

def proximity(rows,lat,lon,radius,route=None):
    targets=route if route else [(lat,lon)]
    result=[]
    for r in rows:
        distance=min(km(a,b,r['lat'],r['lon']) for a,b in targets)
        result.append({**r,'distance_km':round(distance,2),'inside':distance<=radius})
    return sorted(result,key=lambda x:x['distance_km'])

def route_from_upload(blob,filename):
    if filename.lower().endswith('.kmz'):
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            names=[n for n in z.namelist() if n.lower().endswith('.kml')]
            if not names:raise ValueError('KMZ contains no KML')
            blob=z.read(names[0])
    elif not filename.lower().endswith('.kml'):raise ValueError('Upload .kml or .kmz')
    root=ET.fromstring(blob); coords=[]
    for node in root.iter():
        if node.tag.split('}')[-1]!='coordinates' or not node.text:continue
        for token in node.text.split():
            parts=token.split(',')
            if len(parts)<2:continue
            lon,lat=number(parts[0]),number(parts[1])
            if lat is not None and lon is not None and -90<=lat<=90 and -180<=lon<=180:coords.append((lat,lon))
    if not coords:raise ValueError('No valid route coordinates in file')
    # Sample long routes to bound processing time. All samples remain on the supplied route.
    stride=max(1,math.ceil(len(coords)/1500))
    return coords[::stride]+([coords[-1]] if coords[-1]!=coords[::stride][-1] else [])

def age_minutes(ts):return (now()-ts).total_seconds()/60 if isinstance(ts,datetime) else None
