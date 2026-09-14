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
    earliest_run_timestamp: Any = None
) -> Dict[str, Any]:
    """
    Computes composite hackathon score (0 - 1100) including TrueTime speed bonus and awards badges.
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
    
    # 1. Technical Core DDL Points (Max 300 pts)
    core_tables = ["disneylandpark", "attraction", "path"]
    found_core = sum(1 for t in core_tables if any(t == existing.lower() for existing in tables))
    ddl_score = found_core * 100
    
    # 2. Graph DDL Points (Max 100 pts)
    graph_score = 100 if has_graph else 0
    
    # 3. Data Row Points (Max 100 pts)
    # 50 rows = full 100 points
    row_score = min(100, int((row_count / 50.0) * 100))
    
    # 4. Extended DDL (AttractionRun) (Max 100 pts)
    extended_tables = ["attractionrun", "rideexecution", "parkrun"]
    has_extended = any(any(ext in t.lower() for ext in extended_tables) for t in tables) or runs > 0
    extended_score = 100 if has_extended else 0
    
    # 5. Cluster Compute Scaling (Max 100 pts)
    # 100 PUs = 25 pts (baseline)
    # 200 - 400 PUs = 50 pts
    # 500 - 900 PUs = 75 pts
    # >= 1000 PUs (1+ node) = 100 pts
    if processing_units >= 1000:
        scaling_score = 100
    elif processing_units >= 500:
        scaling_score = 75
    elif processing_units >= 200:
        scaling_score = 50
    else:
        scaling_score = 25 if found_core > 0 else 0
        
    # 6. Ingestion Throughput Velocity (Max 100 pts)
    # Scales up to 200 runs/sec
    throughput_score = min(100, int((qps / 200.0) * 100))
    
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
        
    total_score = ddl_score + graph_score + row_score + extended_score + scaling_score + throughput_score + biz_score + speed_bonus
    
    # Badges
    badges = []
    if found_core == 3 and has_graph:
        badges.append(("🏰", "Castle Architect", "Full DDL & Disneyland Property Graph operational"))
    if row_count >= 50:
        badges.append(("🎢", "Rollercoaster Tycoon", f"High catalog data volume ({row_count} rows)"))
    if processing_units >= 500:
        badges.append(("⚡", "Hyperscale Operator", f"Scaled Spanner to {processing_units} PUs"))
    if qps >= 100.0:
        badges.append(("🚀", "Throughput Titan", f"High write velocity ({qps:.1f} runs/sec)"))
    if cpu_util > 50.0:
        badges.append(("🔥", "Spanner Meltdown", f"Pushing Spanner hard ({cpu_util:.1f}% CPU)"))
    if speed_bonus >= 75:
        badges.append(("⚡", "Speed Demon", f"First-mover execution velocity (+{speed_bonus} pts)"))
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
        "badges": badges
    }

