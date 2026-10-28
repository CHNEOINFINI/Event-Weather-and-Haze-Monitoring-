"""Run every 15 minutes using cron or an external scheduler."""
from backend import fetch,normalize_air,save,now
for kind,endpoint in [('PSI','psi'),('PM2.5','pm25')]:
    try:
        df=normalize_air(fetch(endpoint),kind)
        save(df)
        print(now().isoformat(),kind,len(df),'saved')
    except Exception as exc:
        print(now().isoformat(),kind,'ERROR',exc)
