"""
High-Performance Telemetry collection module for Disneyland Spanner Hackathon Admin.
Direct authoritative Cloud Spanner schema & row counts + Cloud Monitoring API integration.
Parallelized with ThreadPoolExecutor across all 25 projects.
"""
import os
import datetime
import time
import logging
from typing import Dict, List, Any, Optional, Tuple
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

import subprocess

def find_projects_txt() -> str:
    """Finds projects.txt path dynamically by checking env or walking up parent directories."""
    env_path = os.environ.get("PROJECTS_TXT_PATH")
    if env_path and os.path.exists(env_path):
        return env_path
    cur = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        candidate = os.path.join(cur, "projects.txt")
        if os.path.exists(candidate):
            return candidate
        cur = os.path.dirname(cur)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../projects.txt"))

def get_default_admin_project() -> str:
    """Dynamically determines the admin project from env, active gcloud config, or projects.txt."""
    if os.environ.get("ADMIN_PROJECT_ID"):
        return os.environ["ADMIN_PROJECT_ID"].strip()
    try:
        res = subprocess.run(["gcloud", "config", "get-value", "project"], capture_output=True, text=True, timeout=3)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass
    pts = parse_projects_mapping(admin_project_id="")
    if pts:
        return pts[-1]["project_id"]
    return ""

PROJECTS_TXT_PATH = find_projects_txt()

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

