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

import importlib
import metrics
import business_rules
import llm_announcer
import ceremony_engine
importlib.reload(metrics)
importlib.reload(business_rules)
importlib.reload(llm_announcer)
importlib.reload(ceremony_engine)
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

@st.cache_data(ttl=15)
def load_snapshot(mock_mode: bool):
    return get_leaderboard_snapshot(admin_project_id="dataforge26krk-6725", use_mock=mock_mode)

data = load_snapshot(use_mock_data)
df = pd.DataFrame(data)

st.sidebar.markdown("---")
st.sidebar.subheader("🎙️ AI Roaster Control")
roaster_enabled = st.sidebar.toggle(
    "Enable AI Roaster Announcer", 
    value=True, 
    help="Start or stop the automated Gemini 3.8 Flash roast broadcasts and floating toast HUD"
)

if roaster_enabled:
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
else:
    st.sidebar.markdown("🎙️ **Live Roast Status**: ⏸️ Stopped (Disabled)")

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
tab_leaderboard, tab_business, tab_spanner, tab_schema, tab_ceremony = st.tabs([
    "🏆 City Leaderboard & Awards",
    "💰 Disneyland Business Arena (Revenue & Pricing)",
    "⚡ Spanner Telemetry & Load",
    "🗂️ DDL & Schema Progress",
    "🎪 Disneyland Park Closing Ceremony"
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
            "Speed Bonus": f"+{r.get('speed_bonus', 0)} pts" if r.get('speed_bonus', 0) > 0 else "—",
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
                "Total Score (Max 1100)",
                min_value=0,
                max_value=1100,
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

# --- TAB 5: Disneyland Park Closing Ceremony ---
with tab_ceremony:
    st.subheader("🎪 Disneyland Park Closing Ceremony")
    st.markdown("""
    *Execute 5 consecutive dramatic disaster and fortune iterations before declaring the absolute hackathon champion!
    Each round alters standings, simulates or applies live Cloud Spanner DML, and bridges hands-on database engineering concepts with gameplay.*
    """)
    
    if "ceremony_round" not in st.session_state:
        st.session_state["ceremony_round"] = 0
    if "live_dml_logs" not in st.session_state:
        st.session_state["live_dml_logs"] = []
    if "show_winner_revealed" not in st.session_state:
        st.session_state["show_winner_revealed"] = False

    # Interactive Step Controls
    ctrl_col1, ctrl_col2, ctrl_col3, ctrl_col4 = st.columns([1, 1, 1, 2])
    with ctrl_col1:
        if st.button("⏮️ Reset Freeze (Round 0)"):
            st.session_state["ceremony_round"] = 0
            st.session_state["live_dml_logs"] = []
            st.session_state["show_winner_revealed"] = False
            st.rerun()
    with ctrl_col2:
        if st.button("◀ Previous Event", disabled=(st.session_state["ceremony_round"] <= 0)):
            st.session_state["ceremony_round"] = max(0, st.session_state["ceremony_round"] - 1)
            st.session_state["show_winner_revealed"] = False
            st.rerun()
    with ctrl_col3:
        if st.session_state["ceremony_round"] < 5:
            if st.button("Next Event ▶"):
                st.session_state["ceremony_round"] = min(5, st.session_state["ceremony_round"] + 1)
                st.session_state["show_winner_revealed"] = False
                st.rerun()
        else:
            if not st.session_state.get("show_winner_revealed", False):
                if st.button("👑 Show Winner", type="primary"):
                    st.session_state["show_winner_revealed"] = True
                    st.rerun()
            else:
                if st.button("🎉 Replay Celebration", type="primary"):
                    st.session_state["show_winner_revealed"] = True
                    st.rerun()
    with ctrl_col4:
        execute_spanner_live = st.checkbox(
            "⚡ Also execute live DML on Cloud Spanner instances", 
            value=False,
            help="When checked and stepping to Round 1 or 2, executes the actual Spanner DML query against participant instances in parallel."
        )

    cur_round = st.session_state["ceremony_round"]
    
    # Progress Tracker
    st.progress(cur_round / 5.0, text=f"Ceremony Progress: Round {cur_round} / 5")
    
    # If execute_spanner_live was selected and we are on an active round
    if execute_spanner_live and cur_round in [1, 2]:
        if st.button(f"🚀 Dispatch Round {cur_round} DML to Spanner Now"):
            with st.spinner(f"Executing Spanner DML across affected participant projects..."):
                results = ceremony_engine.execute_spanner_round_live(data, cur_round)
                st.session_state["live_dml_logs"] = results
                st.success("Spanner execution complete! Check logs below.")

    # Calculate simulated standings
    sim_data, round_meta = ceremony_engine.apply_event_simulation(data, cur_round)
    
    # Round Announcement Banner
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #1f2335 0%, #292e42 100%); border-left: 5px solid #ff79c6; border-radius: 8px; padding: 16px 20px; margin: 15px 0;">
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <h3 style="margin: 0; color: #ff79c6;">{round_meta.get('icon', '🎪')} {round_meta.get('title', '')}</h3>
        <span style="font-size: 0.85em; background: #3b4261; color: #7aa2f7; padding: 3px 10px; border-radius: 12px; font-weight: bold;">
          ROUND {cur_round} OF 5
        </span>
      </div>
      <h5 style="margin: 6px 0 10px 0; color: #7dcfff;">{round_meta.get('subtitle', '')}</h5>
      <p style="margin: 0; font-size: 1.05em; color: #c0caf5; line-height: 1.5;">
        {round_meta.get('storyline', '')}
      </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Educational Concept Card
    if cur_round > 0:
        with st.expander(f"💡 Cloud Spanner Architecture Deep Dive: {round_meta.get('concept_title', '')}", expanded=True):
            st.markdown(round_meta.get("concept_description", ""))
            st.code(round_meta.get("sql_statement", ""), language="sql")
    
    # Winner Announcement & Podium on Round 5
    if cur_round == 5:
        if not st.session_state.get("show_winner_revealed", False):
            # Pre-reveal suspense teaser with prominent call-to-action button
            st.markdown("""
            <div style="background: linear-gradient(135deg, #1e2030 0%, #24283b 100%); border: 2px dashed #f6c177; border-radius: 12px; padding: 25px; text-align: center; margin: 20px 0;">
              <h2 style="color: #f6c177; margin: 0 0 8px 0;">🏁 Round 5 Concluded • The Stage Is Set!</h2>
              <p style="color: #c0caf5; font-size: 1.1em; margin: 0 0 15px 0;">
                All 5 rounds of theme park events and Spanner dynamic calculations are complete. Click below to reveal the podium and celebrate the top 3 winners!
              </p>
            </div>
            """, unsafe_allow_html=True)
            if st.button("👑 Show Winner & Reveal Top 3 Podium", type="primary", use_container_width=True):
                st.session_state["show_winner_revealed"] = True
                st.rerun()
        else:
            # Multi-layer Confetti Celebration Animation
            st.balloons()
            
            # 1. Full-screen HTML5 Canvas Confetti Cannon
            components.html("""
            <script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.9.3/dist/confetti.browser.min.js"></script>
            <script>
              var duration = 5 * 1000;
              var animationEnd = Date.now() + duration;
              var colors = ['#ffd700', '#c0c0c0', '#cd7f32', '#ff5555', '#50fa7b', '#8be9fd', '#bd93f9'];

              (function frame() {
                var timeLeft = animationEnd - Date.now();
                if (timeLeft <= 0) return;
                
                confetti({
                  particleCount: 7,
                  angle: 60,
                  spread: 80,
                  origin: { x: 0, y: 0.7 },
                  colors: colors
                });
                confetti({
                  particleCount: 7,
                  angle: 120,
                  spread: 80,
                  origin: { x: 1, y: 0.7 },
                  colors: colors
                });
                confetti({
                  particleCount: 4,
                  angle: 90,
                  spread: 120,
                  origin: { x: 0.5, y: 0.2 },
                  colors: colors
                });

                requestAnimationFrame(frame);
              }());
            </script>
            """, height=0)
            
            # 2. Pure CSS Falling Confetti Streamers (air-gap safe fallback)
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
                z-index: 9999;
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
            
            # 3. Grand Olympic Podium Celebrating All Top 3 Places
            p_first = sim_data[0] if len(sim_data) >= 1 else None
            p_second = sim_data[1] if len(sim_data) >= 2 else None
            p_third = sim_data[2] if len(sim_data) >= 3 else None
            
            st.markdown("""
            <div style="background: linear-gradient(135deg, #1f2335 0%, #292e42 50%, #1a1b26 100%); border-radius: 16px; padding: 25px; text-align: center; margin: 20px 0; border: 2px solid #ffd700; box-shadow: 0 10px 40px rgba(255, 215, 0, 0.25);">
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
            
            # Silver: 2nd Place (Left Column)
            with pod_left:
                if p_second:
                    shift_sec = p_second.get("rank_shift", 0)
                    shift_badge_sec = f"<span style='color: #50fa7b;'>▲ +{shift_sec}</span>" if shift_sec > 0 else (f"<span style='color: #ff5555;'>▼ {abs(shift_sec)}</span>" if shift_sec < 0 else "<span style='color: #8be9fd;'>▬ Stable</span>")
                    st.markdown(f"""
                    <div style="background: linear-gradient(180deg, rgba(192,192,192,0.18) 0%, #1e222d 100%); border: 2px solid #c0c0c0; border-radius: 12px; padding: 18px; text-align: center; margin-top: 35px; box-shadow: 0 8px 24px rgba(192,192,192,0.2);">
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
            
            # Gold: 1st Place (Center Column - Elevated & Crowned)
            with pod_center:
                if p_first:
                    shift_fir = p_first.get("rank_shift", 0)
                    shift_badge_fir = f"<span style='color: #50fa7b;'>▲ +{shift_fir}</span>" if shift_fir > 0 else (f"<span style='color: #ff5555;'>▼ {abs(shift_fir)}</span>" if shift_fir < 0 else "<span style='color: #8be9fd;'>▬ Maintained #1</span>")
                    st.markdown(f"""
                    <div style="background: linear-gradient(180deg, rgba(255,215,0,0.25) 0%, #1e222d 100%); border: 3px solid #ffd700; border-radius: 14px; padding: 22px; text-align: center; box-shadow: 0 12px 35px rgba(255,215,0,0.35);">
                      <div style="font-size: 3.2em;">👑 🥇</div>
                      <div style="font-size: 1.0em; font-weight: 900; color: #ffd700; letter-spacing: 1.5px;">1ST PLACE • GRAND CHAMPION</div>
                      <h1 style="margin: 6px 0 2px 0; color: #ffffff; font-size: 2.2em;">{p_first['city']}</h1>
                      <div style="font-size: 0.85em; color: #a9b1d6; font-family: monospace;">{p_first['project_id']}</div>
                      <div style="margin: 14px 0 8px 0; font-size: 1.8em; font-weight: 900; color: #ffd700;">{p_first['score']:,} pts</div>
                      <div style="font-size: 1.1em; color: #50fa7b; font-weight: 700;">${p_first['revenue']:,.2f}</div>
                      <div style="margin-top: 8px; font-size: 0.9em;">Ceremony Net Shift: {shift_badge_fir}</div>
                      <div style="margin-top: 12px; padding: 8px; background: rgba(255,215,0,0.12); border: 1px solid #ffd700; border-radius: 8px; font-size: 0.85em; color: #fff;">
                        ⚡ <b>Cloud Spanner Architect Titan:</b> Dominated distributed throughput, dynamic elasticity, and TrueTime speed!
                      </div>
                    </div>
                    """, unsafe_allow_html=True)
            
            # Bronze: 3rd Place (Right Column)
            with pod_right:
                if p_third:
                    shift_thi = p_third.get("rank_shift", 0)
                    shift_badge_thi = f"<span style='color: #50fa7b;'>▲ +{shift_thi}</span>" if shift_thi > 0 else (f"<span style='color: #ff5555;'>▼ {abs(shift_thi)}</span>" if shift_thi < 0 else "<span style='color: #8be9fd;'>▬ Stable</span>")
                    st.markdown(f"""
                    <div style="background: linear-gradient(180deg, rgba(205,127,50,0.18) 0%, #1e222d 100%); border: 2px solid #cd7f32; border-radius: 12px; padding: 18px; text-align: center; margin-top: 55px; box-shadow: 0 8px 24px rgba(205,127,50,0.2);">
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

    # Kahoot-Style Round Highlights & Analytics
    st.markdown("---")
    st.subheader("🔥 Round Movement & Impact Highlights")
    
    climbers = [p for p in sim_data if p.get("rank_shift", 0) > 0]
    climbers.sort(key=lambda x: x.get("rank_shift", 0), reverse=True)
    
    fallers = [p for p in sim_data if p.get("rank_shift", 0) < 0]
    fallers.sort(key=lambda x: x.get("rank_shift", 0))
    
    impacted_parks = [p for p in sim_data if p.get("revenue_delta", 0.0) != 0.0 or p.get("score_delta", 0) != 0]
    net_revenue_delta = sum(p.get("revenue_delta", 0.0) for p in sim_data)
    total_rank_changes = len(climbers) + len(fallers)
    
    # 1. Kahoot KPI Scorecard
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

    # 2. Kahoot Top-3 Podium
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

    # 3. Interactive Plotly Impact Visualizations
    st.markdown("#### 📊 Movement & Impact Analytics")
    ch_col1, ch_col2 = st.columns(2)
    
    with ch_col1:
        # Leaderboard Movement (Rank Shifts)
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
        st.plotly_chart(fig_shift, use_container_width=True)
        
    with ch_col2:
        # Financial Impact ($ Delta)
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
        st.plotly_chart(fig_fin, use_container_width=True)

    # 4. Detailed Partition: Hit vs Safe Parks
    with st.expander("🔍 Filter Parks by Incident Status (Hit vs Safe)", expanded=False):
        sub_col1, sub_col2 = st.columns(2)
        with sub_col1:
            st.markdown("##### 💥 Parks Incurring Damage or Fines")
            damaged = [p for p in sim_data if p.get("revenue_delta", 0.0) < 0 or p.get("score_delta", 0) < 0]
            if damaged:
                for d in damaged:
                    shift_icon = f"▲ +{d['rank_shift']}" if d['rank_shift'] > 0 else (f"▼ {abs(d['rank_shift'])}" if d['rank_shift'] < 0 else "▬ 0")
                    st.markdown(f"• **{d['city']}** (`{d['project_id']}`): {d.get('round_impact_text', '')} | *Shift: {shift_icon}*")
            else:
                st.info("No parks incurred damage in this round.")
        with sub_col2:
            st.markdown("##### 🛡️ Safe or Rewarded Parks")
            safe = [p for p in sim_data if p.get("revenue_delta", 0.0) >= 0 and p.get("score_delta", 0) >= 0]
            if safe:
                for s in safe:
                    shift_icon = f"▲ +{s['rank_shift']}" if s['rank_shift'] > 0 else (f"▼ {abs(s['rank_shift'])}" if s['rank_shift'] < 0 else "▬ 0")
                    st.markdown(f"• **{s['city']}** (`{s['project_id']}`): {s.get('round_impact_text', '')} | *Shift: {shift_icon}*")
            else:
                st.info("All parks were hit.")

    # Shift Leaderboard Table
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
        
    st.dataframe(
        pd.DataFrame(ceremony_rows),
        use_container_width=True,
        hide_index=True
    )
    
    # Show live Spanner DML execution receipt if available
    if st.session_state.get("live_dml_logs"):
        with st.expander("📝 Cloud Spanner Live DML Execution Receipt", expanded=True):
            st.dataframe(pd.DataFrame(st.session_state["live_dml_logs"]), use_container_width=True, hide_index=True)

# Auto-refresh loop
if auto_refresh:
    time.sleep(refresh_interval)
    st.rerun()

