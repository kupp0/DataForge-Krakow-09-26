"""
Disneyland Hackathon Gamification & Business KPI Engine
Computes price elasticity, attraction revenue, composite scores, and humorous awards.
"""
from typing import Dict, List, Any

# Realistic Theme Park Operational & Capacity Constraints
BENCHMARK_PRICE = 15.0
MIN_REALISTIC_PRICE = 5.0
MAX_REALISTIC_PRICE = 40.0
MAX_CAPACITY_PER_RUN = 100
MAX_PARK_DAILY_CAPACITY = 85_000    # Peak physical guest admission capacity per park (Disneyland benchmark)
BASE_FACILITY_OVERHEAD = 120_000.0  # Daily baseline park operational overhead (cast members, utilities)
MARGINAL_RUN_COST = 0.50           # Variable maintenance & power cost per ride execution ($0.50/run)
MAX_REVENUE_CEILING = 3_500_000.0   # Hard physical economic ceiling for single-park daily revenue ($3.5M)

def calculate_elasticity_demand(ticket_price: float) -> float:
    """
    Computes visitor demand ratio based on ticket price elasticity.
    Lower price = more people per run (up to max capacity).
    Higher price = fewer people per run.
    At price >= $40, demand drops to 0.
    """
    if ticket_price <= 0:
        return 0.0
    # Clamped elasticity model centered at $15 benchmark
    # Price $15 -> demand 1.0 (80 visitors out of 100 capacity)
    # Price $5  -> demand 1.25 (100 visitors)
    # Price $25 -> demand 0.60 (48 visitors)
    # Price >= $40 -> demand 0.00 (0 visitors)
    clamped_price = max(MIN_REALISTIC_PRICE, min(MAX_REALISTIC_PRICE, ticket_price))
    demand_factor = max(0.0, min(1.25, 1.0 - 0.04 * (clamped_price - BENCHMARK_PRICE)))
    if ticket_price > MAX_REALISTIC_PRICE:
        demand_factor = 0.0
    return demand_factor

def calculate_attraction_run_metrics(ticket_price: float, runs: int, raw_visitors: int = 0) -> Dict[str, float]:
    """
    Calculates effective visitors, gross revenue, operating costs, and net profit
    subject to physical park capacity constraints and realistic marginal costs.
    """
    if runs <= 0:
        return {"effective_visitors": 0, "revenue": 0.0, "cost": 0.0, "profit": 0.0, "avg_price": 0.0, "runs": 0}
    
    demand = calculate_elasticity_demand(ticket_price)
    base_turnout = 80.0
    effective_visitors_per_run = min(float(MAX_CAPACITY_PER_RUN), base_turnout * demand)
    
    # If participant supplied visitor counts, blend them with the elasticity constraint
    if raw_visitors > 0:
        actual_per_run = min(float(raw_visitors) / max(1, runs), float(MAX_CAPACITY_PER_RUN)) * (demand if ticket_price > BENCHMARK_PRICE else 1.0)
    else:
        actual_per_run = effective_visitors_per_run
        
    # Physical Park Daily Capacity Constraint (capped at 85,000 guests)
    unconstrained_visitors = int(actual_per_run * runs)
    total_visitors = min(MAX_PARK_DAILY_CAPACITY, unconstrained_visitors)
    
    # Base admission revenue from physical guests
    clamped_price = max(0.0, min(50.0, ticket_price))
    admission_revenue = total_visitors * clamped_price

    # High-Throughput Operations Bonus: Beyond base capacity, high run volume represents
    # ride turnover efficiency and ancillary concession/merchandise micro-spend ($0.025 per run)
    extra_run_bonus = max(0.0, (runs - 1_000) * 0.025)
    
    # Bounded total park revenue (realistic maximum of $3.5M per park)
    revenue = round(min(MAX_REVENUE_CEILING, admission_revenue + extra_run_bonus), 2)
    
    # Realistic operational cost: Base park facility overhead + marginal cost per ride run
    cost = round(BASE_FACILITY_OVERHEAD + (runs * MARGINAL_RUN_COST), 2)
    profit = round(revenue - cost, 2)
    
    return {
        "effective_visitors": total_visitors,
        "revenue": revenue,
        "cost": cost,
        "profit": profit,
        "avg_price": ticket_price,
        "runs": runs
    }