def parse_projects_mapping(admin_project_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Parses projects.txt and returns all participants, dynamically labeling admin as Facilitator.
    Format: PROJECT_ID, IAP_MEMBER, REGION, CITY
    """
    if admin_project_id is None:
        admin_project_id = get_default_admin_project()

    participants = []
    txt_path = find_projects_txt()
    if not os.path.exists(txt_path):
        return participants

    with open(txt_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 4:
                proj_id, member, region, city = parts[0], parts[1], parts[2], parts[3]
                is_admin = bool(admin_project_id and proj_id == admin_project_id)
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

    # 2. Fetch Storage (used_bytes across all storage classes for instance disneyland)
    try:
        filter_storage = (
            'metric.type = "spanner.googleapis.com/instance/storage/used_bytes" '
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
        total_bytes = 0
        for ts in results_st:
            if ts.points:
                total_bytes += ts.points[0].value.int64_value
        storage_mb = round(total_bytes / (1024.0 * 1024.0), 2)
    except Exception as e:
        logging.warning(f"Error fetching storage for {project_id}: {e}")

    return {
        "cpu_utilization_pct": round(max_cpu, 2),
        "storage_mb": storage_mb
    }

def fetch_participant_spanner_details(project_id: str) -> Dict[str, Any]:
    """
    Authoritative, direct Cloud Spanner schema, row count, compute scale, and throughput inspection.
    """
    tables = []
    has_graph = False
    total_rows = 0
    runs = 0
    ticket_price = 0.0
    processing_units = 100
    qps = 0.0
    first_run_timestamp = None

    client = get_spanner_client(project_id)
    if not client:
        return {
            "tables": tables,
            "total_rows": total_rows,
            "has_graph": has_graph,
            "runs": runs,
            "ticket_price": ticket_price,
            "processing_units": processing_units,
            "qps": qps,
            "first_run_timestamp": first_run_timestamp
        }

    try:
        inst = client.instance("disneyland")
        try:
            inst.reload()
            processing_units = inst.processing_units or 100
        except Exception:
            processing_units = 100

        db = inst.database("agent-lab")
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
                    sql_runs = f"""
                    SELECT 
                      COUNT(1), 
                      AVG(TicketPrice),
                      TIMESTAMP_DIFF(MAX(RunTimestamp), MIN(RunTimestamp), SECOND),
                      COUNTIF(RunTimestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 2 MINUTE)),
                      MIN(RunTimestamp)
                    FROM {t}
                    """
                    for r in s.execute_sql(sql_runs):
                        runs = r[0] or 0
                        ticket_price = float(r[1]) if r[1] is not None else 0.0
                        duration_sec = r[2] or 0
                        recent_runs = r[3] or 0
                        first_run_timestamp = r[4]
                        
                        burst_qps = (runs / max(1, duration_sec)) if duration_sec > 0 and runs > 1 else (float(runs) if runs > 0 and duration_sec == 0 else 0.0)
                        live_qps = recent_runs / 120.0
                        qps = round(max(burst_qps, live_qps), 1)
    except Exception:
        # Database might not exist yet or instance not provisioned
        pass

    return {
        "tables": tables,
        "total_rows": total_rows,
        "has_graph": has_graph,
        "runs": runs,
        "ticket_price": ticket_price,
        "processing_units": processing_units,
        "qps": qps,
        "first_run_timestamp": first_run_timestamp
    }

def run_spanner_dml(project_id: str, query: str, params: Optional[dict] = None) -> tuple[bool, str, int]:
    """
    Executes a DML statement on Spanner in a read-write transaction with error handling.
    """
    client = get_spanner_client(project_id)
    if not client:
        return False, "Spanner client unavailable", 0
    try:
        inst = client.instance("disneyland")
        db = inst.database("agent-lab")
        def tx_dml(tx):
            return tx.execute_update(query, params=params or {})
        modified_count = db.run_in_transaction(tx_dml)
        return True, f"Success: {modified_count} rows modified", modified_count
    except Exception as e:
        return False, str(e), 0

def get_leaderboard_snapshot(
    admin_project_id: Optional[str] = None,
    use_mock: bool = False,
    selected_project_ids: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Compiles snapshot across participants in parallel from projects.txt.
    """
    if admin_project_id is None:
        admin_project_id = get_default_admin_project()
    participants = parse_projects_mapping(admin_project_id)
    if selected_project_ids:
        participants = [p for p in participants if p["project_id"] in selected_project_ids]
    
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
            pu_tiers = [100, 100, 200, 500, 500, 1000, 1000]
            mock_pu = pu_tiers[val % len(pu_tiers)]
            mock_qps = round(val * 24.5, 1) if val >= 4 else 0.0
            mock_base_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=45)
            mock_ts = (mock_base_time + datetime.timedelta(minutes=(6 - (val % 5)) * 4)) if val >= 4 else None
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
                "processing_units": mock_pu,
                "qps": mock_qps,
                "visitors": biz["effective_visitors"],
                "revenue": biz["revenue"],
                "profit": biz["profit"],
                "first_run_timestamp": mock_ts,
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
            
            # If Spanner has active rows/runs but Cloud Monitoring rounds down to 0 MB, provide a baseline floor
            storage_val = mon_metrics["storage_mb"]
            total_act_rows = spanner_data["total_rows"] + spanner_data["runs"]
            if storage_val == 0.0 and total_act_rows > 0:
                storage_val = round(max(0.05, total_act_rows * 0.0005), 2)

            return {
                "project_id": proj_id,
                "city": p["city"],
                "member": p["member"],
                "short_id": p["short_id"],
                "tables": spanner_data["tables"],
                "total_rows": spanner_data["total_rows"],
                "has_graph": spanner_data["has_graph"],
                "cpu_utilization_pct": mon_metrics["cpu_utilization_pct"],
                "storage_mb": storage_val,
                "ticket_price": spanner_data["ticket_price"],
                "runs": spanner_data["runs"],
                "processing_units": spanner_data["processing_units"],
                "qps": spanner_data["qps"],
                "visitors": biz["effective_visitors"],
                "revenue": biz["revenue"],
                "profit": biz["profit"],
                "first_run_timestamp": spanner_data["first_run_timestamp"],
                "is_facilitator": p.get("is_facilitator", False)
            }

        with ThreadPoolExecutor(max_workers=25) as executor:
            temp_records = list(executor.map(process_participant, participants))

    max_revenue = max([r["revenue"] for r in temp_records], default=1.0)
    
    # Identify the earliest TrueTime run across all participants who launched runs
    earliest_run_ts = None
    for r in temp_records:
        ts = r.get("first_run_timestamp")
        if ts and r.get("runs", 0) > 0:
            if earliest_run_ts is None or ts < earliest_run_ts:
                earliest_run_ts = ts

    # Calculate final composite scores and badges
    results = []
    for r in temp_records:
        scored = compute_participant_score(
            r, 
            max_revenue_in_event=max_revenue,
            earliest_run_timestamp=earliest_run_ts
        )
        r.update(scored)
        results.append(r)
        
    # Sort descending by total score, then by revenue, then total rows
    results.sort(key=lambda x: (x["score"], x["revenue"], x["total_rows"]), reverse=True)
    for rank, r in enumerate(results, start=1):
        r["rank"] = rank
        
    return results

import threading
import random

