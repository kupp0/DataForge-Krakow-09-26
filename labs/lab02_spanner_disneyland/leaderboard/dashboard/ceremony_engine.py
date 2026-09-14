"""
Disneyland Hackathon: Disneyland Park Closing Ceremony Engine
Implements 5 interactive dramatic event rounds that alter leaderboard standings
focusing purely on theme park operational events, dynamic rankings, and winner celebration.
"""
import copy
import logging
from typing import Dict, List, Any, Tuple

CEREMONY_ROUNDS = [
    {
        "round_id": 1,
        "icon": "🌧️",
        "title": "Round 1: Monsoon over the Magic Kingdom",
        "subtitle": "The Great Rainstorm & Dynamic Refund Discounts",
        "storyline": (
            "A sudden torrential thunderstorm strikes 50% of the theme parks! Outdoor attractions "
            "and rollercoasters are drenched, forcing park directors to issue an emergency 10% ticket refund discount. "
            "Furthermore, parks with exorbitant ticket prices (TicketPrice > $25) face angry guest chargebacks and an extra 3% storm surcharge fine!"
        )
    },
    {
        "round_id": 2,
        "icon": "💥",
        "title": "Round 2: Space Mountain Mechanical Breakdown",
        "subtitle": "Sensor Trip & Emergency Attraction Closure",
        "storyline": (
            "Critical safety sensors fail on Attraction #40 (Space Mountain) across 25% of the parks! "
            "Emergency shutdown protocols trigger, cancelling 5% of recorded runs (-5% revenue). "
            "Impacted parks must pay an immediate 2% urgent mechanical engineering repair invoice."
        )
    },
    {
        "round_id": 3,
        "icon": "🕵️",
        "title": "Round 3: Antitrust Monopoly & Price-Gouging Commission",
        "subtitle": "Fair Pricing Audit & Municipal Tourism Grants",
        "storyline": (
            "The Disney Fair Pricing Bureau audits all park operations! Operators exploiting visitors "
            "with extortionate ticket prices (> $30.00, Luxury Trap) are penalized with a 15% antitrust revenue fine and -100 points! "
            "Conversely, parks maintaining affordable family-friendly prices ($10.00 - $18.00) receive a 5% municipal tourism grant and +75 bonus points!"
        )
    },
    {
        "round_id": 4,
        "icon": "⚡",
        "title": "Round 4: Regional Spanner Power Grid Brownout",
        "subtitle": "Compute Scale vs. Operational Throughput Efficiency",
        "storyline": (
            "An electricity crisis hits! The Green Cloud Efficiency Board audits compute allocation: "
            "parks running on 1,000+ PUs (1 to 4+ full Nodes) with under-utilized capacity (under 400 runs/sec per node) "
            "were burning idle cloud power and lose 90 points plus a 3% carbon tax penalty on attraction revenues! "
            "Lean parks achieving over 100 runs/sec on 500 PUs or less earn a Green Cloud Engineering trophy (+90 points and a 3% clean energy rebate)!"
        )
    },
    {
        "round_id": 5,
        "icon": "🎆",
        "title": "Round 5: Mickey's Centenary Jubilee & Grand Graph Finale",
        "subtitle": "Property Graph Traversal Velocity & Compute Density",
        "storyline": (
            "The grand finale! 50,000 VIP tourists flood into the parks for Mickey Mouse's 100th Anniversary Fireworks Parade! "
            "Disneyland's Central Dispatch routes crowds in real-time using property graph pathfinding. "
            "Parks are evaluated on Graph Traversal Velocity per Compute Unit (Runs/sec per 100 PUs). "
            "Parks achieving high throughput density navigate crowds seamlessly, earning massive Jubilee Grants (up to +$300,000) "
            "and a final score surge (up to +310 pts)! Over-provisioned or low-density clusters suffer heavy pedestrian traffic delays!"
        )
    }
]

def is_project_active(p: Dict[str, Any]) -> bool:
    """Identifies if a project is actively participating (created tables, runs, or rows)."""
    return bool(len(p.get("tables", [])) > 0 or p.get("runs", 0) > 0 or p.get("total_rows", 0) > 0)

