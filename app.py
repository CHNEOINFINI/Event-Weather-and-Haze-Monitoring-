import streamlit as st
import pandas as pd
from datetime import timedelta
from backend import (fetch,normalize_air,latest_air,extract_forecasts,extract_24h,save,history,backfill,assess,now,REGIONS,ENDPOINTS)

st.set_page_config(page_title='Singapore Weather & Haze Operations',page_icon='🌤️',layout='wide')
st.title('🌤️ Singapore Weather & Haze | Operations Dashboard')
st.caption('Official NEA observations via data.gov.sg • Singapore-wide • Asia/Singapore time • advisory decision support, not an official safety clearance')

@st.cache_data(ttl=600,show_spinner=False)
def live_data():
    out={}; errors={}
    for name,endpoint in ENDPOINTS.items():
        try:out[name]=fetch(endpoint)
        except Exception as exc:errors[name]=str(exc)
    return out,errors

with st.sidebar:
    st.header('Controls')
    selected=st.selectbox('Focus region',['Singapore-wide']+[r.title() for r in REGIONS])
    show_hours=st.selectbox('History window (hours)',[24,48,72],index=2)
    st.caption('API responses cached for 10 minutes. Use Refresh now to request new readings.')
    if st.button('🔄 Refresh now',use_container_width=True):
        live_data.clear();st.rerun()
    if st.button('📥 Backfill last 3 days',use_container_width=True):
        with st.spinner('Fetching dated observations from NEA…'):
            for kind in ['PSI','PM2.5']:
                n,err=backfill(kind)
                st.write(f'{kind}: {n} valid regional readings saved')
                if err:st.warning('; '.join(err[:3]))
    st.markdown('**Official sources**')
    st.markdown('[NEA haze portal](https://www.haze.gov.sg/) | [NEA/MSS weather](https://www.weather.gov.sg/) | [ASEAN hotspot outlook](https://asmc.asean.org/)')
    st.info('For uninterrupted collection, schedule collector.py externally. Streamlit page refresh alone does not guarantee 24/7 historical logging.')

with st.spinner('Loading official data…'):
    data,errors=live_data()
frames={}
for kind in ['PSI','PM2.5']:
    frames[kind]=normalize_air(data[kind],kind) if kind in data else pd.DataFrame()
    if not frames[kind].empty:save(frames[kind])
for name,error in errors.items():st.warning(f'**{name} unavailable:** {error}')

focus=selected.lower()
metric_vals={};ages=[]
cols=st.columns(3)
for i,kind in enumerate(['PSI','PM2.5']):
    df=latest_air(frames[kind])
    if focus!='singapore-wide':df=df[df['region']==focus]
    value=float(df['value'].max()) if not df.empty else None
    age=(now()-df['timestamp'].min().to_pydatetime()).total_seconds()/60 if not df.empty else None
    if age is not None:ages.append(age)
    metric_vals[kind]=value
    with cols[i]:
        st.metric(('Highest regional ' if focus=='singapore-wide' else '')+kind, 'Unavailable' if value is None else f'{value:g}',help='PSI is 24-hour PSI. PM2.5 is 1-hour concentration in µg/m³. These are different measures.')
        st.caption('Reading age: unavailable' if age is None else f'Oldest displayed reading: {age:.0f} min ago')
with cols[2]:
    st.metric('Feed health',f'{len(data)}/4 available')
    st.caption('Missing feeds are never filled with guessed values')

status,message=assess(metric_vals['PSI'],metric_vals['PM2.5'],max(ages) if len(ages)==2 else None)
st.subheader('Operational assessment')
if status=='ROUTINE MONITORING':st.success(f'**{status}** — {message}')
elif status in ('DATA UNAVAILABLE / STALE','INCOMPLETE DATA'):st.warning(f'**{status}** — {message}')
else:st.error(f'**{status}** — {message}')
st.caption('Illustrative internal escalation rules only. Lightning, heat stress, rain and official sport-specific haze guidance must be assessed separately. PSI and PM2.5 are not interchangeable.')

st.subheader('Regional air quality')
regional=[]
for kind in ['PSI','PM2.5']:
    df=latest_air(frames[kind])
    if not df.empty:
        for row in df.itertuples():regional.append({'Region':row.region.title(),'Metric':kind,'Reading':row.value,'Observed (SGT)':row.timestamp.strftime('%d %b %H:%M')})
