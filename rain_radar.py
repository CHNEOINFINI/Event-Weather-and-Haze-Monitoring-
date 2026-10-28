"""NEA rainfall radar with approximate Singapore reference outline and venue marker."""
from datetime import datetime, timezone
from io import BytesIO
import math
import requests
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

BASE = 'https://api-open.data.gov.sg/v2/real-time/api/weather-radar-images'
VENUES = {
    'Marina Bay / F1 Pit Building': (1.2914, 103.8639),
    'Padang / Connaught Drive': (1.2898, 103.8534),
    'East Coast Park': (1.3008, 103.9122),
    'Punggol Digital District': (1.4055, 103.9118),
    'Singapore Sports Hub': (1.3040, 103.8748),
    'Bayfront Event Space': (1.2838, 103.8591),
    'Marina Promontory': (1.2802, 103.8543),
    'Marina Barrage': (1.2806, 103.8705),
}
# Approximate Singapore mainland outline for visual orientation ONLY.
# Not an authoritative coastline, survey map, or georeferenced safety boundary.
MAINLAND = [
    (103.606,1.318),(103.626,1.339),(103.650,1.361),(103.681,1.388),
    (103.708,1.418),(103.743,1.432),(103.775,1.440),(103.814,1.453),
    (103.850,1.451),(103.881,1.438),(103.915,1.424),(103.946,1.414),
    (103.972,1.392),(104.004,1.385),(104.032,1.372),(104.054,1.352),
    (104.071,1.327),(104.053,1.308),(104.023,1.299),(103.988,1.300),
    (103.961,1.314),(103.935,1.310),(103.909,1.299),(103.884,1.292),
    (103.864,1.276),(103.843,1.264),(103.812,1.261),(103.788,1.266),
    (103.767,1.276),(103.746,1.290),(103.722,1.304),(103.691,1.313),
    (103.663,1.305),(103.632,1.307)
]

@st.cache_data(ttl=240, show_spinner=False)
def radar_data(coverage):
    response = requests.get(f'{BASE}/{coverage}', timeout=25, headers={'Accept':'application/json'})
    response.raise_for_status()
    payload = response.json()
    if payload.get('code') not in (None, 0):
        raise ValueError(payload.get('errorMsg') or 'NEA API returned an error')
    data = payload.get('data') or {}
    records = data.get('records') or []
    if isinstance(records, dict):
        records = [records]
    return records, data.get('boundaryBox')

@st.cache_data(ttl=180, show_spinner=False)
def radar_image(url):
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    if not response.headers.get('content-type', '').lower().startswith('image/'):
        raise ValueError('Image link did not return an image')
    return response.content

def _font(size):
    for path in ('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
                 '/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf'):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()

def annotated_image(raw, boundary, venue, zoom):
    image = Image.open(BytesIO(raw)).convert('RGB')
    if not isinstance(boundary, dict):
        raise ValueError('NEA response does not include the radar boundary box')
    ul, lr = boundary['upperLeft'], boundary['lowerRight']
    west, east = float(ul['longitude']), float(lr['longitude'])
    north, south = float(ul['latitude']), float(lr['latitude'])
    width, height = image.size
    if not (west < east and south < north):
        raise ValueError('Invalid geographic radar bounds')

    def pixel(lon, lat):
        return ((lon-west)/(east-west)*width, (north-lat)/(north-south)*height)

    draw = ImageDraw.Draw(image)
    poly = [pixel(lon,lat) for lon,lat in MAINLAND]
    # Outline only, preserving the original radar echoes.
    line_width = max(2, width//380)
    draw.line(poly+[poly[0]], fill='#ffffff', width=line_width, joint='curve')
    lat, lon = VENUES[venue]
    x, y = pixel(lon,lat)
    radius = max(6, width//160)
    draw.ellipse((x-radius-2,y-radius-2,x+radius+2,y+radius+2), fill='#000000')
    draw.ellipse((x-radius,y-radius,x+radius,y+radius), fill='#ff4d4d', outline='#ffffff', width=2)
    label_font = _font(max(13, width//80))
    name = 'EVENT VENUE'
    tx, ty = min(max(8, x+radius+8), max(8,width-200)), max(8,y-24)
    draw.text((tx+1,ty+1), name, fill='#000000', font=label_font, stroke_width=2, stroke_fill='#000000')
    draw.text((tx,ty), name, fill='#ffffff', font=label_font)

    if zoom:
        # Show Singapore mainland plus nearby rain systems; not a venue-specific radius.
        crop_bounds = (103.54, 104.18, 1.15, 1.53)  # west, east, south, north
        left, top = pixel(crop_bounds[0],crop_bounds[3])
        right, bottom = pixel(crop_bounds[1],crop_bounds[2])
        l,t,r,b = max(0,int(left)),max(0,int(top)),min(width,int(right)),min(height,int(bottom))
        if r-l > 50 and b-t > 50:
            image = image.crop((l,t,r,b))
    return image

def render_rain_radar():
    st.subheader('Singapore Rain Radar')
    st.caption('Official NEA radar observations with an approximate Singapore outline and venue marker.')
    a,b = st.columns([2,1])
    with a:
        coverage = st.selectbox('Radar coverage', ['70km','240km','480km'], key='radar_coverage')
    with b:
        if st.button('Refresh radar', key='radar_refresh'):
            radar_data.clear()
            radar_image.clear()
            st.rerun()
    venue = st.selectbox('Highlight event venue', list(VENUES), key='radar_venue_marker')
    zoom = st.checkbox('Zoom closer to Singapore', value=True, key='radar_zoom_sg')
    try:
        records, boundary = radar_data(coverage)
        frames = []
        for record in records:
            if not isinstance(record,dict):
                continue
            image = record.get('image') or {}
            url = image.get('url') if isinstance(image,dict) else None
            timestamp = record.get('timestamp')
            if isinstance(url,str) and url.startswith('https://') and timestamp:
                frames.append((str(timestamp),url))
        frames = sorted(set(frames))
        if not frames:
            st.warning('NEA returned no usable radar frames.')
            return
        if len(frames)>1:
            idx = st.slider('Available radar frames', 0,len(frames)-1,len(frames)-1,key='radar_frame')
        else:
            idx = 0
            st.info('One radar frame available. Showing latest observation.')
        stamp,url = frames[idx]
        st.write(f'Observation timestamp: **{stamp}**')
        try:
            observed = datetime.fromisoformat(stamp.replace('Z','+00:00'))
            if observed.tzinfo:
                age = (datetime.now(timezone.utc)-observed.astimezone(timezone.utc)).total_seconds()/60
                if age > 20:
                    st.warning(f'Radar observation is {age:.0f} minutes old.')
        except (ValueError,TypeError):
            pass
        img = annotated_image(radar_image(url), boundary, venue, zoom)
        st.image(img, caption=f'{venue} (red marker) | Approximate Singapore mainland outline (white)', use_container_width=True)
        st.caption('The outline and venue marker are approximate visual references, not survey-grade georeferencing. Radar echoes are observations, not forecasts or a lightning all-clear.')
    except Exception as exc:
        st.error(f'Rain radar unavailable: {exc}')
    st.link_button('View official MSS rain radar with map', 'https://www.weather.gov.sg/weather-rain-area-50km/')
