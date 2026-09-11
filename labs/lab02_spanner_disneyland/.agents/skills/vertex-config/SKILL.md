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

## 3. Agent Setup Scaffold
Implement the `Agent` configuration inside the backend Python application using the `google.adk` SDK:

```python
from google.adk.agents import Agent

agent = Agent(
    name="disneyland_agent",
    model="gemini-3.8-flash",  # Verified Vertex AI model name
    description="Agent configured to answer database and attraction route questions.",
    instruction=system_instruction,
    tools=tools,               # List of loaded MCP tools
)
```

---

## 4. MCP Connection & Session Lifecycle Management
To avoid validation collisions, `TaskGroup` sub-exceptions, or connection issues:
- Always instantiate fresh client sessions/MCP stream servers for distinct agent runs.
- Never reuse a closed `McpStreamableHttpServer` or client instance across sequential runner lifecycles.
