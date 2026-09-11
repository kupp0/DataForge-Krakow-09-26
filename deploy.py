#!/usr/bin/env python3
# ==============================================================================
# Data Forge: Resilient Parallel Local Loop Orchestrator (Deploy & Destroy)
# ==============================================================================
import os
import sys
import json
import time
import shutil
import random
import re
import zipfile
import argparse
import subprocess
import logging
from concurrent.futures import ThreadPoolExecutor

STATE_FILE = ".deploy_state.json"
PROJECTS_FILE = "projects.txt"
WORKDIR_BASE = ".deploy_workdirs"
PLUGIN_CACHE_DIR = ".terraform_plugin_cache"

# Configure local file logging
LOG_DIR = "deploy_logs"
LOG_FILE = None

def setup_logging():
    global LOG_FILE
    os.makedirs(LOG_DIR, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    LOG_FILE = os.path.join(LOG_DIR, f"deploy_{timestamp}.log")
    logging.basicConfig(
        filename=LOG_FILE,
        filemode="w",
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s"
    )
    return LOG_FILE

# ANSI Color Codes for Premium CLI Styling
COLOR_RESET = "\033[0m"
COLOR_BOLD = "\033[1m"
COLOR_GREEN = "\033[92m"
COLOR_YELLOW = "\033[93m"
COLOR_RED = "\033[91m"
COLOR_GRAY = "\033[90m"
COLOR_CYAN = "\033[96m"
COLOR_MAGENTA = "\033[95m"

BANNER = f"""{COLOR_CYAN}{COLOR_BOLD}
=================================================================
  🚀 DATA FORGE LOCAL PARALLEL PROVISIONING ENGINE 🚀
================================================================={COLOR_RESET}
"""

DESTROY_BANNER = f"""{COLOR_RED}{COLOR_BOLD}
=================================================================
  🔥 DATA FORGE LOCAL PARALLEL TEARDOWN ENGINE 🔥
================================================================={COLOR_RESET}
"""

def classify_error(error_text):
    """
    Classifies an error string into a standardized failure category,
    a concise badge, and actionable resolution advice.
    """
    err = str(error_text).lower()
    
    if any(kw in err for kw in ["oauth2: access_denied", "invalid_grant", "restricted", "credentials not found", "application default credentials", "invalid credentials", "autherror", "access_token_type_unsupported", "error 401"]):
        return (
            "ADC_AUTH_EXPIRED",
            "ADC Expired",
            "Application Default Credentials (ADC) token missing, expired, or restricted.",
            "Run: gcloud auth application-default login"
        )
    if any(kw in err for kw in ["not found", "not_found", "does not exist", "404", "cannot find project"]):
        return (
            "PROJECT_NOT_FOUND",
            "Bad Project ID",
            "Project does not exist or project ID is mistyped in projects.txt.",
            "Check projects.txt: Use GCP Project ID (e.g. data-forge26tst-XXXX), not username (devstarXXXX)."
        )
    if any(kw in err for kw in ["permission denied", "forbidden", "403 forbidden", "unauthorized", "caller does not have permission"]):
        return (
            "IAM_UNAUTHORIZED",
            "Permission Denied",
            "Caller account does not have sufficient IAM permissions on this project.",
            "Ensure your gcloud active account has Owner/Editor role on the target GCP Project."
        )
    if any(kw in err for kw in ["state locked", "412 precondition", "tflock", "lock info"]):
        return (
            "STATE_LOCK",
            "State Lock",
            "Terraform remote state lock contention in GCS bucket.",
            "Run: gcloud storage rm gs://[PROJECT_ID]-tfstate/terraform/state/default.tflock"
        )
    if any(kw in err for kw in ["429", "quota", "rate limit", "too many requests", "resource_exhausted"]):
        return (
            "QUOTA_RATE_LIMIT",
            "Rate Limited",
            "GCP API rate limit or quota exceeded.",
            "Transient rate limit. Re-run deploy.sh with lower concurrency (--max-workers 5)."
        )
    if any(kw in err for kw in ["500", "503", "internal error", "service unavailable", "backend error"]):
        return (
            "SERVICE_UNAVAILABLE",
            "GCP 503/500",
            "Transient GCP internal API error.",
            "Transient backend issue. Re-run deploy.sh to resume provisioning from remote state."
        )
    if any(kw in err for kw in ["billing not enabled", "billing_disabled", "account is disabled"]):
        return (
            "BILLING_DISABLED",
            "Billing Disabled",
            "Cloud Billing is not enabled or linked to this GCP project.",
            "Link a Cloud Billing account to the project in Google Cloud Console."
        )
        
    return (
        "TERRAFORM_ERROR",
        "Apply Error",
        "Terraform apply failed. Inspect the detailed execution log.",
        "Inspect log: deploy_logs/[PROJECT_ID]_apply.log"
    )

def is_retryable_error(error_text):
    """
    Distinguishes transient network/rate-limit glitches from permanent fatal errors.
    Fatal errors (auth expired, missing project, unauthorized IAM) FAIL FAST.
    """
    err = str(error_text).lower()
    
    # 1. Hard fatal indicators -> NEVER retry
    fatal_keywords = [
        "not found", "does not exist", "permission denied", "forbidden",
        "account restricted", "invalid_grant", "unauthorized", "unauthenticated",
        "credentials not found", "403", "404", "invalid project", "billing not enabled",
        "billing_disabled"
    ]
    if any(kw in err for kw in fatal_keywords):
        return False
        
    # 2. Transient retryable indicators
    transient_keywords = [
        "429", "quota", "rate limit", "too many requests", "resource_exhausted",
        "service unavailable", "503", "500", "internal error", "try again later",
        "deadline exceeded", "timeout", "connection reset", "broken pipe"
    ]
    return any(kw in err for kw in transient_keywords)

def check_environment_and_auth():
    """
    Verifies that gcloud CLI, Terraform, and Application Default Credentials (ADC)
    are installed, active, and properly aligned before starting execution.
    """
    print(f"🔍 Step 0: Checking environment & authentication consistency...")
    
    # 1. Check gcloud CLI active account
    res_gcloud = subprocess.run(["gcloud", "config", "get-value", "account"], capture_output=True, text=True)
    active_account = res_gcloud.stdout.strip()
    if not active_account:
        print(f"\n{COLOR_RED}❌ ERROR: No active gcloud account found.{COLOR_RESET}")
        print(f"👉 Please authenticate with your Google account:")
        print(f"   {COLOR_GREEN}gcloud auth login{COLOR_RESET}\n")
        sys.exit(1)
        
    # 2. Check Application Default Credentials (ADC) token validity (Terraform requirement)
    res_adc = subprocess.run(
        ["gcloud", "auth", "application-default", "print-access-token"],
        capture_output=True, text=True
    )
    if res_adc.returncode != 0 or not res_adc.stdout.strip():
        err_msg = res_adc.stderr.strip()
        print(f"\n{COLOR_RED}================================================================={COLOR_RESET}")
        print(f"{COLOR_RED}❌ AUTHENTICATION ERROR: Application Default Credentials (ADC) Missing/Expired{COLOR_RESET}")
        print(f"{COLOR_RED}================================================================={COLOR_RESET}")
        print(f"Active gcloud account is: {COLOR_BOLD}{active_account}{COLOR_RESET}")
        print(f"However, Terraform uses Application Default Credentials (ADC), which is not active or expired.")
        if err_msg:
            print(f"{COLOR_GRAY}Details: {err_msg}{COLOR_RESET}")
        print(f"\n👉 {COLOR_BOLD}Run the following command to authenticate ADC for Terraform:{COLOR_RESET}")
        print(f"   {COLOR_GREEN}{COLOR_BOLD}gcloud auth application-default login{COLOR_RESET}\n")
        sys.exit(1)

    # 3. Check Terraform binary
    res_tf = subprocess.run(["terraform", "version"], capture_output=True, text=True)
    if res_tf.returncode != 0:
        print(f"\n{COLOR_RED}❌ ERROR: Terraform is not working properly.{COLOR_RESET}")
        print(res_tf.stderr)
        sys.exit(1)
        
    logging.info(f"Pre-flight check passed: Active gcloud account '{active_account}' with valid ADC.")
    print(f"  {COLOR_GREEN}✔{COLOR_RESET} Authenticated as: {COLOR_BOLD}{active_account}{COLOR_RESET} (ADC verified & active)")

def parse_and_validate_projects(auto_yes=False):
    """
    Parses projects.txt, lints syntax/formats, and performs a fast reachability
    probe for each project. Partitions projects into valid and invalid sets.
    """
    logging.info(f"Parsing and validating projects file: {PROJECTS_FILE}")
    if not os.path.exists(PROJECTS_FILE):
        logging.error(f"Projects file not found: {PROJECTS_FILE}")
        print(f"{COLOR_RED}❌ ERROR: {PROJECTS_FILE} not found.{COLOR_RESET}")
        print("Please ensure the target repository has been scaffolded.")
        sys.exit(1)
        
    raw_entries = []
    with open(PROJECTS_FILE, "r") as f:
        for line_num, line in enumerate(f, 1):
            line_clean = line.split("#")[0].strip()
            if not line_clean:
                continue
            parts = [p.strip() for p in line_clean.split(",")]
            if len(parts) < 2:
                print(f"{COLOR_YELLOW}⚠️ Warning: Line {line_num} in {PROJECTS_FILE} is malformed (needs: PROJECT_ID, PARTICIPANT_EMAIL). Skipping.{COLOR_RESET}")
                continue
                
            project_id = parts[0]
            iap_member = parts[1]
            if "@" in iap_member and not any(iap_member.startswith(prefix) for prefix in ["user:", "group:", "serviceAccount:", "domain:"]):
                iap_member = f"user:{iap_member}"
            region = parts[2] if len(parts) >= 3 else "europe-west3"
            
            raw_entries.append({
                "project_id": project_id,
                "user": iap_member,
                "region": region,
                "line_num": line_num
            })
            
    if not raw_entries:
        print(f"{COLOR_RED}❌ ERROR: No valid project mappings found in {PROJECTS_FILE}.{COLOR_RESET}")
        sys.exit(1)
        
    print(f"\n📡 Probing {len(raw_entries)} project(s) for reachability and IAM authorization...")
    
    valid_projects = []
    invalid_projects = []
    
    # Fast synchronous reachability probe
    for entry in raw_entries:
        pid = entry["project_id"]
        
        # Heuristic 1: Detect username prefix mistake (devstar123 vs data-forge26tst-123)
        if re.match(r"^devstar\d+$", pid, re.IGNORECASE):
            suffix = pid.lower().replace("devstar", "")
            reason = f"Looks like a lab participant username ('{pid}') rather than a GCP Project ID. Did you mean 'data-forge26tst-{suffix}'?"
            invalid_projects.append((entry, reason))
            continue
            
        # Probe GCP Project describe
        probe_cmd = ["gcloud", "projects", "describe", pid, "--format=value(projectNumber)"]
        probe_res = subprocess.run(probe_cmd, capture_output=True, text=True)
        
        if probe_res.returncode == 0 and probe_res.stdout.strip():
            entry["project_number"] = probe_res.stdout.strip()
            valid_projects.append(entry)
        else:
            err_text = probe_res.stderr.strip()
            if "not found" in err_text.lower() or "404" in err_text:
                reason = "Project does not exist in Google Cloud. Verify project ID spelling."
            elif "permission denied" in err_text.lower() or "403" in err_text:
                reason = "Permission denied. Active account lacks Viewer/Owner permission on this project."
            else:
                reason = f"Describe failed: {err_text[:100]}"
            invalid_projects.append((entry, reason))
            
    if invalid_projects:
        print(f"\n{COLOR_YELLOW}================================================================={COLOR_RESET}")
        print(f"{COLOR_YELLOW}⚠️  PROJECT REACHABILITY WARNINGS ({len(invalid_projects)} Inaccessible / Invalid){COLOR_RESET}")
        print(f"{COLOR_YELLOW}================================================================={COLOR_RESET}")
        for entry, reason in invalid_projects:
            print(f"  • {COLOR_BOLD}{entry['project_id']}{COLOR_RESET} (Line {entry['line_num']}): {COLOR_RED}{reason}{COLOR_RESET}")
        print(f"{COLOR_YELLOW}================================================================={COLOR_RESET}\n")
        
        if not valid_projects:
            print(f"{COLOR_RED}❌ ERROR: None of the projects in {PROJECTS_FILE} are valid or accessible. Aborting.{COLOR_RESET}")
            sys.exit(1)
            
        if not auto_yes:
            prompt_msg = f"Proceed with provisioning the {COLOR_GREEN}{len(valid_projects)} valid project(s){COLOR_RESET} and skip the {COLOR_RED}{len(invalid_projects)} invalid one(s){COLOR_RESET}? (y/n): "
            choice = input(prompt_msg).strip().lower()
            if choice not in ("y", "yes"):
                print("Deployment aborted by user. Please correct projects.txt and try again.")
                sys.exit(0)
        else:
            print(f"⚡ Headless mode: Proceeding with {len(valid_projects)} valid project(s) (Skipping {len(invalid_projects)} invalid).")
            
    return valid_projects, invalid_projects

def clear_stale_tf_lock(project_id):
    """Removes any stale Terraform state lock in GCS to prevent 412 Precondition errors."""
    lock_uri = f"gs://{project_id}-tfstate/terraform/state/default.tflock"
    logging.info(f"[{project_id}] Checking for stale Terraform state lock...")
    cmd = ["gcloud", "storage", "rm", lock_uri, f"--project={project_id}"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0:
        logging.info(f"[{project_id}] Successfully removed stale state lock: {lock_uri}")
    else:
        logging.debug(f"[{project_id}] No active or stale state lock found.")
    return True, None

def prepare_single_project(project):
    """Ensures compute and resource manager APIs are enabled and GCE SA has Owner permissions."""
    project_id = project["project_id"]
    logging.info(f"[{project_id}] Starting prerequisites preparation...")
    
    try:
        # 1. Enable Required Core APIs
        for api in ["compute.googleapis.com", "cloudresourcemanager.googleapis.com"]:
            logging.info(f"[{project_id}] Enabling API: {api}")
            cmd = ["gcloud", "services", "enable", api, f"--project={project_id}"]
            for attempt in range(4):
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode == 0:
                    break
                if is_retryable_error(res.stderr) and attempt < 3:
                    sleep_time = min(40, (2 ** attempt) * 3 + random.uniform(1, 3))
                    logging.info(f"[{project_id}] API {api} retryable error ({res.stderr.strip()}). Retrying in {sleep_time:.1f}s... (Attempt {attempt+1}/4)")
                    time.sleep(sleep_time)
                    continue
                cat, badge, desc, fix = classify_error(res.stderr)
                raise Exception(f"Failed to enable API {api} [{badge}]: {res.stderr.strip()}")
                
        # 2. Get Project Number (cached if already probed)
        project_number = project.get("project_number")
        if not project_number:
            logging.info(f"[{project_id}] Retrieving project number...")
            cmd = ["gcloud", "projects", "describe", project_id, "--format=value(projectNumber)"]
            for attempt in range(3):
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode == 0 and res.stdout.strip():
                    project_number = res.stdout.strip()
                    break
                if is_retryable_error(res.stderr) and attempt < 2:
                    time.sleep((2 ** attempt) * 2 + random.uniform(1, 2))
                    continue
                cat, badge, desc, fix = classify_error(res.stderr)
                raise Exception(f"Failed to describe project [{badge}]: {res.stderr.strip()}")
        
        # 3. Configure Compute Engine Service Account IAM Bindings
        gce_sa = f"serviceAccount:{project_number}-compute@developer.gserviceaccount.com"
        for role in ["roles/owner", "roles/storage.objectAdmin"]:
            logging.info(f"[{project_id}] Granting {role} to Compute Engine Service Account...")
            cmd = [
                "gcloud", "projects", "add-iam-policy-binding", project_id,
                f"--member={gce_sa}", f"--role={role}"
            ]
            for attempt in range(4):
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode == 0:
                    break
                if is_retryable_error(res.stderr) and attempt < 3:
                    sleep_time = min(40, (2 ** attempt) * 3 + random.uniform(1, 3))
                    time.sleep(sleep_time)
                    continue
                cat, badge, desc, fix = classify_error(res.stderr)
                raise Exception(f"Failed to grant {role} [{badge}]: {res.stderr.strip()}")
                
        # 4. Create Terraform remote state GCS bucket
        state_bucket = f"gs://{project_id}-tfstate"
        check_cmd = ["gcloud", "storage", "buckets", "describe", state_bucket, f"--project={project_id}"]
        res = subprocess.run(check_cmd, capture_output=True, text=True)
        if res.returncode != 0:
            create_cmd = [
                "gcloud", "storage", "buckets", "create", state_bucket,
                f"--project={project_id}", f"--location={project.get('region', 'europe-west3')}",
                "--uniform-bucket-level-access"
            ]
            for attempt in range(4):
                res = subprocess.run(create_cmd, capture_output=True, text=True)
                if res.returncode == 0 or "already exists" in res.stderr.lower() or "409" in res.stderr:
                    break
                if is_retryable_error(res.stderr) and attempt < 3:
                    time.sleep((2 ** attempt) * 3 + random.uniform(1, 2))
                    continue
                cat, badge, desc, fix = classify_error(res.stderr)
                raise Exception(f"Failed to create GCS state bucket {state_bucket} [{badge}]: {res.stderr.strip()}")
            
            # Enable versioning
            versioning_cmd = [
                "gcloud", "storage", "buckets", "update", state_bucket,
                f"--project={project_id}", "--versioning"
            ]
            for attempt in range(3):
                res = subprocess.run(versioning_cmd, capture_output=True, text=True)
                if res.returncode == 0:
                    break
                if is_retryable_error(res.stderr) and attempt < 2:
                    time.sleep(2)
                    continue
            
        # 5. Clear stale state locks
        clear_stale_tf_lock(project_id)
        return True, None
    except Exception as e:
        logging.error(f"[{project_id}] Failed during prerequisites: {e}")
        return False, str(e)

def get_active_oauth_token():
    """Retrieves the active gcloud OAuth2 access token."""
    cmd = ["gcloud", "auth", "print-access-token"]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return res.stdout.strip()

def run_post_apply_patches(project_id, region, log_file):
    """Enables the AlloyDB Data API if the cluster and instance exist using the direct GCP REST API."""
    import urllib.request
    import urllib.error
    
    logging.info(f"[{project_id}] Running post-apply patches...")
    with open(log_file, "a") as f:
        f.write("\n=== STEP 3: RUNNING POST-DEPLOYMENT PATCHES ===\n")
        
        check_cmd = ["gcloud", "alloydb", "clusters", "describe", "search-cluster", f"--region={region}", f"--project={project_id}"]
        res = subprocess.run(check_cmd, capture_output=True, text=True)
        if res.returncode == 0:
            f.write("AlloyDB cluster 'search-cluster' found. Enabling AlloyDB Data API via GCP REST API...\n")
            try:
                token = get_active_oauth_token()
                url = f"https://alloydb.googleapis.com/v1alpha/projects/{project_id}/locations/{region}/clusters/search-cluster/instances/search-primary?updateMask=dataApiAccess"
                
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "X-Goog-User-Project": project_id
                }
                data = json.dumps({"dataApiAccess": "ENABLED"}).encode("utf-8")
                
                req = urllib.request.Request(url, data=data, headers=headers, method="PATCH")
                with urllib.request.urlopen(req) as response:
                    resp_data = response.read().decode("utf-8")
                    f.write(f"AlloyDB Data API Patch response:\n{resp_data}\n")
                    f.write("AlloyDB Data API enabled successfully.\n")
                    logging.info(f"[{project_id}] AlloyDB Data API enabled successfully.")
            except urllib.error.HTTPError as e:
                err_resp = e.read().decode("utf-8")
                f.write(f"⚠️ AlloyDB Data API Patch HTTP Error ({e.code}):\n{err_resp}\n")
                f.write("⚠️ Notice: Could not automatically enable AlloyDB Data API due to domain/auth policies on alpha endpoint. This is non-fatal; participants will activate it via user_guide.md during the lab.\n")
                logging.warning(f"[{project_id}] AlloyDB Data API patch skipped (HTTP {e.code}: domain restriction). Non-fatal.")
            except Exception as e:
                f.write(f"⚠️ AlloyDB Data API Patch Exception:\n{e}\n")
                f.write("⚠️ Notice: Could not automatically enable AlloyDB Data API. This is non-fatal; participants will activate it via user_guide.md during the lab.\n")
                logging.warning(f"[{project_id}] AlloyDB Data API patch skipped ({e}). Non-fatal.")
        else:
            f.write("No AlloyDB cluster found in deployment. Skipping Data API patch.\n")

def prewarm_workstation_async(project_id, region, log_file):
    """Initiates asynchronous startup of the Cloud Workstation to pre-warm container, code, and virtualenv."""
    logging.info(f"[{project_id}] Triggering asynchronous Cloud Workstation startup for pre-warming...")
    with open(log_file, "a") as f:
        f.write("\n=== STEP 4: PRE-WARMING CLOUD WORKSTATION ===\n")
        cmd = [
            "gcloud", "workstations", "start", "my-workstation",
            "--cluster=workstation-cluster",
            "--config=workstation-config",
            f"--region={region}",
            f"--project={project_id}",
            "--async"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            f.write(f"Workstation pre-warming triggered asynchronously.\n{res.stdout}\n")
            logging.info(f"[{project_id}] Workstation pre-warming triggered successfully.")
        else:
            f.write(f"⚠️ Workstation pre-warm warning (non-fatal): {res.stderr.strip()}\n")
            logging.warning(f"[{project_id}] Workstation pre-warm warning: {res.stderr.strip()}")

def run_local_terraform_apply(project, builds, index):
    """Executes a local Terraform init & apply in an isolated workspace for a single project."""
    project_id = project["project_id"]
    iap_member = project["user"]
    region = project["region"]
    workdir = os.path.join(WORKDIR_BASE, project_id)
    log_file_path = os.path.join(LOG_DIR, f"{project_id}_apply.log")
    
    try:
        if os.path.exists(workdir):
            shutil.rmtree(workdir, ignore_errors=True)
        os.makedirs(workdir, exist_ok=True)
        
        for item in ["00-core-infra", "labs", "main.tf", "variables.tf", "terraform.tfvars", "bootstrapping.sh", "event-manifest.json", ".terraform.lock.hcl"]:
            if os.path.exists(item):
                if os.path.isdir(item):
                    shutil.copytree(item, os.path.join(workdir, item))
                else:
                    shutil.copy(item, os.path.join(workdir, item))
                    
        shared_assets_zip = os.path.join(WORKDIR_BASE, "assets.zip")
        assets_zip_path = os.path.join(workdir, "assets.zip")
        if os.path.exists(shared_assets_zip):
            shutil.copy(shared_assets_zip, assets_zip_path)
        else:
            with zipfile.ZipFile(assets_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for item in ["event-manifest.json", "bootstrapping.sh"]:
                    if os.path.exists(item):
                        zipf.write(item, item)
                if os.path.exists("labs"):
                    for root, dirs, files in os.walk("labs"):
                        for file in files:
                            file_path = os.path.join(root, file)
                            zipf.write(file_path, file_path)
                    
        env = os.environ.copy()
        env["TF_PLUGIN_CACHE_DIR"] = os.path.abspath(PLUGIN_CACHE_DIR)
        env.pop("GOOGLE_OAUTH_ACCESS_TOKEN", None)
        env.pop("CLOUDSDK_AUTH_ACCESS_TOKEN", None)
        
        # Step 1: Terraform Initialization
        builds[index]["status"] = "INIT"
        with open(log_file_path, "w") as log_f:
            log_f.write("=== STEP 1: TERRAFORM INITIALIZATION ===\n")
            log_f.flush()
            
            init_cmd = [
                "terraform", "init",
                f"-backend-config=bucket={project_id}-tfstate",
                "-backend-config=prefix=terraform/state"
            ]
            init_res = None
            for attempt in range(3):
                init_res = subprocess.run(
                    init_cmd,
                    cwd=workdir, env=env, stdout=log_f, stderr=log_f, text=True
                )
                if init_res.returncode == 0:
                    break
                if attempt < 2:
                    sleep_time = (2 ** attempt) * 4 + random.uniform(1, 3)
                    log_f.write(f"\n⚠️ Terraform Init failed (attempt {attempt+1}/3). Retrying in {sleep_time:.1f}s...\n")
                    log_f.flush()
                    time.sleep(sleep_time)
                    
            if init_res.returncode != 0:
                with open(log_file_path, "r") as check_f:
                    log_tail = check_f.read()[-2000:]
                cat, badge, desc, fix = classify_error(log_tail)
                builds[index]["failure_category"] = cat
                builds[index]["failure_badge"] = badge
                builds[index]["failure_advice"] = fix
                raise Exception(f"Terraform Init failed [{badge}]")
                
            # Step 2: Terraform Apply
            builds[index]["status"] = "APPLY"
            log_f.write("\n=== STEP 2: TERRAFORM DEPLOYMENT ===\n")
            log_f.flush()
            
            apply_cmd = [
                "terraform", "apply",
                "-var", f"project_id={project_id}",
                "-var", f"iap_member={iap_member}",
                "-var", f"region={region}",
                "-auto-approve"
            ]
            
            apply_res = None
            for attempt in range(3):
                apply_res = subprocess.run(
                    apply_cmd,
                    cwd=workdir, env=env, stdout=log_f, stderr=log_f, text=True
                )
                if apply_res.returncode == 0:
                    break
                if attempt < 2:
                    with open(log_file_path, "r") as check_f:
                        log_tail = check_f.read()[-2000:]
                    if not is_retryable_error(log_tail):
                        log_f.write(f"\n❌ Non-retryable error detected. Failing fast.\n")
                        break
                    sleep_time = min(60, (2 ** attempt) * 10 + random.uniform(2, 5))
                    log_f.write(f"\n⚠️ Terraform Apply failed (attempt {attempt+1}/3). Retrying in {sleep_time:.1f}s...\n")
                    log_f.flush()
                    time.sleep(sleep_time)
                    
            if apply_res.returncode != 0:
                with open(log_file_path, "r") as check_f:
                    log_tail = check_f.read()[-2000:]
                cat, badge, desc, fix = classify_error(log_tail)
                builds[index]["failure_category"] = cat
                builds[index]["failure_badge"] = badge
                builds[index]["failure_advice"] = fix
                raise Exception(f"Terraform Apply failed [{badge}]")
                
        # Step 3: Run Post-Apply Patches (AlloyDB Data API)
        builds[index]["status"] = "POST_PATCH"
        run_post_apply_patches(project_id, region, log_file_path)
        
        # Step 4: Pre-warm Cloud Workstation
        builds[index]["status"] = "PREWARM"
        prewarm_workstation_async(project_id, region, log_file_path)
        
        builds[index]["status"] = "SUCCESS"
        shutil.rmtree(workdir, ignore_errors=True)
    except Exception as e:
        logging.error(f"[{project_id}] Local provisioning failed: {e}")
        cat, badge, desc, fix = classify_error(str(e))
        builds[index]["status"] = f"FAILED: {badge}"
        builds[index]["error"] = str(e)
        if "failure_category" not in builds[index]:
            builds[index]["failure_category"] = cat
            builds[index]["failure_badge"] = badge
            builds[index]["failure_advice"] = fix
        with open(log_file_path, "a") as log_f:
            log_f.write(f"\n❌ EXCEPTION: {e}\n")

def run_local_terraform_destroy(project, builds, index):
    """Executes a local Terraform init & destroy in an isolated workspace for a single project."""
    project_id = project["project_id"]
    iap_member = project["user"]
    region = project["region"]
    workdir = os.path.join(WORKDIR_BASE, project_id)
    log_file_path = os.path.join(LOG_DIR, f"{project_id}_destroy.log")
    
    try:
        os.makedirs(workdir, exist_ok=True)
        
        for item in ["00-core-infra", "labs", "main.tf", "variables.tf", "terraform.tfvars", "bootstrapping.sh", "event-manifest.json", ".terraform.lock.hcl"]:
            if os.path.exists(item):
                if os.path.isdir(item):
                    shutil.copytree(item, os.path.join(workdir, item), dirs_exist_ok=True)
                else:
                    shutil.copy(item, os.path.join(workdir, item))
                    
        env = os.environ.copy()
        env["TF_PLUGIN_CACHE_DIR"] = os.path.abspath(PLUGIN_CACHE_DIR)
        env.pop("GOOGLE_OAUTH_ACCESS_TOKEN", None)
        env.pop("CLOUDSDK_AUTH_ACCESS_TOKEN", None)
        
        # Step 1: Terraform Initialization for Destroy
        builds[index]["status"] = "INIT"
        with open(log_file_path, "w") as log_f:
            log_f.write("=== STEP 1: TERRAFORM INITIALIZATION (FOR DESTROY) ===\n")
            log_f.flush()
            
            init_cmd = [
                "terraform", "init",
                f"-backend-config=bucket={project_id}-tfstate",
                "-backend-config=prefix=terraform/state"
            ]
            init_res = None
            for attempt in range(3):
                init_res = subprocess.run(
                    init_cmd,
                    cwd=workdir, env=env, stdout=log_f, stderr=log_f, text=True
                )
                if init_res.returncode == 0:
                    break
                if attempt < 2:
                    sleep_time = (2 ** attempt) * 4 + random.uniform(1, 3)
                    log_f.write(f"\n⚠️ Terraform Init failed (attempt {attempt+1}/3). Retrying in {sleep_time:.1f}s...\n")
                    log_f.flush()
                    time.sleep(sleep_time)
                    
            if init_res.returncode != 0:
                with open(log_file_path, "r") as check_f:
                    log_tail = check_f.read()[-2000:]
                cat, badge, desc, fix = classify_error(log_tail)
                builds[index]["failure_category"] = cat
                builds[index]["failure_badge"] = badge
                builds[index]["failure_advice"] = fix
                raise Exception(f"Terraform Init failed [{badge}]")
                
            # Step 2: Terraform Destroy
            builds[index]["status"] = "DESTROY"
            log_f.write("\n=== STEP 2: TERRAFORM DESTROY ===\n")
            log_f.flush()
            
            destroy_cmd = [
                "terraform", "destroy",
                "-var", f"project_id={project_id}",
                "-var", f"iap_member={iap_member}",
                "-var", f"region={region}",
                "-auto-approve"
            ]
            
            destroy_res = None
            for attempt in range(3):
                destroy_res = subprocess.run(
                    destroy_cmd,
                    cwd=workdir, env=env, stdout=log_f, stderr=log_f, text=True
                )
                if destroy_res.returncode == 0:
                    break
                if attempt < 2:
                    subprocess.run(["terraform", "state", "rm", "module.lab_alloydb_vectors.google_alloydb_user.iam_user"], cwd=workdir, env=env, capture_output=True)
                    sleep_time = min(60, (2 ** attempt) * 10 + random.uniform(2, 5))
                    log_f.write(f"\n⚠️ Terraform Destroy failed (attempt {attempt+1}/3). Retrying in {sleep_time:.1f}s (auto-healing state)...\n")
                    log_f.flush()
                    time.sleep(sleep_time)
                    
            if destroy_res.returncode != 0:
                with open(log_file_path, "r") as check_f:
                    log_tail = check_f.read()[-2000:]
                cat, badge, desc, fix = classify_error(log_tail)
                builds[index]["failure_category"] = cat
                builds[index]["failure_badge"] = badge
                builds[index]["failure_advice"] = fix
                raise Exception(f"Terraform Destroy failed [{badge}]")
                
        # Step 3: State Bucket Cleanup
        builds[index]["status"] = "CLEANUP"
        state_bucket = f"gs://{project_id}-tfstate"
        del_cmd = ["gcloud", "storage", "rm", "--recursive", state_bucket, f"--project={project_id}", "--quiet"]
        subprocess.run(del_cmd, capture_output=True, text=True)
        
        builds[index]["status"] = "DESTROYED"
        shutil.rmtree(workdir, ignore_errors=True)
    except Exception as e:
        logging.error(f"[{project_id}] Local teardown failed: {e}")
        cat, badge, desc, fix = classify_error(str(e))
        builds[index]["status"] = f"FAILED: {badge}"
        builds[index]["error"] = str(e)
        if "failure_category" not in builds[index]:
            builds[index]["failure_category"] = cat
            builds[index]["failure_badge"] = badge
            builds[index]["failure_advice"] = fix
        with open(log_file_path, "a") as log_f:
            log_f.write(f"\n❌ EXCEPTION: {e}\n")

def print_remediation_matrix(builds, is_destroy=False):
    """Renders an actionable post-mortem remediation matrix for any failed projects."""
    failed_builds = [b for b in builds if b["status"].startswith("FAILED") or b["status"].startswith("PREREQ_FAILED")]
    if not failed_builds:
        return
        
    print(f"\n{COLOR_RED}{COLOR_BOLD}===================================================================================================={COLOR_RESET}")
    print(f"{COLOR_RED}{COLOR_BOLD}❌ DEPLOYMENT FAILURES DETECTED - REMEDIATION MATRIX:{COLOR_RESET}")
    print(f"{COLOR_RED}{COLOR_BOLD}===================================================================================================={COLOR_RESET}")
    print(f"{COLOR_BOLD}{'PROJECT ID':<24} | {'FAILURE BADGE':<18} | {'ACTIONABLE RESOLUTION ADVICE':<52}{COLOR_RESET}")
    print(f"----------------------------------------------------------------------------------------------------")
    
    for b in failed_builds:
        pid = b["project_id"]
        badge = b.get("failure_badge", "Failed")
        advice = b.get("failure_advice", "Inspect individual log file for error details.")
        print(f"{COLOR_RED}{pid:<24}{COLOR_RESET} | {COLOR_YELLOW}{badge:<18}{COLOR_RESET} | {advice:<52}")
        
    print(f"{COLOR_RED}{COLOR_BOLD}===================================================================================================={COLOR_RESET}")
    log_type = "destroy" if is_destroy else "apply"
    print(f"📂 Detailed per-project logs are available in: {COLOR_BOLD}{LOG_DIR}/[PROJECT_ID]_{log_type}.log{COLOR_RESET}\n")

def run_live_dashboard(builds, is_destroy=False):
    """Renders a real-time console cockpit dashboard in the main thread."""
    total = len(builds)
    max_display_rows = 25
    
    while True:
        # Calculate statistics
        queued = sum(1 for b in builds if b["status"] == "QUEUED")
        init = sum(1 for b in builds if b["status"] == "INIT")
        apply_or_destroy = sum(1 for b in builds if b["status"] in ("APPLY", "DESTROY"))
        patch_or_cleanup = sum(1 for b in builds if b["status"] in ("POST_PATCH", "CLEANUP", "PREWARM"))
        success = sum(1 for b in builds if b["status"] in ("SUCCESS", "DESTROYED"))
        failed = sum(1 for b in builds if b["status"].startswith("FAILED") or b["status"].startswith("PREREQ_FAILED"))
        
        # Render Dashboard
        os.system("clear" if os.name != "nt" else "cls")
        print(DESTROY_BANNER if is_destroy else BANNER)
        print(f"📝 Main Log File: {COLOR_BOLD}{LOG_FILE}{COLOR_RESET}")
        log_type = "destroy" if is_destroy else "apply"
        print(f"📂 Individual Run Logs: {COLOR_BOLD}{LOG_DIR}/[PROJECT_ID]_{log_type}.log{COLOR_RESET}\n")
        
        print(f"{COLOR_BOLD}Parallel Local Thread Summary:{COLOR_RESET}")
        print(f"  Total Projects : {total}")
        if is_destroy:
            print(f"  {COLOR_GRAY}Queued: {queued}{COLOR_RESET} | {COLOR_CYAN}Init: {init}{COLOR_RESET} | {COLOR_YELLOW}Destroy: {apply_or_destroy}{COLOR_RESET} | {COLOR_YELLOW}Cleanup: {patch_or_cleanup}{COLOR_RESET} | {COLOR_GREEN}Destroyed: {success}{COLOR_RESET} | {COLOR_RED}Failed: {failed}{COLOR_RESET}")
        else:
            print(f"  {COLOR_GRAY}Queued: {queued}{COLOR_RESET} | {COLOR_CYAN}Init: {init}{COLOR_RESET} | {COLOR_YELLOW}Apply: {apply_or_destroy}{COLOR_RESET} | {COLOR_YELLOW}Pre-warm: {patch_or_cleanup}{COLOR_RESET} | {COLOR_GREEN}Success: {success}{COLOR_RESET} | {COLOR_RED}Failed: {failed}{COLOR_RESET}")
        print("=================================================================")
        print(f"{COLOR_BOLD}{'PROJECT ID':<25} | {'PARTICIPANT':<25} | {'CURRENT STEP / STATUS':<25}{COLOR_RESET}")
        print("-----------------------------------------------------------------")
        
        if total <= max_display_rows:
            display_builds = builds
        else:
            active_statuses = ("INIT", "APPLY", "POST_PATCH", "PREWARM", "DESTROY", "CLEANUP")
            active_builds = [b for b in builds if b["status"] in active_statuses]
            failed_builds = [b for b in builds if b["status"].startswith("FAILED") or b["status"].startswith("PREREQ_FAILED")]
            other_builds = [b for b in builds if b["status"] in ("SUCCESS", "DESTROYED", "QUEUED")]
            
            display_builds = []
            display_builds.extend(active_builds[:15])
            display_builds.extend(failed_builds[:10])
            
            remaining_slots = max_display_rows - len(display_builds)
            if remaining_slots > 0:
                display_builds.extend(other_builds[:remaining_slots])
                
        for b in display_builds:
            proj = b["project_id"]
            user = b["user"].replace("user:", "")
            status = b["status"]
            
            if status in ("SUCCESS", "DESTROYED"):
                status_str = f"{COLOR_GREEN}✔ {status}{COLOR_RESET}"
            elif status == "INIT":
                status_str = f"{COLOR_CYAN}⏳ TERRAFORM INIT{COLOR_RESET}"
            elif status == "APPLY":
                status_str = f"{COLOR_YELLOW}⏳ TERRAFORM APPLY{COLOR_RESET}"
            elif status == "DESTROY":
                status_str = f"{COLOR_YELLOW}⏳ TERRAFORM DESTROY{COLOR_RESET}"
            elif status == "POST_PATCH":
                status_str = f"{COLOR_YELLOW}⏳ POST-CONFIG PATCH{COLOR_RESET}"
            elif status == "PREWARM":
                status_str = f"{COLOR_CYAN}⏳ PRE-WARM WS{COLOR_RESET}"
            elif status == "CLEANUP":
                status_str = f"{COLOR_YELLOW}⏳ CLEANING STATE{COLOR_RESET}"
            elif status == "QUEUED":
                status_str = f"{COLOR_GRAY}💤 QUEUED{COLOR_RESET}"
            elif "failure_badge" in b and b["failure_badge"]:
                status_str = f"{COLOR_RED}❌ {b['failure_badge']}{COLOR_RESET}"
            elif status.startswith("PREREQ_FAILED"):
                badge = b.get("failure_badge", "Prereq Failed")
                status_str = f"{COLOR_RED}❌ {badge}{COLOR_RESET}"
            else:
                badge = b.get("failure_badge", "Failed")
                status_str = f"{COLOR_RED}❌ {badge}{COLOR_RESET}"
                
            print(f"{proj:<25} | {user:<25} | {status_str:<25}")
            
        if total > max_display_rows:
            print("-----------------------------------------------------------------")
            print(f"{COLOR_GRAY}  [Displaying {len(display_builds)} of {total} projects - Check {STATE_FILE} for full status list]{COLOR_RESET}")
        print("=================================================================")
        
        # Persist status to disk
        state_payload = {
            "event_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "builds": builds
        }
        try:
            with open(STATE_FILE, "w") as f:
                json.dump(state_payload, f, indent=2)
        except Exception:
            pass
            
        # Check if all threads have completed
        all_done = all(b["status"] in ("SUCCESS", "DESTROYED") or b["status"].startswith("FAILED") or b["status"].startswith("PREREQ_FAILED") for b in builds)
        if all_done:
            break
            
        time.sleep(2)
        
    if is_destroy:
        print("\n🎉 Local Parallel Teardown Complete!")
        print(f"  -> Successfully Destroyed : {COLOR_GREEN}{success}{COLOR_RESET}")
        print(f"  -> Failed Teardowns       : {COLOR_RED}{failed}{COLOR_RESET}")
        if failed > 0:
            print_remediation_matrix(builds, is_destroy=True)
            sys.exit(1)
        else:
            print(f"\n{COLOR_GREEN}✔ All project infrastructure successfully destroyed! Sandbox environments are clean.{COLOR_RESET}")
    else:
        print("\n🎉 Local Parallel Provisioning Complete!")
        print(f"  -> Successfully Deployed : {COLOR_GREEN}{success}{COLOR_RESET}")
        print(f"  -> Failed Deployments     : {COLOR_RED}{failed}{COLOR_RESET}")
        if failed > 0:
            print_remediation_matrix(builds, is_destroy=False)
            sys.exit(1)
        else:
            print(f"\n{COLOR_GREEN}✔ All projects successfully provisioned! Sandbox environments are live and ready for handoff.{COLOR_RESET}")

def main():
    parser = argparse.ArgumentParser(description="Data Forge Parallel Provisioning & Teardown Engine")
    parser.add_argument("action", nargs="?", default="apply", choices=["apply", "destroy"], help="Action to perform: apply or destroy (default: apply)")
    parser.add_argument("--max-workers", "-w", type=int, default=int(os.environ.get("MAX_WORKERS", 20)), help="Maximum concurrent threads (default: 20)")
    parser.add_argument("--yes", "-y", action="store_true", help="Automatic yes to prompts for headless execution")
    parser.add_argument("--destroy", "-d", action="store_true", help="Destroy infrastructure across all projects")
    args = parser.parse_args()
    
    if args.action == "destroy":
        args.destroy = True
    
    setup_logging()
    print(DESTROY_BANNER if args.destroy else BANNER)
    print(f"📝 Logging execution orchestration to: {COLOR_BOLD}{LOG_FILE}{COLOR_RESET}")
    print(f"⚡ Max Concurrency: {COLOR_BOLD}{args.max_workers} worker threads{COLOR_RESET}")
    
    # 1. Pre-flight Environment & Authentication Guard
    check_environment_and_auth()
    
    # 2. Parse, Lint, and Probe Projects
    projects, invalid_projects = parse_and_validate_projects(auto_yes=args.yes)
    print(f"Found {len(projects)} active & verified project mapping(s) in {PROJECTS_FILE}.")
    
    if not args.destroy:
        total, used, free = shutil.disk_usage(".")
        free_gb = free / (1024 ** 3)
        estimated_needed_gb = 0.5 + (len(projects) * 0.015)
        
        if free_gb < estimated_needed_gb:
            print(f"\n{COLOR_RED}❌ ERROR: Insufficient disk space.{COLOR_RESET}")
            print(f"  Available: {free_gb:.2f} GB")
            print(f"  Estimated Required: {estimated_needed_gb:.2f} GB")
            sys.exit(1)
        elif free_gb < 5.0:
            print(f"\n{COLOR_YELLOW}⚠️ WARNING: Low disk space ({free_gb:.2f} GB free). Continuing anyway...{COLOR_RESET}")
            
    os.makedirs(PLUGIN_CACHE_DIR, exist_ok=True)
    os.makedirs(WORKDIR_BASE, exist_ok=True)
    
    action_str = "DESTROY" if args.destroy else "PROVISION"
    if not args.yes:
        confirm = input(f"\nReady to launch local parallel Terraform {action_str} loops across {len(projects)} projects (Max Workers: {args.max_workers})? (y/n): ").strip().lower()
        if confirm not in ("y", "yes"):
            print("Aborted.")
            sys.exit(0)
            
    print(f"\n📦 Step 1: Pre-warming Terraform provider cache sequentially...")
    logging.info("Starting sequential pre-warm of Terraform provider plugin cache...")
    
    env = os.environ.copy()
    env["TF_PLUGIN_CACHE_DIR"] = os.path.abspath(PLUGIN_CACHE_DIR)
    
    init_cmd = ["terraform", "init", "-backend=false", "-upgrade=false"]
    res = subprocess.run(init_cmd, env=env, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"{COLOR_RED}❌ ERROR: Failed to pre-warm Terraform provider cache.{COLOR_RESET}")
        print(res.stderr)
        logging.error(f"Sequential pre-warm failed: {res.stderr}")
        sys.exit(1)
        
    print(f"  {COLOR_GREEN}✔{COLOR_RESET} Provider plugins cached and .terraform.lock.hcl verified.")
    
    if not args.destroy:
        shared_assets_zip = os.path.join(WORKDIR_BASE, "assets.zip")
        with zipfile.ZipFile(shared_assets_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for item in ["event-manifest.json", "bootstrapping.sh"]:
                if os.path.exists(item):
                    zipf.write(item, item)
            if os.path.exists("labs"):
                for root, dirs, files in os.walk("labs"):
                    for file in files:
                        file_path = os.path.join(root, file)
                        zipf.write(file_path, file_path)
        print(f"  {COLOR_GREEN}✔{COLOR_RESET} Shared assets bundle generated: {shared_assets_zip}")
        
    print(f"\n⚙ Step 2: Verifying & preparing remote GCS state buckets in parallel...")
    
    prereq_results = []
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        if args.destroy:
            futures = {executor.submit(clear_stale_tf_lock, p["project_id"]): p for p in projects}
        else:
            futures = {executor.submit(prepare_single_project, p): p for p in projects}
        for future in futures:
            project = futures[future]
            success, err = future.result()
            if success:
                print(f"  {COLOR_GREEN}✔{COLOR_RESET} {project['project_id']}: State bucket & permissions verified.")
                prereq_results.append((project, True, None, None, None, None))
            else:
                cat, badge, desc, fix = classify_error(err)
                print(f"  {COLOR_RED}❌{COLOR_RESET} {project['project_id']}: Verification failed [{badge}]: {err}")
                prereq_results.append((project, False, err, cat, badge, fix))
                
    print(f"\n🚀 Step 3: Launching parallel local {action_str.lower()}ing threads...")
    
    builds = []
    for project, success, err, cat, badge, fix in prereq_results:
        builds.append({
            "project_id": project["project_id"],
            "user": project["user"],
            "region": project["region"],
            "status": "QUEUED" if success else f"PREREQ_FAILED: {badge}",
            "error": err,
            "failure_category": cat,
            "failure_badge": badge,
            "failure_advice": fix
        })
        
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        for idx, item in enumerate(prereq_results):
            project, success, err, cat, badge, fix = item
            if success:
                if args.destroy:
                    executor.submit(run_local_terraform_destroy, project, builds, idx)
                else:
                    executor.submit(run_local_terraform_apply, project, builds, idx)
                
        print(f"⏳ Entering Live Cockpit Dashboard (Parallel {action_str.lower()} threads running)...")
        run_live_dashboard(builds, is_destroy=args.destroy)

if __name__ == "__main__":
    main()