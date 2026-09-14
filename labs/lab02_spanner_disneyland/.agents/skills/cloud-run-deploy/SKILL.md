---
name: cloud-run-deploy
description: Provides guidelines and best practices for containerizing FastAPI applications with Docker and deploying them seamlessly to Google Cloud Run using the gcloud CLI.
---
# Cloud Run Deployment for FastAPI Applications

## 1. Containerization Best Practices

### Dynamic Port Binding
Cloud Run injects the listening port into the `PORT` environment variable (defaults to `8080`). Ensure the application server reads this variable:
```python
import os
import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("app:app", host="0.0.0.0", port=port)
```

### Dockerfile Pattern
Use an official lightweight Python runtime. Keep layers cached and minimal:
```dockerfile
FROM python:3.11-slim

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files (app.py, index.html, static assets)
COPY . .

# Set default port (overridden by Cloud Run runtime)
ENV PORT=8080
EXPOSE 8080

CMD exec uvicorn app:app --host 0.0.0.0 --port ${PORT}
```

### .dockerignore
Exclude local environments and caches from the build context:
```text
__pycache__
*.pyc
*.pyo
*.pyd
.Python
env/
venv/
.venv/
.git
.gitignore
.agents/
```

---

## 2. Deployment via gcloud CLI

Deploy directly from source using Cloud Run's automated source deployment:
```bash
gcloud run deploy disneyland-navigator \
  --source . \
  --region europe-west1 \
  --allow-unauthenticated \
  --set-env-vars GOOGLE_CLOUD_LOCATION=global,GOOGLE_GENAI_USE_VERTEXAI=true \
  --quiet
```

* `--source .`: Automatically builds the container image using the `Dockerfile` in the current directory and uploads it to Artifact Registry.
* `--allow-unauthenticated`: Makes the endpoint publicly accessible for testing in the browser.
* `--set-env-vars`: Injects required routing flags for Vertex AI / ADK.

To retrieve the live URL:
```bash
gcloud run services describe disneyland-navigator --region europe-west1 --format="value(status.url)"
```
