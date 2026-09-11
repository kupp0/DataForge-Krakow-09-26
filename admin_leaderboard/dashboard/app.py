"""
Disneyland Spanner Hackathon: Admin Leaderboard & Live Telemetry Dashboard
Streamlit Application connecting to BigQuery and Cloud Monitoring API.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import time

import importlib
import metrics
import business_rules
import llm_announcer
importlib.reload(metrics)
importlib.reload(business_rules)
importlib.reload(llm_announcer)
from metrics import get_leaderboard_snapshot
from business_rules import BENCHMARK_PRICE, calculate_elasticity_demand
from llm_announcer import generate_flash_commentary

# Streamlit Page Config
st.set_page_config(
    page_title="Disneyland Spanner Global Leaderboard",
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
</style>
""", unsafe_allow_html=True)

# Sidebar Controls
st.sidebar.title("🏰 Admin Command Center")
st.sidebar.markdown("**Admin Project**: `dataforge26krk-6725`")
st.sidebar.markdown("**Database**: `disneyland/agent-lab`")

auto_refresh = st.sidebar.checkbox("Auto-Refresh (every 20s)", value=False)
refresh_interval = 20

use_mock_data = st.sidebar.checkbox("Simulation / Mock Mode", value=False, help="Use deterministic simulation for UI testing before hackathon kickoff")

if st.sidebar.button("🔄 Refresh Data Now"):
    st.cache_data.clear()

if st.sidebar.button("🎙️ Re-generate Flash Commentary"):
    st.session_state["force_announcer_refresh"] = True

@st.cache_data(ttl=15)
def load_snapshot(mock_mode: bool):
    return get_leaderboard_snapshot(admin_project_id="dataforge26krk-6725", use_mock=mock_mode)

data = load_snapshot(use_mock_data)
df = pd.DataFrame(data)

# Header
st.title("🎢 Disneyland Spanner Hackathon: Global Leaderboard")
st.markdown("Real-time telemetry, Spanner performance metrics, and gamified Disneyland park revenue optimization across all participant cities.")

# Live AI Park Announcer Flash Commentary
force_announcer = st.session_state.pop("force_announcer_refresh", False)

@st.cache_data(ttl=60)
def get_cached_flash_commentary(telemetry_data, project_id, bust_token=0):
    return generate_flash_commentary(telemetry_data, project_id)

if force_announcer:
    get_cached_flash_commentary.clear()

flash_msg, flash_ts, flash_model = get_cached_flash_commentary(data, "dataforge26krk-6725")

st.markdown(f"""
<div style="background: linear-gradient(135deg, #181c24 0%, #281e3a 100%); border-left: 5px solid #ff79c6; border-radius: 8px; padding: 14px 18px; margin: 12px 0 18px 0; box-shadow: 0 4px 14px rgba(0,0,0,0.35);">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
        <span style="font-size: 0.85em; font-weight: bold; color: #ff79c6; letter-spacing: 1px; text-transform: uppercase;">
            🎙️ Live Park Announcer • {flash_model}
        </span>
        <span style="font-size: 0.8em; color: #8be9fd; font-family: monospace;">
            ⏱️ {flash_ts}
        </span>
    </div>
    <div style="font-size: 1.1em; color: #f8f8f2; font-style: italic; line-height: 1.45;">
        "{flash_msg}"
    </div>
</div>
""", unsafe_allow_html=True)

# Summary Metrics Row
col1, col2, col3, col4, col5 = st.columns(5)

total_participants = len(df)
top_city = df.iloc[0]["city"] if not df.empty else "N/A"
total_rows = df["total_rows"].sum() if not df.empty else 0
total_revenue = df["revenue"].sum() if not df.empty else 0.0
peak_cpu = df["cpu_utilization_pct"].max() if not df.empty else 0.0

with col1:
    st.metric("Active Cities", f"{total_participants} Parks")
with col2:
    st.metric("Leading City", f"🥇 {top_city}")
with col3:
    st.metric("Total Spanner Rows", f"{total_rows:,}")
with col4:
    st.metric("Total Disney Revenue", f"${total_revenue:,.2f}")
with col5:
    st.metric("Peak Spanner CPU", f"{peak_cpu:.1f}%")

st.divider()

# Tabs
tab_leaderboard, tab_business, tab_spanner, tab_schema = st.tabs([
    "🏆 City Leaderboard & Awards",
    "💰 Disneyland Business Arena (Revenue & Pricing)",
    "⚡ Spanner Telemetry & Load",
    "🗂️ DDL & Schema Progress"
])

