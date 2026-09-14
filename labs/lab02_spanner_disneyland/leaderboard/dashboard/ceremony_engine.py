"""
Disneyland Hackathon: Disneyland Park Closing Ceremony Engine
Implements 5 interactive dramatic event rounds that alter leaderboard standings
with educational Spanner architecture concepts and live DML execution capabilities.
"""
import copy
import logging
from typing import Dict, List, Any, Tuple
from concurrent.futures import ThreadPoolExecutor

import metrics

CEREMONY_ROUNDS = [
    {
        "round_id": 1,
        "icon": "🌧️",
        "title": "Round 1: Monsoon over the Magic Kingdom",
        "subtitle": "The Great Rainstorm & Dynamic Refund Discounts",
        "storyline": (
            "A sudden torrential thunderstorm strikes 50% of the theme parks! Outdoor attractions "
            "and rollercoasters are drenched, forcing park directors to issue an emergency 10% ticket refund discount. "
            "Furthermore, parks with exorbitant ticket prices ($TicketPrice > $25) face angry guest chargebacks and an extra 3% storm surcharge fine!"
        ),
        "concept_title": "1. Mass DML with Modulo Hashing on Bit-Reversed Primary Keys",
        "concept_description": (
            "In distributed databases like Cloud Spanner, updating records naively can cause severe hotspotting "
            "if primary keys are monotonically sequential. Because AttractionRun's RunID uses BIT_REVERSED_POSITIVE, "
            "MOD(ABS(RunID), 10) < 5 uniformly targets exactly 50% of records distributed across all splits in parallel "
            "without saturating a single Paxos group."
        ),
        "sql_statement": """-- 10% emergency weather discount on outdoor ride tickets
UPDATE AttractionRun
SET TicketPrice = ROUND(TicketPrice * 0.90, 2)
WHERE AttractionID IN (
  SELECT AttractionID FROM Attraction 
  WHERE Type IN ('Thrill Ride', 'Boat Ride', 'Family Ride')
)
AND MOD(ABS(RunID), 10) < 5;""",
        "spanner_dml": """UPDATE AttractionRun
SET TicketPrice = ROUND(TicketPrice * 0.90, 2)
WHERE AttractionID IN (
  SELECT AttractionID FROM Attraction 
  WHERE Type IN ('Thrill Ride', 'Boat Ride', 'Family Ride')
)
AND MOD(ABS(RunID), 10) < 5"""
    },
    {
        "round_id": 2,
        "icon": "💥",
        "title": "Round 2: Space Mountain Mechanical Breakdown",
        "subtitle": "Sensor Trip & Interleaved Partitioned Run Deletions",
        "storyline": (
            "Critical safety sensors fail on Attraction #40 (Space Mountain) across 25% of the parks! "
            "Emergency shutdown protocols trigger, deleting 5% of recorded runs from the database (-5% revenue). "
            "Impacted parks must pay an immediate 2% urgent mechanical engineering repair invoice."
        ),
        "concept_title": "2. Targeted Partitioned Deletion in Interleaved Child Tables",
        "concept_description": (
            "Because AttractionRun is defined with INTERLEAVE IN PARENT Attraction ON DELETE CASCADE, "
            "all child run records are physically co-located on the exact same storage split as their parent Attraction row. "
            "Deleting runs for a specific AttractionID requires zero cross-server RPC hops, executing at maximum local I/O throughput."
        ),
        "sql_statement": """-- Emergency run cancellation: delete 5% of runs on Space Mountain (ID = 40)
DELETE FROM AttractionRun
WHERE AttractionID = 40
  AND MOD(ABS(RunID), 100) < 5;""",
        "spanner_dml": """DELETE FROM AttractionRun
WHERE AttractionID = 40
  AND MOD(ABS(RunID), 100) < 5"""
    },
    {
        "round_id": 3,
        "icon": "🕵️",
        "title": "Round 3: Antitrust Monopoly & Price-Gouging Commission",
        "subtitle": "Auditing Ticket Pricing with Secondary Covering Indexes (STORING)",
        "storyline": (
            "The Disney Fair Pricing Bureau audits all park operations! Operators exploiting visitors "
            "with extortionate ticket prices (> $30.00, Luxury Trap) are penalized with a 15% antitrust revenue fine and -100 points! "
            "Conversely, parks maintaining affordable family-friendly prices ($10.00 - $18.00) receive a 5% municipal tourism grant and +75 bonus points!"
        ),
        "concept_title": "3. Covering Indexes (STORING) for Zero-Hop Real-Time Auditing",
        "concept_description": (
            "Calculating pricing aggregates across millions of rows can be slow if secondary indexes must join back to the primary table. "
            "By declaring CREATE INDEX Idx_AttractionRun_Timestamp ON AttractionRun (RunTimestamp DESC) STORING (TicketPrice), "
            "Cloud Spanner executes aggregate queries entirely out of index memory without touching base storage."
        ),
        "sql_statement": """-- Index-only scan to evaluate average park ticket pricing
SELECT 
  AVG(TicketPrice) AS AvgPrice,
  COUNT(1) AS TotalRuns,
  COUNTIF(TicketPrice > 30.0) AS ExtortionRuns
FROM AttractionRun@{FORCE_INDEX=Idx_AttractionRun_Timestamp};""",
        "spanner_dml": None
    },
    {
        "round_id": 4,
        "icon": "⚡",
        "title": "Round 4: Regional Spanner Power Grid Brownout",
        "subtitle": "Compute Scale vs. Operational Throughput Efficiency",
        "storyline": (
            "An electricity crisis hits! The Green Cloud Efficiency Board audits Spanner compute allocation: "
            "parks running 1,000 PUs (1 full Node) with under 50 runs/sec were burning idle cloud power and lose 90 points plus a 3% carbon tax! "
            "Lean parks achieving over 100 runs/sec on 500 PUs or less earn a Green Cloud Engineering trophy (+90 points and a 3% clean energy rebate)!"
        ),
        "concept_title": "4. Right-Sizing Compute: Processing Units (PUs) vs. Active Concurrency",
        "concept_description": (
            "Cloud Spanner decouples compute from storage, allowing dynamic scaling from 100 PUs to thousands of nodes. "
            "Scaling to 1,000 PUs is only cost-effective if client workloads provide sufficient concurrent threads "
            "to saturate the allocated multi-core compute bandwidth."
        ),
        "sql_statement": """-- Query Spanner instance sizing vs active CPU consumption
SELECT 
  instance_id, 
  processing_units,
  state
FROM spanner_sys.instance_info;""",
        "spanner_dml": None
    },
    {
        "round_id": 5,
        "icon": "🎆",
        "title": "Round 5: Mickey's Centenary Jubilee & Grand Graph Finale",
        "subtitle": "50,000 Visitor Flood & Property Graph Pathfinding",
        "storyline": (
            "The grand finale! 50,000 VIP tourists flood into the parks for Mickey Mouse's 100th Anniversary Fireworks Parade! "
            "Parks with a compiled Spanner Property Graph (DisneylandGraph) and at least 50 catalog attractions navigate the crowds seamlessly, "
            "earning a massive 20% final score surge and an 8% jubilee parade revenue boost! Parks without graph navigation suffer total crowd gridlock!"
        ),
        "concept_title": "5. Native Property Graph Pattern Matching (ISO GQL Standard)",
        "concept_description": (
            "Cloud Spanner Property Graph allows complex multi-hop pathfinding queries without writing recursive SQL CTEs or expensive multi-way table joins. "
            "Using GRAPH DisneylandGraph MATCH ... lets the database engine optimize graph traversal across attraction nodes and path edges at native database speed."
        ),
        "sql_statement": """-- Execute GQL path traversal for jubilee parade crowd routing
GRAPH DisneylandGraph
MATCH (start:Attraction)-[p:Path]->(hub:Attraction)-[p2:Path]->(dest:Attraction)
WHERE start.Land = 'Fantasyland' AND dest.Land = 'Discoveryland'
RETURN start.Name AS StartRide, hub.Name AS HubRide, dest.Name AS TargetRide, 
       (p.DistanceMeters + p2.DistanceMeters) AS TotalMeters
ORDER BY TotalMeters ASC
LIMIT 3;""",
        "spanner_dml": None
    }
]

