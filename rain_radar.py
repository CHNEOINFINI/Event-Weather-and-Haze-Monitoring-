"""NEA rain radar viewer. Read-only observations; no forecast or safety clearance."""
from datetime import datetime, timezone
from io import BytesIO
import requests
import streamlit as st

BASE = 'https://api-open.data.gov.sg/v2/real-time/api/weather-radar-images'

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
    return records

@st.cache_data(ttl=180, show_spinner=False)
def radar_image(url):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    if not r.headers.get('content-type', '').lower().startswith('image/'):
        raise ValueError('Image link did not return an image')
    from PIL import Image
    img = Image.open(BytesIO(r.content))
    img.verify()
    return r.content

def render_rain_radar():
    st.subheader('Singapore Rain Radar')
    st.caption('Official NEA radar images (observations, not forecasts). The timeline displays available API frames.')
    a, b = st.columns([2,1])
    with a:
        coverage = st.selectbox('Radar coverage', ['70km','240km','480km'], key='radar_coverage')
    with b:
        if st.button('Refresh radar', key='radar_refresh'):
            radar_data.clear()
            radar_image.clear()
            st.rerun()
    try:
        records = radar_data(coverage)
        frames = []
        for record in records:
            if not isinstance(record, dict):
                continue
            image = record.get('image') or {}
            url = image.get('url') if isinstance(image,dict) else None
            timestamp = record.get('timestamp')
            if isinstance(url,str) and url.startswith('https://') and timestamp:
                frames.append((str(timestamp), url))
        frames = sorted(set(frames))
        if not frames:
            st.warning('No usable radar frames returned. Check the NEA dataset or try again later.')
            st.link_button('Official MSS rain radar', 'https://www.weather.gov.sg/weather-rain-area-50km/')
            return
        idx = st.slider('Available radar frames', 0, len(frames)-1, len(frames)-1, key='radar_frame')
        stamp, url = frames[idx]
        st.write(f'Observation timestamp: **{stamp}**')
        try:
            observed = datetime.fromisoformat(stamp.replace('Z','+00:00'))
            if observed.tzinfo:
                age = (datetime.now(timezone.utc)-observed.astimezone(timezone.utc)).total_seconds()/60
                if age > 20:
                    st.warning(f'Radar frame is {age:.0f} minutes old.')
        except (ValueError, TypeError):
            pass
        try:
            st.image(radar_image(url), use_container_width=True)
        except Exception as exc:
            st.warning(f'Radar image unavailable or expired: {exc}. Try Refresh radar.')
        if len(frames)==1:
            st.info('Only one frame returned by the API. Animation requires multiple historical frames.')
        st.link_button('Official MSS rain radar', 'https://www.weather.gov.sg/weather-rain-area-50km/')
        st.caption('Radar echoes may not equal ground-level rainfall. Follow official lightning warnings and on-site safety procedures.')
    except Exception as exc:
        st.error(f'Rain radar feed unavailable: {exc}')
        st.link_button('View official MSS rain radar', 'https://www.weather.gov.sg/weather-rain-area-50km/')
