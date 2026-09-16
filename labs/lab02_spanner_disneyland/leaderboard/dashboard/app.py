"""
Disneyland Spanner Hackathon: Admin Leaderboard & Live Telemetry Dashboard
Streamlit Application connecting to BigQuery and Cloud Monitoring API.
"""
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import time
import copy

import metrics
import business_rules
import llm_announcer
import ceremony_engine
import ceremony_audio
# NOTE: Do NOT importlib.reload() these modules here. Reloading rebinds
# BackgroundTelemetryManager to a new class object whose _instance is None, so
# every Streamlit rerun built a new manager and started an additional
# SpannerTelemetryPoller thread that was never stopped (measured: 1 -> 2 -> 3
# pollers over 3 reruns). Streamlit's file watcher already reloads on change.

from metrics import get_leaderboard_snapshot, get_default_admin_project, parse_projects_mapping, clear_telemetry_cache
from business_rules import BENCHMARK_PRICE, calculate_elasticity_demand
from llm_announcer import generate_flash_commentary

# Streamlit Page Config
st.set_page_config(
    page_title="Lab 2: Disneyland Spanner Global Leaderboard",
    page_icon="🏰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""
<style>
    .main {
        background-color: #0e1117;
    }
    .metric-card {
        background-color: #1e222d;
        border-radius: 8px;
        padding: 15px;
        border: 1px solid #2d3139;
    }
    .badge-tag {
        display: inline-block;
        padding: 2px 8px;
        margin: 2px;
        border-radius: 4px;
        background-color: #2b313e;
        font-size: 0.85em;
        font-weight: bold;
    }
    .rank-1 { color: #ffd700; font-weight: bold; font-size: 1.2em; }
    .rank-2 { color: #c0c0c0; font-weight: bold; font-size: 1.1em; }
    .rank-3 { color: #cd7f32; font-weight: bold; font-size: 1.1em; }

    /* Prevent transition flashing on element containers */
    .stElementContainer {
        transition: none !important;
    }

    /* Disable markdown shimmering text masks during reload */
    span.stMarkdownShimmer {
        animation: none !important;
        mask-image: none !important;
    }

    /* Completely hide the distracting top-right 'Stop / Running' status indicator */
    div[data-testid="stStatusWidget"],
    .stStatusWidget {
        display: none !important;
        visibility: hidden !important;
        opacity: 0 !important;
    }

    /* Completely hide the top-right Streamlit Deploy button */
    .stDeployButton,
    .stAppDeployButton,
    div[data-testid="stDeployButton"],
    div[data-testid="stAppDeployButton"],
    button[data-testid="stDeployButton"] {
        display: none !important;
        visibility: hidden !important;
        opacity: 0 !important;
    }

    /* Modal Dialog Flashy Styling */
    div[role="dialog"] {
        max-width: 95vw !important;
        width: 1280px !important;
        background: linear-gradient(145deg, #131722 0%, #1a1e2e 50%, #201b33 100%) !important;
        border: 2px solid #ff79c6 !important;
        border-radius: 16px !important;
        box-shadow: 0 0 50px rgba(255, 121, 198, 0.45), 0 0 100px rgba(189, 147, 249, 0.3) !important;
    }
    div[data-testid="stDialog"] > div:first-child {
        background: rgba(10, 14, 26, 0.85) !important;
        backdrop-filter: blur(14px) !important;
    }
</style>
""", unsafe_allow_html=True)



def build_empty_chart(title: str, x_label: str, y_label: str):
    fig = go.Figure()
    fig.update_layout(
        title=title,
        xaxis_title=x_label,
        yaxis_title=y_label,
        annotations=[{
            "text": "⏳ Waiting for participant attraction telemetry...",
            "xref": "paper",
            "yref": "paper",
            "showarrow": False,
            "font": {"size": 14, "color": "#7aa2f7"}
        }]
    )
    return fig

# Cached Plotly Chart Builders for Ultra-Fast Instant In-Memory Rendering
def build_revenue_chart(df: pd.DataFrame):
    if df.empty or "revenue" not in df.columns or "city" not in df.columns:
        return build_empty_chart("Total Disneyland Revenue by City ($)", "City", "Revenue ($)")
    fig_rev = px.bar(
        df.sort_values("revenue", ascending=False),
        x="city",
        y="revenue",
        color="revenue",
        color_continuous_scale="Viridis",
        title="Total Disneyland Revenue by City ($)",
        labels={"revenue": "Revenue ($)", "city": "City"}
    )
    fig_rev.update_layout(xaxis_tickangle=-45)
    return fig_rev

def build_scatter_chart(df: pd.DataFrame):
    if df.empty or "revenue" not in df.columns or "ticket_price" not in df.columns:
        return build_empty_chart("Ticket Price vs Revenue vs Total Visitors", "Ticket Price ($)", "Revenue ($)")
    target_df = df[df["runs"] > 0] if not df[df["runs"] > 0].empty else df
    fig_scatter = px.scatter(
        target_df,
        x="ticket_price",
        y="revenue",
        size="visitors" if "visitors" in target_df.columns and target_df["visitors"].sum() > 0 else None,
        color="city" if "city" in target_df.columns else None,
        hover_name="city" if "city" in target_df.columns else None,
        title="Ticket Price vs Revenue vs Total Visitors",
        labels={"ticket_price": "Ticket Price ($)", "revenue": "Revenue ($)"}
    )
    return fig_scatter

def build_qps_chart(df: pd.DataFrame):
    if df.empty or "qps" not in df.columns or "city" not in df.columns:
        return build_empty_chart("Direct Write Ingestion Throughput (Runs / Sec)", "City", "Runs/sec")
    fig_qps = px.bar(
        df.sort_values("qps", ascending=False),
        x="city",
        y="qps",
        color="qps",
        color_continuous_scale="Greens",
        title="Direct Write Ingestion Throughput (Runs / Sec)",
        labels={"qps": "Runs/sec", "city": "City"}
    )
    fig_qps.add_hline(y=100.0, line_dash="dash", line_color="orange", annotation_text="High Velocity (100 runs/s)")
    fig_qps.update_layout(xaxis_tickangle=-45)
    return fig_qps

def build_pu_chart(df: pd.DataFrame):
    if df.empty or "processing_units" not in df.columns or "city" not in df.columns:
        return build_empty_chart("Spanner Compute Capacity (Processing Units)", "City", "PUs")
    fig_pu = px.bar(
        df.sort_values("processing_units", ascending=False),
        x="city",
        y="processing_units",
        color="processing_units",
        color_continuous_scale="Purples",
        title="Spanner Compute Capacity (Processing Units)",
        labels={"processing_units": "Processing Units (PUs)", "city": "City"}
    )
    fig_pu.add_hline(y=100.0, line_dash="dash", line_color="gray", annotation_text="Baseline (100 PUs)")
    fig_pu.add_hline(y=1000.0, line_dash="dot", line_color="red", annotation_text="1 Full Node (1,000 PUs)")
    fig_pu.update_layout(xaxis_tickangle=-45)
    return fig_pu

def build_cpu_chart(df: pd.DataFrame):
    if df.empty or "cpu_utilization_pct" not in df.columns or "city" not in df.columns:
        return build_empty_chart("Spanner Max CPU Utilization (%)", "City", "Max CPU %")
    fig_cpu = px.bar(
        df.sort_values("cpu_utilization_pct", ascending=False),
        x="city",
        y="cpu_utilization_pct",
        color="cpu_utilization_pct",
        color_continuous_scale="Reds",
        title="Spanner Max CPU Utilization (%) across Projects",
        labels={"cpu_utilization_pct": "Max CPU %", "city": "City"}
    )
    fig_cpu.add_hline(y=50.0, line_dash="dash", line_color="orange", annotation_text="Heavy Load Threshold (50%)")
    fig_cpu.add_hline(y=80.0, line_dash="dot", line_color="red", annotation_text="Spanner Meltdown (80%)")
    fig_cpu.update_layout(xaxis_tickangle=-45)
    return fig_cpu

def build_storage_chart(df: pd.DataFrame):
    if df.empty or "storage_mb" not in df.columns or "city" not in df.columns:
        return build_empty_chart("Spanner Storage Consumption (MB)", "City", "Storage (MB)")
    max_storage = df["storage_mb"].max() if not df.empty and not pd.isna(df["storage_mb"].max()) else 1.0
    fig_storage = px.bar(
        df.sort_values("storage_mb", ascending=False),
        x="city",
        y="storage_mb",
        color="storage_mb",
        color_continuous_scale="Blues",
        range_color=[0, max(1.0, max_storage)],
        title="Spanner Storage Consumption (MB)",
        labels={"storage_mb": "Storage (MB)", "city": "City"}
    )
    fig_storage.update_traces(texttemplate='%{y:.2f} MB', textposition='outside')
    fig_storage.update_layout(xaxis_tickangle=-45)
    return fig_storage

# Sidebar Controls
st.sidebar.title("🏰 Lab 2 Command Center")

admin_project = st.sidebar.text_input("Admin Project ID", value=get_default_admin_project(), help="GCP project hosting BigQuery connection and central administration")
st.sidebar.markdown("**Database**: `disneyland/agent-lab`")

# Dynamic Project Scope Filtering
st.sidebar.markdown("---")
st.sidebar.subheader("🎯 Project Scope")

all_mapped = parse_projects_mapping(admin_project)
mapped_options = [p["project_id"] for p in all_mapped]
mapped_labels = {p["project_id"]: f"{p['city']} ({p['project_id'].split('-')[-1]})" for p in all_mapped}

filter_inactive = st.sidebar.checkbox(
    "Hide Inactive Projects",
    value=st.session_state.get("filter_inactive_state", True),
    key="filter_inactive_state",
    help="Exclude projects with 0 attraction runs and 0 created tables from the leaderboard"
)

selected_project_ids = st.sidebar.multiselect(
    "Active Projects in Scope",
    options=mapped_options,
    default=st.session_state.get("selected_project_ids_state", mapped_options),
    format_func=lambda pid: mapped_labels.get(pid, pid),
    key="selected_project_ids_state",
    help="Select which participant projects are active in this hackathon session"
)

auto_refresh = st.sidebar.checkbox("Auto-Refresh UI (every 10s)", value=True, help="Automatically updates the screen from in-memory cache without page freezing")
refresh_interval = 10

use_mock_data = st.sidebar.checkbox("Simulation / Mock Mode", value=False, help="Use deterministic simulation for UI testing before hackathon kickoff")

# Initialize background poller singleton (completely non-blocking)
telemetry_mgr = metrics.BackgroundTelemetryManager.get_instance()
telemetry_mgr.ensure_started(admin_project, interval=15)

def freeze_ceremony_baseline(admin_proj, selected_ids, filter_inact, mock_mode):
    raw_snap, _ = telemetry_mgr.get_snapshot(admin_proj, use_mock=mock_mode)
    snap = [d for d in raw_snap if d.get("project_id") in selected_ids]
    if filter_inact:
        snap = [d for d in snap if ceremony_engine.is_project_active(d)]
    for rank_idx, item in enumerate(snap, start=1):
        item["rank"] = rank_idx
    return copy.deepcopy(snap)

# Main Title & Subheader with Flashy Ceremony Pop-up Launcher
col_head_title, col_head_btn = st.columns([3, 1.2])
with col_head_title:
    st.title("🏰 Lab 2: Disneyland Spanner Global Leaderboard")
    st.markdown("Real-time telemetry, scoring, revenue gamification & closing ceremony for **Lab 2 (Disneyland Spanner Hackathon)**.")
with col_head_btn:
    st.markdown("<div style='height: 14px;'></div>", unsafe_allow_html=True)
    if st.button("🎪 Launch Closing Ceremony", type="primary", width='stretch', help="Open the flashy full-screen Closing Ceremony pop-up"):
        st.session_state["ceremony_frozen_snapshot"] = freeze_ceremony_baseline(admin_project, selected_project_ids, filter_inactive, use_mock_data)
        st.session_state["ceremony_modal_open"] = True
        # Rewind to the pre-ceremony state. Without this, relaunching after a
        # finished ceremony reopens on the final round with the podium already
        # decided, skipping the entire build-up.
        st.session_state["ceremony_round"] = 0
        st.session_state["show_winner_revealed"] = False
        st.rerun()

# Dedicated placeholder for Roast HUD to preserve static element indices
roast_hud_placeholder = st.empty()

col_ref1, col_ref2 = st.sidebar.columns([3, 2])
with col_ref1:
    if st.button("⚡ Sync Live Now", help="Signal background worker to poll Spanner immediately without freezing the UI"):
        telemetry_mgr.trigger_immediate_sync()
        st.toast("Background telemetry sync initiated!", icon="⚡")
with col_ref2:
    if st.button("🔄 Redraw UI"):
        st.rerun()

if st.sidebar.button("🧹 Clean Cache / Restart", help="Wipes disk and in-memory cache, clears session state, and restarts the application", width='stretch'):
    telemetry_mgr.reset_and_clear_cache()
    st.cache_data.clear()
    st.cache_resource.clear()
    st.session_state.clear()
    st.toast("Cache cleaned and application restarted!", icon="🧹")
    st.rerun()

# Telemetry Poller status badge
_, initial_status = telemetry_mgr.get_snapshot(admin_project, use_mock=use_mock_data)
age = initial_status["age_seconds"]
poller_error = initial_status.get("last_error")
if initial_status["is_fetching"]:
    st.sidebar.caption("📡 **Telemetry Poller**: 🟡 *Querying Spanner in background...*")
elif poller_error:
    # Previously this always showed green once a fetch finished, so a board
    # frozen by backend failures looked healthy on the projector.
    st.sidebar.caption(
        f"📡 **Telemetry Poller**: 🔴 *Sync FAILED ({age}s ago)* — {poller_error[:120]}"
    )
elif age > 180:
    st.sidebar.caption(f"📡 **Telemetry Poller**: 🟠 *Stale — last good sync {age}s ago*")
else:
    st.sidebar.caption(f"📡 **Telemetry Poller**: 🟢 *Synced ({age}s ago)*")

st.sidebar.markdown("---")
st.sidebar.subheader("🎪 Closing Ceremony")
if st.sidebar.button("🎪 Launch Ceremony Pop-up", type="primary", width='stretch', key="sidebar_ceremony_launch"):
    st.session_state["ceremony_frozen_snapshot"] = freeze_ceremony_baseline(admin_project, selected_project_ids, filter_inactive, use_mock_data)
    st.session_state["ceremony_modal_open"] = True
    # Rewind to the pre-ceremony state (see the header launch button).
    st.session_state["ceremony_round"] = 0
    st.session_state["show_winner_revealed"] = False
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.subheader("🎙️ AI Roaster Control")
roaster_enabled = st.sidebar.toggle(
    "Enable AI Roaster Announcer", 
    value=False, 
    help="Start or stop the automated Gemini 3.8 Flash roast broadcasts and floating toast HUD"
)

always_show_roast = False
if roaster_enabled:
    always_show_roast = st.sidebar.checkbox("Pin Roast HUD on Screen", value=False, help="Keep the funny roast HUD visible permanently so the facilitator can position and move it anywhere")

    col_rst1, col_rst2 = st.sidebar.columns(2)
    with col_rst1:
        if st.sidebar.button("🎭 Roast Now", help="Draft a fresh AI roast immediately"):
            with st.spinner("🎙️ Drafting fresh Gemini 3.8 Flash roast..."):
                telemetry_mgr.generate_immediate_roast(admin_project_id=admin_project)
                st.session_state["roast_dismissed"] = False
                st.session_state["clear_dismissed_ts"] = True
            st.toast("🎙️ Fresh AI roast is now on the air!", icon="🎭")
            st.rerun()
    with col_rst2:
        if st.session_state.get("roast_dismissed", False):
            if st.sidebar.button("👁️ Show HUD", help="Restore the floating roast card"):
                st.session_state["roast_dismissed"] = False
                st.session_state["clear_dismissed_ts"] = True
                st.rerun()
        else:
            if st.sidebar.button("❌ Hide HUD", help="Dismiss the floating roast card"):
                st.session_state["roast_dismissed"] = True
                st.rerun()

    # 4-Minute Cadence & 1-Minute Active Visibility Engine
    CYCLE_SECONDS = 240   # Every 4 minutes (240s)
    DISPLAY_SECONDS = 60  # Stays on screen for 1 minute (60s)

    now_ts = time.time()
    last_r_time = telemetry_mgr.last_roast_time

    # If roaster was enabled and never roasted, activate now
    if last_r_time == 0:
        telemetry_mgr.last_roast_time = now_ts
        last_r_time = now_ts
        telemetry_mgr.trigger_roast_sync()

    roast_age = (now_ts - last_r_time) if last_r_time > 0 else 0
    is_active_window = roast_age < DISPLAY_SECONDS
    remaining_seconds = max(1, int(DISPLAY_SECONDS - roast_age))

    # Trigger next background roast when cycle duration has elapsed
    if roast_age >= CYCLE_SECONDS:
        telemetry_mgr.trigger_roast_sync()

    if is_active_window or always_show_roast:
        status_label = f"{remaining_seconds}s left" if (is_active_window and not always_show_roast) else "Pinned / Live"
        st.sidebar.markdown(f"🎙️ **Live Roast Status**: 🔴 On-Air ({status_label})")
    else:
        time_until_next = max(1, int(CYCLE_SECONDS - roast_age))
        mins = time_until_next // 60
        secs = time_until_next % 60
        st.sidebar.markdown(f"⏳ **Next Roast In**: `{mins}m {secs:02d}s`")
else:
    st.sidebar.markdown("🎙️ **Live Roast Status**: ⏸️ Stopped (Disabled)")

def on_ceremony_dismiss():
    st.session_state["ceremony_modal_open"] = False

@st.dialog("🎪 Disneyland Park Closing Ceremony", width="large", on_dismiss=on_ceremony_dismiss)
def show_closing_ceremony_modal(
    admin_project: str, 
    baseline_data: list,
    selected_project_ids: list,
    filter_inactive: bool
):
    if "ceremony_round" not in st.session_state:
        st.session_state["ceremony_round"] = 0
    if "show_winner_revealed" not in st.session_state:
        st.session_state["show_winner_revealed"] = False

    cur_round = st.session_state["ceremony_round"]
    is_revealed = st.session_state.get("show_winner_revealed", False)

    # 1. Strictly scope baseline data to selected project IDs
    scoped_baseline = [p for p in baseline_data if p.get("project_id") in selected_project_ids]

    # Active Project Scope Selector inside Ceremony
    col_sc1, col_sc2 = st.columns([3, 1.2])
    with col_sc1:
        ceremony_only_active = st.checkbox(
            "⚡ Only Active Projects in Ceremony",
            value=st.session_state.get("ceremony_only_active", True),
            key="ceremony_only_active_toggle",
            help="Strictly include only projects with recorded runs or created tables in Spanner"
        )
        st.session_state["ceremony_only_active"] = ceremony_only_active
    with col_sc2:
        st.caption(f"🎯 Scope: **{len(scoped_baseline)}** selected parks")

    if ceremony_only_active:
        active_candidates = [p for p in scoped_baseline if ceremony_engine.is_project_active(p)]
        if active_candidates:
            scoped_baseline = active_candidates
        else:
            st.caption("ℹ️ *All sandboxes currently at baseline (0 rows). Including all selected projects.*")

    for rank_idx, item in enumerate(scoped_baseline, start=1):
        item["rank"] = rank_idx

    # 2. On Round 5 Grand Finale Winner Reveal, render HTML5 Canvas Fireworks
    if cur_round == ceremony_engine.TOTAL_ROUNDS and is_revealed:
        components.html(ceremony_audio.get_fireworks_canvas_html(), height=0)

    # 3. Interactive Step Controls
    ctrl_col1, ctrl_col2, ctrl_col3, ctrl_col4 = st.columns([1.2, 1.2, 1.5, 1.0])
    with ctrl_col1:
        if st.button("⏮️ Round 0 (Reset)", width='stretch'):
            st.session_state["ceremony_round"] = 0
            st.session_state["show_winner_revealed"] = False
            raw_snap, _ = telemetry_mgr.get_snapshot(admin_project, use_mock=use_mock_data)
            snap = [d for d in raw_snap if d.get("project_id") in selected_project_ids]
            if filter_inactive or ceremony_only_active:
                snap = [d for d in snap if ceremony_engine.is_project_active(d)]
            for rank_idx, item in enumerate(snap, start=1):
                item["rank"] = rank_idx
            st.session_state["ceremony_frozen_snapshot"] = copy.deepcopy(snap)
            st.rerun()
    with ctrl_col2:
        if st.button("◀ Previous Event", width='stretch', disabled=(cur_round <= 0)):
            st.session_state["ceremony_round"] = max(0, cur_round - 1)
            st.session_state["show_winner_revealed"] = False
            st.rerun()
    with ctrl_col3:
        if cur_round < ceremony_engine.TOTAL_ROUNDS:
            if st.button(f"Next Event ▶ (Round {cur_round + 1}/{ceremony_engine.TOTAL_ROUNDS})", type="primary", width='stretch'):
                st.session_state["ceremony_round"] = min(ceremony_engine.TOTAL_ROUNDS, cur_round + 1)
                st.session_state["show_winner_revealed"] = False
                st.rerun()
        else:
            if not is_revealed:
                if st.button("👑 Show Winner", type="primary", width='stretch'):
                    st.session_state["show_winner_revealed"] = True
                    st.rerun()
            else:
                if st.button("🎉 Replay Winner Reveal", type="primary", width='stretch'):
                    st.session_state["show_winner_revealed"] = True
                    st.rerun()
    with ctrl_col4:
        if st.button("✖ Close Stage", width='stretch'):
            st.session_state["ceremony_modal_open"] = False
            st.rerun()

    # Progress Tracker
    st.progress(cur_round / float(ceremony_engine.TOTAL_ROUNDS),
                text=f"Ceremony Progress: Round {cur_round} / {ceremony_engine.TOTAL_ROUNDS}")

    # Calculate simulated standings based on frozen scoped baseline snapshot
    sim_data, round_meta = ceremony_engine.apply_event_simulation(scoped_baseline, cur_round)

    # Scoped impacted parks for current round
    impacted_parks = [p for p in sim_data if p.get("round_revenue_delta", 0.0) != 0.0 or p.get("round_score_delta", 0) != 0]

    # Clean up any lingering city popup animation overlays
    components.html(ceremony_audio.get_impacted_cities_popup_html(), height=0, width=0)

    # Round Announcement Banner
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #1f2335 0%, #292e42 100%); border-left: 5px solid #ff79c6; border-radius: 8px; padding: 16px 20px; margin: 15px 0;">
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <h3 style="margin: 0; color: #ff79c6;">{round_meta.get('icon', '🎪')} {round_meta.get('title', '')}</h3>
        <span style="font-size: 0.85em; background: #3b4261; color: #7aa2f7; padding: 3px 10px; border-radius: 12px; font-weight: bold;">
          ROUND {cur_round} OF {ceremony_engine.TOTAL_ROUNDS}
        </span>
      </div>
      <h5 style="margin: 6px 0 10px 0; color: #7dcfff;">{round_meta.get('subtitle', '')}</h5>
      <p style="margin: 0; font-size: 1.05em; color: #c0caf5; line-height: 1.5;">
        {round_meta.get('storyline', '')}
      </p>
    </div>
    """, unsafe_allow_html=True)

    if cur_round >= 1 and impacted_parks:
        city_tags = " ".join([
            f"<span style='background: rgba(30, 34, 52, 0.95); border: 1.5px solid #ff79c6; color: #ffffff; padding: 5px 14px; border-radius: 18px; font-size: 0.88em; font-weight: 800; display: inline-flex; align-items: center; gap: 6px; box-shadow: 0 3px 10px rgba(0,0,0,0.5);'>"
            f"{round_meta.get('icon', '💥')} {p['city']}"
            f"</span>"
            for p in impacted_parks
        ])
        st.markdown(f"""
        <div style="background: rgba(255, 121, 198, 0.09); border: 1.5px solid #ff79c6; border-radius: 10px; padding: 12px 18px; margin: 10px 0 18px 0;">
          <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
            <span style="font-size: 0.82em; font-weight: 800; color: #ff79c6; letter-spacing: 1.2px; text-transform: uppercase;">
              🚨 CITIES IMPACTED BY THIS EVENT ({len(impacted_parks)} OF {len(sim_data)} PARKS):
            </span>
          </div>
          <div style="display: flex; flex-wrap: wrap; gap: 8px;">
            {city_tags}
          </div>
        </div>
        """, unsafe_allow_html=True)

    # Winner Announcement & Podium on Round 5
    if cur_round == ceremony_engine.TOTAL_ROUNDS:
        if not is_revealed:
            st.markdown(f"""
            <div style="background: linear-gradient(135deg, #1e2030 0%, #24283b 100%); border: 2px dashed #f6c177; border-radius: 12px; padding: 25px; text-align: center; margin: 20px 0;">
              <h2 style="color: #f6c177; margin: 0 0 8px 0;">🏁 Final Round Concluded • The Stage Is Set!</h2>
              <p style="color: #c0caf5; font-size: 1.1em; margin: 0 0 15px 0;">
                All {ceremony_engine.TOTAL_ROUNDS} rounds of theme park events are complete. Click below to reveal the podium and celebrate the top 3 winners!
              </p>
            </div>
            """, unsafe_allow_html=True)
            if st.button("👑 Show Winner & Reveal Top 3 Podium", type="primary", width='stretch', key="dlg_show_winner_btn"):
                st.session_state["show_winner_revealed"] = True
                st.session_state["last_sound_fx"] = "winner_revealed"
                st.rerun()
        else:
            st.balloons()
            st.markdown("""
            <style>
              @keyframes confetti-fall {
                0% { transform: translateY(-100vh) rotate(0deg); opacity: 1; }
                100% { transform: translateY(100vh) rotate(720deg); opacity: 0.2; }
              }
              .confetti-particle {
                position: fixed;
                top: 0;
                font-size: 24px;
                pointer-events: none;
                z-index: 999999;
                animation: confetti-fall 4s linear infinite;
              }
            </style>
            <div class="confetti-particle" style="left: 5%; animation-delay: 0s;">🎉</div>
            <div class="confetti-particle" style="left: 15%; animation-delay: 0.8s;">✨</div>
            <div class="confetti-particle" style="left: 28%; animation-delay: 0.3s;">🥇</div>
            <div class="confetti-particle" style="left: 42%; animation-delay: 1.2s;">🌟</div>
            <div class="confetti-particle" style="left: 58%; animation-delay: 0.5s;">👑</div>
            <div class="confetti-particle" style="left: 72%; animation-delay: 1.5s;">🥈</div>
            <div class="confetti-particle" style="left: 85%; animation-delay: 0.2s;">🥉</div>
            <div class="confetti-particle" style="left: 93%; animation-delay: 1.0s;">🎊</div>
            """, unsafe_allow_html=True)

            p_first = sim_data[0] if len(sim_data) >= 1 else None
            p_second = sim_data[1] if len(sim_data) >= 2 else None
            p_third = sim_data[2] if len(sim_data) >= 3 else None

            st.markdown("""
            <div style="background: linear-gradient(135deg, #1f2335 0%, #292e42 50%, #1a1b26 100%); border-radius: 16px; padding: 25px; text-align: center; margin: 20px 0; border: 2px solid #ffd700; box-shadow: 0 10px 40px rgba(255, 215, 0, 0.35);">
              <span style="font-size: 2.8em;">👑 🏆 🌟</span>
              <h1 style="color: #ffd700; margin: 8px 0 4px 0; font-size: 2.3em; letter-spacing: 1px;">
                DISNEYLAND CLOSING CEREMONY GRAND FINALE
              </h1>
              <h3 style="color: #7dcfff; margin: 0; font-weight: 400;">
                Celebrating All Top Three Cloud Spanner Theme Park Engineering Teams
              </h3>
            </div>
            """, unsafe_allow_html=True)

            pod_left, pod_center, pod_right = st.columns([1, 1.2, 1])

            with pod_left:
                if p_second:
                    shift_sec = p_second.get("rank_shift", 0)
                    shift_badge_sec = f"<span style='color: #50fa7b;'>▲ +{shift_sec}</span>" if shift_sec > 0 else (f"<span style='color: #ff5555;'>▼ {abs(shift_sec)}</span>" if shift_sec < 0 else "<span style='color: #8be9fd;'>▬ Stable</span>")
                    st.markdown(f"""
                    <div style="background: linear-gradient(180deg, rgba(192,192,192,0.18) 0%, #1e222d 100%); border: 2px solid #c0c0c0; border-radius: 12px; padding: 18px; text-align: center; margin-top: 35px; box-shadow: 0 8px 24px rgba(192,192,192,0.25);">
                      <div style="font-size: 2.5em;">🥈</div>
                      <div style="font-size: 0.9em; font-weight: 800; color: #c0c0c0; letter-spacing: 1px;">2ND PLACE • RUNNER-UP</div>
                      <h2 style="margin: 6px 0 2px 0; color: #f8f8f2;">{p_second['city']}</h2>
                      <div style="font-size: 0.8em; color: #6272a4; font-family: monospace;">{p_second['project_id']}</div>
                      <div style="margin: 12px 0 6px 0; font-size: 1.4em; font-weight: bold; color: #c0c0c0;">{p_second['score']:,} pts</div>
                      <div style="font-size: 0.95em; color: #bd93f9; font-weight: 600;">${p_second['revenue']:,.2f}</div>
                      <div style="margin-top: 8px; font-size: 0.85em;">Ceremony Net Shift: {shift_badge_sec}</div>
                      <div style="margin-top: 10px; padding: 6px; background: #282a36; border-radius: 6px; font-size: 0.8em; color: #c0caf5;">
                        🛡️ <b>Resilience Maestro:</b> Absorbed weather shocks & infrastructure anomalies with remarkable stability!
                      </div>
                    </div>
                    """, unsafe_allow_html=True)

            with pod_center:
                if p_first:
                    shift_fir = p_first.get("rank_shift", 0)
                    shift_badge_fir = f"<span style='color: #50fa7b;'>▲ +{shift_fir}</span>" if shift_fir > 0 else (f"<span style='color: #ff5555;'>▼ {abs(shift_fir)}</span>" if shift_fir < 0 else "<span style='color: #8be9fd;'>▬ Maintained #1</span>")
                    st.markdown(f"""
                    <div style="background: linear-gradient(180deg, rgba(255,215,0,0.28) 0%, #1e222d 100%); border: 3px solid #ffd700; border-radius: 14px; padding: 22px; text-align: center; box-shadow: 0 12px 35px rgba(255,215,0,0.4);">
                      <div style="font-size: 3.2em;">👑 🥇</div>
                      <div style="font-size: 1.0em; font-weight: 900; color: #ffd700; letter-spacing: 1.5px;">1ST PLACE • GRAND CHAMPION</div>
                      <h1 style="margin: 6px 0 2px 0; color: #ffffff; font-size: 2.2em;">{p_first['city']}</h1>
                      <div style="font-size: 0.85em; color: #a9b1d6; font-family: monospace;">{p_first['project_id']}</div>
                      <div style="margin: 14px 0 8px 0; font-size: 1.8em; font-weight: 900; color: #ffd700;">{p_first['score']:,} pts</div>
                      <div style="font-size: 1.1em; color: #50fa7b; font-weight: 700;">${p_first['revenue']:,.2f}</div>
                      <div style="margin-top: 8px; font-size: 0.9em;">Ceremony Net Shift: {shift_badge_fir}</div>
                      <div style="margin-top: 12px; padding: 8px; background: rgba(255,215,0,0.15); border: 1px solid #ffd700; border-radius: 8px; font-size: 0.85em; color: #fff;">
                        ⚡ <b>Cloud Spanner Architect Titan:</b> Dominated distributed throughput, dynamic elasticity, and TrueTime speed!
                      </div>
                    </div>
                    """, unsafe_allow_html=True)

            with pod_right:
                if p_third:
                    shift_thi = p_third.get("rank_shift", 0)
                    shift_badge_thi = f"<span style='color: #50fa7b;'>▲ +{shift_thi}</span>" if shift_thi > 0 else (f"<span style='color: #ff5555;'>▼ {abs(shift_thi)}</span>" if shift_thi < 0 else "<span style='color: #8be9fd;'>▬ Stable</span>")
                    st.markdown(f"""
                    <div style="background: linear-gradient(180deg, rgba(205,127,50,0.18) 0%, #1e222d 100%); border: 2px solid #cd7f32; border-radius: 12px; padding: 18px; text-align: center; margin-top: 55px; box-shadow: 0 8px 24px rgba(205,127,50,0.25);">
                      <div style="font-size: 2.5em;">🥉</div>
                      <div style="font-size: 0.9em; font-weight: 800; color: #cd7f32; letter-spacing: 1px;">3RD PLACE • BRONZE MEDALIST</div>
                      <h2 style="margin: 6px 0 2px 0; color: #f8f8f2;">{p_third['city']}</h2>
                      <div style="font-size: 0.8em; color: #6272a4; font-family: monospace;">{p_third['project_id']}</div>
                      <div style="margin: 12px 0 6px 0; font-size: 1.4em; font-weight: bold; color: #cd7f32;">{p_third['score']:,} pts</div>
                      <div style="font-size: 0.95em; color: #bd93f9; font-weight: 600;">${p_third['revenue']:,.2f}</div>
                      <div style="margin-top: 8px; font-size: 0.85em;">Ceremony Net Shift: {shift_badge_thi}</div>
                      <div style="margin-top: 10px; padding: 6px; background: #282a36; border-radius: 6px; font-size: 0.8em; color: #c0caf5;">
                        🚀 <b>Consistency Specialist:</b> Mastered ACID transactions across high concurrency ride surges!
                      </div>
                    </div>
                    """, unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

    # Kahoot-Style Round Movement & Impact Highlights
    st.markdown("---")
    st.subheader("🔥 Round Movement & Impact Highlights")

    climbers = [p for p in sim_data if p.get("rank_shift", 0) > 0]
    climbers.sort(key=lambda x: x.get("rank_shift", 0), reverse=True)

    fallers = [p for p in sim_data if p.get("rank_shift", 0) < 0]
    fallers.sort(key=lambda x: x.get("rank_shift", 0))

    impacted_parks = [p for p in sim_data if p.get("revenue_delta", 0.0) != 0.0 or p.get("score_delta", 0) != 0]
    net_revenue_delta = sum(p.get("revenue_delta", 0.0) for p in sim_data)
    total_rank_changes = len(climbers) + len(fallers)

    m_col1, m_col2, m_col3, m_col4 = st.columns(4)
    with m_col1:
        pct_hit = int((len(impacted_parks) / max(1, len(sim_data))) * 100)
        st.metric("💥 Parks Impacted", f"{len(impacted_parks)} / {len(sim_data)}", f"{pct_hit}% of park network")
    with m_col2:
        if climbers:
            top_c = climbers[0]
            st.metric("🚀 Highest Climber", f"{top_c['city']}", f"▲ +{top_c['rank_shift']} ranks (#{top_c['orig_rank']} → #{top_c['new_rank']})")
        else:
            st.metric("🚀 Highest Climber", "None", "No upward movement")
    with m_col3:
        delta_sign = "+" if net_revenue_delta >= 0 else ""
        st.metric("💰 Net Financial Swing", f"{delta_sign}${net_revenue_delta:,.2f}", "Total park network delta")
    with m_col4:
        st.metric("🔀 Leaderboard Shakeup", f"{total_rank_changes} Position Shifts", f"{len(climbers)} up, {len(fallers)} down")

    if len(sim_data) >= 3:
        st.markdown("#### 🏆 Current Podium Leaders")
        p1, p2, p3 = st.columns(3)
        podium_colors = [
            ("#ffd700", "🥇 1ST PLACE", sim_data[0]),
            ("#c0c0c0", "🥈 2ND PLACE", sim_data[1]),
            ("#cd7f32", "🥉 3RD PLACE", sim_data[2])
        ]
        for col, (border_col, label, p_data) in zip([p1, p2, p3], podium_colors):
            with col:
                shift = p_data.get("rank_shift", 0)
                if shift > 0:
                    shift_badge = f"<span style='color: #50fa7b; font-weight: bold;'>▲ +{shift} ranks</span>"
                elif shift < 0:
                    shift_badge = f"<span style='color: #ff5555; font-weight: bold;'>▼ {abs(shift)} ranks</span>"
                else:
                    shift_badge = "<span style='color: #8be9fd;'>▬ Maintained</span>"
                
                score_str = f"{p_data['score']:,} pts ({'+' if p_data.get('score_delta',0)>=0 else ''}{p_data.get('score_delta',0)})"
                rev_str = f"${p_data['revenue']:,.2f}"
            
                st.markdown(f"""
                <div style="background: #1e222d; border-top: 4px solid {border_col}; border-radius: 8px; padding: 14px; text-align: center;">
                  <div style="font-size: 0.85em; font-weight: bold; color: {border_col};">{label}</div>
                  <h3 style="margin: 4px 0 2px 0; color: #f8f8f2;">{p_data['city']}</h3>
                  <div style="font-size: 0.8em; color: #6272a4; font-family: monospace;">{p_data['project_id']}</div>
                  <div style="margin-top: 8px; font-size: 1.1em; font-weight: bold; color: #50fa7b;">{score_str}</div>
                  <div style="font-size: 0.88em; color: #bd93f9;">{rev_str}</div>
                  <div style="margin-top: 6px; font-size: 0.85em;">{shift_badge}</div>
                </div>
                """, unsafe_allow_html=True)

    st.markdown("#### 📊 Movement & Impact Analytics")
    if sim_data:
        ch_col1, ch_col2 = st.columns(2)
    
        with ch_col1:
            movement_df = pd.DataFrame([
                {
                    "City": p["city"],
                    "Rank Shift": p.get("rank_shift", 0),
                    "New Rank": p.get("new_rank", 1),
                    "Orig Rank": p.get("orig_rank", 1),
                    "Direction": "Climbed ▲" if p.get("rank_shift", 0) > 0 else ("Fell ▼" if p.get("rank_shift", 0) < 0 else "Unchanged ▬")
                }
                for p in sim_data
            ]).sort_values(by=["Rank Shift", "New Rank"], ascending=[True, False])
        
            fig_shift = px.bar(
                movement_df,
                x="Rank Shift",
                y="City",
                orientation="h",
                color="Direction",
                color_discrete_map={
                    "Climbed ▲": "#50fa7b",
                    "Fell ▼": "#ff5555",
                    "Unchanged ▬": "#6272a4"
                },
                title="Leaderboard Shifts (Ranks Gained / Lost)",
                hover_data=["Orig Rank", "New Rank"]
            )
            fig_shift.update_layout(
                height=450, 
                margin=dict(l=10, r=10, t=40, b=10),
                xaxis_title="Position Delta (Ranks)",
                yaxis_title=""
            )
            st.plotly_chart(fig_shift, width='stretch')
        
        with ch_col2:
            fin_df = pd.DataFrame([
                {
                    "City": p["city"],
                    "Revenue Delta ($)": p.get("revenue_delta", 0.0),
                    "Score Delta (pts)": p.get("score_delta", 0),
                    "Impact Type": "Gain +" if p.get("revenue_delta", 0.0) > 0 else ("Loss -" if p.get("revenue_delta", 0.0) < 0 else "Neutral 0")
                }
                for p in sim_data
            ]).sort_values(by="Revenue Delta ($)", ascending=True)
        
            fig_fin = px.bar(
                fin_df,
                x="Revenue Delta ($)",
                y="City",
                orientation="h",
                color="Impact Type",
                color_discrete_map={
                    "Gain +": "#50fa7b",
                    "Loss -": "#ff5555",
                    "Neutral 0": "#6272a4"
                },
                title="Financial Impact ($ Revenue Delta)",
                hover_data=["Score Delta (pts)"]
            )
            fig_fin.update_layout(
                height=450, 
                margin=dict(l=10, r=10, t=40, b=10),
                xaxis_title="Revenue Change ($)",
                yaxis_title=""
            )
            st.plotly_chart(fig_fin, width='stretch')

    with st.expander("🔍 Filter Parks by Incident Status (Hit vs Safe)", expanded=False):
        sub_col1, sub_col2 = st.columns(2)
        with sub_col1:
            st.markdown("##### 💥 Parks Incurring Damage or Fines")
            damaged = [p for p in sim_data if p.get("round_revenue_delta", 0.0) < 0 or p.get("round_score_delta", 0) < 0]
            if damaged:
                for d in damaged:
                    shift_icon = f"▲ +{d['rank_shift']}" if d['rank_shift'] > 0 else (f"▼ {abs(d['rank_shift'])}" if d['rank_shift'] < 0 else "▬ 0")
                    st.markdown(f"• **{d['city']}** (`{d['project_id']}`): {d.get('round_impact_text', '')} | *Shift: {shift_icon}*")
            else:
                st.info("No parks incurred damage in this round.")
        with sub_col2:
            st.markdown("##### 🛡️ Safe or Rewarded Parks")
            safe = [p for p in sim_data if p.get("round_revenue_delta", 0.0) >= 0 and p.get("round_score_delta", 0) >= 0]
            if safe:
                for s in safe:
                    shift_icon = f"▲ +{s['rank_shift']}" if s['rank_shift'] > 0 else (f"▼ {abs(s['rank_shift'])}" if s['rank_shift'] < 0 else "▬ 0")
                    st.markdown(f"• **{s['city']}** (`{s['project_id']}`): {s.get('round_impact_text', '')} | *Shift: {shift_icon}*")
            else:
                st.info("All parks were hit.")

    st.markdown("### 📊 Complete Standings Shift Matrix")
    ceremony_rows = []
    for p in sim_data:
        curr_rank = p.get("new_rank", p.get("rank", 1))
        r_icon = "🥇" if curr_rank == 1 else ("🥈" if curr_rank == 2 else ("🥉" if curr_rank == 3 else f"#{curr_rank}"))
    
        shift_val = p.get("rank_shift", 0)
        if shift_val > 0:
            shift_display = f"🟢 ▲ +{shift_val}"
        elif shift_val < 0:
            shift_display = f"🔴 ▼ {abs(shift_val)}"
        else:
            shift_display = "⚪ ▬ 0"
        
        score_diff = p.get("score_delta", 0)
        score_display = f"{p['score']} ({'+' if score_diff >= 0 else ''}{score_diff})"
    
        rev_diff = p.get("revenue_delta", 0.0)
        rev_display = f"${p['revenue']:,.2f} ({'+' if rev_diff >= 0 else ''}${rev_diff:,.2f})"
    
        badge_str = " ".join([f"{b[0]} {b[1]}" for b in p.get("badges", [])])
    
        ceremony_rows.append({
            "New Rank": r_icon,
            "Shift": shift_display,
            "City": p["city"],
            "Project": p["project_id"],
            "Final Score": score_display,
            "Speed Bonus": f"+{p.get('speed_bonus', 0)} pts" if p.get('speed_bonus', 0) > 0 else "—",
            "Disney Revenue": rev_display,
            "Incident Report": p.get("round_impact_text", "—"),
            "Badges": badge_str or "—"
        })
    
    st.dataframe(pd.DataFrame(ceremony_rows), width='stretch', hide_index=True)


is_ceremony_active = st.session_state.get("ceremony_modal_open", False)
fragment_run_every = f"{refresh_interval}s" if (auto_refresh and not is_ceremony_active) else None

# Fragment: Isolated In-Place Auto-Refresh Engine (0ms Freeze, Seamless Numbers Update)
@st.fragment(run_every=fragment_run_every)
def render_live_telemetry_board(
    admin_project: str,
    selected_project_ids: list,
    filter_inactive: bool,
    use_mock_data: bool,
    roaster_enabled: bool,
    always_show_roast: bool
):
    # Instant 0ms retrieval from in-memory cache (Zero UI freeze)
    raw_data, sync_status = telemetry_mgr.get_snapshot(admin_project, use_mock=use_mock_data)

    # Respect persistent filter state from session_state if available
    effective_filter_inactive = st.session_state.get("filter_inactive_state", filter_inactive)
    effective_selected_ids = st.session_state.get("selected_project_ids_state", selected_project_ids)

    # Filter raw data strictly by scope
    data = [d for d in raw_data if d.get("project_id") in effective_selected_ids]

    if effective_filter_inactive:
        data = [d for d in data if ceremony_engine.is_project_active(d)]

    # Re-rank filtered entries
    for rank_idx, item in enumerate(data, start=1):
        item["rank"] = rank_idx

    if data:
        telemetry_mgr.set_active_snapshot(data)
        df = pd.DataFrame(data)
    else:
        df = pd.DataFrame(columns=[
            "rank", "city", "project_id", "member", "short_id", "score", "revenue", 
            "profit", "visitors", "ticket_price", "processing_units", "qps", 
            "cpu_utilization_pct", "storage_mb", "tables", "total_rows", "runs", 
            "has_graph", "badges", "speed_bonus", "round_impact_text"
        ])

    # Roast HUD rendering
    if roaster_enabled and not st.session_state.get("roast_dismissed", False):
        CYCLE_SECONDS = 240
        DISPLAY_SECONDS = 60
        now_ts = time.time()
        last_r_time = telemetry_mgr.last_roast_time
        roast_age = (now_ts - last_r_time) if last_r_time > 0 else 0
        is_active_window = roast_age < DISPLAY_SECONDS
        remaining_seconds = max(1, int(DISPLAY_SECONDS - roast_age))

        if is_active_window or always_show_roast:
            roast = telemetry_mgr.get_roast(admin_project)
            target_city = roast.get("target_city", "Contenders")
            emoji = roast.get("emoji", "🎪")
            joke = roast.get("roast", "")
            rhyme_lines = roast.get("rhyme", "").split("\n")
            rhyme_html = "<br/>".join([f"✨ <em>{l.strip()}</em>" for l in rhyme_lines if l.strip()])
            model_name = roast.get("model", "Gemini 3.8 Flash")
            roast_ts = roast.get("timestamp", time.strftime("%H:%M:%S"))

            with roast_hud_placeholder.container():
                st.markdown(f"""
            <style>
            @keyframes neonGlow {{
              0% {{ box-shadow: 0 10px 30px rgba(0, 0, 0, 0.7), 0 0 15px rgba(255, 121, 198, 0.4); border-color: #ff79c6; }}
              50% {{ box-shadow: 0 12px 35px rgba(0, 0, 0, 0.8), 0 0 25px rgba(189, 147, 249, 0.6); border-color: #bd93f9; }}
              100% {{ box-shadow: 0 10px 30px rgba(0, 0, 0, 0.7), 0 0 15px rgba(255, 121, 198, 0.4); border-color: #ff79c6; }}
            }}

            @keyframes progressShrink {{
              from {{ width: 100%; }}
              to {{ width: 0%; }}
            }}

            .roast-floating-card {{
              position: fixed;
              top: 15%;
              left: 50%;
              transform: translateX(-50%);
              width: 480px;
              max-width: 90vw;
              background: linear-gradient(135deg, #181926 0%, #281e3a 100%);
              border: 2px solid #ff79c6;
              border-radius: 12px;
              padding: 16px 20px;
              z-index: 999999;
              color: #f8f8f2;
              font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
              animation: neonGlow 3s infinite ease-in-out;
              box-shadow: 0 12px 35px rgba(0, 0, 0, 0.8), 0 0 20px rgba(255, 121, 198, 0.4);
              backdrop-filter: blur(12px);
              user-select: auto;
              transition: box-shadow 0.25s ease;
            }}

            .roast-floating-card:hover {{
              box-shadow: 0 16px 45px rgba(0, 0, 0, 0.85), 0 0 35px rgba(255, 121, 198, 0.85) !important;
            }}

            .roast-floating-card:hover .roast-timer-bar {{
              animation-play-state: paused !important;
            }}

            .roast-drag-handle {{
              cursor: grab;
              user-select: none;
              padding-bottom: 8px;
              margin-bottom: 8px;
              border-bottom: 1px solid rgba(255, 121, 198, 0.2);
              display: flex;
              justify-content: space-between;
              align-items: center;
            }}

            .roast-drag-handle:active {{
              cursor: grabbing;
            }}

            .rhyme-box {{
              background: rgba(255, 215, 0, 0.08);
              border-left: 3px solid #ffd700;
              border-radius: 6px;
              padding: 10px 14px;
              margin: 10px 0;
              font-family: 'Georgia', serif;
              color: #f1fa8c;
              font-size: 0.95em;
              line-height: 1.45;
            }}
            </style>

            <div class="roast-floating-card" id="roastCard" data-ts="{roast_ts}" data-pinned="{str(always_show_roast).lower()}" data-clear-dismissed="{str(st.session_state.get('clear_dismissed_ts', False)).lower()}">
              <div class="roast-drag-handle" id="roastDragHandle" title="Drag to reposition card on screen">
                <div style="display: flex; align-items: center; gap: 8px;">
                  <span style="font-size: 1.1em; color: #ff79c6; cursor: grab;" title="Drag handle">⠿</span>
                  <span style="font-size: 0.78em; font-weight: 800; color: #ff79c6; letter-spacing: 1.2px; text-transform: uppercase;">
                    🎪 LIVE ROAST BULLETIN • {model_name}
                  </span>
                </div>
                <div style="display: flex; align-items: center; gap: 6px;">
                  <span style="font-size: 0.75em; color: #8be9fd; font-family: monospace;">⏱️ {roast_ts}</span>
                  <button id="roastResetBtn" title="Reset card to center position" style="background: rgba(255, 255, 255, 0.1); border: 1px solid rgba(255, 121, 198, 0.4); color: #f8f8f2; border-radius: 4px; font-size: 0.7em; padding: 2px 6px; cursor: pointer;">🎯 Center</button>
                  <button id="roastCloseBtn" title="Close roast popup" style="background: rgba(255, 121, 198, 0.2); border: 1px solid rgba(255, 121, 198, 0.6); color: #ff79c6; border-radius: 4px; font-size: 0.75em; padding: 2px 7px; cursor: pointer; font-weight: bold; line-height: 1;">✕</button>
                </div>
              </div>
              <div style="display: inline-block; background: #44475a; color: #50fa7b; font-size: 0.82em; font-weight: bold; padding: 2px 10px; border-radius: 12px; margin-bottom: 8px;">
                🎯 TARGET: {target_city.upper()} {emoji}
              </div>
              <div style="font-size: 1.05em; color: #f8f8f2; line-height: 1.45; margin-bottom: 6px;">
                "{joke}"
              </div>
              <div class="rhyme-box">
                {rhyme_html}
              </div>
              <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 10px; font-size: 0.75em; color: #8be9fd;">
                <span>⏱️ On-Air for {remaining_seconds}s (Hover to pause)</span>
                <span style="color: #6272a4;">Drag header to move</span>
              </div>
              <div style="height: 4px; width: 100%; background: #282a36; border-radius: 2px; margin-top: 6px; overflow: hidden;">
                <div class="roast-timer-bar" style="height: 100%; width: 100%; background: linear-gradient(90deg, #ff79c6, #bd93f9); animation: progressShrink {remaining_seconds}s linear forwards;"></div>
              </div>
            </div>
            """, unsafe_allow_html=True)

            components.html("""
            <script>
            (function() {
              const pDoc = window.parent.document;
              const pWin = window.parent;

              if (window.frameElement) {
                window.frameElement.style.display = 'none';
                window.frameElement.style.height = '0px';
                if (window.frameElement.parentElement) {
                  window.frameElement.parentElement.style.display = 'none';
                  window.frameElement.parentElement.style.height = '0px';
                }
              }

              function setupDraggable() {
                const card = pDoc.getElementById("roastCard");
                const handle = pDoc.getElementById("roastDragHandle");
                const resetBtn = pDoc.getElementById("roastResetBtn");
                const closeBtn = pDoc.getElementById("roastCloseBtn");

                if (!card || !handle) {
                  setTimeout(setupDraggable, 50);
                  return;
                }

                const clearDismissed = card.getAttribute("data-clear-dismissed") === "true";
                if (clearDismissed) {
                  pWin.sessionStorage.removeItem("roast_dismissed_ts");
                }

                const isPinned = card.getAttribute("data-pinned") === "true";
                const currentTs = card.getAttribute("data-ts") || "";
                if (!isPinned && currentTs && pWin.sessionStorage.getItem("roast_dismissed_ts") === currentTs) {
                  card.remove();
                  return;
                }

                if (closeBtn) {
                  closeBtn.onclick = function(e) {
                    e.stopPropagation();
                    e.preventDefault();
                    if (currentTs) {
                      pWin.sessionStorage.setItem("roast_dismissed_ts", currentTs);
                    }
                    card.style.display = "none";
                    card.remove();
                  };
                }

                // Restore position if previously saved
                const saved = pWin.sessionStorage.getItem("roast_card_pos");
                if (saved) {
                  try {
                    const pos = JSON.parse(saved);
                    if (pos.left !== undefined && pos.top !== undefined) {
                      card.style.transform = "none";
                      card.style.left = pos.left + "px";
                      card.style.top = pos.top + "px";
                    }
                  } catch(e) {}
                }

                if (resetBtn) {
                  resetBtn.onclick = function(e) {
                    e.stopPropagation();
                    e.preventDefault();
                    pWin.sessionStorage.removeItem("roast_card_pos");
                    card.style.transform = "translateX(-50%)";
                    card.style.left = "50%";
                    card.style.top = "15%";
                  };
                }

                handle.ondblclick = function(e) {
                  pWin.sessionStorage.removeItem("roast_card_pos");
                  card.style.transform = "translateX(-50%)";
                  card.style.left = "50%";
                  card.style.top = "15%";
                };

                let isDragging = false;
                let startX = 0, startY = 0;
                let origLeft = 0, origTop = 0;

                function startDrag(clientX, clientY) {
                  isDragging = true;
                  startX = clientX;
                  startY = clientY;

                  const rect = card.getBoundingClientRect();
                  origLeft = rect.left;
                  origTop = rect.top;

                  card.style.transform = "none";
                  card.style.left = origLeft + "px";
                  card.style.top = origTop + "px";

                  handle.style.cursor = "grabbing";
                  card.style.cursor = "grabbing";
                  pDoc.body.style.userSelect = "none";
                }

                function moveDrag(clientX, clientY) {
                  if (!isDragging) return;
                  const dx = clientX - startX;
                  const dy = clientY - startY;

                  let newLeft = origLeft + dx;
                  let newTop = origTop + dy;

                  const maxLeft = pWin.innerWidth - card.offsetWidth - 10;
                  const maxTop = pWin.innerHeight - card.offsetHeight - 10;

                  newLeft = Math.max(10, Math.min(newLeft, maxLeft));
                  newTop = Math.max(10, Math.min(newTop, maxTop));

                  card.style.left = newLeft + "px";
                  card.style.top = newTop + "px";
                }

                function stopDrag() {
                  if (!isDragging) return;
                  isDragging = false;
                  handle.style.cursor = "grab";
                  card.style.cursor = "auto";
                  pDoc.body.style.userSelect = "auto";

                  pWin.sessionStorage.setItem("roast_card_pos", JSON.stringify({
                    left: card.offsetLeft,
                    top: card.offsetTop
                  }));
                }

                handle.onmousedown = function(e) {
                  if (e.target === resetBtn || e.target === closeBtn) return;
                  e.preventDefault();
                  startDrag(e.clientX, e.clientY);
                };

                handle.ontouchstart = function(e) {
                  if (e.target === resetBtn || e.target === closeBtn) return;
                  if (e.touches.length === 1) {
                    startDrag(e.touches[0].clientX, e.touches[0].clientY);
                  }
                };

                const onMouseMove = function(e) {
                  if (isDragging) {
                    e.preventDefault();
                    moveDrag(e.clientX, e.clientY);
                  }
                };

                const onTouchMove = function(e) {
                  if (isDragging && e.touches.length === 1) {
                    moveDrag(e.touches[0].clientX, e.touches[0].clientY);
                  }
                };

                const onMouseUp = function(e) {
                  stopDrag();
                };

                if (pDoc._roastMouseMove) pDoc.removeEventListener("mousemove", pDoc._roastMouseMove);
                if (pDoc._roastMouseUp) pDoc.removeEventListener("mouseup", pDoc._roastMouseUp);
                if (pDoc._roastTouchMove) pDoc.removeEventListener("touchmove", pDoc._roastTouchMove);
                if (pDoc._roastTouchEnd) pDoc.removeEventListener("touchend", pDoc._roastTouchEnd);

                pDoc._roastMouseMove = onMouseMove;
                pDoc._roastMouseUp = onMouseUp;
                pDoc._roastTouchMove = onTouchMove;
                pDoc._roastTouchEnd = onMouseUp;

                pDoc.addEventListener("mousemove", onMouseMove);
                pDoc.addEventListener("mouseup", onMouseUp);
                pDoc.addEventListener("touchmove", onTouchMove, { passive: false });
                pDoc.addEventListener("touchend", onMouseUp);
              }

              setupDraggable();
            })();
            </script>
            """, height=0, width=0)

            if st.session_state.get("clear_dismissed_ts", False):
                st.session_state["clear_dismissed_ts"] = False

        else:
            roast_hud_placeholder.empty()
    else:
        roast_hud_placeholder.empty()

    # Summary Metrics Row
    col1, col2, col3, col4, col5, col6 = st.columns(6)

    total_participants = len(df)
    top_city = df.iloc[0]["city"] if not df.empty else "N/A"
    total_rows = (df["total_rows"] + (df["runs"] if "runs" in df.columns else 0)).sum() if not df.empty else 0
    total_revenue = df["revenue"].sum() if not df.empty else 0.0
    peak_cpu = df["cpu_utilization_pct"].max() if not df.empty else 0.0
    total_cloud_runs = sum(1 for r in data if r.get("has_cloud_run"))

    with col1:
        st.metric("Active Cities", f"{total_participants} Parks")
    with col2:
        st.metric("Leading City", f"🥇 {top_city}")
    with col3:
        st.metric("Cloud Run Apps", f"🚀 {total_cloud_runs} / {total_participants} Live")
    with col4:
        st.metric("Total Spanner Rows", f"{total_rows:,}")
    with col5:
        st.metric("Total Disney Revenue", f"${total_revenue:,.2f}")
    with col6:
        st.metric("Peak Spanner CPU", f"{peak_cpu:.1f}%")

    st.divider()

    # Tabs
    tab_leaderboard, tab_business, tab_spanner, tab_schema, tab_ceremony = st.tabs([
        "🏆 Lab 2 City Leaderboard & Awards",
        "💰 Disneyland Business Arena (Revenue & Pricing)",
        "⚡ Spanner Telemetry & Load",
        "🗂️ DDL & Schema Progress",
        "🎪 Disneyland Park Closing Ceremony"
    ])

    # --- TAB 1: Main Leaderboard ---
    with tab_leaderboard:
        st.subheader("🏁 Global City Standings")
    
        if not data:
            st.info("ℹ️ No active participant projects detected with tables or runs yet. Uncheck 'Hide Inactive Projects' in the sidebar to view all sandboxes.")
        else:
            # Format table for display
            display_rows = []
            for r in data:
                rank_icon = "🥇" if r["rank"] == 1 else ("🥈" if r["rank"] == 2 else ("🥉" if r["rank"] == 3 else f"#{r['rank']}"))
                badge_str = " ".join([f"{b[0]} {b[1]}" for b in r.get("badges", [])])
                
                cr_pts = r.get("cloud_run_score", 0) + r.get("cloud_run_bonus", 0)
                cr_display = f"🚀 Live (+{cr_pts} pts)" if r.get("has_cloud_run") else "⏳ Pending"
                
                spanner_speed = r.get("speed_bonus", 0)
                cr_speed = r.get("cloud_run_bonus", 0)
                total_speed = spanner_speed + cr_speed
                speed_str = f"+{total_speed} pts" if total_speed > 0 else "—"

                display_rows.append({
                    "Rank": rank_icon,
                    "City": r["city"],
                    "Project": r["project_id"],
                    "Score": r["score"],
                    "Cloud Run": cr_display,
                    "App URL": r.get("cloud_run_url") if r.get("has_cloud_run") and r.get("cloud_run_url") else None,
                    "Speed Bonus": speed_str,
                    "Revenue": f"${r['revenue']:,.2f}",
                    "Ticket Price": f"${r['ticket_price']:.2f}" if r['ticket_price'] > 0 else "Not set",
                    "Compute": f"{r.get('processing_units', 100)} PUs" if r.get('processing_units', 100) < 1000 else f"{r.get('processing_units', 100)//1000} Node ({r.get('processing_units', 100)} PUs)",
                    "Throughput": f"{r.get('qps', 0.0):.1f} runs/s",
                    "Tables": len(r["tables"]),
                    "Rows": r["total_rows"] + r.get("runs", 0),
                    "Graph": "✅ Yes" if r["has_graph"] else "⏳ Pending",
                    "CPU Max": f"{r['cpu_utilization_pct']:.1f}%",
                    "Storage": f"{r.get('storage_mb', 0.0):.2f} MB" if r.get('storage_mb', 0.0) > 0 else "—",
                    "Awards & Badges": badge_str or "—"
                })
        
            leaderboard_df = pd.DataFrame(display_rows)
            st.dataframe(
                leaderboard_df, 
                width='stretch',
                hide_index=True,
                column_config={
                    "Score": st.column_config.ProgressColumn(
                        "Total Score (Max 1250)",
                        min_value=0,
                        max_value=1250,
                        format="%d"
                    ),
                    "App URL": st.column_config.LinkColumn(
                        "Live Web App",
                        display_text="Open ↗"
                    )
                }
            )

        # Awards Showcase
        st.markdown("### 🎖️ Hall of Fame & Badges")
        b_col1, b_col2, b_col3, b_col4, b_col5 = st.columns(5)
    
        # Find award winners
        architects = [r["city"] for r in data if any(b[1] == "Castle Architect" for b in r.get("badges", []))]
        cloud_pilots = [r["city"] for r in data if any(b[1] == "Cloud Pilot" for b in r.get("badges", []))]
        hyperscalers = [r["city"] for r in data if any(b[1] == "Hyperscale Operator" for b in r.get("badges", []))]
        titans = [r["city"] for r in data if any(b[1] == "Throughput Titan" for b in r.get("badges", []))]
        highest_rev = df.sort_values(by="revenue", ascending=False).iloc[0]["city"] if not df.empty and df["revenue"].max() > 0 else "None"
    
        with b_col1:
            st.info(f"**🏰 Castle Architects**\n\n{', '.join(architects) if architects else 'No city has completed the graph yet.'}")
        with b_col2:
            st.success(f"**☁️ Cloud Pilots**\n\n{', '.join(cloud_pilots) if cloud_pilots else 'No Cloud Run apps deployed yet.'}")
        with b_col3:
            st.success(f"**💰 Disney Tycoon**\n\n🏆 **{highest_rev}** (Top revenue)")
        with b_col4:
            st.info(f"**⚡ Hyperscalers**\n\n{', '.join(hyperscalers) if hyperscalers else 'All parks on 100 PUs.'}")
        with b_col5:
            st.warning(f"**🚀 Throughput Titans**\n\n{', '.join(titans) if titans else 'All instances quiet.'}")

    with tab_business:
        st.subheader("🎢 Price Elasticity & Revenue Optimization")
    
        intel_col, pop_col = st.columns([4, 1])
        with intel_col:
            st.markdown("""
            > 🎪 **Disneyland Economic Intelligence Briefing**:
            > Park visitor attendance is governed by **price elasticity**:
            > * **Premium Pricing**: Higher ticket prices yield higher margin per head, but attendance drops.
            > * **Discount Pricing**: Lower ticket prices pack the ride queues up to maximum capacity (100 visitors), but compress gross margins.
            > * **Extreme Risk**: Unreasonable prices empty the queues (*Luxury Trap*), while rock-bottom prices fail to cover attraction operating costs (*Bargain Basement*).
            > 
            > 💡 *Market Guidance: Typical Disneyland attractions charge between **$10.00** and **$30.00**. Prompt your AI agent to optimize ticket pricing to maximize total park revenue!*
            """)
        with pop_col:
            with st.popover("🔐 Facilitator Rules"):
                st.markdown(f"""
                **Confidential Ground Truth**:
                - **Benchmark Price**: `${BENCHMARK_PRICE:.2f}` (80 visitors)
                - **Formula**: `max(0, 1.0 - 0.04 * (Price - 15))`
                - **Sweet Spot**: `$20.00 – $22.50`
                - **Luxury Trap**: `> $35.00` (0 visitors)
                - **Bargain Basement**: `< $8.00`
                """)
    
        chart_col1, chart_col2 = st.columns(2)
    
        with chart_col1:
            st.plotly_chart(build_revenue_chart(df), width='stretch')
        
        with chart_col2:
            st.plotly_chart(build_scatter_chart(df), width='stretch')

    # --- TAB 3: Spanner Telemetry & Load ---
    with tab_spanner:
        st.subheader("⚡ Spanner Health, Throughput & Cluster Capacity")
    
        scale_col1, scale_col2 = st.columns(2)
        with scale_col1:
            st.plotly_chart(build_qps_chart(df), width='stretch')
        
        with scale_col2:
            st.plotly_chart(build_pu_chart(df), width='stretch')
        
        cpu_col1, cpu_col2 = st.columns(2)
        with cpu_col1:
            st.plotly_chart(build_cpu_chart(df), width='stretch')
        
        with cpu_col2:
            st.plotly_chart(build_storage_chart(df), width='stretch')

    # --- TAB 4: DDL & Schema Progress ---
    with tab_schema:
        st.subheader("🗂️ Table Completion Matrix")
    
        if not data:
            st.info("ℹ️ No active participant projects detected yet.")
        else:
            schema_rows = []
            for r in data:
                runs_count = r.get("runs", 0)
                has_run_table = any(ext in " ".join(r["tables"]).lower() for ext in ["run", "execution"]) or runs_count > 0
                cr_pts = r.get("cloud_run_score", 0) + r.get("cloud_run_bonus", 0)
                schema_rows.append({
                    "City": r["city"],
                    "Project": r["project_id"],
                    "DisneylandPark": "✅" if any(t.lower() == "disneylandpark" for t in r["tables"]) else "❌",
                    "Attraction": "✅" if any(t.lower() == "attraction" for t in r["tables"]) else "❌",
                    "Path": "✅" if any(t.lower() == "path" for t in r["tables"]) else "❌",
                    "DisneylandGraph": "✅" if r["has_graph"] else "❌",
                    "Cloud Run App": f"🚀 Live (+{cr_pts} pts)" if r.get("has_cloud_run") else "⏳ Pending",
                    "App URL": r.get("cloud_run_url") if r.get("has_cloud_run") and r.get("cloud_run_url") else None,
                    "AttractionRun (Challenge)": "✅" if has_run_table else "⏳ Pending",
                    "Attraction Runs": runs_count,
                    "Base Rows": r["total_rows"],
                    "Total Rows": r["total_rows"] + runs_count
                })
        
            st.dataframe(
                pd.DataFrame(schema_rows), 
                width='stretch', 
                hide_index=True,
                column_config={
                    "App URL": st.column_config.LinkColumn(
                        "Live Web App",
                        display_text="Open ↗"
                    )
                }
            )

    # --- TAB 5: Disneyland Park Closing Ceremony ---
    with tab_ceremony:
        st.subheader("🎪 Disneyland Park Closing Ceremony Stage")
        
        cur_round = st.session_state.get("ceremony_round", 0)
        is_revealed = st.session_state.get("show_winner_revealed", False)
        
        status_badge = "❄️ Baseline Frozen (Round 0)" if cur_round == 0 else (
            f"⚡ In Progress (Round {cur_round} / {ceremony_engine.TOTAL_ROUNDS})" if cur_round < ceremony_engine.TOTAL_ROUNDS else (
                "👑 Concluded & Champion Crowned" if is_revealed else "🏁 Round 5 Completed (Awaiting Reveal)"
            )
        )

        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #181c2b 0%, #291e3a 100%); border: 2px solid #ff79c6; border-radius: 12px; padding: 22px; margin: 10px 0 20px 0; box-shadow: 0 8px 30px rgba(0,0,0,0.6), 0 0 20px rgba(255, 121, 198, 0.2);">
          <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
            <div>
              <h2 style="margin: 0; color: #ff79c6; font-size: 1.8em;">🎪 Interactive Closing Ceremony Arena</h2>
              <div style="margin-top: 4px; color: #c0caf5; font-size: 1.05em;">
                Dramatic multi-round disaster simulation, live Cloud Spanner DML, and Olympic podium with celebratory music.
              </div>
            </div>
            <span style="background: #3b4261; color: #7dcfff; padding: 6px 16px; border-radius: 20px; font-weight: bold; font-size: 0.9em; border: 1px solid #7dcfff;">
              {status_badge}
            </span>
          </div>
          <div style="margin-top: 14px; color: #a9b1d6; font-size: 0.9em; line-height: 1.4;">
            🛡️ <b>Decoupled & Isolated</b>: The ceremony runs as a pop-up modal on top of the UI with an immutable telemetry snapshot, completely immune to data refresh cycles and background screen reloads.
          </div>
        </div>
        """, unsafe_allow_html=True)

        stage_col1, stage_col2 = st.columns([1.5, 1])
        with stage_col1:
            if st.button("🎪 Launch Closing Ceremony Pop-up", type="primary", width='stretch', key="tab5_launch_btn"):
                st.session_state["ceremony_frozen_snapshot"] = freeze_ceremony_baseline(admin_project, selected_project_ids, filter_inactive, use_mock_data)
                st.session_state["ceremony_modal_open"] = True
                # Rewind to the pre-ceremony state (see the header launch button).
                st.session_state["ceremony_round"] = 0
                st.session_state["show_winner_revealed"] = False
                st.rerun()
        with stage_col2:
            if st.button("⏮️ Reset Ceremony Freeze (Round 0)", width='stretch', key="tab5_reset_btn"):
                st.session_state["ceremony_round"] = 0
                st.session_state["show_winner_revealed"] = False
                st.session_state["ceremony_frozen_snapshot"] = freeze_ceremony_baseline(admin_project, selected_project_ids, filter_inactive, use_mock_data)
                st.toast("Ceremony state reset to Round 0 baseline freeze!", icon="❄️")
                st.rerun()

        # Show current simulation matrix in Tab 5
        base_to_show = st.session_state.get("ceremony_frozen_snapshot")
        if not base_to_show:
            base_to_show = freeze_ceremony_baseline(admin_project, selected_project_ids, filter_inactive, use_mock_data)
        
        # Strictly ensure scope
        base_to_show = [p for p in base_to_show if p.get("project_id") in selected_project_ids]
        if filter_inactive:
            base_to_show = [p for p in base_to_show if ceremony_engine.is_project_active(p)]
        for rank_idx, item in enumerate(base_to_show, start=1):
            item["rank"] = rank_idx

        sim_data, round_meta = ceremony_engine.apply_event_simulation(base_to_show, cur_round)

        st.markdown(f"#### 📊 Ceremony Standings Shift Matrix ({round_meta.get('title', 'Baseline Freeze')})")
        ceremony_rows = []
        for p in sim_data:
            curr_rank = p.get("new_rank", p.get("rank", 1))
            r_icon = "🥇" if curr_rank == 1 else ("🥈" if curr_rank == 2 else ("🥉" if curr_rank == 3 else f"#{curr_rank}"))
            shift_val = p.get("rank_shift", 0)
            if shift_val > 0:
                shift_display = f"🟢 ▲ +{shift_val}"
            elif shift_val < 0:
                shift_display = f"🔴 ▼ {abs(shift_val)}"
            else:
                shift_display = "⚪ ▬ 0"

            score_diff = p.get("score_delta", 0)
            score_display = f"{p['score']} ({'+' if score_diff >= 0 else ''}{score_diff})"
            rev_diff = p.get("revenue_delta", 0.0)
            rev_display = f"${p['revenue']:,.2f} ({'+' if rev_diff >= 0 else ''}${rev_diff:,.2f})"
            badge_str = " ".join([f"{b[0]} {b[1]}" for b in p.get("badges", [])])

            ceremony_rows.append({
                "Rank": r_icon,
                "Shift": shift_display,
                "City": p["city"],
                "Project": p["project_id"],
                "Final Score": score_display,
                "Disney Revenue": rev_display,
                "Incident Report": p.get("round_impact_text", "—"),
                "Badges": badge_str or "—"
            })

        st.dataframe(pd.DataFrame(ceremony_rows), width='stretch', hide_index=True)

# Mount live telemetry board
render_live_telemetry_board(
    admin_project=admin_project,
    selected_project_ids=selected_project_ids,
    filter_inactive=filter_inactive,
    use_mock_data=use_mock_data,
    roaster_enabled=roaster_enabled,
    always_show_roast=always_show_roast
)

# Open Closing Ceremony Modal if Active
if st.session_state.get("ceremony_modal_open", False):
    baseline_snap = st.session_state.get("ceremony_frozen_snapshot")
    if not baseline_snap:
        baseline_snap = freeze_ceremony_baseline(admin_project, selected_project_ids, filter_inactive, use_mock_data)
        st.session_state["ceremony_frozen_snapshot"] = copy.deepcopy(baseline_snap)

    show_closing_ceremony_modal(
        admin_project=admin_project,
        baseline_data=st.session_state["ceremony_frozen_snapshot"],
        selected_project_ids=selected_project_ids,
        filter_inactive=filter_inactive
    )

# Clean up any legacy client-side auto-refresh timers
components.html(
    """
    <script>
    (function() {
        const pWin = window.parent;
        if (pWin && pWin._autoRefreshTimer) {
            clearTimeout(pWin._autoRefreshTimer);
            pWin._autoRefreshTimer = null;
        }
    })();
    </script>
    """,
    height=0,
    width=0
)
