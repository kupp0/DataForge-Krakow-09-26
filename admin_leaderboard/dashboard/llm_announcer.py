"""
Disneyland Spanner Hackathon: Live AI Park Announcer & Roaster
Generates hilarious, theatrical roast bulletins and 2-line rhymes via Gemini 3.8 Flash
mocking participant cities based on real-time leaderboard statistics.
"""
import os
import json
import time
import random
import urllib.request
import urllib.error
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

FALLBACK_ROASTS = [
    {
        "target_city": "London",
        "emoji": "🌧️",
        "roast": "London’s Spanner instance has lower throughput than the line for Peter Pan's Flight in a downpour.",
        "rhyme": "Big Ben stopped ticking while your nodes fell asleep,\nWith zero transactions, even Mickey had to weep!"
    },
    {
        "target_city": "Tokyo",
        "emoji": "🔥",
        "roast": "Tokyo is redlining their CPU so hard that Space Mountain is legally classified as an active volcano.",
        "rhyme": "Your queries are blazing, your CPU is pure heat,\nScale up your PUs or face catastrophic defeat!"
    },
    {
        "target_city": "Paris",
        "emoji": "🥐",
        "roast": "Paris is taking a 2-hour café break while their Spanner property graph remains completely unbuilt.",
        "rhyme": "You ordered a croissant and forgot about your graph,\nNow the other twenty-four parks are having a good laugh!"
    },
    {
        "target_city": "Berlin",
        "emoji": "🎛️",
        "roast": "Berlin spent forty minutes tuning their database schema to techno beats without inserting a single row.",
        "rhyme": "The bass is pumping loud but the table has no data,\nYou can party at Berghain, but you'll fail the hackathon later!"
    },
    {
        "target_city": "Sydney",
        "emoji": "🦘",
        "roast": "Sydney's throughput is bouncing like a startled kangaroo, but their error rate is doing triple flips.",
        "rhyme": "Down under you're pushing ten thousand requests a minute,\nToo bad half of your transactions don't have any rows in it!"
    }
]

def generate_roast_broadcast(
    leaderboard_data: List[Dict[str, Any]], 
    admin_project_id: str = "dataforge26krk-6725",
    model: str = "gemini-3.8-flash"
) -> Dict[str, Any]:
    """
    Calls Gemini 3.8 Flash to pick one participant city to roast with a witty joke and 2-line rhyme.
    Returns: dict with target_city, emoji, roast, rhyme, timestamp, model
    """
    now_str = time.strftime("%H:%M:%S")
    
    if not leaderboard_data:
        fallback = random.choice(FALLBACK_ROASTS)
        fallback.update({"timestamp": now_str, "model": "Offline Fallback"})
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
                "responseMimeType": "application/json",
                "temperature": 0.95,
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
                parsed["model"] = "Gemini 3.8 Flash"
                return parsed

    except Exception as e:
        logger.warning(f"LLM roast generation fallback: {e}")

    # Fallback to rich random selection
    fallback = dict(random.choice(FALLBACK_ROASTS))
    fallback["timestamp"] = now_str
    fallback["model"] = "Dynamic Roaster (Fallback)"
    return fallback

# Legacy compatibility wrapper
def generate_flash_commentary(leaderboard_data, admin_project_id="dataforge26krk-6725", model="gemini-3.8-flash"):
    roast_data = generate_roast_broadcast(leaderboard_data, admin_project_id, model)
    combined = f"[{roast_data['target_city']}] {roast_data['roast']} ✨ \"{roast_data['rhyme']}\""
    return combined, roast_data["timestamp"], roast_data["model"]

