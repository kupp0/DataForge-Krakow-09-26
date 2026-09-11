"""
Disneyland Spanner Hackathon: Live AI Park Announcer
Generates motivational, witty flash commentary broadcasts via Gemini 3.8 Flash
based on real-time leaderboard statistics and telemetry.
"""
import os
import json
import time
import urllib.request
import urllib.error
import logging
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

FALLBACK_MESSAGES = [
    "⚡ Attention park operators: Keep those Spanner queries optimized and don't let your CPU spike into Tomorrowland!",
    "🏰 The magic is compiling! Leading parks are pushing hyperscale throughput—scale your processing units to stay in the race!",
    "🚀 Main Street throughput is heating up! Remember to interleave your AttractionRun tables to avoid lock contention!",
    "🎢 High roller alert: Balance your ticket elasticity! Lower prices boost volume, but watch your Spanner compute capacity!",
    "✨ Pixie dust won't fix a 90% CPU meltdown—scale up to 500 PUs before the crowds overwhelm your rides!"
]

def _extract_telemetry_digest(leaderboard_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compresses 25 projects into key narrative bullet points for the LLM."""
    if not leaderboard_data:
        return {"status": "No active telemetry yet"}

    sorted_by_score = sorted(leaderboard_data, key=lambda x: x.get("score", 0), reverse=True)
    leader = sorted_by_score[0] if sorted_by_score else {}
    top3 = [{"city": r.get("city"), "score": r.get("score"), "rev": r.get("revenue"), "qps": r.get("qps", 0)} for r in sorted_by_score[:3]]

    # Highest throughput
    max_qps_city = max(leaderboard_data, key=lambda x: x.get("qps", 0))
    # Highest CPU
    max_cpu_city = max(leaderboard_data, key=lambda x: x.get("cpu_utilization_pct", 0))
    # Cities without property graph yet
    pending_graphs = [r.get("city") for r in leaderboard_data if not r.get("has_graph", False)]
    # Total revenue
    total_rev = sum(r.get("revenue", 0) for r in leaderboard_data)

    return {
        "leader": {"city": leader.get("city"), "score": leader.get("score"), "revenue": round(leader.get("revenue", 0), 2)},
        "top3": top3,
        "max_throughput": {"city": max_qps_city.get("city"), "qps": round(max_qps_city.get("qps", 0), 1)},
        "max_cpu": {"city": max_cpu_city.get("city"), "cpu_pct": round(max_cpu_city.get("cpu_utilization_pct", 0), 1)},
        "pending_graphs_count": len(pending_graphs),
        "pending_graph_sample": pending_graphs[:3],
        "total_revenue": round(total_rev, 2),
        "total_parks": len(leaderboard_data)
    }

def generate_flash_commentary(
    leaderboard_data: List[Dict[str, Any]], 
    admin_project_id: str = "dataforge26krk-6725",
    model: str = "gemini-3.8-flash"
) -> Tuple[str, str, str]:
    """
    Calls Gemini 3.8 Flash to generate a 1-2 sentence real-time motivational broadcast.
    Returns: (commentary_text, timestamp, status_label)
    """
    now_str = time.strftime("%H:%M:%S")
    digest = _extract_telemetry_digest(leaderboard_data)

    # Prompt Engineering
    prompt_text = f"""You are the electrifying, witty, high-energy live stadium announcer for the Global Disneyland Cloud Spanner Hackathon.
Analyze this real-time telemetry snapshot:
{json.dumps(digest, indent=2)}

Generate a 1 to 2 sentence high-octane motivational flash bulletin for the live leaderboard broadcast banner.
Rules:
- Shout out the leader or rising stars.
- If CPU for any city is > 70%, warn them about imminent meltdown or advise scaling PUs!
- If throughput (QPS) is huge, celebrate the Throughput Titan.
- Urge cities without graphs to deploy their Spanner Graph DDL immediately.
- Use fun Disney/theme-park and cloud/database puns (Space Mountain, pixie dust, PUs, ACID, lock contention, Main Street).
- Do NOT output preamble, quotes, markdown headings, or bullet points. Just output the clean broadcast string."""

    try:
        import google.auth
        from google.auth.transport.requests import Request

        creds, proj = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        creds.refresh(Request())
        token = creds.token
        target_project = proj or admin_project_id

        url = f"https://aiplatform.googleapis.com/v1/projects/{target_project}/locations/global/publishers/google/models/{model}:generateContent"
        
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt_text}]
                }
            ],
            "generationConfig": {
                "temperature": 0.85,
                "maxOutputTokens": 1000
            }
        }

        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            data=json.dumps(payload).encode("utf-8")
        )

        with urllib.request.urlopen(req, timeout=12) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            candidate = res_data.get("candidates", [{}])[0]
            parts = candidate.get("content", {}).get("parts", [{}])
            text = parts[0].get("text", "").strip()
            # Clean up outer quotes if present
            if text.startswith('"') and text.endswith('"'):
                text = text[1:-1].strip()
            
            if text:
                return text, now_str, f"Gemini 3.8 Flash ({model})"

    except Exception as e:
        logger.warning(f"LLM broadcast generation fallback: {e}")

    # Fallback to dynamic template if LLM is unreachable or timed out
    leader_city = digest.get("leader", {}).get("city", "Leading Park")
    max_cpu = digest.get("max_cpu", {}).get("cpu_pct", 0)
    cpu_city = digest.get("max_cpu", {}).get("city", "")

    if max_cpu >= 75:
        fallback = f"🔥 Meltdown Alert! {cpu_city} is redlining at {max_cpu}% Spanner CPU—scale those Processing Units before Space Mountain halts!"
    elif digest.get("pending_graphs_count", 0) > 0:
        sample = ", ".join(digest.get("pending_graph_sample", []))
        fallback = f"🏰 {leader_city} is commanding the standings, but {sample} still need to deploy their Spanner Graphs! Time is ticking!"
    else:
        import random
        fallback = random.choice(FALLBACK_MESSAGES)

    return fallback, now_str, "Dynamic Rules (Offline Fallback)"
