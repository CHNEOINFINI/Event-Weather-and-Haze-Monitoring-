"""Server-side NEA data.gov.sg client, validation and SQLite observation archive."""
import os, time, sqlite3, threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
import requests
import pandas as pd

SGT=ZoneInfo('Asia/Singapore')
BASE='https://api-open.data.gov.sg/v2/real-time/api'
REGIONS=['north','south','east','west','central']
ENDPOINTS={'PSI':'psi','PM2.5':'pm25','4-day forecast':'four-day-outlook','24-hour forecast':'twenty-four-hr-forecast'}
DB=Path(os.getenv('SG_HAZE_DB','observations.sqlite3'))
_RATE_LOCK=threading.Lock()
_LAST_REQUEST=[0.0]

def now(): return datetime.now(SGT)
def get_api_key(): return os.getenv('DATA_GOV_SG_API_KEY','').strip()

def fetch(endpoint,params=None):
    headers={'Accept':'application/json','User-Agent':'SG-Weather-Haze-Operations-Dashboard/1.0'}
    if get_api_key(): headers['x-api-key']=get_api_key()
    last=None
    for attempt in range(3):
        try:
            with _RATE_LOCK:
                wait=max(0.0, 2.0-(time.monotonic()-_LAST_REQUEST[0]))
                if wait: time.sleep(wait)
                _LAST_REQUEST[0]=time.monotonic()
            r=requests.get(f'{BASE}/{endpoint}',params=params,headers=headers,timeout=18)
            if r.status_code in (429,500,502,503,504) and attempt<2:
                time.sleep(min(30, float(r.headers.get('Retry-After','0') or 0) or (3*(2**attempt)))); continue
            r.raise_for_status()
            obj=r.json()
            if not isinstance(obj,dict) or not isinstance(obj.get('data'),dict):
                raise ValueError('Unexpected API envelope (missing data object)')
            if obj.get('code') not in (None,0):
                raise ValueError(f"API code {obj.get('code')}: {obj.get('errorMsg')}")
            return obj['data']
        except (requests.RequestException,ValueError) as exc:
            last=exc
            if attempt<2: time.sleep(0.6)
    raise RuntimeError(f'{endpoint}: {last}')

def items(data):
    val=data.get('items',[])
    return val if isinstance(val,list) else []

def parse_time(value):
    if not value:return None
    try:
        dt=pd.to_datetime(value,utc=True)
        return dt.tz_convert(SGT).to_pydatetime()
    except Exception:return None

def normalize_air(data,kind):
    output=[]
    key='psi_twenty_four_hourly' if kind=='PSI' else 'pm25_one_hourly'
    for item in items(data):
        ts=parse_time(item.get('timestamp') or item.get('updatedTimestamp') or item.get('date'))
        if ts is None:continue
        reading=item.get('readings') or {}
        vals=reading.get(key)
        if not isinstance(vals,dict):continue
        for region in REGIONS:
            val=vals.get(region)
            if isinstance(val,bool) or not isinstance(val,(int,float)) or not 0<=val<=2000:continue
            output.append({'timestamp':ts,'metric':kind,'region':region,'value':float(val)})
    return pd.DataFrame(output,columns=['timestamp','metric','region','value'])

def latest_air(df):
    if df.empty:return pd.DataFrame(columns=['region','value','timestamp'])
    return df.sort_values('timestamp').drop_duplicates('region',keep='last').sort_values('region')

def extract_forecasts(data):
    result=[]
    for item in items(data):
        for f in item.get('forecasts',[]) or []:
            if not isinstance(f,dict):continue
            date=f.get('date')
            if not date:continue
            temp=f.get('temperature') or {}
            humid=f.get('relativeHumidity') or f.get('relative_humidity') or {}
            wind=f.get('wind') or {}
            result.append({'date':str(date)[:10], 'forecast':f.get('forecast') or f.get('text') or 'Unavailable',
                           'temp_low':temp.get('low'), 'temp_high':temp.get('high'),
                           'humidity_low':humid.get('low'),'humidity_high':humid.get('high'),
                           'wind':wind.get('direction','') if isinstance(wind,dict) else '',
                           'issued':item.get('updatedTimestamp') or item.get('timestamp')})
    return pd.DataFrame(result).drop_duplicates('date',keep='last') if result else pd.DataFrame()

def extract_24h(data):
    result=[]
    for item in items(data):
        for p in item.get('periods',[]) or []:
            region=(p.get('regions') or {})
            obj={'start':(p.get('timePeriod') or {}).get('start'), 'end':(p.get('timePeriod') or {}).get('end')}
            for r in REGIONS:
                v=region.get(r)
                obj[r]=v.get('text','') if isinstance(v,dict) else str(v or '')
            result.append(obj)
    return pd.DataFrame(result)

def connect():
    DB.parent.mkdir(parents=True,exist_ok=True)
    conn=sqlite3.connect(DB,timeout=20)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('CREATE TABLE IF NOT EXISTS observations (metric TEXT NOT NULL, region TEXT NOT NULL, timestamp TEXT NOT NULL, value REAL NOT NULL, collected_at TEXT NOT NULL, PRIMARY KEY(metric,region,timestamp))')
    return conn

def save(df):
    if df.empty:return
    with connect() as con:
        con.executemany('INSERT OR REPLACE INTO observations VALUES (?,?,?,?,?)',[(r.metric,r.region,r.timestamp.isoformat(),float(r.value),now().isoformat()) for r in df.itertuples()])

def history(hours=72):
    cutoff=(now()-timedelta(hours=hours)).isoformat()
    with connect() as con:
        cursor=con.execute('SELECT metric,region,timestamp,value FROM observations WHERE timestamp>=? ORDER BY timestamp', (cutoff,))
        df=pd.DataFrame.from_records(cursor.fetchall(), columns=['metric','region','timestamp','value'])
    if not df.empty:df['timestamp']=pd.to_datetime(df['timestamp'],utc=True).dt.tz_convert(SGT)
    return df

def backfill(kind,days=3):
    endpoint=ENDPOINTS[kind]; frames=[]; errors=[]
    for offset in range(days):
        date=(now()-timedelta(days=offset)).date().isoformat()
        try:
            data=fetch(endpoint,{'date':date})
            for _ in range(12):
                frames.append(normalize_air(data,kind))
                token=data.get('paginationToken')
                if not token:break
                data=fetch(endpoint,{'date':date,'paginationToken':token})
        except Exception as exc:errors.append(f'{date}: {exc}')
    frame=pd.concat(frames,ignore_index=True) if frames else pd.DataFrame(columns=['timestamp','metric','region','value'])
    save(frame)
    return len(frame),errors

def assess(psi,pm,age_minutes):
    """Advisory flags only; not an official event cancellation protocol."""
    if age_minutes is None or age_minutes>90:return 'DATA UNAVAILABLE / STALE','Do not treat missing or stale readings as safe. Check official sources manually.'
    if psi is None or pm is None:return 'INCOMPLETE DATA','One or more air-quality feeds are unavailable; check official sources.'
    if psi>200:return 'CRITICAL REVIEW','Very unhealthy PSI. Escalate immediately and apply your approved sport-specific protocol.'
    if psi>100:return 'ELEVATED RISK','Unhealthy PSI. Review exertion, vulnerable groups, medical advice and event modification.'
    if pm>=56:return 'PM2.5 ELEVATED','High 1-hour PM2.5 observation; review immediate exposure and official health advice.'
    return 'ROUTINE MONITORING','No air-quality escalation from these illustrative rules. Weather and lightning still require independent checks.'
