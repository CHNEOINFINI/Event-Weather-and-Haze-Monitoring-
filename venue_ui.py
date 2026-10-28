"""Streamlit venue monitor. Imported by app.py after base dashboard initialization."""
import pandas as pd
import streamlit as st
from venue import VENUES,FEEDS,fetch,readings,lightning_points,proximity,route_from_upload,age_minutes

@st.cache_data(ttl=300,show_spinner=False)
def venue_feeds():
    data,errors={},{}
    for name,endpoint in FEEDS.items():
        try:data[name]=fetch(endpoint)
        except Exception as e:errors[name]=str(e)
    return data,errors

def render():
    st.header('📍 Venue & route proximity monitoring')
    st.caption('Venue coordinates are approximate reference points. Validate event footprints and official warnings. Lightning observations are not a lightning safety clearance.')
    cluster=st.checkbox('Marina Bay Cluster: monitor Bayfront Event Space, Marina Promontory and Marina Barrage together')
    if cluster:
        names=['Bayfront Event Space (approximate)','Marina Promontory','Marina Barrage']
    else:
        names=[st.selectbox('Event venue',list(VENUES))]
    radius=st.select_slider('Proximity radius (km)',options=[2,5,6,10,20],value=5)
    use_custom=st.checkbox('Override venue coordinates (single-venue mode)',disabled=cluster)
    if use_custom:
        initial=VENUES[names[0]]
        c1,c2=st.columns(2)
        with c1:lat=st.number_input('Latitude',value=initial[0],format='%.6f')
        with c2:lon=st.number_input('Longitude',value=initial[1],format='%.6f')
        targets=[(names[0],lat,lon)]
    else:targets=[(name,*VENUES[name][:2]) for name in names]
    uploaded=st.file_uploader('Optional event route (.kml / .kmz): calculate distance to entire route',type=['kml','kmz'])
    route=None
    if uploaded:
        try:
            route=route_from_upload(uploaded.getvalue(),uploaded.name)
            st.success(f'Route loaded: {len(route)} sampled geographic points. Proximity is calculated to the route, not just the start point.')
        except Exception as e:st.error(f'Route unavailable: {e}')
    if st.button('Refresh venue observations'):
        venue_feeds.clear();st.rerun()
    data,errors=venue_feeds()
    for name,error in errors.items():st.warning(f'{name}: feed unavailable — {error}')
    rain=readings(data['Rainfall']) if 'Rainfall' in data else []
    strikes=lightning_points(data['Lightning']) if 'Lightning' in data else []
    st.caption('Data freshness: feed requests cached for 5 minutes. Rainfall is a station observation; lightning is an observed location, not a forecast.')
    rows=[]
    for name,lat,lon in targets:
        near_rain=proximity(rain,lat,lon,radius,route)
        near_lightning=proximity(strikes,lat,lon,radius,route)
        closest_rain=near_rain[0] if near_rain else None
        close_strikes=[p for p in near_lightning if p['inside'] and (age_minutes(p.get('timestamp')) is not None and 0<=age_minutes(p['timestamp'])<=30)]
        lightning_age=[age_minutes(p['timestamp']) for p in near_lightning if p.get('timestamp')]
        fresh_lightning=bool(lightning_age and min(lightning_age)<=30)
        rain_age=age_minutes(closest_rain['timestamp']) if closest_rain else None
        rain_valid=rain_age is not None and 0<=rain_age<=30
        if 'Lightning' not in data or not fresh_lightning:
            light_status='UNVERIFIED / STALE' # No recent strikes does not prove current feed health
        elif close_strikes:light_status=f'ALERT: {len(close_strikes)} strikes within {radius} km (30 min)'
        else:light_status='No nearby strikes in available recent observations'
        rows.append({'Venue':name,'Rainfall (nearest station)':f"{closest_rain['value']:g} mm ({closest_rain['distance_km']:.1f} km away)" if closest_rain and rain_valid else 'Unavailable / stale',
                     'Lightning (last 30 min)':light_status,
                     'Nearest detected lightning':f"{near_lightning[0]['distance_km']:.1f} km" if near_lightning and fresh_lightning else 'Unavailable / unverified',
                     'Operational flag':'REVIEW / ESCALATE' if close_strikes else 'CHECK OFFICIAL WARNINGS'})
    st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
    if any('ALERT' in r['Lightning (last 30 min)'] for r in rows):st.error('Lightning proximity alert. Follow the event lightning action plan and official warnings immediately.')
    st.info('No nearby detected strike does NOT mean safe. Official NEA lightning warnings and on-site observations take precedence. The radius and 30-minute lookback are configurable screening settings, not an approved all-clear rule.')
    pts=[{'lat':lat,'lon':lon,'name':name,'type':'Venue'} for name,lat,lon in targets]
    pts += [{'lat':r['lat'],'lon':r['lon'],'name':r['name'],'type':'Rain station'} for r in rain[:100]]
    pts += [{'lat':r['lat'],'lon':r['lon'],'name':'Detected lightning','type':'Lightning'} for r in strikes[:200]]
    if route:pts += [{'lat':a,'lon':b,'name':'Route','type':'Route'} for a,b in route[::max(1,len(route)//250)]]
    st.map(pd.DataFrame(pts),latitude='lat',longitude='lon',size=30)
    with st.expander('Feed interpretation and limitations'):
        st.write('PSI and PM2.5 remain regional, not venue-specific. Rainfall values represent a nearby station, not necessarily rainfall at the event site. Lightning point precision and API latency can vary. No future lightning-strike locations are predicted. Weather forecasts are area-level, not venue-specific nowcasts.')
        st.write('For critical event safety, confirm official lightning warnings, rain radar, site conditions, medical advice and the approved suspension/resumption protocol. No automatic cancellation or all-clear is issued.')
    st.markdown('[Official lightning and weather warnings](https://www.weather.gov.sg/weather-lightning/) · [NEA haze](https://www.haze.gov.sg/)')
