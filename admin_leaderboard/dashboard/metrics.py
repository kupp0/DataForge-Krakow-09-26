"""
High-Performance Telemetry collection module for Disneyland Spanner Hackathon Admin.
Optimized with parallel multi-threaded queries, singleton client reuse, and single-shot BigQuery union view inspection.
"""
import os
import re
import datetime
from typing import Dict, List, Any, Optional
from concurrent.futures import ThreadPoolExecutor

try:
    from google.cloud import monitoring_v3
    from google.cloud import bigquery
except ImportError:
    monitoring_v3 = None
    bigquery = None

from business_rules import calculate_attraction_run_metrics, compute_participant_score

PROJECTS_TXT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../projects.txt"))

# Singleton Client Cache to avoid gRPC connection handshake overhead
_MONITORING_CLIENT = None
_BQ_CLIENT = None

def get_monitoring_client():
    global _MONITORING_CLIENT
    if _MONITORING_CLIENT is None and monitoring_v3:
        try:
            _MONITORING_CLIENT = monitoring_v3.MetricServiceClient()
        except Exception:
            _MONITORING_CLIENT = None
    return _MONITORING_CLIENT

def get_bq_client(admin_project_id: str):
    global _BQ_CLIENT
    if _BQ_CLIENT is None and bigquery:
        try:
            _BQ_CLIENT = bigquery.Client(project=admin_project_id)
        except Exception:
            _BQ_CLIENT = None
    return _BQ_CLIENT

