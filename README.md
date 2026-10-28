# Singapore 72-hour Weather & Haze Operations Dashboard

Streamlit dashboard + server-side NEA API client + local SQLite historical observations.

## Run locally

Install Python 3.10 or newer. In a terminal:

```bash
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Open the local URL shown by Streamlit, typically http://localhost:8501.

## Deploy on Streamlit Community Cloud

1. Put `app.py`, `backend.py`, `collector.py`, `requirements.txt` in a GitHub repository.
2. In https://share.streamlit.io/ choose **Create app**, select the repository and `app.py`.
3. Optionally add `DATA_GOV_SG_API_KEY` in Streamlit app **Secrets** for improved rate limits. Do **not** commit a key to GitHub.
4. Deploy. Requests are made server-side, avoiding browser CORS restrictions.
5. In the dashboard click **Backfill last 3 days** to populate the SQLite observation history (subject to API availability and pagination limits).

**Hosting caveat:** Streamlit Community Cloud local SQLite storage is not durable. Use a persistent PostgreSQL database (requires adapting `connect()`), or another hosted database, and schedule `python collector.py` every 15 minutes on a continuously running server for permanent monitoring. The dashboard itself does not collect when asleep.

## API endpoints

- PSI: `https://api-open.data.gov.sg/v2/real-time/api/psi`
- 1-hour PM2.5: `https://api-open.data.gov.sg/v2/real-time/api/pm25`
- 4-day weather: `https://api-open.data.gov.sg/v2/real-time/api/four-day-outlook`
- 24-hour weather: `https://api-open.data.gov.sg/v2/real-time/api/twenty-four-hr-forecast`

Official API docs: https://developers.data.gov.sg/datasets?formats=API

## Limitations and safety

- **No official numerical 72-hour haze forecast** is generated or invented. A daily four-day weather forecast provides the multi-day outlook, not hourly precision.
- The PSI and PM2.5 feeds can update at different times; source observation timestamps are shown.
- Alerts are illustrative internal screening prompts, **not** official event suspension/cancellation decisions. Consult SportSG, NEA, medical team, lightning and severe-weather warnings.
- Lightning monitoring, automated notifications, event-specific location and durable cloud history are future enhancements, **not implemented**.
- Backfill is limited to 12 pages per day per metric to avoid unbounded API calls; data may be incomplete if pagination exceeds this limit.

## Troubleshooting

- `429`: add an API key or lower request frequency.
- `401/403`: check API key validity and hosting network.
- No chart: click **Backfill last 3 days**, check API errors, and verify timestamps.
- Missing forecast: check the API endpoint directly and confirm the latest schema.
- To test locally: `python -m unittest discover -s tests -v`.