# --- TAB 1: Main Leaderboard ---
with tab_leaderboard:
    st.subheader("🏁 Global City Standings")
    
    # Format table for display
    display_rows = []
    for r in data:
        rank_icon = "🥇" if r["rank"] == 1 else ("🥈" if r["rank"] == 2 else ("🥉" if r["rank"] == 3 else f"#{r['rank']}"))
        badge_str = " ".join([f"{b[0]} {b[1]}" for b in r.get("badges", [])])
        
        display_rows.append({
            "Rank": rank_icon,
            "City": r["city"],
            "Project": r["project_id"],
            "Score": r["score"],
            "Revenue": f"${r['revenue']:,.2f}",
            "Ticket Price": f"${r['ticket_price']:.2f}" if r['ticket_price'] > 0 else "Not set",
            "Compute": f"{r.get('processing_units', 100)} PUs" if r.get('processing_units', 100) < 1000 else f"{r.get('processing_units', 100)//1000} Node ({r.get('processing_units', 100)} PUs)",
            "Throughput": f"{r.get('qps', 0.0):.1f} runs/s",
            "Tables": len(r["tables"]),
            "Rows": r["total_rows"],
            "Graph": "✅ Yes" if r["has_graph"] else "⏳ Pending",
            "CPU Max": f"{r['cpu_utilization_pct']:.1f}%",
            "Awards & Badges": badge_str or "—"
        })
    
    leaderboard_df = pd.DataFrame(display_rows)
    st.dataframe(
        leaderboard_df, 
        use_container_width=True,
        hide_index=True,
        column_config={
            "Score": st.column_config.ProgressColumn(
                "Total Score (1000)",
                min_value=0,
                max_value=1000,
                format="%d"
            )
        }
    )

    # Awards Showcase
    st.markdown("### 🎖️ Hall of Fame & Badges")
    b_col1, b_col2, b_col3, b_col4 = st.columns(4)
    
    # Find award winners
    architects = [r["city"] for r in data if any(b[1] == "Castle Architect" for b in r.get("badges", []))]
    hyperscalers = [r["city"] for r in data if any(b[1] == "Hyperscale Operator" for b in r.get("badges", []))]
    titans = [r["city"] for r in data if any(b[1] == "Throughput Titan" for b in r.get("badges", []))]
    meltdowns = [r["city"] for r in data if any(b[1] == "Spanner Meltdown" for b in r.get("badges", []))]
    highest_rev = df.sort_values(by="revenue", ascending=False).iloc[0]["city"] if not df.empty and df["revenue"].max() > 0 else "None"
    
    with b_col1:
        st.info(f"**🏰 Castle Architects**\n\n{', '.join(architects) if architects else 'No city has completed the graph yet.'}")
    with b_col2:
        st.success(f"**💰 Disney Tycoon**\n\n🏆 **{highest_rev}** (Top revenue)")
    with b_col3:
        st.info(f"**⚡ Hyperscalers (Scaled PUs)**\n\n{', '.join(hyperscalers) if hyperscalers else 'All parks on 100 PUs.'}")
    with b_col4:
        st.warning(f"**🔥 Stress Testers (High Load)**\n\n{', '.join(meltdowns) if meltdowns else (', '.join(titans) if titans else 'All Spanner instances quiet.')}")

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
        st.plotly_chart(fig_rev, use_container_width=True)
        
    with chart_col2:
        fig_scatter = px.scatter(
            df[df["runs"] > 0] if not df[df["runs"] > 0].empty else df,
            x="ticket_price",
            y="revenue",
            size="visitors",
            color="city",
            hover_name="city",
            title="Ticket Price vs Revenue vs Total Visitors",
            labels={"ticket_price": "Ticket Price ($)", "revenue": "Revenue ($)"}
        )
        st.plotly_chart(fig_scatter, use_container_width=True)

# --- TAB 3: Spanner Telemetry & Load ---
with tab_spanner:
    st.subheader("⚡ Spanner Health, Throughput & Cluster Capacity")
    
    scale_col1, scale_col2 = st.columns(2)
    with scale_col1:
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
        st.plotly_chart(fig_qps, use_container_width=True)
        
    with scale_col2:
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
        st.plotly_chart(fig_pu, use_container_width=True)
        
    cpu_col1, cpu_col2 = st.columns(2)
    with cpu_col1:
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
        st.plotly_chart(fig_cpu, use_container_width=True)
        
    with cpu_col2:
        fig_storage = px.bar(
            df.sort_values("storage_mb", ascending=False),
            x="city",
            y="storage_mb",
            color="storage_mb",
            color_continuous_scale="Blues",
            title="Spanner Storage Consumption (MB)",
            labels={"storage_mb": "Storage (MB)", "city": "City"}
        )
        fig_storage.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig_storage, use_container_width=True)

# --- TAB 4: DDL & Schema Progress ---
with tab_schema:
    st.subheader("🗂️ Table Completion Matrix")
    
    schema_rows = []
    for r in data:
        schema_rows.append({
            "City": r["city"],
            "Project": r["project_id"],
            "DisneylandPark": "✅" if any(t.lower() == "disneylandpark" for t in r["tables"]) else "❌",
            "Attraction": "✅" if any(t.lower() == "attraction" for t in r["tables"]) else "❌",
            "Path": "✅" if any(t.lower() == "path" for t in r["tables"]) else "❌",
            "DisneylandGraph": "✅" if r["has_graph"] else "❌",
            "AttractionRun (Challenge)": "✅" if any(ext in " ".join(r["tables"]).lower() for ext in ["run", "execution"]) or r["runs"] > 0 else "⏳ Pending",
            "Total Rows": r["total_rows"]
        })
    
    st.dataframe(pd.DataFrame(schema_rows), use_container_width=True, hide_index=True)

# Auto-refresh loop
if auto_refresh:
    time.sleep(refresh_interval)
    st.rerun()