def parse_projects_mapping(admin_project_id: str = "dataforge26krk-6725") -> List[Dict[str, str]]:
    """
    Parses projects.txt and returns list of participants excluding the admin project.
    Format: PROJECT_ID, IAP_MEMBER, REGION, CITY
    """
    participants = []
    if not os.path.exists(PROJECTS_TXT_PATH):
        return participants

    with open(PROJECTS_TXT_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 4:
                proj_id, member, region, city = parts[0], parts[1], parts[2], parts[3]
                is_admin = (proj_id == admin_project_id)
                display_city = f"{city} (Facilitator)" if is_admin else city
                participants.append({
                    "project_id": proj_id,
                    "member": member,
                    "region": region,
                    "city": display_city,
                    "short_id": proj_id.split("-")[-1] if "-" in proj_id else proj_id,
                    "is_facilitator": is_admin
                })
    return participants

def fetch_participant_monitoring_metrics(
    project_id: str, 
    interval: Any,
    client: Optional[Any] = None
) -> Dict[str, float]:
    """
    Fetches both CPU utilization (%) and Storage (MB) using the shared monitoring client.
    """
    if not client:
        return {"cpu_utilization_pct": 0.0, "storage_mb": 0.0}

    max_cpu = 0.0
    storage_mb = 0.0
    project_name = f"projects/{project_id}"

    # 1. Fetch CPU Utilization
    try:
        filter_cpu = (
            'metric.type = "spanner.googleapis.com/instance/cpu/utilization" '
            'AND resource.labels.instance_id = "disneyland"'
        )
        results = client.list_time_series(
            request={
                "name": project_name,
                "filter": filter_cpu,
                "interval": interval,
                "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL
            }
        )
        for ts in results:
            for point in ts.points:
                val = point.value.double_value * 100.0
                if val > max_cpu:
                    max_cpu = val
    except Exception:
        pass

    # 2. Fetch Storage
    try:
        filter_storage = (
            'metric.type = "spanner.googleapis.com/instance/storage/total_bytes" '
            'AND resource.labels.instance_id = "disneyland"'
        )
        results_st = client.list_time_series(
            request={
                "name": project_name,
                "filter": filter_storage,
                "interval": interval,
                "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL
            }
        )
        latest_bytes = 0.0
        for ts in results_st:
            if ts.points:
                latest_bytes = max(latest_bytes, ts.points[0].value.int64_value)
        storage_mb = round(latest_bytes / (1024.0 * 1024.0), 2)
    except Exception:
        pass

    return {
        "cpu_utilization_pct": round(max_cpu, 2),
        "storage_mb": storage_mb
    }

def fetch_all_participant_summary_view(admin_project_id: str, bq_client: Optional[Any] = None) -> Dict[str, Dict[str, Any]]:
    """
    Queries the centralized union view v_participant_tables_summary in BigQuery in a single query.
    """
    summary = {}
    if not bq_client:
        return summary
    try:
        query = f"SELECT * FROM `{admin_project_id}.admin_leaderboard.v_participant_tables_summary`"
        for r in bq_client.query(query).result():
            tables_list = [t.strip() for t in r.tables_list.split(",")] if r.tables_list else []
            summary[r.project_id] = {
                "tables": tables_list,
                "total_tables": r.total_tables_created,
                "has_disneylandpark": r.has_disneylandpark,
                "has_attraction": r.has_attraction,
                "has_path": r.has_path,
                "has_runs_challenge": r.has_runs_challenge
            }
    except Exception:
        pass
    return summary

def fetch_participant_rows_and_details(
    admin_project_id: str, 
    participant: Dict[str, str],
    tables_found: List[str],
    bq_client: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Queries row counts only if tables actually exist.
    """
    total_rows = 0
    ticket_price = 0.0
    runs = 0
    raw_visitors = 0
    
    if not bq_client or not tables_found:
        return {
            "total_rows": 0,
            "has_graph": False,
            "ticket_price": 0.0,
            "runs": 0,
            "raw_visitors": 0
        }

    dataset_name = f"spanner_user_{participant['short_id']}"
    for t in tables_found:
        t_lower = t.lower()
        if t_lower in ["disneylandpark", "attraction", "path"]:
            try:
                count_q = f"SELECT COUNT(1) as cnt FROM `{admin_project_id}.{dataset_name}.{t}`"
                for row in bq_client.query(count_q).result():
                    total_rows += row.cnt
            except Exception:
                pass
        elif "attractionrun" in t_lower or "parkrun" in t_lower or "rideexecution" in t_lower:
            try:
                run_q = f"""
                SELECT 
                    COUNT(1) as total_runs, 
                    AVG(SAFE_CAST(ticket_price AS FLOAT64)) as avg_price
                FROM `{admin_project_id}.{dataset_name}.{t}`
                """
                for r in bq_client.query(run_q).result():
                    runs = r.total_runs or 0
                    ticket_price = r.avg_price or 0.0
            except Exception:
                pass

    has_graph = any(t.lower() == "path" for t in tables_found) and any(t.lower() == "attraction" for t in tables_found)

    return {
        "total_rows": total_rows,
        "has_graph": has_graph,
        "ticket_price": ticket_price,
        "runs": runs,
        "raw_visitors": raw_visitors
    }

def get_leaderboard_snapshot(
    admin_project_id: str = "dataforge26krk-6725",
    use_mock: bool = False
) -> List[Dict[str, Any]]:
    """
    Compiles snapshot across all 24 participants in parallel using thread pool.
    """
    participants = parse_projects_mapping(admin_project_id)
    
    if use_mock:
        temp_records = []
        for p in participants:
            proj_id = p["project_id"]
            val = int(p["short_id"]) % 7
            tables = ["DisneylandPark", "Attraction", "Path"] if val >= 2 else (["DisneylandPark"] if val == 1 else [])
            total_rows = 24 if val >= 2 else (5 if val == 1 else 0)
            has_graph = val >= 3
            cpu_util = round(12.5 * val, 1)
            storage_mb = 1.2 * val
            runs = 10 * val if val >= 4 else 0
            price = 15.0 + (val - 3) * 4.0 if val >= 4 else 0.0
            biz = calculate_attraction_run_metrics(price, runs)
            rec = {
                "project_id": proj_id,
                "city": p["city"],
                "member": p["member"],
                "short_id": p["short_id"],
                "tables": tables,
                "total_rows": total_rows,
                "has_graph": has_graph,
                "cpu_utilization_pct": cpu_util,
                "storage_mb": storage_mb,
                "ticket_price": price,
                "runs": runs,
                "visitors": biz["effective_visitors"],
                "revenue": biz["revenue"],
                "profit": biz["profit"]
            }
            temp_records.append(rec)
    else:
        bq_client = get_bq_client(admin_project_id)
        mon_client = get_monitoring_client()

        # Step 1: Single query against BQ union view to get tables for all 24 participants
        bq_summary = fetch_all_participant_summary_view(admin_project_id, bq_client)

        now = datetime.datetime.now(datetime.timezone.utc)
        start_time = now - datetime.timedelta(minutes=15)
        interval = monitoring_v3.TimeInterval({
            "end_time": {"seconds": int(now.timestamp())},
            "start_time": {"seconds": int(start_time.timestamp())}
        }) if monitoring_v3 else None

        # Step 2: Parallel worker for each participant
        def process_participant(p):
            proj_id = p["project_id"]
            tables_found = bq_summary.get(proj_id, {}).get("tables", [])
            
            # Row counts only if tables exist
            tbl_details = fetch_participant_rows_and_details(admin_project_id, p, tables_found, bq_client)
            
            # Monitoring metrics
            mon_metrics = fetch_participant_monitoring_metrics(proj_id, interval, mon_client)
            
            # Business metrics
            biz = calculate_attraction_run_metrics(
                tbl_details["ticket_price"], 
                tbl_details["runs"], 
                tbl_details["raw_visitors"]
            )
            
            return {
                "project_id": proj_id,
                "city": p["city"],
                "member": p["member"],
                "short_id": p["short_id"],
                "tables": tables_found,
                "total_rows": tbl_details["total_rows"],
                "has_graph": tbl_details["has_graph"],
                "cpu_utilization_pct": mon_metrics["cpu_utilization_pct"],
                "storage_mb": mon_metrics["storage_mb"],
                "ticket_price": tbl_details["ticket_price"],
                "runs": tbl_details["runs"],
                "visitors": biz["effective_visitors"],
                "revenue": biz["revenue"],
                "profit": biz["profit"]
            }

        with ThreadPoolExecutor(max_workers=24) as executor:
            temp_records = list(executor.map(process_participant, participants))

    max_revenue = max([r["revenue"] for r in temp_records], default=1.0)
    
    # Calculate final composite scores and badges
    results = []
    for r in temp_records:
        scored = compute_participant_score(r, max_revenue_in_event=max_revenue)
        r.update(scored)
        results.append(r)
        
    results.sort(key=lambda x: (x["score"], x["revenue"], x["total_rows"]), reverse=True)
    for rank, r in enumerate(results, start=1):
        r["rank"] = rank
        
    return results