def compute_participant_score(
    data: Dict[str, Any], 
    max_revenue_in_event: float = 1.0,
    earliest_run_timestamp: Any = None,
    earliest_cloud_run_timestamp: Any = None,
    cloud_run_rank: int = 0
) -> Dict[str, Any]:
    """
    Computes composite hackathon score (0 - 1450) including TrueTime and Cloud Run speed bonuses, and awards badges.
    """
    tables = data.get("tables", [])
    row_count = data.get("total_rows", 0)
    has_graph = data.get("has_graph", False)
    cpu_util = data.get("cpu_utilization_pct", 0.0)
    revenue = data.get("revenue", 0.0)
    ticket_price = data.get("ticket_price", 0.0)
    processing_units = data.get("processing_units", 100)
    qps = data.get("qps", 0.0)
    runs = data.get("runs", 0)
    first_run_timestamp = data.get("first_run_timestamp")
    has_cloud_run = data.get("has_cloud_run", False)
    cloud_run_status = data.get("cloud_run_status", "NONE")
    cr_create_time = data.get("cloud_run_create_time")
    has_embeddings = data.get("has_embeddings", False)
    embedded_count = data.get("embedded_count", 0)
    
    # 1. Technical Core DDL Points (Max 300 pts)
    core_tables = ["disneylandpark", "attraction", "path"]
    found_core = sum(1 for t in core_tables if any(t == existing.lower() for existing in tables))
    ddl_score = found_core * 100
    
    # 2. Graph DDL Points (Max 200 pts)
    # Weighted as a headline Phase 2 deliverable. This was 100 while the closing
    # ceremony's Jubilee round handed out up to +310 more for having a graph;
    # that round has been removed, so the base score now carries the full weight.
    graph_score = 200 if has_graph else 0
    
    # 3. Data Row Points (Max 100 pts)
    # 50 rows = full 100 points
    row_score = min(100, int((row_count / 50.0) * 100))
    
    # 4. Extended DDL (AttractionRun) (Max 100 pts)
    extended_tables = ["attractionrun", "rideexecution", "parkrun"]
    has_extended = any(any(ext in t.lower() for ext in extended_tables) for t in tables) or runs > 0
    extended_score = 100 if has_extended else 0
    
    # 5. Cluster Compute Scaling (Max 100 pts) - utilisation aware.
    #
    # Provisioning capacity is not an achievement; driving it is. This used to
    # award a flat 100 points for >= 1000 PUs with no utilisation test, which
    # paid participants to max out their instance and leave it idle - and then
    # the closing ceremony fined them for exactly that. Size still sets the
    # ceiling, but observed peak CPU decides how much of it is earned.
    if found_core == 0:
        scaling_score = 0
    else:
        if processing_units >= 1000:
            size_tier = 100
        elif processing_units >= 500:
            size_tier = 75
        elif processing_units >= 200:
            size_tier = 50
        else:
            size_tier = 25

        if cpu_util >= 65.0:
            util_factor = 1.0
        elif cpu_util >= 40.0:
            util_factor = 0.8
        elif cpu_util >= 20.0:
            util_factor = 0.55
        elif cpu_util >= 5.0:
            util_factor = 0.35
        else:
            util_factor = 0.25

        # 100 PUs is the Spanner floor, not a sizing decision, so a quiet
        # minimum instance keeps its baseline rather than being penalised.
        if processing_units <= 100:
            scaling_score = 25
        else:
            scaling_score = int(size_tier * util_factor)
        
    # 6. Ingestion Throughput Velocity (Max 100 pts)
    #
    # Tiered, not linear. Participants build their own load generators, so
    # achieved write rates span orders of magnitude: a batched writer commits
    # thousands of rows/sec while a row-at-a-time client manages tens. The old
    # linear `qps / 200` curve saturated at 200 and stopped discriminating
    # between a competent client and an exceptional one.
    if qps >= 2000:
        throughput_score = 100
    elif qps >= 800:
        throughput_score = 85
    elif qps >= 300:
        throughput_score = 70
    elif qps >= 100:
        throughput_score = 50
    elif qps >= 25:
        throughput_score = 30
    elif qps > 0:
        throughput_score = 10
    else:
        throughput_score = 0
    
    # 7. Business Revenue Optimization (Max 200 pts)
    if max_revenue_in_event > 0 and revenue > 0:
        biz_score = min(200, int((revenue / max_revenue_in_event) * 200))
    else:
        biz_score = 0

    # 8. TrueTime Speed Velocity Bonus (Max 100 bonus pts)
    # Rewards early achievement using Spanner commit timestamps to prevent uniform 100% ties.
    speed_bonus = 0
    if runs > 0 and first_run_timestamp:
        if earliest_run_timestamp is not None:
            try:
                diff_sec = (first_run_timestamp - earliest_run_timestamp).total_seconds()
                diff_min = max(0.0, diff_sec / 60.0)
                # 100 bonus points decaying by 2.5 pts per minute elapsed from the earliest finisher
                speed_bonus = max(0, int(100 - diff_min * 2.5))
            except Exception:
                speed_bonus = 50
        else:
            speed_bonus = 100

    # 9. Cloud Run Application Deployment (Max 100 base pts)
    cloud_run_score = 0
    if has_cloud_run:
        if cloud_run_status == "READY":
            cloud_run_score = 100
        elif cloud_run_status == "DEGRADED":
            cloud_run_score = 75
        elif cloud_run_status == "DEPLOYING":
            cloud_run_score = 50
        else:
            cloud_run_score = 100

    # 10. Cloud Run Pioneer / Relative Speed Bonus (Max 50 bonus pts)
    # Rewards early deployments with relative score deviation across the fleet.
    cloud_run_bonus = 0
    if has_cloud_run:
        rank_bonuses = {1: 50, 2: 40, 3: 30, 4: 20, 5: 15}
        if cloud_run_rank in rank_bonuses:
            base_rank_bonus = rank_bonuses[cloud_run_rank]
        elif 0 < cloud_run_rank <= 10:
            base_rank_bonus = 10
        elif cloud_run_rank > 10:
            base_rank_bonus = 5
        else:
            base_rank_bonus = 25

        if cr_create_time and earliest_cloud_run_timestamp is not None:
            try:
                diff_sec = (cr_create_time - earliest_cloud_run_timestamp).total_seconds()
                diff_min = max(0.0, diff_sec / 60.0)
                time_decay = int(diff_min * 0.5)
                cloud_run_bonus = max(5, base_rank_bonus - time_decay)
            except Exception:
                cloud_run_bonus = base_rank_bonus
        else:
            cloud_run_bonus = base_rank_bonus
        
    # 11. Vector Embedding Stretch Goal (Max 100 bonus pts)
    #
    # The Embedding ARRAY<FLOAT32>(vector_length=>768) column ships in the
    # mandatory schema, but populating it is nobody's assigned task - it needs
    # a Vertex AI text-embedding call per attraction and a write back into
    # Spanner. Sized as a bonus rather than a core component on purpose: only a
    # handful of participants will attempt it, and a hidden criterion large
    # enough to decide the winner would be unfair to everyone who simply
    # followed the guide.
    #
    # metrics.py has already validated coverage and vector diversity, so a
    # table full of identical zero vectors does not qualify.
    embedding_score = 100 if has_embeddings else 0

    total_score = (
        ddl_score + graph_score + row_score + extended_score + 
        scaling_score + throughput_score + biz_score + speed_bonus + 
        cloud_run_score + cloud_run_bonus + embedding_score
    )
    
    # Badges
    badges = []
    if found_core == 3 and has_graph:
        badges.append(("🏰", "Castle Architect", "Full DDL & Disneyland Property Graph operational"))
    if row_count >= 50:
        badges.append(("🎢", "Rollercoaster Tycoon", f"High catalog data volume ({row_count} rows)"))
    if processing_units >= 500 and cpu_util >= 40.0:
        badges.append(("⚡", "Hyperscale Operator", f"Scaled Spanner to {processing_units} PUs and drove it to {cpu_util:.0f}% CPU"))
    if 65.0 <= cpu_util < 90.0:
        badges.append(("🎯", "Right-Sized", f"Capacity matched to load ({cpu_util:.0f}% CPU)"))
    if processing_units > 300 and cpu_util < 15.0:
        badges.append(("💸", "Idle Fleet", f"{processing_units} PUs provisioned, only {cpu_util:.0f}% CPU used"))
    if qps >= 100.0:
        badges.append(("🚀", "Throughput Titan", f"High write velocity ({qps:.1f} runs/sec)"))
    if cpu_util > 50.0:
        badges.append(("🔥", "Spanner Meltdown", f"Pushing Spanner hard ({cpu_util:.1f}% CPU)"))
    if has_cloud_run:
        badges.append(("☁️", "Cloud Pilot", "Disneyland Navigator deployed & live on Cloud Run"))
    if cloud_run_bonus >= 40:
        badges.append(("⚡", "Sonic Deployer", f"Pioneer Cloud Run deployment (+{cloud_run_bonus} pts)"))
    if speed_bonus >= 75:
        badges.append(("⚡", "Speed Demon", f"First-mover execution velocity (+{speed_bonus} pts)"))
    if has_embeddings:
        badges.append(("🧠", "Vector Visionary", f"Generated real 768-dim embeddings for {embedded_count} attractions"))
    if found_core == 0 and row_count == 0:
        badges.append(("💤", "Sleeping Beauty", "Park is quiet, no tables created yet"))
    if ticket_price > 35.0:
        badges.append(("💎", "Luxury Trap", f"Price too high (${ticket_price:.1f}), empty rides!"))
    elif 0 < ticket_price < 8.0:
        badges.append(("🏷️", "Bargain Basement", f"Tickets underpriced (${ticket_price:.1f}), leaving money on table"))
        
    return {
        "score": total_score,
        "ddl_score": ddl_score,
        "graph_score": graph_score,
        "row_score": row_score,
        "extended_score": extended_score,
        "scaling_score": scaling_score,
        "throughput_score": throughput_score,
        "biz_score": biz_score,
        "speed_bonus": speed_bonus,
        "cloud_run_score": cloud_run_score,
        "cloud_run_bonus": cloud_run_bonus,
        "cloud_run_total": cloud_run_score + cloud_run_bonus,
        "embedding_score": embedding_score,
        "badges": badges
    }