def apply_event_simulation(
    base_standings: List[Dict[str, Any]], 
    round_id: int,
    only_active: bool = False
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Applies the simulation up to the given round_id (1..5) in sequence.
    Strictly factors in active projects so idle sandboxes are not targeted by disasters.
    Returns (updated_standings, round_metadata).
    """
    if only_active:
        base_standings = [p for p in base_standings if is_project_active(p)]

    participants = [copy.deepcopy(p) for p in base_standings]
    
    for idx, p in enumerate(participants, start=1):
        rank_val = p.get("rank", idx)
        p["orig_rank"] = rank_val
        p["new_rank"] = rank_val
        p["orig_rank"] = rank_val
        p["new_rank"] = rank_val
        p["rank_shift"] = 0
        p["event_log"] = []
        p["round_impact_text"] = "Baseline standing before event kickoff."
        p["score_delta"] = 0
        p["revenue_delta"] = 0.0
        p["round_score_delta"] = 0
        p["round_revenue_delta"] = 0.0
        p["profit"] = p.get("profit", p.get("revenue", 0.0))

    if round_id < 1:
        return participants, {
            "round_id": 0, 
            "title": "Baseline Event Freeze", 
            "icon": "🏁",
            "subtitle": "Standings before dramatic event closure kickoff",
            "storyline": "The hackathon submission window has closed! The park gates are locked, telemetry is frozen, and the disaster wheel is ready to spin."
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

    for r in range(1, round_id + 1):
        for p in participants:
            if r == round_id:
                p["round_score_delta"] = 0
                p["round_revenue_delta"] = 0.0

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
                        if r == round_id:
                            p["round_revenue_delta"] -= (rev_loss + extra_fine)
                            p["round_score_delta"] -= (score_deduct + extra_pts)
                        impact = f"🌧️ Hit by Monsoon (-10% rev: -${rev_loss:,.2f}) + 3% Extortion Price Fine (-${extra_fine:,.2f}, -{extra_pts} pts)"
                    else:
                        p["score"] = max(0, score - score_deduct)
                        p["score_delta"] -= score_deduct
                        if r == round_id:
                            p["round_revenue_delta"] -= rev_loss
                            p["round_score_delta"] -= score_deduct
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
                    if r == round_id:
                        p["round_revenue_delta"] -= total_deduction
                        p["round_score_delta"] -= 35
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
                    if r == round_id:
                        p["round_revenue_delta"] -= fine
                        p["round_score_delta"] -= 100
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
                    if r == round_id:
                        p["round_revenue_delta"] += grant
                        p["round_score_delta"] += 75
                    impact = f"🏆 Family-Friendly Grant: Fair pricing awarded 5% tourism grant (+${grant:,.2f}, +75 pts)!"
                    p["event_log"].append(impact)
                    if r == round_id:
                        p["round_impact_text"] = impact
                else:
                    if r == round_id:
                        p["round_impact_text"] = "⚖️ Audit Neutral: Standard compliance rating maintained."

            # --- ROUND 4: Power Grid Brownout ---
            elif r == 4:
                nodes = max(1.0, pu / 1000.0)
                runs_per_node = qps / nodes
                # Over-provisioned compute: Running 1,000+ PUs (1+ nodes) with < 400 runs/sec per node
                if pu >= 1000 and runs_per_node < 400.0:
                    carbon_tax = round(p["revenue"] * 0.03, 2)
                    p["revenue"] = max(0.0, p["revenue"] - carbon_tax)
                    p["revenue_delta"] -= carbon_tax
                    p["profit"] = round(p["profit"] - carbon_tax, 2)
                    p["score"] = max(0, p["score"] - 90)
                    p["score_delta"] -= 90
                    if r == round_id:
                        p["round_revenue_delta"] -= carbon_tax
                        p["round_score_delta"] -= 90
                    node_desc = f"{int(nodes)} Nodes ({pu} PUs)" if nodes >= 1.0 else f"{pu} PUs"
                    impact = f"⚡ Multi-Node Power Waste: {node_desc} at only {runs_per_node:.0f} runs/s/node penalized -90 pts & 3% carbon tax (-${carbon_tax:,.2f})!"
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
                    if r == round_id:
                        p["round_revenue_delta"] += rebate
                        p["round_score_delta"] += 90
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
                    # Graph Traversal Velocity per Compute Unit (Runs/sec per 100 PUs)
                    eff = qps / max(1.0, pu / 100.0)
                    if eff >= 100.0:
                        pts = 310
                        grant = 300000.0
                        tier_label = f"⚡ Lightning Graph Grandmaster ({eff:.1f} runs/s per 100 PUs)"
                    elif eff >= 70.0:
                        pts = 220
                        grant = 150000.0
                        tier_label = f"🥈 Silver Graph Navigator ({eff:.1f} runs/s per 100 PUs)"
                    elif eff >= 35.0:
                        pts = 160
                        grant = 80000.0
                        tier_label = f"🥉 Bronze Graph Dispatcher ({eff:.1f} runs/s per 100 PUs)"
                    else:
                        pts = 60
                        grant = 50000.0
                        tier_label = f"🚦 Heavy Graph Traffic ({eff:.1f} runs/s per 100 PUs)"

                    p["score"] += pts
                    p["score_delta"] += pts
                    p["revenue"] += grant
                    p["revenue_delta"] += grant
                    p["profit"] = round(p["profit"] + grant, 2)
                    if r == round_id:
                        p["round_revenue_delta"] += grant
                        p["round_score_delta"] += pts
                    impact = f"🎆 {tier_label}: Property Graph routed 50k visitors! (+{pts} pts & +${grant:,.2f} Jubilee Grant)"
                    p["event_log"].append(impact)
                    if r == round_id:
                        p["round_impact_text"] = impact
                else:
                    impact = "🚫 Parade Gridlock: Missing Property Graph caused pedestrian bottlenecks (0 bonus)."
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