if regional:
    pivot=pd.DataFrame(regional).pivot(index='Region',columns='Metric',values='Reading').reindex([r.title() for r in REGIONS])
    st.dataframe(pivot,use_container_width=True)
else:st.info('Regional observations unavailable. Check feed errors above.')

from venue_ui import render as render_venue
render_venue()

from rain_radar import render_rain_radar
st.divider()
render_rain_radar()

st.subheader('Historical observations')
hist=history(show_hours)
if not hist.empty:
    if focus!='singapore-wide':hist=hist[hist.region==focus]
    for kind in ['PSI','PM2.5']:
        st.markdown(f'**{kind}**'+(' (µg/m³)' if kind=='PM2.5' else ' (24-hour index)'))
        subset=hist[hist.metric==kind]
        if not subset.empty:
            chart=subset.pivot_table(index='timestamp',columns='region',values='value',aggfunc='last').sort_index()
            st.line_chart(chart,height=225)
        else:st.info('No archived history for this metric. Use Backfill or leave scheduled collector running.')
    st.download_button('Download observation history (CSV)',hist.to_csv(index=False).encode(),file_name='sg_haze_history.csv',mime='text/csv')
else:st.info('No history yet. Use the Backfill button to request up to three days of archived observations.')

st.subheader('72-hour weather planning outlook')
if '4-day forecast' in data:
    outlook=extract_forecasts(data['4-day forecast'])
    if not outlook.empty:
        start=now().date()
        outlook['parsed_date']=pd.to_datetime(outlook['date'],errors='coerce').dt.date
        upcoming=outlook[(outlook.parsed_date>=start)&(outlook.parsed_date<=start+timedelta(days=3))].sort_values('parsed_date').head(4)
        if not upcoming.empty:
            st.dataframe(upcoming[['date','forecast','temp_low','temp_high','humidity_low','humidity_high','wind']].rename(columns={'date':'Day (SGT)','forecast':'Conditions','temp_low':'Min °C','temp_high':'Max °C','humidity_low':'Min RH %','humidity_high':'Max RH %','wind':'Wind direction'}),hide_index=True,use_container_width=True)
            st.caption('NEA 4-day outlook is daily, not a continuous hourly 72-hour forecast. Days shown may cover more than 72 hours. No hour-by-hour haze forecast is provided.')
        else:st.warning('No forecast dates matching the next 72-hour planning window.')
    else:st.warning('Four-day API responded but forecast fields could not be validated; no forecast displayed.')
else:st.warning('Official multi-day forecast unavailable.')

st.subheader('Next 24-hour regional conditions')
if '24-hour forecast' in data:
    period=extract_24h(data['24-hour forecast'])
    if not period.empty:st.dataframe(period,hide_index=True,use_container_width=True)
    else:st.info('24-hour feed available but no valid regional periods found.')
else:st.info('24-hour regional forecast unavailable.')

st.subheader('Haze and event decision notes')
st.info('**Official 72-hour PSI / PM2.5 numerical forecast: unavailable in this application.** Historical trend lines are observations, not future predictions. Review haze.gov.sg and ASMC for published advisories, winds and hotspot outlooks.')
st.markdown('**Event controller checklist:** Confirm lightning/rain radar and heat stress independently; review event-hour air quality; record latest official advice; consult medical and safety leads; log any decision to continue, modify, suspend or cancel.')
with st.expander('Data quality and methodology'):
    st.write('Sources: official data.gov.sg v2 real-time API; timestamps converted to SGT; numeric range validation; per-region latest reading; SQLite timestamp deduplication; cached requests with retries. Observations older than 90 minutes are flagged as stale for the advisory. The PM2.5 56 µg/m³ alert is a configurable illustrative screening trigger, not an NEA cancellation threshold.')
    st.write('SQLite storage on ephemeral hosting may be lost on redeploy or restart. For durable 24/7 logging use persistent database storage and a scheduled collector.')
st.caption(f'Dashboard rendered: {now().strftime("%d %b %Y %H:%M:%S SGT")}. Readings have separate observation timestamps.')
