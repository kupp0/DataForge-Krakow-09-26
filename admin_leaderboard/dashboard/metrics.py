"""
High-Performance Telemetry collection module for Disneyland Spanner Hackathon Admin.
Direct authoritative Cloud Spanner schema & row counts + Cloud Monitoring API integration.
Parallelized with ThreadPoolExecutor across all 25 projects.
"""
import os
import datetime
import logging
from typing import Dict, List, Any, Optional
from concurrent.futures import ThreadPoolExecutor

# Suppress client-side telemetry export noise
os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ["GOOGLE_CLOUD_SPANNER_ENABLE_OTEL_METRICS"] = "false"
logging.getLogger("google.cloud.monitoring").setLevel(logging.ERROR)

try:
    from google.cloud import monitoring_v3
    from google.cloud import spanner
except ImportError:
    monitoring_v3 = None
    spanner = None

from business_rules import calculate_attraction_run_metrics, compute_participant_score

PROJECTS_TXT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../projects.txt"))

# Reusable client caches
_MONITORING_CLIENT = None
_SPANNER_CLIENTS: Dict[str, Any] = {}

def get_monitoring_client():
    global _MONITORING_CLIENT
    if _MONITORING_CLIENT is None and monitoring_v3:
        try:
            _MONITORING_CLIENT = monitoring_v3.MetricServiceClient()
        except Exception:
            _MONITORING_CLIENT = None
    return _MONITORING_CLIENT

def get_spanner_client(project_id: str):
    global _SPANNER_CLIENTS
    if project_id not in _SPANNER_CLIENTS and spanner:
        try:
            _SPANNER_CLIENTS[project_id] = spanner.Client(project=project_id)
        except Exception:
            return None
    return _SPANNER_CLIENTS.get(project_id)

def parse_projects_mapping(admin_project_id: str = "dataforge26krk-6725") -> List[Dict[str, Any]]:
    """
    Parses projects.txt and returns all 25 participants, labeling admin as Facilitator.
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
    Fetches CPU utilization (%) and Storage (MB) using the shared monitoring client.
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

def fetch_participant_spanner_details(project_id: str) -> Dict[str, Any]:
    """
    Authoritative, direct Cloud Spanner schema & row count inspection.
    """
    tables = []
    has_graph = False
    total_rows = 0
    runs = 0
    ticket_price = 0.0

    client = get_spanner_client(project_id)
    if not client:
        return {
            "tables": tables,
            "total_rows": total_rows,
            "has_graph": has_graph,
            "runs": runs,
            "ticket_price": ticket_price
        }

    try:
        db = client.instance("disneyland").database("agent-lab")
        with db.snapshot(multi_use=True) as s:
            # 1. Query tables
            tables = [r[0] for r in s.execute_sql(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = ''"
            )]
            
            # 2. Query property graph
            graphs = [r[0] for r in s.execute_sql(
                "SELECT property_graph_name FROM information_schema.property_graphs"
            )]
            has_graph = len(graphs) > 0

            # 3. Query row counts for core Disneyland tables
            for t in tables:
                t_lower = t.lower()
                if t_lower in ["disneylandpark", "attraction", "path"]:
                    for r in s.execute_sql(f"SELECT COUNT(1) FROM {t}"):
                        total_rows += r[0]
                elif "attractionrun" in t_lower or "parkrun" in t_lower or "rideexecution" in t_lower:
                    for r in s.execute_sql(f"SELECT COUNT(1), AVG(TicketPrice) FROM {t}"):
                        runs = r[0] or 0
                        ticket_price = float(r[1]) if r[1] is not None else 0.0
    except Exception:
        # Database might not exist yet or instance not provisioned
        pass

    return {
        "tables": tables,
        "total_rows": total_rows,
        "has_graph": has_graph,
        "runs": runs,
        "ticket_price": ticket_price
    }

def get_leaderboard_snapshot(
    admin_project_id: str = "dataforge26krk-6725",
    use_mock: bool = False
) -> List[Dict[str, Any]]:
    """
    Compiles snapshot across all 25 participants in parallel.
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
                "profit": biz["profit"],
                "is_facilitator": p.get("is_facilitator", False)
            }
            temp_records.append(rec)
    else:
        mon_client = get_monitoring_client()

        now = datetime.datetime.now(datetime.timezone.utc)
        start_time = now - datetime.timedelta(minutes=15)
        interval = monitoring_v3.TimeInterval({
            "end_time": {"seconds": int(now.timestamp())},
            "start_time": {"seconds": int(start_time.timestamp())}
        }) if monitoring_v3 else None

        # Parallel worker per project
        def process_participant(p):
            proj_id = p["project_id"]
            
            # 1. Spanner inspection
            spanner_data = fetch_participant_spanner_details(proj_id)
            
            # 2. Monitoring metrics
            mon_metrics = fetch_participant_monitoring_metrics(proj_id, interval, mon_client)
            
            # 3. Business metrics
            biz = calculate_attraction_run_metrics(
                spanner_data["ticket_price"], 
                spanner_data["runs"]
            )
            
            return {
                "project_id": proj_id,
                "city": p["city"],
                "member": p["member"],
                "short_id": p["short_id"],
                "tables": spanner_data["tables"],
                "total_rows": spanner_data["total_rows"],
                "has_graph": spanner_data["has_graph"],
                "cpu_utilization_pct": mon_metrics["cpu_utilization_pct"],
                "storage_mb": mon_metrics["storage_mb"],
                "ticket_price": spanner_data["ticket_price"],
                "runs": spanner_data["runs"],
                "visitors": biz["effective_visitors"],
                "revenue": biz["revenue"],
                "profit": biz["profit"],
                "is_facilitator": p.get("is_facilitator", False)
            }

        with ThreadPoolExecutor(max_workers=25) as executor:
            temp_records = list(executor.map(process_participant, participants))

    max_revenue = max([r["revenue"] for r in temp_records], default=1.0)
    
    # Calculate final composite scores and badges
    results = []
    for r in temp_records:
        scored = compute_participant_score(r, max_revenue_in_event=max_revenue)
        r.update(scored)
        results.append(r)
        
    # Sort descending by total score, then by revenue
    results.sort(key=lambda x: (x["score"], x["revenue"], x["total_rows"]), reverse=True)
    for rank, r in enumerate(results, start=1):
        r["rank"] = rank
        
    return results
