"""
Disneyland Spanner Hackathon: Live AI Park Announcer & Roaster
Generates hilarious, theatrical roast bulletins and 2-line rhymes via Gemini 3.8 Flash
mocking participant cities based on real-time leaderboard statistics.
"""
import os
import json
import time
import datetime
import random
import urllib.request
import urllib.error
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

ROAST_TEMPLATES = [
    {
        "category": "general",
        "emoji": "🎢",
        "roast": "{city}'s park operations are an emotional rollercoaster of query spikes, latency, and glory.",
        "rhyme": "Up and down the metrics go with twists around the bend,\nLet's see if {city} can make it to the winner's circle in the end!"
    },
    {
        "category": "high_cpu",
        "emoji": "🔥",
        "roast": "{city}'s Spanner cluster is redlining so hot that Space Mountain is feeling the heat across the park.",
        "rhyme": "Your queries are blazing and your nodes are running hot,\nCool down your cluster, {city}, give it everything you've got!"
    },
    {
        "category": "low_activity",
        "emoji": "😴",
        "roast": "{city} is taking a leisurely stroll down Main Street while the other parks race ahead.",
        "rhyme": "The rides are empty and the queue has zero line,\nWake up {city}, it's database hackathon time!"
    },
    {
        "category": "leader",
        "emoji": "🏰",
        "roast": "{city} is minting Disney dollars faster than Scrooge McDuck can swim through them.",
        "rhyme": "Your throughput is soaring and your profits break the bank,\nKeep on pushing {city}, hold onto that top rank!"
    },
    {
        "category": "no_graph",
        "emoji": "🗺️",
        "roast": "{city}'s park visitors are wandering Fantasyland in circles because the Property Graph is still missing.",
        "rhyme": "You need nodes and edges to show visitors the way,\nBuild out your graph, {city}, and save the park today!"
    },
    {
        "category": "schema_tuning",
        "emoji": "🛠️",
        "roast": "{city} spent the last thirty minutes fine-tuning database schemas without recording a single ticket sale.",
        "rhyme": "The schema looks pretty and the indexes are aligned,\nNow push some transactions, {city}, don't get left behind!"
    },
    {
        "category": "throughput",
        "emoji": "⚡",
        "roast": "{city} is pushing transactions with such frantic energy that the park's backup generators kicked in.",
        "rhyme": "The throughput is humming and the lights begin to shake,\n{city} is determined to take the biggest piece of cake!"
    }
]

from metrics import get_default_admin_project, parse_projects_mapping

