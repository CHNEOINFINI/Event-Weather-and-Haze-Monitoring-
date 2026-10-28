
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
import streamlit as st
import plotly.graph_objects as go
from PIL import Image
from io import BytesIO

API = "https://api-open.data.gov.sg/v2/real-time/api"
SGT = ZoneInfo("Asia/Singapore")

VENUES = {
    "F1 Pit Building": (1.2914, 103.8639),
    "Padang / Connaught Drive": (1.2898, 103.8534),
    "East Coast Park": (1.3008, 103.9122),
    "Punggol Digital District": (1.4055, 103.9118),
    "Singapore Sports Hub": (1.3040, 103.8748),
    "Bayfront Event Space": (1.2838, 103.8591),
    "Marina Promontory": (1.2802, 103.8543),
    "Marina Barrage": (1.2806, 103.8705),
}

@st.cache_data(ttl=300, show_spinner=False)
def get_radar_metadata(radar_range, day):
    url = f"{API}/weather-radar-images/{radar_range}"
    response = requests.get(
        url,
        params={"date": day},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise ValueError(payload.get("errorMsg", "Radar API error"))
    return payload["data"]

@st.cache_data(ttl=240, show_spinner=False)
def download_radar_image(url):
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    return Image.open(BytesIO(response.content)).convert("RGBA")

def load_frames(radar_range, minutes=60):
    now = datetime.now(SGT)
    cutoff = now - timedelta(minutes=minutes)
    frames = []
    boundary = None

    # Include yesterday if the playback window crosses midnight.
    days = sorted({
        now.date().isoformat(),
        cutoff.date().isoformat()
    })

    for day in days:
        try:
            data = get_radar_metadata(radar_range, day)
            boundary = data.get("boundaryBox", boundary)

            for record in data.get("records", []):
                ts = datetime.fromisoformat(record["timestamp"])
                if ts >= cutoff and ts <= now:
                    frames.append(record)
        except Exception as exc:
            st.warning(f"Radar metadata unavailable for {day}: {exc}")

    frames.sort(key=lambda x: x["timestamp"])

    # Avoid duplicates.
    unique = {f["timestamp"]: f for f in frames}
    return list(unique.values()), boundary

def draw_radar(image, boundary, venue, radius_km):
    lat, lon = VENUES[venue]

    ul = boundary["upperLeft"]
    lr = boundary["lowerRight"]

    west = ul["longitude"]
    east = lr["longitude"]
    north = ul["latitude"]
    south = lr["latitude"]

    fig = go.Figure()

    fig.add_layout_image(
        dict(
            source=image,
            xref="x",
            yref="y",
            x=west,
            y=north,
            sizex=east-west,
            sizey=north-south,
            sizing="stretch",
            layer="below",
        )
    )

    fig.add_trace(go.Scatter(
        x=[lon],
        y=[lat],
        mode="markers+text",
        marker=dict(size=14, color="red", symbol="circle"),
        text=[venue],
        textposition="top center",
        name="Event venue",
    ))

    # Approximate radius circle for visual screening only.
    import math
    xs, ys = [], []
    for degree in range(0, 361, 5):
        angle = math.radians(degree)
        dlat = radius_km / 111.32
        dlon = radius_km / (
            111.32 * math.cos(math.radians(lat))
        )
        ys.append(lat + dlat * math.sin(angle))
        xs.append(lon + dlon * math.cos(angle))

    fig.add_trace(go.Scatter(
        x=xs,
        y=ys,
        mode="lines",
        line=dict(color="red", width=2, dash="dash"),
        name=f"{radius_km} km radius",
    ))

    fig.update_layout(
        height=600,
        margin=dict(l=0, r=0, t=10, b=0),
        xaxis=dict(range=[west, east], visible=False),
        yaxis=dict(
            range=[south, north],
            visible=False,
            scaleanchor="x",
        ),
        showlegend=True,
    )
    return fig

def render_rain_radar():
    st.header("Singapore Animated Rain Radar")
    st.caption("Official NEA radar observations — not a rainfall forecast")

    col1, col2, col3 = st.columns(3)

    with col1:
        venue = st.selectbox(
            "Event venue",
            list(VENUES.keys()),
            key="radar_venue"
        )
    with col2:
        radar_range = st.selectbox(
            "Radar coverage",
            ["70km", "240km", "480km"],
            key="radar_range"
        )
    with col3:
        radius = st.selectbox(
            "Venue monitoring radius",
            [2, 5, 6, 10, 20],
            index=1,
            key="radar_radius"
        )

    with st.spinner("Loading NEA radar frames..."):
        frames, boundary = load_frames(radar_range)

    if not frames or not boundary:
        st.error("No recent radar frames available.")
        st.info("Check the official NEA radar dataset or try again later.")
        return

    index = st.slider(
        "Radar playback timeline",
        min_value=0,
        max_value=len(frames)-1,
        value=len(frames)-1,
        key="radar_frame_index",
    )

    selected = frames[index]
    timestamp = selected["timestamp"]

    st.write(f"Radar observation: **{timestamp}**")

    try:
        image = download_radar_image(selected["image"]["url"])
        fig = draw_radar(image, boundary, venue, radius)
        st.plotly_chart(fig, use_container_width=True)
    except Exception as exc:
        st.error(f"Unable to display radar image: {exc}")

    st.info(
        "Use the timeline to compare recent radar frames. "
        "Radar echoes indicate precipitation, but do not "
        "guarantee rain at ground level."
    )

    if st.button("Refresh radar data"):
        get_radar_metadata.clear()
        download_radar_image.clear()
        st.rerun()
