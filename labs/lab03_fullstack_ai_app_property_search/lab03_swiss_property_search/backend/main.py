import os
import asyncio
import json
import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import google.auth
from google.cloud import storage
import logging
import sys
import re
from typing import List, Any

# ==============================================================================
# LOGGING CONFIGURATION
# ==============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ==============================================================================
# CONFIGURATION & INITIALIZATION
# ==============================================================================

# Load environment variables from .env file
backend_dir = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(backend_dir, '.env')
load_dotenv(dotenv_path=dotenv_path)

app = FastAPI(title="AlloyDB Property Search GDA Demo")

# Configure CORS
ALLOWED_ORIGINS_STR = os.getenv("ALLOWED_ORIGINS", "*")
ALLOWED_ORIGINS = [origin.strip() for origin in ALLOWED_ORIGINS_STR.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PROJECT_ID = os.getenv("GCP_PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT")
AGENT_CONTEXT_SET_ID_ALLOYDB = os.getenv("AGENT_CONTEXT_SET_ID_ALLOYDB")
DB_NAME = os.getenv("DB_NAME", "postgres")

# Security: SSRF Protection
ALLOWED_GCS_BUCKET = os.getenv("ALLOWED_GCS_BUCKET")
if not ALLOWED_GCS_BUCKET and PROJECT_ID:
    ALLOWED_GCS_BUCKET = f"property-images-data-agent-{PROJECT_ID}"
    logger.info(f"ALLOWED_GCS_BUCKET not set. Defaulting to: {ALLOWED_GCS_BUCKET}")
elif ALLOWED_GCS_BUCKET:
    logger.info(f"ALLOWED_GCS_BUCKET set to: {ALLOWED_GCS_BUCKET}")

storage_client = None
try:
    credentials, _ = google.auth.default(
        scopes=['https://www.googleapis.com/auth/cloud-platform']
    )
    storage_client = storage.Client(project=PROJECT_ID, credentials=credentials)
    print("Google Cloud Storage client initialized successfully.")
except Exception as e:
    print(f"Warning: Google Cloud storage client initialization failed. Image serving may not work.\nError: {e}")

# ==============================================================================
# DATA MODELS
# ==============================================================================

class SearchRequest(BaseModel):
    query: str
    backend: str = "alloydb"
    demo_mode: bool = False

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

_gda_credentials = None

def get_gda_credentials():
    """
    Retrieves and caches Google credentials for GDA access.
    """
    global _gda_credentials
    scopes = ['https://www.googleapis.com/auth/cloud-platform', 'https://www.googleapis.com/auth/userinfo.email']

    if _gda_credentials is None:
        _gda_credentials, _ = google.auth.default(scopes=scopes)

    if not _gda_credentials.valid:
        _gda_credentials.refresh(google.auth.transport.requests.Request())

    return _gda_credentials

SAMPLE_QUERIES = [
    "Show me 2-bedroom apartments in Zurich under 3000 CHF",
    "Show me family apartments in Zurich with a nice view up to 16k",
    "Show me cheap studios in Geneva",
    "Show me Lovely Mountain Cabins under 15k"
]

def get_normalized_query_slug(query: str) -> str:
    normalized = re.sub(r'[^a-z0-9]', '_', query.lower())
    normalized = re.sub(r'_+', '_', normalized).strip('_')
    return normalized

def is_sample_query(query: str) -> bool:
    q = query.strip().lower()
    return any(ex.strip().lower() == q for ex in SAMPLE_QUERIES)

def save_to_gcs(bucket_name: str, blob_name: str, data: dict):
    if not storage_client:
        logger.warning("Storage client not initialized. Cannot save to GCS.")
        return
    try:
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.upload_from_string(
            json.dumps(data, indent=2),
            content_type='application/json'
        )
        logger.info(f"Successfully saved data to gs://{bucket_name}/{blob_name}")
    except Exception as e:
        logger.error(f"Failed to save data to GCS: {e}")

def load_from_gcs(bucket_name: str, blob_name: str) -> dict:
    if not storage_client:
        logger.warning("Storage client not initialized. Cannot load from GCS.")
        return None
    try:
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        if not blob.exists():
            logger.info(f"GCS Blob gs://{bucket_name}/{blob_name} does not exist.")
            return None
        content = blob.download_as_text()
        return json.loads(content)
    except Exception as e:
        logger.error(f"Failed to load data from GCS: {e}")
        return None

def query_gda(prompt: str, backend: str = "alloydb") -> dict:
    """
    Queries the Gemini Data Agent (GDA) API.
    """
    gda_location = os.getenv("GCP_LOCATION", "europe-west1")
    url = f"https://geminidataanalytics.googleapis.com/v1beta/projects/{PROJECT_ID}/locations/{gda_location}:queryData"
    
    creds = get_gda_credentials()
    headers = {
        "Authorization": f"Bearer {creds.token}",
        "Content-Type": "application/json"
    }
    
    if backend != "alloydb":
         raise HTTPException(400, f"Unsupported backend: {backend}. Only 'alloydb' is supported.")
         
    if not AGENT_CONTEXT_SET_ID_ALLOYDB:
        raise HTTPException(500, "AGENT_CONTEXT_SET_ID_ALLOYDB is not configured.")
        
    datasource_references = {
        "alloydb": {
            "databaseReference": {
                "project_id": PROJECT_ID,
                "region": os.getenv("GCP_LOCATION", gda_location),
                "cluster_id": os.getenv("ALLOYDB_CLUSTER_ID", "search-cluster"),
                "instance_id": os.getenv("ALLOYDB_INSTANCE_ID", "search-primary"),
                "database_id": DB_NAME
            },
            "agentContextReference": {"context_set_id": AGENT_CONTEXT_SET_ID_ALLOYDB}
        }
    }

    payload = {
        "parent": f"projects/{PROJECT_ID}/locations/{gda_location}",
        "prompt": prompt,
        "context": {
            "datasourceReferences": datasource_references
        },
        "generation_options": {
            "generate_query_result": True,
            "generate_natural_language_answer": True,
            "generate_explanation": True
        }
    }
    
    try:
        logger.info(f"Sending request to GDA API: {url}")
        resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=120)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"GDA API Request Failed: {e}")
        if hasattr(e, 'response') and e.response:
             logger.error(f"GDA Error Response: {e.response.text}")
        raise HTTPException(500, f"Failed to query Gemini Data Agent: {e}")

