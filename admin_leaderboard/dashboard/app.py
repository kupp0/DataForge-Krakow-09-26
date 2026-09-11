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

always_show_roast = st.sidebar.checkbox("Always Show Roast HUD (Preview)", value=False, help="Keep the funny roast HUD visible permanently for testing or demoing")

if st.sidebar.button("🎭 Roast A Park Now (Re-Roll)"):
    st.session_state["force_roast_refresh"] = True

# 4-Minute Cadence & 1-Minute Active Visibility Engine
CYCLE_SECONDS = 240   # Every 4 minutes (240s)
DISPLAY_SECONDS = 60  # Stays on screen for 1 minute (60s)

now_ts = time.time()
current_cycle_id = int(now_ts) // CYCLE_SECONDS
elapsed_in_cycle = int(now_ts) % CYCLE_SECONDS
is_active_window = elapsed_in_cycle < DISPLAY_SECONDS
remaining_seconds = max(1, DISPLAY_SECONDS - elapsed_in_cycle)

if is_active_window or always_show_roast:
    st.sidebar.markdown(f"🎙️ **Live Roast Status**: 🔴 On-Air ({remaining_seconds}s left)")
else:
    time_until_next = CYCLE_SECONDS - elapsed_in_cycle
    mins = time_until_next // 60
    secs = time_until_next % 60
    st.sidebar.markdown(f"⏳ **Next Roast In**: `{mins}m {secs:02d}s`")

force_roast = st.session_state.pop("force_roast_refresh", False)

@st.cache_data(ttl=CYCLE_SECONDS)
def get_cached_roast(telemetry_data, project_id, cycle_id):
    import llm_announcer
    importlib.reload(llm_announcer)
    return llm_announcer.generate_roast_broadcast(telemetry_data, project_id)

if force_roast:
    get_cached_roast.clear()

roast = get_cached_roast(data, "dataforge26krk-6725", current_cycle_id)

# Render Hover Flashy Message HUD if in active 1-minute window or toggled on
if is_active_window or always_show_roast or force_roast:
    target_city = roast.get("target_city", "Contenders")
    emoji = roast.get("emoji", "🎪")
    joke = roast.get("roast", "")
    rhyme_lines = roast.get("rhyme", "").split("\n")
    rhyme_html = "<br/>".join([f"✨ <em>{l.strip()}</em>" for l in rhyme_lines if l.strip()])
    model_name = roast.get("model", "Gemini 3.8 Flash")
    roast_ts = roast.get("timestamp", time.strftime("%H:%M:%S"))

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
      bottom: 24px;
      right: 24px;
      width: 440px;
      max-width: 90vw;
      background: linear-gradient(135deg, #181926 0%, #281e3a 100%);
      border: 2px solid #ff79c6;
      border-radius: 12px;
      padding: 18px 20px;
      z-index: 999999;
      color: #f8f8f2;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      animation: neonGlow 3s infinite ease-in-out;
      transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.25s ease;
      backdrop-filter: blur(12px);
    }}

    .roast-floating-card:hover {{
      transform: translateY(-6px) scale(1.02);
      box-shadow: 0 16px 45px rgba(0, 0, 0, 0.8), 0 0 35px rgba(255, 121, 198, 0.85) !important;
    }}

    .roast-floating-card:hover .roast-timer-bar {{
      animation-play-state: paused !important;
    }}

    .rhyme-box {{
      background: rgba(255, 215, 0, 0.08);
      border-left: 3px solid #ffd700;
      border-radius: 6px;
      padding: 10px 14px;
      margin: 12px 0 10px 0;
      font-family: 'Georgia', serif;
      color: #f1fa8c;
      font-size: 0.95em;
      line-height: 1.45;
    }}
    </style>

    <div class="roast-floating-card" id="roastCard">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
        <span style="font-size: 0.78em; font-weight: 800; color: #ff79c6; letter-spacing: 1.2px; text-transform: uppercase;">
          🎪 LIVE ROAST BULLETIN • {model_name}
        </span>
        <span style="font-size: 0.75em; color: #8be9fd; font-family: monospace;">⏱️ {roast_ts}</span>
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
        <span style="color: #6272a4;">Every 4 mins</span>
      </div>
      <div style="height: 4px; width: 100%; background: #282a36; border-radius: 2px; margin-top: 6px; overflow: hidden;">
        <div class="roast-timer-bar" style="height: 100%; width: 100%; background: linear-gradient(90deg, #ff79c6, #bd93f9); animation: progressShrink {remaining_seconds}s linear forwards;"></div>
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