def generate_dynamic_fallback_roast(leaderboard_data: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Generates a dynamic fallback roast by picking an actual participant city from
    the real-time leaderboard or projects mapping, tailoring the joke to their actual status.
    Guarantees no hardcoded event cities!
    """
    target_city = "The Contenders"
    chosen_participant: Optional[Dict[str, Any]] = None

    # 1. Try to pick from real active leaderboard participants
    if leaderboard_data:
        valid_participants = [p for p in leaderboard_data if p.get("city")]
        if valid_participants:
            chosen_participant = random.choice(valid_participants)
            target_city = chosen_participant.get("city", target_city)
    
    # 2. If no leaderboard data, look up projects mapping dynamically
    if target_city == "The Contenders":
        try:
            mapped = parse_projects_mapping()
            if mapped:
                chosen_p = random.choice(mapped)
                target_city = chosen_p.get("city", target_city)
        except Exception:
            pass

    # Clean any facilitator suffix for a natural roast headline
    clean_city = target_city.replace(" (Facilitator)", "").strip()

    # 3. Match template based on participant metrics if available
    selected_template = None
    if chosen_participant:
        cpu = chosen_participant.get("cpu_utilization_pct", 0)
        score = chosen_participant.get("score", 0)
        runs = chosen_participant.get("runs", 0)
        has_graph = chosen_participant.get("has_graph", False)

        if cpu > 60:
            selected_template = next(t for t in ROAST_TEMPLATES if t["category"] == "high_cpu")
        elif runs == 0 and score == 0:
            selected_template = random.choice([
                next(t for t in ROAST_TEMPLATES if t["category"] == "low_activity"),
                next(t for t in ROAST_TEMPLATES if t["category"] == "schema_tuning")
            ])
        elif score > 500:
            selected_template = next(t for t in ROAST_TEMPLATES if t["category"] == "leader")
        elif not has_graph:
            selected_template = next(t for t in ROAST_TEMPLATES if t["category"] == "no_graph")

    if not selected_template:
        selected_template = random.choice(ROAST_TEMPLATES)

    now = datetime.datetime.now()
    return {
        "target_city": clean_city,
        "emoji": selected_template["emoji"],
        "roast": selected_template["roast"].format(city=clean_city),
        "rhyme": selected_template["rhyme"].format(city=clean_city),
        "timestamp": now.strftime("%H:%M:%S"),
        "timestamp_epoch": time.time(),
        "model": "Dynamic Roaster (Fallback)"
    }

def generate_roast_broadcast(
    leaderboard_data: List[Dict[str, Any]], 
    admin_project_id: Optional[str] = None,
    model: str = "gemini-3.8-flash"
) -> Dict[str, Any]:
    """
    Calls Gemini 3.8 Flash to pick one participant city to roast with a witty joke and 2-line rhyme.
    Returns: dict with target_city, emoji, roast, rhyme, timestamp, model
    """
    if admin_project_id is None:
        admin_project_id = get_default_admin_project()
    now_str = time.strftime("%H:%M:%S")
    
    if not leaderboard_data:
        fallback = generate_dynamic_fallback_roast(leaderboard_data)
        fallback.update({"timestamp": now_str, "model": "Dynamic Roaster (Offline)"})
        return fallback

    # Compress participant data for prompt context
    participants_summary = []
    for r in leaderboard_data:
        participants_summary.append({
            "city": r.get("city", "Unknown"),
            "score": r.get("score", 0),
            "rev": round(r.get("revenue", 0), 2),
            "cpu": round(r.get("cpu_utilization_pct", 0), 1),
            "qps": round(r.get("qps", 0), 1),
            "has_graph": r.get("has_graph", False),
            "has_cloud_run": r.get("has_cloud_run", False),
            "pus": r.get("processing_units", 100)
        })

    prompt_text = f"""You are the roasting, hilarious, and theatrical Disney Park Stadium Jester at the Global Spanner Hackathon.
Inspect the real-time leaderboard statistics for these participant parks:
{json.dumps(participants_summary, indent=2)}

Task:
1. Pick ONE city from the list to playfully roast or mock based on their specific numbers:
   - If their CPU is high (>70%), mock them for melting down Space Mountain or running an easy-bake oven.
   - If their score or rows are near zero, tease them for sleeping on Main Street or taking a union break.
   - If they are #1, playfully accuse them of bribing the fairy godmother with counterfeit Disney dollars.
   - If they lack a property graph, roast them for getting lost in Fantasyland without a map.
   - If they deployed Cloud Run, praise or roast their supersonic cloud deployment speed.
   - If their throughput (QPS) is wild, wonder if they hooked their laptop to the park's primary power grid.
2. Produce a sharp, hilarious 1-sentence roast joke.
3. Produce a funny, catchy 2-line rhyming couplet about that specific city's engineering performance.
Rule: Never use double quotes inside the roast or rhyme text (use single quotes 'like this' instead).

Respond ONLY with valid JSON in this exact structure:
{{
  "target_city": "ExactCityName",
  "emoji": "🎭",
  "roast": "1 razor-sharp hilarious sentence mocking their performance",
  "rhyme_lines": [
    "First line of the funny rhyme",
    "Second line of the funny rhyme"
  ]
}}"""

    try:
        import google.auth
        from google.auth.transport.requests import Request
        import re

        target_project = admin_project_id or os.environ.get("GOOGLE_CLOUD_QUOTA_PROJECT") or os.environ.get("ADMIN_PROJECT_ID")
        creds, proj = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
            quota_project_id=target_project if target_project else None
        )
        creds.refresh(Request())
        token = creds.token
        target_project = target_project or proj

        url = f"https://aiplatform.googleapis.com/v1/projects/{target_project}/locations/global/publishers/google/models/{model}:generateContent"
        
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt_text}]
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.95,
                # NOTE: on Gemini 3.x this budget is shared between *thinking*
                # tokens and output tokens. Measured thinking usage for this
                # prompt is 682-956 tokens, so the previous value of 1000 left
                # too little room for the ~110-token JSON body and truncated it
                # (finishReason=MAX_TOKENS) in roughly 1 of every 10 calls.
                "maxOutputTokens": 4000
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

        # A thinking model on a ~2.4k-token prompt regularly needs more than 12s.
        with urllib.request.urlopen(req, timeout=45) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            candidates = res_data.get("candidates") or [{}]
            candidate = candidates[0]
            finish_reason = candidate.get("finishReason")
            parts = candidate.get("content", {}).get("parts", [])
            text = "".join([p.get("text", "") for p in parts if "text" in p]).strip()
            
            # Clean markdown codeblocks if present
            if text.startswith("```"):
                lines = text.splitlines()
                if lines and lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                text = "\n".join(lines).strip()

            parsed = None
            try:
                parsed = json.loads(text, strict=False)
            except Exception:
                # Regex fallback extractor
                t_match = re.search(r'"target_city"\s*:\s*"([^"]+)"', text)
                r_match = re.search(r'"roast"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
                e_match = re.search(r'"emoji"\s*:\s*"([^"]+)"', text)
                rhyme_matches = re.findall(r'"([^"\n\r]{10,})"', text.split("rhyme_lines")[-1]) if "rhyme_lines" in text else []
                if t_match and r_match:
                    parsed = {
                        "target_city": t_match.group(1),
                        "emoji": e_match.group(1) if e_match else "🎭",
                        "roast": r_match.group(1),
                        "rhyme_lines": rhyme_matches[:2]
                    }

            if parsed and "target_city" in parsed and "roast" in parsed:
                rhyme = "\n".join(parsed.get("rhyme_lines", [])) if "rhyme_lines" in parsed else parsed.get("rhyme", "")
                parsed["rhyme"] = rhyme
                parsed["timestamp"] = now_str
                parsed["timestamp_epoch"] = time.time()
                parsed["model"] = "Gemini 3.8 Flash"
                return parsed

            # Reaching here previously fell through to the fallback silently,
            # making a degraded roaster indistinguishable from a healthy one.
            logger.warning(
                "LLM roast unusable, using fallback "
                f"(finishReason={finish_reason}, text_len={len(text)}): {text[:200]!r}"
            )

    except Exception as e:
        logger.warning(f"LLM roast generation fallback: {e}")


    # Fallback to rich dynamic selection
    fallback = generate_dynamic_fallback_roast(leaderboard_data)
    fallback["timestamp"] = now_str
    fallback["timestamp_epoch"] = time.time()
    fallback["model"] = "Dynamic Roaster (Fallback)"
    return fallback

# Legacy compatibility wrapper
def generate_flash_commentary(leaderboard_data, admin_project_id=None, model="gemini-3.8-flash"):
    roast_data = generate_roast_broadcast(leaderboard_data, admin_project_id, model)
    combined = f"[{roast_data['target_city']}] {roast_data['roast']} ✨ \"{roast_data['rhyme']}\""
    return combined, roast_data["timestamp"], roast_data["model"]

