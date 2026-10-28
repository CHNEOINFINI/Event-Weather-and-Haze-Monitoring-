# Singapore Weather, Haze & Venue Monitoring v2

## Deploy to Streamlit Community Cloud

1. Extract this ZIP and upload its files to the **root** of your existing GitHub dashboard repository, replacing `app.py`, `backend.py`, `collector.py`, and `requirements.txt`, and adding `venue.py`, `venue_ui.py`, and `tests/`.
2. In Streamlit Community Cloud, keep `app.py` as the entry point. The app will redeploy after your GitHub commit.
3. Use **Venue & route proximity monitoring** below the regional air-quality summary. Choose an event venue, enable **Marina Bay Cluster**, or upload a `.kml`/`.kmz` route.
4. Click **Refresh venue observations** to clear the five-minute API cache.
5. Check official warnings independently before any operational decision.

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Windows activation: `.venv\\Scripts\\activate`.

Optional: set `DATA_GOV_SG_API_KEY` environment variable if required for your usage tier. Optional `SG_HAZE_DB` sets SQLite location.

## Sources

Official data.gov.sg v2 real-time endpoints: `psi`, `pm25`, `four-day-outlook`, `twenty-four-hr-forecast`, `rainfall`, `lightning`, `wind-direction`, `wind-speed`, `two-hr-forecast`.

## Critical limitations

- Venue coordinates are approximate planning reference points. In particular Bayfront Event Space is an approximate marker, not a surveyed boundary. Override the coordinates for exact event footprint.
- Regional PSI/PM2.5 cannot resolve conditions at a particular venue.
- Rainfall is reported at stations, not at every venue; nearest-station distance is displayed.
- Lightning feed parsing accepts location-based observations only. If the feed's schema changes, the dashboard reports unverified readings rather than inventing lightning positions. No nearby strikes does not prove the site is safe.
- A KML/KMZ route is sampled for performance. Proximity is computed to route sample points; narrow-route exactness depends on sample density.
- The current app does not include a guaranteed 24/7 collector, durable hosted database, official warning integration, or push alerts. SQLite on Streamlit Community Cloud may reset. `collector.py` can be scheduled externally.
- The 72-hour weather outlook is a daily forecast, not hourly site-specific prediction. No 72-hour numeric haze or lightning forecast is fabricated.
- Monitoring radius and last-30-minute strike screening are advisory defaults only. Follow your approved lightning protocol, official warnings and event safety plan.

## Tests

`python -m pytest -q` (pytest must be installed in development environment).
