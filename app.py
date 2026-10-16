"""
Bhoonidhi Disaster Data Downloader & GEE Verification Portal
============================================================
Interactive Streamlit portal for searching, verifying, and downloading
ISRO & Sentinel satellite data via the Bhoonidhi STAC API.

Features:
  - Disaster-optimized sensor prioritization (SAR / Radar over Optical)
  - Interactive Google Earth Engine (ee.Image) accessibility verification
  - Multi-language code generator (GEE Python, GEE JS, QGIS, CLI)
  - Robust exception handling across Bhoonidhi authentication, search, and downloads

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import io
import json
import math
import os
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import folium
from folium.plugins import Draw
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

import bhoonidhi_client as client
from bhoonidhi_client import (
    BhoonidhiError,
    BhoonidhiAuthError,
    BhoonidhiTimeoutError,
    BhoonidhiRateLimitError,
    BhoonidhiDateRangeError,
    BhoonidhiGatewayError,
    BhoonidhiNetworkError,
    BhoonidhiDownloadError,
)
import gee_verifier as gee

# ─────────────────────────────────────────────────────────────────────────────
# Page configuration
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ISRO Bhoonidhi & GEE Disaster STAC Portal",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded",
)

CARTO_KEY = "cb1_4cqs_1_dfe3ef9649fa8d565f2002de"

# ─────────────────────────────────────────────────────────────────────────────
# Custom CSS — Clean Modern Aerospace Design System
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ─── Typography & Base Layout ─── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

code, kbd, samp, pre, .mono-font {
    font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Consolas, monospace !important;
}

.block-container {
    padding-top: 1.2rem !important;
    padding-bottom: 2.5rem !important;
    max-width: 96% !important;
}

/* ─── Modern Scrollbar ─── */
::-webkit-scrollbar {
    width: 6px;
    height: 6px;
}
::-webkit-scrollbar-track {
    background: #0b1329;
}
::-webkit-scrollbar-thumb {
    background: #1e293b;
    border-radius: 4px;
}
::-webkit-scrollbar-thumb:hover {
    background: #334155;
}

/* ─── Sidebar Styling ─── */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #080e1e 0%, #0d1527 100%) !important;
    border-right: 1px solid rgba(255, 255, 255, 0.08) !important;
}

[data-testid="stSidebar"] .block-container {
    padding: 1.2rem 1rem !important;
}

.sidebar-title {
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: #38bdf8;
    margin: 16px 0 8px 0;
    display: flex;
    align-items: center;
    gap: 6px;
}

hr {
    border: none !important;
    height: 1px !important;
    background: rgba(255, 255, 255, 0.08) !important;
    margin: 14px 0 !important;
}

/* ─── Brand Crest ─── */
.brand-box {
    background: linear-gradient(135deg, rgba(2, 132, 199, 0.15) 0%, rgba(37, 99, 235, 0.08) 100%);
    border: 1px solid rgba(56, 189, 248, 0.25);
    border-radius: 12px;
    padding: 14px 16px;
    text-align: center;
    margin-bottom: 14px;
}
.brand-icon {
    font-size: 1.8rem;
    line-height: 1;
    margin-bottom: 4px;
}
.brand-title {
    font-size: 1.15rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    color: #f8fafc;
    margin: 0;
}
.brand-sub {
    font-size: 0.72rem;
    color: #94a3b8;
    margin-top: 3px;
    font-weight: 500;
}
.brand-badge {
    display: inline-block;
    background: rgba(14, 165, 233, 0.18);
    color: #38bdf8;
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    padding: 2px 8px;
    border-radius: 20px;
    margin-top: 6px;
    border: 1px solid rgba(56, 189, 248, 0.3);
}

/* ─── Auth Badge Card ─── */
.auth-card {
    background: rgba(16, 27, 56, 0.7);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 10px;
    padding: 10px 12px;
    margin-bottom: 8px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.auth-card-text {
    font-size: 0.82rem;
    font-weight: 600;
}
.auth-ok {
    color: #10b981;
}
.auth-err {
    color: #f43f5e;
}
.auth-wait {
    color: #94a3b8;
}

/* ─── Disaster Advisor Card ─── */
.disaster-advisor-card {
    background: linear-gradient(135deg, rgba(14, 165, 233, 0.12) 0%, rgba(15, 23, 42, 0.85) 100%);
    border: 1px solid rgba(56, 189, 248, 0.3);
    border-radius: 10px;
    padding: 12px 14px;
    margin: 8px 0 14px 0;
}
.disaster-advisor-title {
    font-size: 0.80rem;
    font-weight: 700;
    color: #38bdf8;
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 6px;
}
.disaster-advisor-body {
    font-size: 0.72rem;
    color: #cbd5e1;
    line-height: 1.45;
}

/* ─── Query Feasibility & Suggestion Card ─── */
.feasibility-card {
    background: rgba(13, 22, 47, 0.85);
    border-radius: 10px;
    padding: 12px 14px;
    margin: 8px 0 14px 0;
    backdrop-filter: blur(8px);
    transition: all 0.25s ease;
}
.feasibility-optimal {
    border: 1px solid rgba(16, 185, 129, 0.45);
    background: linear-gradient(135deg, rgba(16, 185, 129, 0.12) 0%, rgba(13, 22, 47, 0.9) 100%);
    box-shadow: 0 2px 12px rgba(16, 185, 129, 0.12);
}
.feasibility-moderate {
    border: 1px solid rgba(234, 179, 8, 0.45);
    background: linear-gradient(135deg, rgba(234, 179, 8, 0.12) 0%, rgba(13, 22, 47, 0.9) 100%);
    box-shadow: 0 2px 12px rgba(234, 179, 8, 0.10);
}
.feasibility-risky {
    border: 1px solid rgba(249, 115, 22, 0.55);
    background: linear-gradient(135deg, rgba(249, 115, 22, 0.16) 0%, rgba(13, 22, 47, 0.9) 100%);
    box-shadow: 0 2px 14px rgba(249, 115, 22, 0.18);
}
.feasibility-blocked {
    border: 1px solid rgba(244, 63, 94, 0.45);
    background: linear-gradient(135deg, rgba(244, 63, 94, 0.12) 0%, rgba(13, 22, 47, 0.9) 100%);
    box-shadow: 0 2px 12px rgba(244, 63, 94, 0.12);
}
.feasibility-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 6px;
    padding-bottom: 6px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}
.feasibility-badge {
    font-size: 0.74rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
}
.feasibility-meta {
    font-size: 0.69rem;
    color: #94a3b8;
    font-weight: 600;
    background: rgba(0, 0, 0, 0.25);
    padding: 2px 6px;
    border-radius: 4px;
}
.feasibility-title {
    font-size: 0.82rem;
    font-weight: 700;
    color: #f8fafc;
    margin-bottom: 5px;
}
.feasibility-tips {
    font-size: 0.73rem;
    color: #cbd5e1;
    line-height: 1.45;
}
.feasibility-tips ul {
    margin: 0;
    padding-left: 14px;
}
.feasibility-tips li {
    margin-bottom: 3px;
}

/* ─── Hero Header ─── */
.geo-hero {
    background: linear-gradient(135deg, #0f1c3d 0%, #0d152c 100%);
    border: 1px solid rgba(56, 189, 248, 0.22);
    border-radius: 14px;
    padding: 18px 24px;
    margin-bottom: 18px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 14px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
}
.geo-hero-left h1 {
    font-size: 1.55rem;
    font-weight: 800;
    color: #ffffff;
    margin: 0;
    letter-spacing: -0.01em;
}
.geo-hero-left p {
    font-size: 0.86rem;
    color: #94a3b8;
    margin: 4px 0 0 0;
}
.geo-hero-chips {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
}
.geo-chip {
    background: rgba(11, 19, 41, 0.8);
    border: 1px solid rgba(255, 255, 255, 0.12);
    color: #cbd5e1;
    font-size: 0.76rem;
    font-weight: 500;
    padding: 5px 12px;
    border-radius: 8px;
    display: flex;
    align-items: center;
    gap: 6px;
}
.geo-chip b {
    color: #38bdf8;
}

/* ─── Segmented Tabs ─── */
.stTabs [data-baseweb="tab-list"] {
    background: #0f1c3d;
    border-radius: 10px;
    padding: 4px;
    gap: 4px;
    border: 1px solid rgba(255, 255, 255, 0.08);
    width: fit-content;
    margin-bottom: 16px;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px !important;
    padding: 8px 22px !important;
    font-weight: 600 !important;
    font-size: 0.88rem !important;
    color: #94a3b8 !important;
    background: transparent !important;
    border: none !important;
    transition: all 0.2s ease;
}
.stTabs [data-baseweb="tab"]:hover {
    color: #f1f5f9 !important;
    background: rgba(255, 255, 255, 0.05) !important;
}
.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, #0284c7 0%, #2563eb 100%) !important;
    color: #ffffff !important;
    box-shadow: 0 2px 10px rgba(2, 132, 199, 0.4) !important;
}
.stTabs [data-baseweb="tab-highlight"],
.stTabs [data-baseweb="tab-border"] {
    display: none !important;
}

/* ─── Metric Cards ─── */
[data-testid="stMetric"] {
    background: #0f1c3d !important;
    border-radius: 12px !important;
    padding: 14px 18px !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.2) !important;
    transition: transform 0.2s ease, border-color 0.2s ease;
}
[data-testid="stMetric"]:hover {
    border-color: rgba(56, 189, 248, 0.3) !important;
    transform: translateY(-2px);
}
[data-testid="stMetricLabel"] {
    color: #94a3b8 !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
}
[data-testid="stMetricValue"] {
    color: #ffffff !important;
    font-size: 1.55rem !important;
    font-weight: 700 !important;
}

/* ─── Primary / Secondary Buttons ─── */
.stButton > button[kind="primary"],
[data-testid="stSidebar"] .stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #0284c7 0%, #2563eb 100%) !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    box-shadow: 0 3px 12px rgba(2, 132, 199, 0.35) !important;
    transition: all 0.2s ease !important;
}
.stButton > button[kind="primary"]:hover,
[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {
    background: linear-gradient(135deg, #0ea5e9 0%, #3b82f6 100%) !important;
    box-shadow: 0 4px 16px rgba(2, 132, 199, 0.5) !important;
    transform: translateY(-1px);
}

.stDownloadButton > button {
    background: #14203b !important;
    color: #cbd5e1 !important;
    border: 1px solid rgba(255, 255, 255, 0.12) !important;
    border-radius: 8px !important;
    font-weight: 500 !important;
    transition: all 0.2s ease !important;
}
.stDownloadButton > button:hover {
    background: #1e2e54 !important;
    color: #ffffff !important;
    border-color: #38bdf8 !important;
}

/* ─── Custom Telemetry & Verification Cards ─── */
.geo-panel {
    background: #0f1c3d;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
    padding: 16px 18px;
    margin-bottom: 12px;
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.2);
}
.geo-panel-title {
    font-size: 0.80rem;
    font-weight: 700;
    color: #38bdf8;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 12px;
    display: flex;
    align-items: center;
    gap: 8px;
}
.coord-grid-2x2 {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 8px;
}
.coord-cell {
    background: rgba(11, 19, 41, 0.6);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 8px;
    padding: 8px 12px;
}
.coord-cell-label {
    font-size: 0.70rem;
    color: #94a3b8;
    font-weight: 600;
    text-transform: uppercase;
}
.coord-cell-value {
    font-size: 0.95rem;
    color: #f1f5f9;
    font-family: 'JetBrains Mono', monospace;
    font-weight: 600;
    margin-top: 2px;
}

/* ─── Verification Workflow Styling ─── */
.verify-card {
    background: linear-gradient(135deg, #0b152d 0%, #0d1a38 100%);
    border: 1px solid rgba(56, 189, 248, 0.3);
    border-radius: 12px;
    padding: 16px 20px;
    margin-top: 14px;
    margin-bottom: 14px;
}
.verify-step {
    padding: 8px 12px;
    margin-bottom: 8px;
    border-radius: 8px;
    background: rgba(15, 28, 61, 0.6);
    border-left: 4px solid #38bdf8;
    font-size: 0.80rem;
}
.verify-step-pass {
    border-left-color: #10b981;
}
.verify-step-warn {
    border-left-color: #f59e0b;
}
.verify-step-info {
    border-left-color: #38bdf8;
}

/* ─── Footer ─── */
.footer-bar {
    background: #0f1c3d;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
    padding: 12px 20px;
    color: #94a3b8 !important;
    font-size: 0.80rem;
    margin-top: 28px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 10px;
}
.footer-bar a {
    color: #38bdf8 !important;
    text-decoration: none;
    font-weight: 500;
}
.footer-bar a:hover {
    text-decoration: underline;
}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Collections & Disaster Presets (Radar/SAR Prioritized)
# ─────────────────────────────────────────────────────────────────────────────
SATELLITE_COLLECTIONS: dict[str, list[str]] = {
    "Sentinel-1A (Radar SAR)": [
        "Sentinel-1A_SAR-IW_GRD",  # ⭐ Top pick for Disasters / Floods / Landslides
        "Sentinel-1A_SAR-IW_SLC",
    ],
    "EOS-04 (Radar SAR)": [
        "EOS-04_SAR-MRS_L2A",
        "EOS-04_SAR-MRS_L2B",
        "EOS-04_SAR-MRS_SM",
        "EOS-04_SAR-CRS_L2A",
        "EOS-04_SAR-CRS_L2B",
        "EOS-04_SAR-FRS1_L2A",
        "EOS-04_SAR-FRS2_L2A",
        "EOS-04_SAR-MRS_1deg-mosaic",
        "EOS-04_SAR-MRS_WS-1deg-mosaic",
    ],
    "ResourceSat-2 (Optical)": [
        "ResourceSat-2_LISS3_L2",
        "ResourceSat-2_AWIFS_L2",
        "ResourceSat-2_AWIFS_BOA",
        "ResourceSat-2_LISS3_BOA",
        "ResourceSat-2_LISS4-MX70_L2",
    ],
    "ResourceSat-2A (Optical)": [
        "ResourceSat-2A_LISS3_L2",
        "ResourceSat-2A_AWIFS_L2",
        "ResourceSat-2A_AWIFS_BOA",
        "ResourceSat-2A_LISS3_BOA",
        "ResourceSat-2A_LISS4-MX70_L2",
    ],
    "CartoSat-1 (DEM Elevation)": [
        "CartoSat-1_PAN_CartoDEM_30m",
    ],
    "EOS-06 OCM-LAC": [
        "EOS-06_OCM-LAC_L1C",
        "EOS-06_OCM-LAC_L2C-AOD",
        "EOS-06_OCM-LAC_L2C-CHL",
        "EOS-06_OCM-LAC_L2C-DA",
        "EOS-06_OCM-LAC_L2C-NDVI",
        "EOS-06_OCM-LAC_L2C-RRS",
        "EOS-06_OCM-LAC_L2C-TSM",
        "EOS-06_OCM-LAC_NDVI_8day_360m",
        "EOS-06_OCM-LAC_AOD_8day_500m",
        "EOS-06_OCM-LAC_TSM_8day_500m",
    ],
    "EOS-06 OCM-GAC": [
        "EOS-06_OCM-GAC_L1C",
        "EOS-06_OCM-GAC_L2C-AOD",
        "EOS-06_OCM-GAC_L2C-CHL",
        "EOS-06_OCM-GAC_L2C-DA",
        "EOS-06_OCM-GAC_L2C-NDVI",
        "EOS-06_OCM-GAC_L2C-RRS",
        "EOS-06_OCM-GAC_L2C-TSM",
        "EOS-06_OCM-GAC_L2C-VF",
        "EOS-06_OCM-GAC_NDVI_8day_1km",
        "EOS-06_OCM-GAC_AOD_8day_4km",
        "EOS-06_OCM-GAC_Chlorophyll_8day_4km",
        "EOS-06_OCM-GAC_DA_8day_4km",
        "EOS-06_OCM-GAC_TSM_8day_4km",
    ],
    "EOS-06 SCAT": [
        "EOS-06_SCAT_1B",
        "EOS-06_SCAT_2B",
        "EOS-06_SCAT_3SH",
        "EOS-06_SCAT_3SV",
        "EOS-06_SCAT_3WW",
    ],
    "Novasar-1": [
        "Novasar-1_AIS",
    ],
    "NISAR": [
        "NISAR_SSAR_RSLC",
        "NISAR_SSAR_GSLC",
        "NISAR_SSAR_GCOV",
        "NISAR_SSAR_RUNW",
        "NISAR_SSAR_GUNW",
        "NISAR_SSAR_RIFG",
        "NISAR_SSAR_ROFF",
        "NISAR_SSAR_GOFF",
    ],
}

ALL_SATELLITES = list(SATELLITE_COLLECTIONS.keys())

# Quick Disaster Response AOI Presets [min_lon, min_lat, max_lon, max_lat]
DISASTER_PRESETS: dict[str, list[float]] = {
    "🌿 Kerala / Ghats": [75.0, 8.2, 77.5, 12.8],
    "🌊 Assam Floods": [89.7, 24.5, 96.0, 28.0],
    "🌀 Odisha Coast": [83.5, 18.0, 87.5, 21.8],
    "⛰️ Himalayas / UK": [77.5, 28.8, 81.2, 31.5],
    "🇮🇳 Central India": [75.0, 19.5, 82.5, 25.5],
    "🌐 All India": [68.1, 6.7, 97.4, 37.1],
}


# ─────────────────────────────────────────────────────────────────────────────
# Session State Initialization
# ─────────────────────────────────────────────────────────────────────────────
def _init_state() -> None:
    defaults = {
        "auth_status": None,
        "auth_message": "",
        "bbox": None,  # Clean start — no pre-drawn polygon until user draws or selects preset
        "start_date": date.today() - timedelta(days=30),
        "end_date": date.today(),
        "search_results": [],
        "search_ran": False,
        "selected_items": [],
        "inspected_scene_id": None,
        "verification_result": None,
        "download_results": {},
        "downloading": False,
        "map_center": [20.5937, 78.9629],  # Centered on India overview
        "map_zoom": 5,
        "map_key": "fmap_init",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()


def _set_span_callback(days: int) -> None:
    """Callback to update start_date in session state based on current end_date."""
    cur_end = st.session_state.get("end_date") or date.today()
    st.session_state["start_date"] = cur_end - timedelta(days=days)


def calc_approx_area_km2(b: list[float]) -> float:
    """Calculate approximate area in km² for a WGS84 bounding box."""
    min_lon, min_lat, max_lon, max_lat = b
    mid_lat_rad = math.radians((min_lat + max_lat) / 2.0)
    lat_km = (max_lat - min_lat) * 111.0
    lon_km = (max_lon - min_lon) * 111.0 * math.cos(mid_lat_rad)
    return abs(lat_km * lon_km)


def analyze_query_feasibility(
    bbox: list[float] | None,
    start_date: date,
    end_date: date,
    mission: str,
    collection: str,
) -> dict[str, Any]:
    """
    Evaluate query constraints, spatial scale, date span, and dataset profile
    to predict search feasibility, estimated latency, and timeout risks.
    """
    if not bbox:
        return {
            "level": "blocked",
            "badge": "📍 AOI Required",
            "color": "#f43f5e",
            "title": "Area of Interest Not Defined",
            "area_km2": 0,
            "span_days": (end_date - start_date).days if start_date <= end_date else 0,
            "suggestions": [
                "Select a disaster preset (e.g. <b>Kerala / Ghats</b>, <b>Assam Floods</b>) or draw a bounding box (□) on the map."
            ],
            "can_search": False,
        }

    area = calc_approx_area_km2(bbox)
    span_days = (end_date - start_date).days

    if start_date > end_date:
        return {
            "level": "blocked",
            "badge": "❌ Invalid Dates",
            "color": "#f43f5e",
            "title": "Start Date Must Precede End Date",
            "area_km2": area,
            "span_days": span_days,
            "suggestions": ["Ensure Start Date is earlier than or equal to End Date."],
            "can_search": False,
        }

    if span_days > 366:
        return {
            "level": "blocked",
            "badge": "❌ 366-Day Cap Exceeded",
            "color": "#f43f5e",
            "title": f"{span_days} Days Selected (Limit: 366 Days)",
            "area_km2": area,
            "span_days": span_days,
            "suggestions": [
                f"Bhoonidhi API rejects queries > 366 days. Reduce observation window by <b>{span_days - 366} days</b>."
            ],
            "can_search": False,
        }

    suggestions = []
    level = "optimal"
    badge = "🟢 Query Feasible (Fast)"
    color = "#10b981"
    title = "Optimal Parameters — High Chance of Fast Search (~1–3s)"

    is_sentinel = "sentinel" in mission.lower() or "sentinel" in collection.lower()

    if area > 1_500_000 and span_days > 45:
        if is_sentinel:
            level = "risky"
            badge = "🟠 High Timeout Risk"
            color = "#f97316"
            title = "Subcontinental Scale on Global SAR Archive"
            suggestions.append(
                f"Sentinel-1A is a dense dataset. Querying <b>{area:,.0f} km²</b> across <b>{span_days} days</b> may cause server timeouts (502 / ReadTimeout)."
            )
            suggestions.append("💡 <i>Recommendation:</i> Click <b>30 Days</b> or narrow the AOI bounding box.")
        else:
            level = "moderate"
            badge = "🟡 Heavy Query (~5–15s)"
            color = "#eab308"
            title = "Large AOI Scope"
            suggestions.append(f"Subcontinental AOI (<b>{area:,.0f} km²</b>). STAC scan may take 5–15 seconds.")
    elif area > 600_000 or span_days > 120:
        level = "moderate"
        badge = "🟡 Moderate Query Load"
        color = "#eab308"
        title = "Moderate Query Size"
        if is_sentinel and span_days > 60:
            suggestions.append("Sentinel-1A SAR index is dense. If response is slow, consider narrowing the date range.")
        else:
            suggestions.append(f"Scope: <b>{area:,.0f} km²</b> across <b>{span_days} days</b>. Expected response: 2–6s.")
    else:
        suggestions.append(f"✅ Well-targeted AOI (<b>{area:,.0f} km²</b>) and compact date span (<b>{span_days} days</b>).")
        suggestions.append(f"⚡ Fast index lookup on <b>{collection.split('_')[-1]}</b>.")

    return {
        "level": level,
        "badge": badge,
        "color": color,
        "title": title,
        "area_km2": area,
        "span_days": span_days,
        "suggestions": suggestions,
        "can_search": True,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar: Mission Configuration & Disaster Advisor
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div class="brand-box">
        <div class="brand-icon">🛰️</div>
        <div class="brand-title">BHOONIDHI & GEE</div>
        <div class="brand-sub">Disaster Rapid Response & Verification Portal</div>
        <div class="brand-badge">ISRO / NRSC GATEWAY</div>
    </div>
    """, unsafe_allow_html=True)

    # ── Auth Status Section ──────────────────────────────────────────────────
    st.markdown('<div class="sidebar-title">🔐 Gateway Authentication</div>', unsafe_allow_html=True)
    if st.session_state.auth_status == "ok":
        st.markdown("""
        <div class="auth-card">
            <span class="auth-card-text auth-ok">🟢 Authenticated</span>
            <span style="font-size:0.75rem; color:#94a3b8;">Token Active</span>
        </div>
        """, unsafe_allow_html=True)
    elif st.session_state.auth_status == "error":
        st.markdown("""
        <div class="auth-card">
            <span class="auth-card-text auth-err">🔴 Auth Failed</span>
            <span style="font-size:0.75rem; color:#f43f5e;">Action Needed</span>
        </div>
        """, unsafe_allow_html=True)
        with st.expander("Details & resolution", expanded=True):
            st.caption(f"**Error:** {st.session_state.auth_message}")
            if "hyphen" in st.session_state.auth_message.lower() or "-" in os.environ.get("BHOONIDHI_USER_ID", ""):
                st.warning("⚠️ **Important:** Bhoonidhi's API rejects hyphens (`-`) in `userId`. Please verify your exact Bhoonidhi username (e.g. `shyam06`).")
            st.info(
                "💡 **ISRO Bhoonidhi Policy Note:**\n"
                "As confirmed by Bhoonidhi Admin (`bhoonidhi@nrsc.gov.in`), Bhoonidhi STAC API does not require special administrative clearances — it is open for all registered users under Indian Space Policy 2023.\n"
                "Ensure your `.env` contains your active portal username and password."
            )
    else:
        st.markdown("""
        <div class="auth-card">
            <span class="auth-card-text auth-wait">⚪ Ready</span>
            <span style="font-size:0.75rem; color:#94a3b8;">Auto on Search</span>
        </div>
        """, unsafe_allow_html=True)

    if st.button("🔄 Test / Refresh Auth", use_container_width=True, type="secondary"):
        with st.spinner("Connecting to Bhoonidhi STAC…"):
            try:
                client.authenticate()
                st.session_state.auth_status = "ok"
                st.session_state.auth_message = ""
                st.toast("Authenticated with Bhoonidhi Gateway!", icon="✅")
                st.rerun()
            except BhoonidhiAuthError as exc:
                st.session_state.auth_status = "error"
                st.session_state.auth_message = str(exc)
                st.error(f"Authentication Error: {exc.message}")
            except BhoonidhiNetworkError as exc:
                st.session_state.auth_status = "error"
                st.session_state.auth_message = str(exc)
                st.error(f"Network Error: {exc.message}")
            except Exception as exc:
                st.session_state.auth_status = "error"
                st.session_state.auth_message = str(exc)
                st.error(f"Auth failed: {exc}")

    st.markdown("<hr/>", unsafe_allow_html=True)

    # ── Disaster Response Sensor Advisor ──────────────────────────────────────
    st.markdown('<div class="sidebar-title">⚡ Disaster Sensor Advisor</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="disaster-advisor-card">
        <div class="disaster-advisor-title">🛡️ Radar (SAR) Priority Guidance</div>
        <div class="disaster-advisor-body">
            <b>1. Top Pick:</b> <code>Sentinel-1A_SAR-IW_GRD</code> (Radar SAR) — penetrates dense clouds/monsoons, day & night. Floodwaters appear <b>pitch black</b>.<br/>
            <b>2. Alt Radar:</b> <code>EOS-04_SAR-MRS_L2A/B</code> (ISRO Radar SAR).<br/>
            <b>3. High-Res Optical:</b> <code>ResourceSat-2/2A LISS-3</code> — post-disaster damage mapping only under cloud-free skies.
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<hr/>", unsafe_allow_html=True)

    # ── Date Range Section (Balanced 2-Columns) ──────────────────────────────
    st.markdown('<div class="sidebar-title">📅 Observation Window</div>', unsafe_allow_html=True)
    
    col_d1, col_d2 = st.columns(2)

    with col_d1:
        start_date = st.date_input(
            "Start Date",
            min_value=date(2010, 1, 1),
            max_value=date.today(),
            format="YYYY-MM-DD",
            key="start_date",
        )
    with col_d2:
        end_date = st.date_input(
            "End Date",
            min_value=date(2010, 1, 1),
            max_value=date.today(),
            format="YYYY-MM-DD",
            key="end_date",
        )

    # Quick date spans using callbacks
    q1, q2, q3 = st.columns(3)
    q1.button("7 Days", on_click=_set_span_callback, args=(7,), use_container_width=True)
    q2.button("30 Days", on_click=_set_span_callback, args=(30,), use_container_width=True)
    q3.button("90 Days", on_click=_set_span_callback, args=(90,), use_container_width=True)

    st.markdown("<hr/>", unsafe_allow_html=True)

    # ── Satellite & Collection Filter ─────────────────────────────────────────
    st.markdown('<div class="sidebar-title">🛰️ Satellite & Mission Sensor</div>', unsafe_allow_html=True)

    selected_satellite = st.selectbox(
        "Mission / Constellation",
        options=ALL_SATELLITES,
        index=0,  # Sentinel-1A SAR (Top pick for disasters)
        key="satellite_select",
    )

    available_collections = SATELLITE_COLLECTIONS[selected_satellite]

    selected_collection = st.selectbox(
        "Product Collection",
        options=available_collections,
        index=0,  # GRD for Sentinel-1A
        key="collection_select",
    )

    st.markdown("<hr/>", unsafe_allow_html=True)

    # ── Search Parameters ─────────────────────────────────────────────────────
    st.markdown('<div class="sidebar-title">⚙️ Query Constraints</div>', unsafe_allow_html=True)

    online_only = st.checkbox(
        "Online scenes only",
        value=True,
        help="Filters for immediate download products (Online='Y'). Offline products require archive retrieval.",
    )
    result_limit = st.slider("Max Results Limit", min_value=10, max_value=500, value=100, step=10)

    st.markdown("<hr/>", unsafe_allow_html=True)

    # ── Query Feasibility & Pre-Check Suggestion Box ───────────────────────────
    st.markdown('<div class="sidebar-title">💡 Query Feasibility & Pre-Check</div>', unsafe_allow_html=True)

    feasibility = analyze_query_feasibility(
        bbox=st.session_state.bbox,
        start_date=start_date,
        end_date=end_date,
        mission=selected_satellite,
        collection=selected_collection,
    )

    tips_html = "".join(f"<li>{s}</li>" for s in feasibility["suggestions"])
    area_display = f"{feasibility['area_km2']:,.0f} km²" if feasibility["area_km2"] > 0 else "No AOI"

    st.markdown(f"""
    <div class="feasibility-card feasibility-{feasibility['level']}">
        <div class="feasibility-header">
            <span class="feasibility-badge" style="color:{feasibility['color']};">{feasibility['badge']}</span>
            <span class="feasibility-meta">{area_display} • {feasibility['span_days']}d</span>
        </div>
        <div class="feasibility-title">{feasibility['title']}</div>
        <div class="feasibility-tips">
            <ul>
                {tips_html}
            </ul>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Search Action ─────────────────────────────────────────────────────────
    search_clicked = st.button(
        "🔍  Search Satellite Catalog",
        type="primary",
        use_container_width=True,
        disabled=not feasibility["can_search"],
    )

    if not feasibility["can_search"]:
        st.caption("🔒 *Resolve query pre-check items above to enable search.*")
    else:
        st.caption("✅ *Parameters verified. Click to query Bhoonidhi.*")


# ─────────────────────────────────────────────────────────────────────────────
# Main Command Center Header
# ─────────────────────────────────────────────────────────────────────────────
aoi_chip_text = "Defined" if st.session_state.bbox else "Not Set"
aoi_chip_color = "#10b981" if st.session_state.bbox else "#94a3b8"

st.markdown(f"""
<div class="geo-hero">
    <div class="geo-hero-left">
        <h1>🛰️ ISRO Bhoonidhi & GEE Disaster STAC Portal</h1>
        <p>Disaster Rapid Response & Earth Observation Data Downloader & Google Earth Engine Verifier</p>
    </div>
    <div class="geo-hero-chips">
        <div class="geo-chip">🛰️ Mission: <b>{selected_satellite}</b></div>
        <div class="geo-chip">📦 Collection: <b>{selected_collection.split('_')[-1]}</b></div>
        <div class="geo-chip">📅 Span: <b>{start_date} → {end_date}</b></div>
        <div class="geo-chip">📍 AOI: <b style="color:{aoi_chip_color};">{aoi_chip_text}</b></div>
    </div>
</div>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Search Execution Trigger with Robust Error Handling Layer
# ─────────────────────────────────────────────────────────────────────────────
if search_clicked:
    if not st.session_state.bbox:
        st.error("Please define an Area of Interest on the map or select a preset.")
    elif start_date > end_date:
        st.error("Please ensure Start Date is before End Date.")
    elif (end_date - start_date).days > 366:
        st.error("Please ensure the observation window is 366 days or less.")
    else:
        with st.spinner(f"Querying STAC API for {selected_collection}…"):
            try:
                client.get_valid_token()
                st.session_state.auth_status = "ok"
                st.session_state.auth_message = ""

                features = client.search_stac(
                    collections=[selected_collection],
                    start_date=start_date.strftime("%Y-%m-%d"),
                    end_date=end_date.strftime("%Y-%m-%d"),
                    bbox=st.session_state.bbox,
                    limit=result_limit,
                    online_only=online_only,
                )
                st.session_state.search_results = features
                st.session_state.search_ran = True
                st.session_state.selected_items = [f["id"] for f in features]  # default select all
                st.session_state.download_results = {}
                st.session_state.verification_result = None

                if features:
                    st.session_state.inspected_scene_id = features[0]["id"]

                n = len(features)
                if n > 0:
                    st.toast(f"Found {n} scenes!", icon="📦")
                else:
                    st.toast("No scenes matching criteria", icon="⚠️")

            except BhoonidhiDateRangeError as exc:
                st.session_state.auth_status = "error"
                st.session_state.auth_message = str(exc)
                st.error("⚠️ **Observation Window Limit (406)**: Bhoonidhi STAC API restricts queries to a maximum of 366 days. Please reduce your date span.")
            except BhoonidhiTimeoutError as exc:
                st.session_state.auth_status = "error"
                st.session_state.auth_message = str(exc)
                st.error(
                    "⏱️ **Bhoonidhi STAC Request Timed Out**\n\n"
                    f"{exc.message}\n\n"
                    "**Quick Fixes:**\n"
                    "- **Narrow your AOI:** Use the rectangle tool (□) on the map or select a regional preset.\n"
                    "- **Reduce Date Span:** Click **30 Days** in the sidebar.\n"
                    "- **Try ISRO SAR:** Missions like **EOS-04 (Radar SAR)** query within 1–2 seconds."
                )
            except BhoonidhiGatewayError as exc:
                st.session_state.auth_status = "error"
                st.session_state.auth_message = str(exc)
                st.error(
                    "⏱️ **Bhoonidhi Server Gateway Timeout (502 / 504)**\n\n"
                    f"{exc.message}\n\n"
                    "**Tip:** Narrow down your Area of Interest using the map drawing tool or select a regional preset."
                )
            except BhoonidhiRateLimitError as exc:
                st.session_state.auth_status = "error"
                st.session_state.auth_message = str(exc)
                st.error("⚠️ **Rate Limit Exceeded (429)**: Bhoonidhi limits requests to 3 req/sec. Please wait a few seconds.")
            except BhoonidhiAuthError as exc:
                st.session_state.auth_status = "error"
                st.session_state.auth_message = str(exc)
                st.error(f"🔒 **Authentication Failed**: {exc.message}")
            except BhoonidhiNetworkError as exc:
                st.session_state.auth_status = "error"
                st.session_state.auth_message = str(exc)
                st.error(f"🌐 **Network Connectivity Error**: {exc.message}")
            except Exception as exc:
                err = str(exc)
                st.session_state.auth_status = "error"
                st.session_state.auth_message = err
                st.error(f"Search query error: {err}")


# ─────────────────────────────────────────────────────────────────────────────
# Primary Dashboard Tabs
# ─────────────────────────────────────────────────────────────────────────────
tab_map, tab_results, tab_downloads = st.tabs([
    "📍  AOI & Geospatial Map",
    "📦  Search Results & GEE Verifier",
    "⬇️  Download Manager & QGIS Hub",
])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Interactive Map & AOI Definition
# ═══════════════════════════════════════════════════════════════════════════════
with tab_map:
    # ── Preset Toolbar ───────────────────────────────────────────────────────
    st.markdown('<div class="sidebar-title">⚡ Quick Disaster & Regional Presets</div>', unsafe_allow_html=True)
    
    preset_cols = st.columns(len(DISASTER_PRESETS))
    for idx, (p_name, p_bbox) in enumerate(DISASTER_PRESETS.items()):
        with preset_cols[idx]:
            if st.button(p_name, key=f"btn_preset_{idx}", use_container_width=True):
                st.session_state.bbox = p_bbox
                st.session_state.map_center = [
                    (p_bbox[1] + p_bbox[3]) / 2.0,
                    (p_bbox[0] + p_bbox[2]) / 2.0,
                ]
                st.session_state.map_zoom = 7 if p_name == "🌿 Kerala / Ghats" else (6 if p_name != "🌐 All India" else 5)
                st.session_state.map_key = f"fmap_preset_{idx}_{time.time()}"
                st.rerun()

    # ── Map Construction ─────────────────────────────────────────────────────
    m = folium.Map(
        location=st.session_state.map_center,
        zoom_start=st.session_state.map_zoom,
        tiles=None,
    )

    CARTO_ATTR = (
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> '
        'contributors &copy; <a href="https://carto.com/">CARTO</a>'
    )

    # 1. Carto Voyager (Default)
    folium.TileLayer(
        tiles=f"https://basemaps.cartocdn.com/rastertiles/voyager/{{z}}/{{x}}/{{y}}.png?key={CARTO_KEY}",
        attr=CARTO_ATTR,
        name="🗺️ Carto Voyager",
        overlay=False,
        control=True,
        max_zoom=19,
    ).add_to(m)

    # 2. Google Satellite
    folium.TileLayer(
        tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
        attr="Google Satellite",
        name="🛰️ Google Satellite",
        overlay=False,
        control=True,
        max_zoom=21,
    ).add_to(m)

    # 3. Carto Dark
    folium.TileLayer(
        tiles=f"https://basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}.png?key={CARTO_KEY}",
        attr=CARTO_ATTR,
        name="🌑 Carto Dark",
        overlay=False,
        control=True,
        max_zoom=19,
    ).add_to(m)

    # 4. OpenStreetMap
    folium.TileLayer(
        tiles="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        name="🌐 OpenStreetMap",
        overlay=False,
        control=True,
        max_zoom=19,
    ).add_to(m)

    folium.LayerControl(position="topright", collapsed=False).add_to(m)

    # Drawing Tool — Azure Modern Style
    Draw(
        draw_options={
            "rectangle": {
                "shapeOptions": {
                    "color": "#0ea5e9",
                    "weight": 3,
                    "fillColor": "#0ea5e9",
                    "fillOpacity": 0.15,
                }
            },
            "polygon": False,
            "polyline": False,
            "circle": False,
            "circlemarker": False,
            "marker": False,
        },
        edit_options={"edit": False, "remove": False},
        position="topleft",
    ).add_to(m)

    # Render saved bbox on map if present
    if st.session_state.bbox:
        b = st.session_state.bbox
        area_km2 = calc_approx_area_km2(b)
        folium.Rectangle(
            bounds=[[b[1], b[0]], [b[3], b[2]]],
            color="#0ea5e9",
            weight=3,
            fill=True,
            fill_color="#0ea5e9",
            fill_opacity=0.15,
            tooltip=f"Selected AOI ({area_km2:,.0f} km²)",
        ).add_to(m)

    # Render folium map
    map_out = st_folium(
        m,
        width="100%",
        height=520,
        returned_objects=["all_drawings", "last_active_drawing"],
        key=st.session_state.get("map_key", "fmap_init"),
    )

    # Update state if new drawing occurred
    drawings = map_out.get("all_drawings") or []
    last_draw = map_out.get("last_active_drawing")

    draw_target = None
    if last_draw and isinstance(last_draw, dict) and last_draw.get("geometry"):
        draw_target = last_draw.get("geometry")
    elif drawings and isinstance(drawings, list) and len(drawings) > 0:
        draw_target = drawings[-1].get("geometry")

    if draw_target and draw_target.get("type") == "Polygon":
        coords = draw_target["coordinates"][0]
        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        new_bb = [round(min(lons), 4), round(min(lats), 4), round(max(lons), 4), round(max(lats), 4)]
        if new_bb != st.session_state.bbox:
            st.session_state.bbox = new_bb
            st.session_state.map_center = [
                round((min(lats) + max(lats)) / 2.0, 4),
                round((min(lons) + max(lons)) / 2.0, 4),
            ]
            st.session_state.map_zoom = 7
            st.rerun()

    # ── Below-Map Balanced Deck ──────────────────────────────────────────────
    col_telemetry, col_actions = st.columns(2)

    with col_telemetry:
        if st.session_state.bbox:
            b = st.session_state.bbox
            area = calc_approx_area_km2(b)
            st.markdown(f"""
            <div class="geo-panel">
                <div class="geo-panel-title">
                    <span>🌐 Active Geographic Extent (WGS84)</span>
                    <span style="font-size:0.75rem; color:#10b981; margin-left:auto;">● Ready</span>
                </div>
                <div class="coord-grid-2x2">
                    <div class="coord-cell">
                        <div class="coord-cell-label">West (Min Lon)</div>
                        <div class="coord-cell-value">{b[0]:.4f}° E</div>
                    </div>
                    <div class="coord-cell">
                        <div class="coord-cell-label">South (Min Lat)</div>
                        <div class="coord-cell-value">{b[1]:.4f}° N</div>
                    </div>
                    <div class="coord-cell">
                        <div class="coord-cell-label">East (Max Lon)</div>
                        <div class="coord-cell-value">{b[2]:.4f}° E</div>
                    </div>
                    <div class="coord-cell">
                        <div class="coord-cell-label">North (Max Lat)</div>
                        <div class="coord-cell-value">{b[3]:.4f}° N</div>
                    </div>
                </div>
                <div style="margin-top:10px; font-size:0.78rem; color:#94a3b8; display:flex; justify-content:space-between;">
                    <span>Approx. Coverage: <b style="color:#f1f5f9;">{area:,.0f} km²</b></span>
                    <span>Coordinates Span: <b style="color:#38bdf8;">{(b[2]-b[0]):.2f}° × {(b[3]-b[1]):.2f}°</b></span>
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="geo-panel">
                <div class="geo-panel-title">
                    <span>🌐 Geographic Extent (WGS84)</span>
                    <span style="font-size:0.75rem; color:#94a3b8; margin-left:auto;">○ None</span>
                </div>
                <p style="color:#94a3b8; font-size:0.86rem; margin:10px 0;">
                    No Area of Interest selected yet. Use the <b>rectangle tool (□)</b> on the map toolbar, 
                    or click any quick disaster preset button above.
                </p>
            </div>
            """, unsafe_allow_html=True)

    with col_actions:
        st.markdown("""
        <div class="geo-panel">
            <div class="geo-panel-title">
                <span>🛠️ AOI Tools & Manual Entry</span>
            </div>
        """, unsafe_allow_html=True)

        act_c1, act_c2 = st.columns(2)
        with act_c1:
            if st.button("🗑️ Clear Active AOI", use_container_width=True, disabled=st.session_state.bbox is None):
                st.session_state.bbox = None
                st.session_state.map_center = [20.5937, 78.9629]
                st.session_state.map_zoom = 5
                st.session_state.map_key = f"fmap_cleared_{time.time()}"
                st.rerun()

        with act_c2:
            if st.session_state.bbox:
                b = st.session_state.bbox
                bbox_geojson = {
                    "type": "Polygon",
                    "coordinates": [[
                        [b[0], b[1]],
                        [b[2], b[1]],
                        [b[2], b[3]],
                        [b[0], b[3]],
                        [b[0], b[1]],
                    ]],
                }
                st.download_button(
                    "📋 Export GeoJSON",
                    data=json.dumps(bbox_geojson, indent=2),
                    file_name="bhoonidhi_aoi.geojson",
                    mime="application/json",
                    use_container_width=True,
                )
            else:
                st.button("📋 Export GeoJSON", disabled=True, use_container_width=True)

        with st.expander("✏️ Enter Exact Coordinates Manually"):
            cur_b = st.session_state.bbox or [75.0, 8.2, 77.5, 12.8]
            m_c1, m_c2 = st.columns(2)
            with m_c1:
                man_w = st.number_input("West (Min Lon)", value=float(cur_b[0]), format="%.4f")
                man_s = st.number_input("South (Min Lat)", value=float(cur_b[1]), format="%.4f")
            with m_c2:
                man_e = st.number_input("East (Max Lon)", value=float(cur_b[2]), format="%.4f")
                man_n = st.number_input("North (Max Lat)", value=float(cur_b[3]), format="%.4f")

            if st.button("Apply Coordinates", use_container_width=True):
                if man_w < man_e and man_s < man_n:
                    st.session_state.bbox = [round(man_w, 4), round(man_s, 4), round(man_e, 4), round(man_n, 4)]
                    st.session_state.map_center = [(man_s + man_n) / 2.0, (man_w + man_e) / 2.0]
                    st.session_state.map_key = f"fmap_manual_{time.time()}"
                    st.rerun()
                else:
                    st.error("Invalid coordinates: West must be < East and South must be < North.")

        st.markdown("</div>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Search Results Catalog & Interactive GEE Verifier
# ═══════════════════════════════════════════════════════════════════════════════
with tab_results:
    features = st.session_state.search_results

    if not st.session_state.search_ran:
        st.markdown("""
        <div class="geo-panel" style="text-align:center; padding:32px 20px;">
            <div style="font-size:2.2rem; margin-bottom:8px;">🔍</div>
            <h3 style="color:#ffffff; margin:0;">No Query Executed Yet</h3>
            <p style="color:#94a3b8; font-size:0.90rem; max-width:500px; margin:8px auto 16px;">
                Configure your observation parameters in the sidebar, verify your Area of Interest, 
                and hit <b>Search Satellite Catalog</b>.
            </p>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="sidebar-title">Current Query Parameters</div>', unsafe_allow_html=True)
        m_c1, m_c2, m_c3 = st.columns(3)
        m_c1.metric("Mission", selected_satellite)
        m_c2.metric("Collection", selected_collection)
        m_c3.metric("Date Span", f"{start_date} → {end_date}")

    elif not features:
        st.warning(
            "⚠️ **No satellite scenes matched your query criteria.**\n\n"
            "**This could happen for several reasons:**\n\n"
            "1️⃣ **API Access Not Activated (Most Common)**\n"
            "   Your Bhoonidhi portal account works, but API access must be separately activated.\n"
            "   - **Action:** Email `bhoonidhi@nrsc.gov.in` with your user ID (`shyam06`) requesting API access activation.\n"
            "   - Include: 'Request for Bhoonidhi STAC API data access'\n\n"
            "2️⃣ **No data in your specific query window:**\n"
            "   - Expand the observation date range in the sidebar (try 90 days)\n"
            "   - Enlarge your Area of Interest (AOI) on the map\n"
            "   - Try different satellite missions (Sentinel-1, EOS-04, etc.)\n\n"
            "3️⃣ **Online-only filter too strict:**\n"
            "   - Uncheck 'Online scenes only' in the sidebar to include deep archive products\n\n"
            "4️⃣ **Try example regions:**\n"
            "   - Use the disaster preset buttons (Assam Floods, Odisha Coast, etc.) above the map\n"
            "   - These cover known data-rich areas"
        )
    else:
        # Cache file sizes in session state
        if "file_sizes" not in st.session_state:
            st.session_state.file_sizes = {}

        rows = []
        for f in features:
            p = f.get("properties", {})
            cc_raw = p.get("eo:cloud_cover", p.get("Cloud_Cover", 0))
            try:
                cc = float(cc_raw)
            except (ValueError, TypeError):
                cc = 0.0

            size_mb: float | None = None
            raw_size = p.get("file:size") or p.get("FileSize") or p.get("file_size")
            if raw_size:
                try:
                    size_mb = round(int(raw_size) / (1024 * 1024), 1)
                except Exception:
                    pass

            if size_mb is None:
                size_mb = st.session_state.file_sizes.get(f["id"])

            rows.append({
                "Select": f["id"] in st.session_state.selected_items,
                "ID": f["id"],
                "Date": (p.get("datetime") or p.get("start_datetime") or "")[:10],
                "Online": p.get("Online", "?"),
                "Cloud %": round(cc, 1),
                "Size (MB)": size_mb,
                "Collection": f.get("collection", selected_collection),
            })

        df_all = pd.DataFrame(rows)

        online_count = sum(1 for r in rows if r["Online"] == "Y")
        offline_count = len(rows) - online_count
        selected_count = len(st.session_state.selected_items)

        # ── Top KPI Metrics Row ──────────────────────────────────────────────
        kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
        kpi1.metric("Total Scenes Found", len(features))
        kpi2.metric("🟢 Online (Instant)", online_count)
        kpi3.metric("⏳ Offline (Archive)", offline_count)
        kpi4.metric("🎯 Selected", selected_count)

        known_sizes = [r["Size (MB)"] for r in rows if r["Select"] and r["Size (MB)"] is not None]
        unknown_count = sum(1 for r in rows if r["Select"] and r["Size (MB)"] is None)
        if known_sizes:
            total_est = sum(known_sizes)
            size_label = f"~{total_est:.0f} MB"
            if unknown_count:
                size_label += f" + {unknown_count} unknown"
        elif unknown_count:
            size_label = f"{unknown_count} scenes (unknown)"
        else:
            size_label = "—"
        kpi5.metric("💾 Est. Download Size", size_label)

        # ── Fetch missing sizes button ───────────────────────────────────────
        missing_ids = [
            (f["id"], f.get("collection", selected_collection))
            for f in features
            if f["id"] not in st.session_state.file_sizes
            and df_all[df_all["ID"] == f["id"]]["Size (MB)"].values[0] is None
        ]
        if missing_ids:
            if st.button(
                f"📏 Fetch file sizes for {len(missing_ids)} scene(s) *(HEAD requests — fast, no download)*",
                use_container_width=False,
            ):
                with st.spinner(f"Fetching sizes for {len(missing_ids)} scene(s)…"):
                    import concurrent.futures
                    def _head(args):
                        iid, col = args
                        return iid, client.get_file_size_mb(iid, col)
                    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
                        for iid, sz in ex.map(_head, missing_ids):
                            if sz is not None:
                                st.session_state.file_sizes[iid] = sz
                st.rerun()

        st.markdown("<hr/>", unsafe_allow_html=True)

        # ── Filter & Search Toolbar ──────────────────────────────────────────
        f_c1, f_c2, f_c3 = st.columns([2, 1.2, 1.2])

        with f_c1:
            search_query = st.text_input(
                "Filter by Scene ID or Date",
                placeholder="Type to filter...",
                label_visibility="collapsed",
            )
        with f_c2:
            status_filter = st.selectbox(
                "Status Filter",
                options=["All Statuses", "Online Only (🟢)", "Offline Only (⏳)"],
                label_visibility="collapsed",
            )
        with f_c3:
            max_cloud = st.slider(
                "Max Cloud %",
                min_value=0,
                max_value=100,
                value=100,
                step=5,
                help="Hide scenes with cloud cover exceeding this percentage",
            )

        # Apply in-memory filters
        filtered_df = df_all.copy()
        if search_query:
            q = search_query.strip().lower()
            filtered_df = filtered_df[
                filtered_df["ID"].str.lower().str.contains(q) |
                filtered_df["Date"].str.contains(q)
            ]
        if status_filter == "Online Only (🟢)":
            filtered_df = filtered_df[filtered_df["Online"] == "Y"]
        elif status_filter == "Offline Only (⏳)":
            filtered_df = filtered_df[filtered_df["Online"] != "Y"]

        filtered_df = filtered_df[filtered_df["Cloud %"] <= max_cloud]

        # ── Quick Selection Actions ──────────────────────────────────────────
        sel_c1, sel_c2, sel_c3, sel_c4 = st.columns([1, 1, 1, 2])
        with sel_c1:
            if st.button("☑️ Select All Visible", use_container_width=True):
                st.session_state.selected_items = list(set(
                    st.session_state.selected_items + filtered_df["ID"].tolist()
                ))
                st.rerun()
        with sel_c2:
            if st.button("🟢 Select Online Only", use_container_width=True):
                online_ids = filtered_df[filtered_df["Online"] == "Y"]["ID"].tolist()
                st.session_state.selected_items = online_ids
                st.rerun()
        with sel_c3:
            if st.button("✖️ Clear Selection", use_container_width=True):
                st.session_state.selected_items = []
                st.rerun()
        with sel_c4:
            st.caption(f"Showing **{len(filtered_df)}** of **{len(df_all)}** scenes.")

        # Update boolean selection column
        filtered_df["Select"] = filtered_df["ID"].isin(st.session_state.selected_items)

        # ── Interactive Data Editor Table ─────────────────────────────────────
        edited_df = st.data_editor(
            filtered_df,
            column_config={
                "Select": st.column_config.CheckboxColumn("Select", default=True),
                "ID": st.column_config.TextColumn("Product Scene ID", width="large"),
                "Date": st.column_config.TextColumn("Acquisition Date"),
                "Online": st.column_config.TextColumn("Online"),
                "Cloud %": st.column_config.ProgressColumn(
                    "Cloud Cover",
                    min_value=0,
                    max_value=100,
                    format="%d%%",
                ),
                "Size (MB)": st.column_config.NumberColumn(
                    "💾 Size (MB)",
                    help="File size in MB. Bhoonidhi ZIPs are typically 100–800 MB per scene.",
                    format="%.0f MB",
                    min_value=0,
                ),
                "Collection": st.column_config.TextColumn("Collection"),
            },
            disabled=["ID", "Date", "Online", "Cloud %", "Size (MB)", "Collection"],
            hide_index=True,
            use_container_width=True,
            height=320,
            key="catalog_editor",
        )

        # Sync selection from data_editor
        new_selected = edited_df[edited_df["Select"]]["ID"].tolist()
        other_selected = [
            x for x in st.session_state.selected_items
            if x not in filtered_df["ID"].values
        ]
        total_selected = list(set(new_selected + other_selected))
        if set(total_selected) != set(st.session_state.selected_items):
            st.session_state.selected_items = total_selected
            st.rerun()

        st.markdown("<hr/>", unsafe_allow_html=True)

        # ══════════════════════════════════════════════════════════════════════
        # 🔬 INTERACTIVE VERIFICATION WORKFLOW & GEE IMAGE INSPECTOR
        # ══════════════════════════════════════════════════════════════════════
        st.markdown('<div class="sidebar-title">🔬 Interactive Scene Inspection & GEE Verification Workflow</div>', unsafe_allow_html=True)

        available_scene_ids = filtered_df["ID"].tolist() if not filtered_df.empty else [f["id"] for f in features]
        if not available_scene_ids:
            available_scene_ids = [f["id"] for f in features]

        # Determine current inspected scene
        default_inspect_idx = 0
        if st.session_state.inspected_scene_id in available_scene_ids:
            default_inspect_idx = available_scene_ids.index(st.session_state.inspected_scene_id)

        inspect_col1, inspect_col2 = st.columns([3, 1.2])
        with inspect_col1:
            selected_scene_id = st.selectbox(
                "Select Scene from Search Results to Inspect & Verify in Earth Engine (ee.Image):",
                options=available_scene_ids,
                index=default_inspect_idx,
                key="scene_inspector_select",
            )
            st.session_state.inspected_scene_id = selected_scene_id

        # Find full feature object
        current_feature = next((f for f in features if f["id"] == selected_scene_id), features[0])
        asset_info = gee.get_gee_asset_info(current_feature)
        profile = asset_info["profile"]

        with inspect_col2:
            st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)
            run_verify_btn = st.button(
                "🧪  Test GEE Accessibility (`ee.Image`)",
                type="primary",
                use_container_width=True,
                help="Execute verification testing if the Bhoonidhi Product ID is immediately accessible via ee.Image call.",
            )

        # Auto-verify on selection or on button click
        if run_verify_btn or st.session_state.verification_result is None or st.session_state.verification_result.get("item_id") != selected_scene_id:
            with st.spinner("Executing interactive verification pipeline for Product ID…"):
                v_res = gee.run_gee_verification(current_feature, mock_mode=False)
                st.session_state.verification_result = v_res

        v_res = st.session_state.verification_result

        # ── Verification Result Display Deck ─────────────────────────────────
        if v_res:
            is_direct = v_res["is_direct_gee"]
            badge_color = "#10b981" if is_direct else "#38bdf8"
            badge_text = "🟢 DIRECT GEE CATALOG (ee.Image Instant Load)" if is_direct else "📦 BHOONIDHI GEOTIFF INGESTION (QGIS / GEE Assets)"

            st.markdown(f"""
            <div class="verify-card">
                <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:12px;">
                    <div>
                        <span style="font-size:0.72rem; color:#94a3b8; text-transform:uppercase; font-weight:700;">Target Scene</span>
                        <h3 style="color:#ffffff; margin:2px 0 0 0; font-family:'JetBrains Mono', monospace; font-size:1.05rem;">{v_res['item_id']}</h3>
                    </div>
                    <div style="text-align:right;">
                        <span style="background:rgba(0,0,0,0.4); color:{badge_color}; border:1px solid {badge_color}; padding:4px 12px; border-radius:20px; font-size:0.75rem; font-weight:700;">
                            {badge_text}
                        </span>
                    </div>
                </div>
                <div style="background:rgba(15, 23, 42, 0.7); border-radius:8px; padding:10px 14px; margin-bottom:12px; border-left:4px solid #38bdf8;">
                    <div style="font-size:0.78rem; font-weight:700; color:#38bdf8;">🛡️ Disaster Management Sensor Assessment:</div>
                    <div style="font-size:0.80rem; color:#e2e8f0; margin-top:2px;">{v_res['disaster_verdict']}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # ── Verification Pipeline Steps ──────────────────────────────────
            with st.expander("📋 Interactive Verification Pipeline Telemetry & Logs", expanded=True):
                st.caption(f"Verification pipeline completed in **{v_res['duration_ms']} ms** across 5 validation checkpoints.")
                for s in v_res["steps"]:
                    icon = "✅" if s["status"] == "passed" else ("⚠️" if s["status"] == "warning" else "ℹ️")
                    st.markdown(f"""
                    <div class="verify-step verify-step-{s['status']}">
                        <b>{icon} Step {s['step']}: {s['name']}</b><br/>
                        <span style="color:#94a3b8; font-family:'JetBrains Mono', monospace; font-size:0.76rem;">{s['details']}</span>
                    </div>
                    """, unsafe_allow_html=True)

            # ── Code & Script Generation Deck ────────────────────────────────
            st.markdown('<div class="sidebar-title">💻 Ready-to-Run Code & Integration Snippets</div>', unsafe_allow_html=True)

            code_tab1, code_tab2, code_tab3, code_tab4 = st.tabs([
                "🐍  Google Earth Engine (Python API)",
                "🌐  GEE Code Editor (JavaScript)",
                "🚀  GEE Asset Upload (CLI)",
                "🗺️  QGIS Desktop & Python",
            ])

            with code_tab1:
                st.caption("Copy this code directly into your Jupyter notebook or Python script. Uses `ee.Image` without downloading massive files locally!")
                py_code = gee.generate_gee_python_script(current_feature)
                st.code(py_code, language="python")

            with code_tab2:
                st.caption("Paste into [Google Earth Engine Code Editor](https://code.earthengine.google.com) to visualize instantly in your browser.")
                js_code = gee.generate_gee_javascript_script(current_feature)
                st.code(js_code, language="javascript")

            with code_tab3:
                st.caption("Command line snippet to upload the downloaded Bhoonidhi GeoTIFF into your Google Earth Engine Asset repository.")
                cli_code = gee.generate_cli_upload_command(current_feature)
                st.code(cli_code, language="bash")

            with code_tab4:
                st.caption("QGIS Python Console snippet & Drag-and-Drop usage for downloaded GeoTIFF rasters.")
                qgis_code = gee.generate_qgis_python_script(current_feature)
                st.code(qgis_code, language="python")
                st.info(
                    "💡 **QGIS Drag & Drop:** Bhoonidhi .tif files contain embedded Coordinate Reference Systems (CRS). "
                    "Simply drag and drop the extracted `.tif` file from your Downloads folder directly onto the QGIS map canvas!"
                )

        st.markdown("<hr/>", unsafe_allow_html=True)

        # ── Quicklook Preview ─────────────────────────────────────────────────
        selected_feature_ids = st.session_state.selected_items
        if selected_feature_ids:
            with st.expander(
                f"🔍 Quicklook Thumbnails ({len(selected_feature_ids)} scenes selected)",
                expanded=False,
            ):
                st.caption(
                    "Thumbnail / browse images for selected scenes. "
                    "Requires Bhoonidhi browse endpoint access."
                )
                preview_features = [f for f in features if f["id"] in selected_feature_ids[:12]]
                cols_per_row = 3
                for row_start in range(0, len(preview_features), cols_per_row):
                    row_feats = preview_features[row_start: row_start + cols_per_row]
                    pcols = st.columns(cols_per_row)
                    for col_idx, feat in enumerate(row_feats):
                        with pcols[col_idx]:
                            p = feat.get("properties", {})
                            scene_date = (p.get("datetime") or p.get("start_datetime") or "")[:10]
                            st.caption(f"📅 {scene_date}  |  {feat['id'][:30]}…")
                            img_bytes = client.fetch_quicklook(feat)
                            if img_bytes:
                                st.image(img_bytes, use_container_width=True)
                            else:
                                geom = feat.get("geometry", {})
                                if geom.get("type") == "Polygon":
                                    coords = geom["coordinates"][0]
                                    lons = [c[0] for c in coords]
                                    lats = [c[1] for c in coords]
                                    cx, cy = sum(lons)/len(lons), sum(lats)/len(lats)
                                    mini = folium.Map(location=[cy, cx], zoom_start=6, tiles=None)
                                    folium.TileLayer(
                                        tiles=f"https://basemaps.cartocdn.com/rastertiles/voyager/{{z}}/{{x}}/{{y}}.png?key={CARTO_KEY}",
                                        attr="CARTO",
                                        name="Carto",
                                    ).add_to(mini)
                                    folium.Polygon(
                                        locations=[[c[1], c[0]] for c in coords],
                                        color="#e53935",
                                        fill=True,
                                        fill_opacity=0.2,
                                        weight=2,
                                        tooltip=feat["id"],
                                    ).add_to(mini)
                                    st_folium(mini, width=260, height=200, key=f"mini_{feat['id']}", returned_objects=[])
                                else:
                                    st.markdown(
                                        """<div style='background:#0f1c3d;border:1px dashed #334155;
                                        border-radius:8px;padding:24px;text-align:center;color:#64748b;
                                        font-size:0.80rem;'>🛰️ No preview available<br/>
                                        <span style='font-size:0.72rem;'>Browse image not served<br/>for this collection</span>
                                        </div>""",
                                        unsafe_allow_html=True,
                                    )
                            sz = st.session_state.file_sizes.get(feat["id"])
                            raw_sz = p.get("file:size") or p.get("FileSize")
                            if raw_sz:
                                sz = round(int(raw_sz) / (1024*1024), 1)
                            if sz:
                                st.markdown(
                                    f"<div style='text-align:center;font-size:0.75rem;"
                                    f"color:#38bdf8;margin-top:4px;'>💾 {sz} MB</div>",
                                    unsafe_allow_html=True,
                                )
                if len(selected_feature_ids) > 12:
                    st.caption(f"*Showing first 12 of {len(selected_feature_ids)} selected scenes.*")

        # ── Batch Download Action Deck ────────────────────────────────────────
        dl_col1, dl_col2, dl_col3 = st.columns([2, 1, 1])

        with dl_col1:
            dl_trigger = st.button(
                f"⬇️  Download {len(st.session_state.selected_items)} Selected Product(s)",
                type="primary",
                disabled=len(st.session_state.selected_items) == 0,
                use_container_width=True,
            )

        with dl_col2:
            csv_buf = io.StringIO()
            filtered_df.to_csv(csv_buf, index=False)
            st.download_button(
                "📥 Export CSV",
                data=csv_buf.getvalue(),
                file_name=f"bhoonidhi_{selected_collection}.csv",
                mime="text/csv",
                use_container_width=True,
            )

        with dl_col3:
            fc = {
                "type": "FeatureCollection",
                "features": [
                    f for f in features
                    if f["id"] in st.session_state.selected_items
                ],
            }
            st.download_button(
                "📋 Export Scene Footprints (GeoJSON)",
                data=json.dumps(fc, indent=2),
                file_name=f"bhoonidhi_{selected_collection}_footprints.geojson",
                mime="application/json",
                use_container_width=True,
                help="Exports scene boundary polygons — NOT satellite imagery. Load in QGIS as a vector overlay only.",
            )

        # ── Download Process Execution with Exception Shield ──────────────────
        if dl_trigger and st.session_state.selected_items:
            items_to_dl = [
                {"id": f["id"], "collection": f.get("collection", selected_collection)}
                for f in features
                if f["id"] in st.session_state.selected_items
            ]
            total_dl = len(items_to_dl)

            status_placeholder = st.empty()
            progress_bar = st.progress(0)
            run_results = dict(st.session_state.download_results)

            for i, itm in enumerate(items_to_dl):
                status_placeholder.info(f"Downloading [{i+1}/{total_dl}]: `{itm['id']}`")
                try:
                    result = client._download_single(itm["id"], itm["collection"])
                    run_results[itm["id"]] = {"status": "ok", **result}
                except BhoonidhiError as exc:
                    run_results[itm["id"]] = {"status": "error", "error": exc.message}
                except Exception as exc:
                    run_results[itm["id"]] = {"status": "error", "error": str(exc)}
                progress_bar.progress((i + 1) / total_dl)

            st.session_state.download_results = run_results
            status_placeholder.empty()

            success_n = sum(1 for v in run_results.values() if v.get("status") == "ok")
            st.success(f"Batch completed: **{success_n}/{total_dl}** downloaded successfully. Open **⬇️ Download Manager** tab.")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Download Manager & Local Data Hub
# ═══════════════════════════════════════════════════════════════════════════════
with tab_downloads:
    dl_results = st.session_state.download_results

    # ── Local Directory Inspection ────────────────────────────────────────────
    dl_dir = client.get_download_dir()
    local_files = []
    total_bytes = 0
    try:
        dl_dir.mkdir(parents=True, exist_ok=True)
        if dl_dir.exists():
            for f in dl_dir.rglob("*"):
                if f.is_file():
                    sz = f.stat().st_size
                    total_bytes += sz
                    local_files.append({
                        "Filename": f.name,
                        "Collection": f.parent.parent.name if f.parent.parent != dl_dir else f.parent.name,
                        "Size (MB)": round(sz / (1024 * 1024), 2),
                        "Path": str(f.resolve()),
                    })
    except Exception:
        pass

    # ── Summary Metrics ───────────────────────────────────────────────────────
    ok_items = {k: v for k, v in dl_results.items() if v.get("status") == "ok"}
    err_items = {k: v for k, v in dl_results.items() if v.get("status") == "error"}

    c_m1, c_m2, c_m3, c_m4 = st.columns(4)
    c_m1.metric("Session Downloaded", len(ok_items))
    c_m2.metric("Session Failed", len(err_items))
    c_m3.metric("Local Disk Storage", f"{total_bytes / (1024 * 1024):,.1f} MB")
    c_m4.metric("Saved Products", len(local_files))

    st.markdown("<hr/>", unsafe_allow_html=True)

    # ── Session Downloads View ────────────────────────────────────────────────
    st.markdown('<div class="sidebar-title">📦 Current Session Downloads</div>', unsafe_allow_html=True)

    if not dl_results:
        st.info("No downloads triggered in this session. Query the catalog and click **Download Selected**.")
    else:
        if ok_items:
            with st.expander(f"✅ Successfully Downloaded ({len(ok_items)})", expanded=True):
                for p_id, info in ok_items.items():
                    fp = Path(info.get("zip_path", info.get("path", "")))
                    rasters = info.get("raster_files", [])
                    sz_str = f"({fp.stat().st_size / (1024*1024):.2f} MB)" if fp.exists() else ""
                    st.markdown(f"**`{p_id}`** {sz_str}")

                    if rasters:
                        st.success(f"✅ **{len(rasters)} GeoTIFF file(s) extracted — ready for QGIS / GEE Asset Upload**")
                        for r in rasters:
                            st.code(r, language="bash")
                    else:
                        st.code(str(fp), language="bash")
                        st.caption("ZIP saved. No .tif files found inside — open the ZIP manually.")

        if err_items:
            with st.expander(f"❌ Failed Downloads ({len(err_items)})", expanded=True):
                for p_id, info in err_items.items():
                    st.markdown(f"**`{p_id}`**")
                    st.error(info.get("error", "Unknown error"))
                    st.caption("Verify if product is Online=Y and whether your credentials permit download.")

    st.markdown("<hr/>", unsafe_allow_html=True)

    # ── QGIS & GEE Workflow Guide ─────────────────────────────────────────────
    st.markdown('<div class="sidebar-title">🗺️ How to Use Bhoonidhi Satellite Data in QGIS & Earth Engine</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="geo-panel">
        <div style="font-size:0.88rem; color:#cbd5e1; line-height:1.7;">
            <p style="color:#38bdf8; font-weight:700; margin-bottom:8px;">
                📦 Bhoonidhi downloads arrive as ZIP files containing GeoTIFF (.tif) rasters.
                The portal auto-extracts them into individual scene directories.
            </p>
            <b style="color:#f1f5f9;">• For QGIS Desktop:</b>
            <ol style="margin:6px 0 12px 18px; padding:0;">
                <li>Open <b>QGIS Desktop</b>.</li>
                <li><b>Drag and drop</b> the extracted <code>.tif</code> file directly onto the map canvas.</li>
                <li>QGIS reads the embedded coordinate reference system (CRS / UTM projection) automatically and overlays it perfectly over your baseline maps.</li>
            </ol>
            <b style="color:#f1f5f9;">• For Google Earth Engine (Local Download -> GEE Upload):</b>
            <ul style="margin:6px 0 12px 18px; padding:0;">
                <li>Open <a href="https://code.earthengine.google.com" target="_blank" style="color:#38bdf8;">GEE Code Editor</a> → go to <b>Assets</b> tab → <b>New → GeoTIFF</b>.</li>
                <li>Select the downloaded <code>.tif</code> file and set the asset ID to upload it to your cloud storage.</li>
            </ul>
            <b style="color:#f1f5f9;">• Alternative for Sentinel-1 in GEE (No Download Needed!):</b>
            <ul style="margin:6px 0 0 18px; padding:0;">
                <li>Since Google Earth Engine already hosts the global Copernicus Sentinel-1 GRD catalog, you can copy the <b>Product ID / Granule Name</b> from this portal and load it instantly via:</li>
                <li style="list-style:none; margin-top:4px;"><code>ee.Image('COPERNICUS/S1_GRD/' + productId)</code> without downloading gigabytes of data locally!</li>
            </ul>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<hr/>", unsafe_allow_html=True)

    # ── Local Storage Data Hub ────────────────────────────────────────────────
    st.markdown(f'<div class="sidebar-title">📁 Local Data Hub — <code>{dl_dir}</code></div>', unsafe_allow_html=True)

    if local_files:
        df_local = pd.DataFrame(local_files)
        df_local["QGIS Ready"] = df_local["Filename"].str.lower().str.endswith(
            (".tif", ".tiff", ".img", ".nc", ".h5", ".hdf")
        ).map({True: "✅ GeoTIFF/Raster", False: "📦 ZIP/Other"})
        st.dataframe(
            df_local,
            column_config={
                "Filename":   st.column_config.TextColumn("File Name", width="medium"),
                "Collection": st.column_config.TextColumn("Collection", width="small"),
                "Size (MB)":  st.column_config.NumberColumn("Size (MB)", format="%.2f MB"),
                "QGIS Ready": st.column_config.TextColumn("QGIS Status", width="small"),
                "Path":       st.column_config.TextColumn("Absolute Path", width="large"),
            },
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.caption(f"No files yet in `{dl_dir}`. They will appear here once downloaded.")


# ─────────────────────────────────────────────────────────────────────────────
# Global Footer
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="footer-bar">
    <div>
        🛰️ Powered by <a href="https://bhoonidhi.nrsc.gov.in" target="_blank">Bhoonidhi STAC API</a> & Google Earth Engine
        &nbsp;—&nbsp; National Remote Sensing Centre (NRSC / ISRO)
    </div>
    <div>
        Rate Limits: 3 req/sec · Max 5 Concurrent Downloads · GEE Native Catalog: Sentinel-1 SAR
    </div>
</div>
""", unsafe_allow_html=True)