def is_project_active(p: Dict[str, Any]) -> bool:
    """Identifies if a project is actively participating (created tables, runs, or rows)."""
    return bool(len(p.get("tables", [])) > 0 or p.get("runs", 0) > 0 or p.get("total_rows", 0) > 0)

def apply_event_simulation(
    base_standings: List[Dict[str, Any]], 
    round_id: int
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Applies the simulation up to the given round_id (1..5) in sequence.
    Strictly factors in active projects so idle sandboxes are not targeted by disasters.
    Returns (updated_standings, round_metadata).
    """
    participants = [copy.deepcopy(p) for p in base_standings]
    
    for idx, p in enumerate(participants, start=1):
        rank_val = p.get("rank", idx)
        p["orig_rank"] = rank_val
        p["new_rank"] = rank_val
        p["rank_shift"] = 0
        p["event_log"] = []
        p["round_impact_text"] = "Baseline standing before event kickoff."
        p["score_delta"] = 0
        p["revenue_delta"] = 0.0
        p["profit"] = p.get("profit", p.get("revenue", 0.0))

    if round_id < 1:
        return participants, {
            "round_id": 0, 
            "title": "Baseline Event Freeze", 
            "icon": "🏁",
            "subtitle": "Standings before dramatic event closure kickoff",
            "storyline": "The hackathon submission window has closed! The park gates are locked, telemetry is frozen, and the disaster wheel is ready to spin.",
            "concept_title": "Cloud Spanner Point-in-Time Read Consistency",
            "concept_description": "Cloud Spanner TrueTime guarantees external consistency, allowing transactions to be frozen at a precise microsecond across global regions.",
            "sql_statement": "SELECT * FROM AttractionRun@{EXACT_STALENESS = '0s'};"
        }

    # Partition active vs inactive participants based on Spanner table existence & runs
    active_pids = set(p["project_id"] for p in participants if is_project_active(p))
    # If all projects are idle (e.g. previewing before start), treat all as active for demo
    if not active_pids:
        active_pids = set(p["project_id"] for p in participants)
        
    active_sorted = sorted(list(active_pids))
    n_active = len(active_sorted)

    # Deterministic selection targeting exact percentage of ACTIVE participants
    n_r1 = max(1, round(n_active * 0.50))
    r1_targets = set(sorted(active_sorted, key=lambda pid: hash(pid + "_monsoon"))[:n_r1])
    
    n_r2 = max(1, round(n_active * 0.25))
    r2_targets = set(sorted(active_sorted, key=lambda pid: hash(pid + "_glitch"))[:n_r2])
    
    n_r4 = max(1, round(n_active * 0.33))
    r4_targets = set(sorted(active_sorted, key=lambda pid: hash(pid + "_brownout"))[:n_r4])

    for r in range(1, round_id + 1):
        for p in participants:
            proj_id = p["project_id"]
            if proj_id not in active_pids:
                if r == round_id:
                    p["round_impact_text"] = "💤 Idle Sandbox: No Spanner tables created yet."
                continue

            ticket_price = p.get("ticket_price", 0.0)
            revenue = p.get("revenue", 0.0)
            score = p.get("score", 0)
            profit = p.get("profit", 0.0)
            runs = p.get("runs", 0)
            pu = p.get("processing_units", 100)
            qps = p.get("qps", 0.0)
            has_graph = p.get("has_graph", False)
            total_rows = p.get("total_rows", 0)
            
            # --- ROUND 1: Monsoon Weather (50% of active parks) ---
            if r == 1:
                is_hit = (proj_id in r1_targets)
                if is_hit:
                    rev_loss = round(revenue * 0.10, 2)
                    p["revenue"] = max(0.0, revenue - rev_loss)
                    p["revenue_delta"] -= rev_loss
                    p["profit"] = round(profit - rev_loss, 2)
                    
                    score_deduct = 20
                    
                    if ticket_price > 25.0:
                        extra_fine = round(p["revenue"] * 0.03, 2)
                        extra_pts = 40
                        p["revenue"] = max(0.0, p["revenue"] - extra_fine)
                        p["profit"] = round(p["profit"] - extra_fine, 2)
                        p["revenue_delta"] -= extra_fine
                        p["score"] = max(0, score - score_deduct - extra_pts)
                        p["score_delta"] -= (score_deduct + extra_pts)
                        impact = f"🌧️ Hit by Monsoon (-10% rev: -${rev_loss:,.2f}) + 3% Extortion Price Fine (-${extra_fine:,.2f}, -{extra_pts} pts)"
                    else:
                        p["score"] = max(0, score - score_deduct)
                        p["score_delta"] -= score_deduct
                        impact = f"🌧️ Hit by Monsoon: 10% emergency refund (-${rev_loss:,.2f}, -{score_deduct} pts)"
                    p["event_log"].append(impact)
                    if r == round_id:
                        p["round_impact_text"] = impact
                else:
                    if r == round_id:
                        p["round_impact_text"] = "☀️ Sunshine Shield: Park stayed dry and dodged rain refunds!"

            # --- ROUND 2: Space Mountain Breakdown (25% of active parks) ---
            elif r == 2:
                is_hit = (proj_id in r2_targets)
                if is_hit:
                    lost_runs = max(1, int(runs * 0.05)) if runs > 0 else 0
                    p["runs"] = max(0, runs - lost_runs)
                    # 5% revenue loss from cancelled runs + 2% urgent mechanical engineering repair invoice
                    rev_loss = round(p["revenue"] * 0.05, 2)
                    repair_bill = round(p["revenue"] * 0.02, 2)
                    total_deduction = round(rev_loss + repair_bill, 2)
                    
                    p["revenue"] = max(0.0, p["revenue"] - total_deduction)
                    p["profit"] = round(p["profit"] - total_deduction, 2)
                    p["revenue_delta"] -= total_deduction
                    p["score"] = max(0, p["score"] - 35)
                    p["score_delta"] -= 35
                    impact = f"💥 Space Mountain Glitch: -5% deleted runs (-${rev_loss:,.2f}) & 2% repair bill (-${repair_bill:,.2f}) [-35 pts]"
                    p["event_log"].append(impact)
                    if r == round_id:
                        p["round_impact_text"] = impact
                else:
                    if r == round_id:
                        p["round_impact_text"] = "🛡️ Coaster Green: Maintenance inspection passed!"

            # --- ROUND 3: Antitrust Audit ---
            elif r == 3:
                if ticket_price > 30.0:
                    fine = round(p["revenue"] * 0.15, 2)
                    p["revenue"] = max(0.0, p["revenue"] - fine)
                    p["revenue_delta"] -= fine
                    p["profit"] = round(p["profit"] - fine, 2)
                    p["score"] = max(0, p["score"] - 100)
                    p["score_delta"] -= 100
                    impact = f"🕵️ Luxury Trap Fine: Overpriced tickets confiscated 15% revenue (-${fine:,.2f}, -100 pts)!"
                    p["event_log"].append(impact)
                    if r == round_id:
                        p["round_impact_text"] = impact
                elif 10.0 <= ticket_price <= 18.0 and runs > 0:
                    grant = round(p["revenue"] * 0.05, 2)
                    p["revenue"] += grant
                    p["revenue_delta"] += grant
                    p["profit"] = round(p["profit"] + grant, 2)
                    p["score"] += 75
                    p["score_delta"] += 75
                    impact = f"🏆 Family-Friendly Grant: Fair pricing awarded 5% tourism grant (+${grant:,.2f}, +75 pts)!"
                    p["event_log"].append(impact)
                    if r == round_id:
                        p["round_impact_text"] = impact
                else:
                    if r == round_id:
                        p["round_impact_text"] = "⚖️ Audit Neutral: Standard compliance rating maintained."

            # --- ROUND 4: Power Grid Brownout ---
            elif r == 4:
                if pu >= 1000 and qps < 50.0:
                    carbon_tax = round(p["revenue"] * 0.03, 2)
                    p["revenue"] = max(0.0, p["revenue"] - carbon_tax)
                    p["revenue_delta"] -= carbon_tax
                    p["profit"] = round(p["profit"] - carbon_tax, 2)
                    p["score"] = max(0, p["score"] - 90)
                    p["score_delta"] -= 90
                    impact = f"⚡ Idle PU Brownout: 1,000 PUs idle waste penalized -90 pts & 3% carbon tax (-${carbon_tax:,.2f})!"
                    p["event_log"].append(impact)
                    if r == round_id:
                        p["round_impact_text"] = impact
                elif qps >= 100.0 and pu <= 500:
                    rebate = round(p["revenue"] * 0.03, 2)
                    p["revenue"] += rebate
                    p["revenue_delta"] += rebate
                    p["profit"] = round(p["profit"] + rebate, 2)
                    p["score"] += 90
                    p["score_delta"] += 90
                    impact = f"🌱 Green Cloud Master: High throughput on lean compute rewarded +90 pts & 3% rebate (+${rebate:,.2f})!"
                    p["event_log"].append(impact)
                    if r == round_id:
                        p["round_impact_text"] = impact
                else:
                    if r == round_id:
                        p["round_impact_text"] = "⚡ Grid Stable: Compute-to-throughput ratio within acceptable band."

            # --- ROUND 5: Mickey's Centenary Jubilee Finale ---
            elif r == 5:
                if has_graph and total_rows >= 50:
                    bonus_pts = int(p["score"] * 0.20)
                    parade_rev = round(p["revenue"] * 0.08, 2)
                    p["score"] += bonus_pts
                    p["score_delta"] += bonus_pts
                    p["revenue"] += parade_rev
                    p["revenue_delta"] += parade_rev
                    p["profit"] = round(p["profit"] + parade_rev, 2)
                    impact = f"🎆 Jubilee Crowd Master: Property Graph routed 50k visitors! (+20% score: +{bonus_pts} pts, +8% rev: +${parade_rev:,.2f})"
                    p["event_log"].append(impact)
                    if r == round_id:
                        p["round_impact_text"] = impact
                else:
                    impact = "🚦 Parade Gridlock: Missing Property Graph caused pedestrian bottlenecks (0 bonus)."
                    p["event_log"].append(impact)
                    if r == round_id:
                        p["round_impact_text"] = impact

    # Re-sort descending by current round score, then revenue
    participants.sort(key=lambda x: (x.get("score", 0), x.get("revenue", 0.0), x.get("total_rows", 0)), reverse=True)
    for rank, p in enumerate(participants, start=1):
        p["new_rank"] = rank
        # Shift: positive means climbed up, negative dropped
        p["rank_shift"] = p["orig_rank"] - p["new_rank"]

    current_round_meta = CEREMONY_ROUNDS[round_id - 1]
    return participants, current_round_meta

def execute_spanner_round_live(
    participants: List[Dict[str, Any]], 
    round_id: int
) -> List[Dict[str, Any]]:
    """
    Executes actual Cloud Spanner DML queries across targeted projects for rounds 1 and 2.
    """
    if round_id < 1 or round_id > len(CEREMONY_ROUNDS):
        return []
        
    round_meta = CEREMONY_ROUNDS[round_id - 1]
    dml_query = round_meta.get("spanner_dml")
    
    if not dml_query:
        return [{"project_id": p["project_id"], "city": p.get("city", ""), "status": "SKIPPED", "message": "Round has no database DML modifications."} for p in participants]

    active_pids = set(p["project_id"] for p in participants if is_project_active(p))
    if not active_pids:
        active_pids = set(p["project_id"] for p in participants)
    active_sorted = sorted(list(active_pids))
    n_active = len(active_sorted)

    n_r1 = max(1, round(n_active * 0.50))
    r1_targets = set(sorted(active_sorted, key=lambda pid: hash(pid + "_monsoon"))[:n_r1])
    
    n_r2 = max(1, round(n_active * 0.25))
    r2_targets = set(sorted(active_sorted, key=lambda pid: hash(pid + "_glitch"))[:n_r2])

    target_projects = []
    for p in participants:
        proj_id = p["project_id"]
        if not is_project_active(p):
            continue
        if round_id == 1 and (proj_id in r1_targets):
            target_projects.append((proj_id, p.get("city", "")))
        elif round_id == 2 and (proj_id in r2_targets):
            target_projects.append((proj_id, p.get("city", "")))

    def run_on_project(item):
        proj_id, city = item
        success, msg, rows = metrics.run_spanner_dml(proj_id, dml_query)
        return {
            "project_id": proj_id,
            "city": city,
            "status": "SUCCESS" if success else "ERROR",
            "message": msg,
            "rows_affected": rows
        }

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(run_on_project, target_projects))

    hit_set = set(p[0] for p in target_projects)
    for p in participants:
        if p["project_id"] not in hit_set:
            results.append({
                "project_id": p["project_id"],
                "city": p.get("city", ""),
                "status": "SKIPPED",
                "message": "Project was not selected by the disaster RNG filter.",
                "rows_affected": 0
            })

    return results