# ==============================================================================
# API ENDPOINTS
# ==============================================================================

@app.get("/api/image")
async def get_image(gcs_uri: str):
    """
    Serves images from Google Cloud Storage (GCS).
    """
    if not storage_client:
        raise HTTPException(500, "Storage client is not initialized.")

    try:
        if gcs_uri.startswith("gs://"):
            path = gcs_uri[5:]
        elif gcs_uri.startswith("https://storage.googleapis.com/"):
            path = gcs_uri[31:]
        else:
            raise HTTPException(400, "Invalid GCS URI format.")
            
        if "/" not in path:
             raise HTTPException(400, "Invalid GCS URI: Missing object path.")

        bucket_name, blob_name = path.split("/", 1)

        if ALLOWED_GCS_BUCKET:
            if bucket_name != ALLOWED_GCS_BUCKET:
                logger.warning(f"Blocked SSRF attempt. Requested bucket: '{bucket_name}', Allowed: '{ALLOWED_GCS_BUCKET}'")
                raise HTTPException(403, "Access to this bucket is restricted.")
        else:
             logger.error("ALLOWED_GCS_BUCKET is not configured. Rejecting request to prevent SSRF.")
             raise HTTPException(500, "Server configuration error: Image source not trusted.")

        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        try:
            signed_url = blob.generate_signed_url(
                version="v4",
                expiration=3600,
                method="GET"
            )
            return RedirectResponse(
                url=signed_url, 
                status_code=307,
                headers={"Cache-Control": "public, max-age=300"}
            )
        except Exception as sign_err:
            logger.warning(f"Signed URL generation failed, falling back to streaming: {sign_err}")
            file_obj = blob.open("rb")
            return StreamingResponse(
                file_obj, 
                media_type="image/jpeg", 
                headers={"Cache-Control": "public, max-age=86400"}
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving image: {e}")
        raise HTTPException(404, "Image not found or inaccessible.")

@app.post("/api/search")
async def search_properties(request: SearchRequest):
    """
    Handles property search requests using the Gemini Data Agent.
    """
    logger.info(f"Processing search query: '{request.query}' (backend: {request.backend}, demo_mode: {request.demo_mode})")
    
    gda_resp = None
    if request.demo_mode and is_sample_query(request.query):
        slug = get_normalized_query_slug(request.query)
        blob_name = f"demo/{request.backend}/{slug}.json"
        bucket_name = ALLOWED_GCS_BUCKET or f"property-images-data-agent-{PROJECT_ID}"
        
        logger.info(f"Demo mode active. Loading raw GDA response from gs://{bucket_name}/{blob_name}")
        gda_resp = load_from_gcs(bucket_name, blob_name)
        if gda_resp:
            logger.info("Simulating GDA API call latency (3 seconds)...")
            await asyncio.sleep(3)
        else:
            logger.warning("Cached GDA response not found on GCS. Falling back to live GDA query.")
            
    try:
        if not gda_resp:
            gda_resp = query_gda(request.query, request.backend)
            
            if is_sample_query(request.query):
                slug = get_normalized_query_slug(request.query)
                blob_name = f"demo/{request.backend}/{slug}.json"
                bucket_name = ALLOWED_GCS_BUCKET or f"property-images-data-agent-{PROJECT_ID}"
                logger.info(f"Persisting raw GDA response to gs://{bucket_name}/{blob_name}")
                save_to_gcs(bucket_name, blob_name, gda_resp)
        
        nl_answer = gda_resp.get("naturalLanguageAnswer", "")
        query_result = gda_resp.get("queryResult", {})
        rows = query_result.get("rows", [])
        cols = query_result.get("columns", [])
        
        results = []
        if rows and cols:
            col_names = [c["name"] for c in cols]
            for row in rows:
                values = row.get("values", [])
                
                item = {
                    k: (v["value"] if isinstance(v, dict) and "value" in v else v)
                    for k, v in zip(col_names, values)
                    if k not in ("description_embedding", "image_embedding")
                }
                
                if item.get("image_gcs_uri") and item["image_gcs_uri"] != "NULL":
                    item["image_gcs_uri"] = f"/api/image?gcs_uri={item['image_gcs_uri']}"
                else:
                    item["image_gcs_uri"] = None
                
                results.append(item)
        
        generated_sql = gda_resp.get("generatedQuery") or gda_resp.get("queryResult", {}).get("query", "SQL not returned by GDA")
        explanation = gda_resp.get('intentExplanation', '')
        total_row_count = gda_resp.get("queryResult", {}).get("totalRowCount", "0")
        
        query_result_preview = {
            "columns": cols,
            "rows": rows[:3] if rows else []
        }
        
        display_sql = f"// GEMINI DATA AGENT CALL\n// Generated SQL: {generated_sql}\n// Answer: {nl_answer}"
        if explanation:
            display_sql += f"\n// Explanation: {explanation}"
        
        return {
            "listings": results, 
            "sql": display_sql, 
            "nl_answer": nl_answer,
            "details": {
                "generated_query": generated_sql,
                "intent_explanation": explanation,
                "total_row_count": total_row_count,
                "query_result_preview": query_result_preview
            }
        }

    except Exception as e:
        logger.error(f"Search failed: {e}")
        return {
            "listings": [], 
            "sql": f"An error occurred during search: {str(e)}",
            "nl_answer": "I encountered an error while processing your request."
        }

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
