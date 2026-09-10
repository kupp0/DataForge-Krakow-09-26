#!/usr/bin/env bash
# ==============================================================================
# Headless Hackathon Engine: Dynamic Workstation Bootstrapping Coordinator
# ==============================================================================
set -euo pipefail

echo "================================================================="
echo "⚙ Starting Dynamic Workstation Bootstrapping..."
echo "================================================================="

TEMP_CLONE_DIR="/tmp/event-repo"

# Ensure the assets zip was extracted
if [[ ! -d "$TEMP_CLONE_DIR" ]]; then
  echo "❌ ERROR: Assets directory $TEMP_CLONE_DIR not found. Did the zip extraction fail?"
  exit 1
fi

MANIFEST_FILE="$TEMP_CLONE_DIR/event-manifest.json"
if [[ ! -f "$MANIFEST_FILE" ]]; then
  echo "❌ ERROR: event-manifest.json not found in the cloned repository."
  exit 1
fi

# --- 2. Manifest-Driven Lab and Skills Hydration (Inline Python) ---
echo "📦 Hydrating selected labs and agent skills from manifest..."

python3 - <<EOF
import os
import json
import shutil
import sys

manifest_path = "$MANIFEST_FILE"
repo_dir = "$TEMP_CLONE_DIR"
target_home = "/home/user"

with open(manifest_path, 'r') as f:
    manifest = json.load(f)

print(f"Processing event: {manifest.get('event_name', 'Unnamed Event')}")

selected_labs = manifest.get('selected_labs', [])
if not selected_labs:
    print("⚠ No labs selected in the manifest!")
    sys.exit(0)

for lab in selected_labs:
    lab_id = lab.get('id')
    lab_name = lab.get('name')
    assets_src = lab.get('assets_src')
    dest_dir = lab.get('dest_dir')
    skills = lab.get('skills', [])
    
    print(f"\nInstalling {lab_name}...")
    
    # 1. Copy Lab Assets/Source
    if assets_src and dest_dir:
        src_path = os.path.join(repo_dir, assets_src)
        dest_path = os.path.join(target_home, dest_dir)
        
        # Check if a nested "src" directory exists inside the lab source
        lab_src_path = os.path.join(src_path, "src")
        actual_src_path = lab_src_path if os.path.exists(lab_src_path) else src_path
        
        if os.path.exists(actual_src_path):
            print(f"  -> Copying assets from {actual_src_path} to {dest_path}")
            # Ensure safe copying that does not overwrite modified user files or delete the folder
            shutil.copytree(actual_src_path, dest_path, ignore=shutil.ignore_patterns("infra"), dirs_exist_ok=True)
        else:
            print(f"  ⚠ WARNING: Lab assets source path not found: {src_path}")
            
        # 2. Copy Agent Skills (if any)
        if skills:
            for skill in skills:
                skill_name = skill.get('name')
                skill_src = skill.get('src')
                
                skill_src_path = os.path.join(repo_dir, skill_src)
                skill_dest_dir = os.path.join(dest_path, ".agents", "skills", skill_name)
                os.makedirs(skill_dest_dir, exist_ok=True)
                
                skill_dest_path = os.path.join(skill_dest_dir, "SKILL.md")
                
                if os.path.exists(skill_src_path):
                    print(f"  -> Copying agent skill {skill_name} to {skill_dest_path}")
                    shutil.copy2(skill_src_path, skill_dest_path)
                else:
                    print(f"  ⚠ WARNING: Agent skill source path not found: {skill_src_path}")
    else:
        print(f"  ⚠ WARNING: Missing asset source or destination directory for lab: {lab_id}")

# --- 3. Dynamic Model Context Protocol (MCP) & IDE Configuration ---
mcp_servers = manifest.get('mcp_servers', [])

def resolve_project_id():
    # 1. Check environment variable
    pid = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT_ID")
    if pid and pid != "CURRENT_PROJECT":
        return pid
    
    # 2. Check Application Default Credentials
    adc_path = os.path.join(target_home, ".config", "gcloud", "application_default_credentials.json")
    if os.path.exists(adc_path):
        try:
            with open(adc_path, "r") as f:
                data = json.load(f)
                quota_role_pid = data.get("quota_project_id")
                if quota_role_pid:
                    return quota_role_pid
        except Exception:
            pass
            
    # 3. Check active gcloud config
    try:
        import subprocess
        result = subprocess.run(
            ["gcloud", "config", "get-value", "project"],
            capture_output=True,
            text=True,
            check=True
        )
        gcloud_pid = result.stdout.strip()
        if gcloud_pid and gcloud_pid != "CURRENT_PROJECT":
            return gcloud_pid
    except Exception:
        pass
        
    return "CURRENT_PROJECT"
 
