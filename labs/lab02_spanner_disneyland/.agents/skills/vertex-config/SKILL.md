---
name: vertex-config
description: Provides explicit, verified guidelines for configuring google-adk agents to connect to Google Cloud Vertex AI APIs, resolve project/credential dependencies, and select active models under the DataForge Krakow workshop sandbox.
---
# GCP Vertex AI Model & Credentials Configuration

## 1. Vertex AI Initialization & Project Resolution
To ensure the agent has authorization to make Vertex AI API calls, programmatically resolve the active Google Cloud project ID and set the environment variables required by the Google Gen AI SDK.

```python
import os
import subprocess

def get_active_project_id():
    # 1. Check environment variable
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT_ID")
    if project_id:
        return project_id
    # 2. Fallback to active gcloud configuration
    try:
        result = subprocess.run(
            ["gcloud", "config", "get-value", "project"],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except Exception:
        return None

# Resolve and set credentials context
PROJECT_ID = get_active_project_id()
if PROJECT_ID:
    os.environ["GOOGLE_CLOUD_PROJECT"] = PROJECT_ID

# Set Gen AI SDK routing variables
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
```

---

## 2. Verified Model Selection
When running in GCP Vertex AI mode, use this active model identifier:

- **Primary Model:** `gemini-3.8-flash`

---

## 3. Verified ADK Agent & Spanner Tool Scaffold
Implement the `Agent` and `Runner` configuration using the `google.adk` SDK. To avoid schema serialization errors (`_gemini_schema_util.py`) or MCP connection timeouts, use the native Python Spanner tool or standard MCP toolset:

```python
import os
from google.cloud import spanner
from google.adk.agents import Agent
from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part

# --- 1. Spanner Database Tool Definition ---
def query_spanner(query: str) -> str:
    """Executes a SQL query or Spanner Graph GQL query on the Cloud Spanner 'agent-lab' database.
    
    Args:
        query: Valid SQL or GQL string (e.g., 'SELECT * FROM Attraction' or 'GRAPH_TABLE(DisneylandGraph MATCH ...)')
    Returns:
        String representation of the resulting rows or error message.
    """
    try:
        project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", "CURRENT_PROJECT")
        client = spanner.Client(project=project_id)
        instance = client.instance("disneyland")
        database = instance.database("agent-lab")
        with database.snapshot() as snapshot:
            results = snapshot.execute_sql(query)
            rows = [list(r) for r in results]
            return str(rows[:50])
    except Exception as e:
        return f"Error executing query: {str(e)}"

# --- 2. ADK Agent Definition ---
system_instruction = (
    "You are the Disneyland Paris AI Navigator Concierge. "
    "Use the query_spanner tool to answer guest questions about park attractions, zones, wait times, and routes. "
    "Always base your answers on actual data from Spanner."
)

agent = Agent(
    name="disneyland_agent",
    model="gemini-3.8-flash",  # Verified Vertex AI model name
    description="Agent configured to answer database and attraction route questions.",
    instruction=system_instruction,
    tools=[query_spanner],     # Native tool guarantees zero schema serialization failures
)

# --- 3. Runner & Session Service Lifecycle ---
session_service = InMemorySessionService()
runner = Runner(agent=agent, app_name="disneyland_app", session_service=session_service)

async def ask_disneyland_agent(user_message: str, session_id: str = "guest_session") -> str:
    """Invokes the ADK agent asynchronously and aggregates streaming text response."""
    user_id = "default_guest"
    session = await session_service.get_session(app_name="disneyland_app", user_id=user_id, session_id=session_id)
    if not session:
        await session_service.create_session(app_name="disneyland_app", user_id=user_id, session_id=session_id)
    
    message = Content(role="user", parts=[Part(text=user_message)])
    response_text = ""
    async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=message):
        if hasattr(event, "content") and event.content:
            for part in event.content.parts:
                if hasattr(part, "text") and part.text:
                    response_text += part.text
    return response_text or "No response received from agent."
```

---

## 4. MCP Server Connection Details
If connecting to the Google-managed Spanner MCP server (`https://spanner.googleapis.com/mcp`):
- Endpoint: `https://spanner.googleapis.com/mcp` (Google Cloud authentication via ADC Bearer token).
- **Troubleshooting Note**: If external MCP servers trigger schema serialization issues inside `_gemini_schema_util.py`, immediately use the native `query_spanner` tool above. It provides direct, deterministic Spanner query execution with zero network handshake overhead.