def create_initial_baseline_snapshot(admin_project_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Creates an instant zero-latency baseline snapshot from projects.txt
    so the UI can render on frame 0 without waiting for Spanner or Cloud Monitoring.
    """
    participants = parse_projects_mapping(admin_project_id)
    records = []
    for rank, p in enumerate(participants, start=1):
        records.append({
            "project_id": p["project_id"],
            "city": p["city"],
            "member": p["member"],
            "short_id": p["short_id"],
            "tables": [],
            "total_rows": 0,
            "has_graph": False,
            "cpu_utilization_pct": 0.0,
            "storage_mb": 0.0,
            "ticket_price": 0.0,
            "runs": 0,
            "processing_units": 100,
            "qps": 0.0,
            "visitors": 0,
            "revenue": 0.0,
            "profit": 0.0,
            "first_run_timestamp": None,
            "is_facilitator": p.get("is_facilitator", False),
            "rank": rank,
            "score": 0,
            "badges": [],
            "speed_bonus": 0,
            "round_impact_text": "Awaiting live telemetry handshake"
        })
    return records

class BackgroundTelemetryManager:
    """
    Singleton manager that completely decouples expensive Cloud Spanner, Cloud Monitoring,
    and Gemini AI roast generation from the Streamlit UI rendering thread.
    Executes polling and roast updates in background daemon threads and serves atomic in-memory cache.
    """
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self.cached_snapshot: List[Dict[str, Any]] = []
        self.cached_mock_snapshot: List[Dict[str, Any]] = []
        self.last_fetch_time: float = 0.0
        self.is_fetching: bool = False
        self.last_error: Optional[str] = None
        self.admin_project_id: Optional[str] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._trigger_event = threading.Event()

        # Background Roast Announcer State (0ms UI retrieval)
        self.cached_roast: Dict[str, Any] = {
            "target_city": "Kraków",
            "emoji": "🏰",
            "roast": "All parks are calibrating Spanner nodes and spinning up TrueTime engines!",
            "rhyme": "Welcome to the Disneyland Spanner Grand Prix,\nLet's see whose database will set the magic free!",
            "timestamp": time.strftime("%H:%M:%S"),
            "model": "Gemini 3.8 Flash"
        }
        self.last_roast_time: float = 0.0
        self._roast_thread: Optional[threading.Thread] = None
        self._roast_lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = BackgroundTelemetryManager()
        return cls._instance

    def ensure_started(self, admin_project_id: Optional[str] = None, interval: int = 15):
        if admin_project_id:
            self.admin_project_id = admin_project_id
        if not self.cached_snapshot:
            self.cached_snapshot = create_initial_baseline_snapshot(self.admin_project_id)
        if self._thread is None or not self._thread.is_alive():
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._polling_loop, 
                args=(interval,), 
                daemon=True,
                name="SpannerTelemetryPoller"
            )
            self._thread.start()

    def trigger_immediate_sync(self):
        """Signals background worker to initiate a sync cycle immediately."""
        self._trigger_event.set()

    def trigger_roast_sync(self):
        """Asynchronously triggers a fresh roast generation via Gemini in the background without blocking."""
        with self._roast_lock:
            if self._roast_thread is None or not self._roast_thread.is_alive():
                self._roast_thread = threading.Thread(
                    target=self._roast_worker,
                    daemon=True,
                    name="RoastBackgroundWorker"
                )
                self._roast_thread.start()

    def _roast_worker(self):
        try:
            import llm_announcer
            target_proj = self.admin_project_id or get_default_admin_project()
            snap = self.cached_snapshot if self.cached_snapshot else create_initial_baseline_snapshot(target_proj)
            new_roast = llm_announcer.generate_roast_broadcast(snap, target_proj)
            if new_roast and isinstance(new_roast, dict) and "roast" in new_roast:
                self.cached_roast = new_roast
                self.last_roast_time = time.time()
        except Exception as e:
            logging.error(f"Background roast worker error: {e}")

    def get_roast(self, admin_project_id: Optional[str] = None, force_refresh: bool = False) -> Dict[str, Any]:
        """Instant 0ms non-blocking retrieval of current roast bulletin."""
        if force_refresh:
            self.trigger_roast_sync()
        return self.cached_roast

    def _polling_loop(self, interval: int):
        while not self._stop_event.is_set():
            try:
                self.is_fetching = True
                snap = get_leaderboard_snapshot(self.admin_project_id, use_mock=False)
                if snap:
                    self.cached_snapshot = snap
                    self.last_fetch_time = time.time()
                    self.last_error = None
            except Exception as e:
                self.last_error = str(e)
                logging.error(f"Background telemetry sync error: {e}")
            finally:
                self.is_fetching = False

            # Check if 4 minutes have passed since last roast, trigger in background
            if (time.time() - self.last_roast_time) >= 240:
                self.trigger_roast_sync()

            # Responsive sleep listening for trigger or stop events
            for _ in range(max(1, interval * 2)):
                if self._stop_event.is_set():
                    return
                if self._trigger_event.is_set():
                    self._trigger_event.clear()
                    break
                time.sleep(0.5)

    def get_snapshot(self, admin_project_id: Optional[str] = None, use_mock: bool = False) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Instant 0ms non-blocking retrieval of latest snapshot from memory.
        NEVER performs network calls on caller thread.
        """
        if admin_project_id and admin_project_id != self.admin_project_id:
            self.admin_project_id = admin_project_id

        if use_mock:
            if not self.cached_mock_snapshot:
                self.cached_mock_snapshot = get_leaderboard_snapshot(self.admin_project_id, use_mock=True)
            return self.cached_mock_snapshot, {
                "last_fetch_time": time.time(),
                "age_seconds": 0,
                "is_fetching": False,
                "mode": "MOCK"
            }

        self.ensure_started(admin_project_id)

        if not self.cached_snapshot:
            self.cached_snapshot = create_initial_baseline_snapshot(self.admin_project_id)

        now = time.time()
        age = int(now - self.last_fetch_time) if self.last_fetch_time > 0 else 0
        meta = {
            "last_fetch_time": self.last_fetch_time,
            "age_seconds": age,
            "is_fetching": self.is_fetching,
            "last_error": self.last_error,
            "mode": "LIVE_BACKGROUND"
        }
        return self.cached_snapshot, meta