project_id = resolve_project_id()
print(f"\n⚙ Dynamic IDE Configuration:")
print(f"  -> Resolved active GCP Project ID: {project_id}")
 
# Target paths
gemini_config_dir = os.path.join(target_home, ".gemini", "config")
agy_config_dir = os.path.join(target_home, ".gemini", "antigravity-cli")
plugins_dir = os.path.join(target_home, ".gemini", "antigravity-cli", "plugins")
 
os.makedirs(gemini_config_dir, exist_ok=True)
os.makedirs(agy_config_dir, exist_ok=True)
os.makedirs(plugins_dir, exist_ok=True)
 
# Build dynamic mcpServers dict
mcp_servers_dict = {}
for server in mcp_servers:
    server_id = server.get('id')
    server_type = server.get('type', 'server')
    server_config = server.get('config', {})
    
    print(f"  -> Wiring MCP Server: {server_id} ({server_type})")
    mcp_servers_dict[server_id] = server_config
    
    if server_type == "plugin":
        plugin_path = os.path.join(plugins_dir, f"{server_id}.json")
        with open(plugin_path, "w") as f:
            json.dump(server_config, f, indent=2)
 
mcp_config = {"mcpServers": mcp_servers_dict}
 
# Write mcp_config.json
with open(os.path.join(gemini_config_dir, "mcp_config.json"), "w") as f:
    json.dump(mcp_config, f, indent=2)
with open(os.path.join(agy_config_dir, "mcp_config.json"), "w") as f:
    json.dump(mcp_config, f, indent=2)
 
# Write general config.json
cli_config = {
    "project": project_id,
    "project_id": project_id,
    "location": "global",
    "theme": "dark",
    "terms_accepted": True
}
with open(os.path.join(gemini_config_dir, "config.json"), "w") as f:
    json.dump(cli_config, f, indent=2)
with open(os.path.join(agy_config_dir, "config.json"), "w") as f:
    json.dump(cli_config, f, indent=2)
 
# Pre-configure gcloud configuration file
gcloud_config_dir = os.path.join(target_home, ".config", "gcloud", "configurations")
os.makedirs(gcloud_config_dir, exist_ok=True)
with open(os.path.join(gcloud_config_dir, "config_default"), "w") as f:
    f.write(f"[core]\nproject = {project_id}\n")

print("✔ Dynamic IDE and MCP configurations written successfully.")
print("\n✔ Manifest processing completed successfully.")
EOF

# --- 3. Configure User .bashrc for Workspace Active Project & Authentication Reminders ---
BASHRC="/home/user/.bashrc"
if ! grep -q "GCP_WORKSPACE_SETUP" "$BASHRC" 2>/dev/null; then
    echo "⚙ Configuring user .bashrc for GCP workspace automatic project routing..."
    cat <<'EOF' >> "$BASHRC"

# >>> GCP_WORKSPACE_SETUP >>>
# Set the default project automatically if needed
if [ "$(gcloud config get-value project 2>/dev/null)" = "CURRENT_PROJECT" ] || [ -z "$(gcloud config get-value project 2>/dev/null)" ]; then
    DET_PROJECT_ID=$(jq -r '.project // empty' /home/user/.gemini/config/config.json 2>/dev/null)
    if [ -n "$DET_PROJECT_ID" ]; then
        gcloud config set project "$DET_PROJECT_ID" &>/dev/null
    fi
fi

# Remind user to authenticate if not already done
if [ -z "$(gcloud config get-value account 2>/dev/null)" ] || [ ! -f ~/.config/gcloud/application_default_credentials.json ]; then
    echo ""
    echo "🚀 Welcome to the Data Forge! 🚀"
    echo "Your custom data cloud experience, built by you."
    echo "Let's wire things up so you can build some database magic."
    echo "Run this command to unlock your Google Cloud authentication gateway:"
    echo "    gcloud auth login --update-adc"
    echo "Go ahead, you've got this! 💪"
    echo ""
fi
# <<< GCP_WORKSPACE_SETUP <<<
EOF
fi

# --- 4. Clean Up and Fix Permissions ---
echo "🧹 Cleaning up temporary git clone..."
rm -rf "$TEMP_CLONE_DIR"

echo "🔒 Adjusting file permissions for Code-OSS user..."
chown -R 1000:1000 /home/user 2>/dev/null || true

# Make all lab verification scripts executable
find /home/user /home/student /home/jupyter -name "verify.sh" -exec chmod +x {} + 2>/dev/null || true

# Signal bootstrapping completion
touch /home/user/.bootstrapping_done /home/student/.bootstrapping_done /home/jupyter/.bootstrapping_done 2>/dev/null || true

echo "================================================================="
echo "🎉 Dynamic Bootstrapping Completed Successfully!"
echo "================================================================="
