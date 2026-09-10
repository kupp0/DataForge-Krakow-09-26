#!/usr/bin/env python3
#
# Automated DB Seeding Script for Lab 3 (Swiss Property Search)
# This script connects to the local private IP of the AlloyDB instance
# and seeds the database using psycopg2, bypassing copy-paste and psql dependencies.

import os
import sys
import subprocess
import psycopg2

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

def get_active_user():
    # 1. Check environment variable
    active_user = os.environ.get("GCP_ACTIVE_USER")
    if active_user:
        return active_user
    # 2. Fallback to active gcloud configuration
    try:
        result = subprocess.run(
            ["gcloud", "config", "get-value", "account"],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except Exception:
        return None

def main():
    print("=================================================================")
    print("AlloyDB Database Seeding (Lab 3)")
    print("=================================================================")

    project_id = get_active_project_id()
    if not project_id:
        print("❌ Error: No active gcloud project set. Please set one first.")
        sys.exit(1)

    active_user = get_active_user()
    if not active_user:
        print("⚠ Warning: Could not detect active gcloud user. Will use fallback owner role.")

    cluster_id = "search-cluster"
    instance_id = "search-primary"

    print("🔍 Detecting AlloyDB primary instance IP address...")
    # Auto-detect location from cluster name segment
    try:
        res_region = subprocess.run(
            ["gcloud", "alloydb", "clusters", "list", 
             f"--filter=name:{cluster_id}", 
             "--format=value(name.segment(3))", 
             "--limit=1", f"--project={project_id}"],
            capture_output=True, text=True, check=True
        )
        region = res_region.stdout.strip()
        if not region:
            raise Exception("Region empty")
    except Exception as e:
        print(f"❌ Error: Could not detect AlloyDB cluster region in project {project_id}. ({e})")
        sys.exit(1)

    try:
        res_ip = subprocess.run(
            ["gcloud", "alloydb", "instances", "describe", instance_id,
             f"--cluster={cluster_id}", f"--region={region}",
             "--format=value(ipAddress)", f"--project={project_id}"],
            capture_output=True, text=True, check=True
        )
        ip_addr = res_ip.stdout.strip()
        if not ip_addr:
            raise Exception("IP address empty")
    except Exception as e:
        print(f"❌ Error: Could not fetch AlloyDB instance IP address. ({e})")
        sys.exit(1)

    print(f"✅ Found AlloyDB primary IP: {ip_addr} in region {region}")

    try:
        print("🔌 Connecting to database...")
        conn = psycopg2.connect(
            host=ip_addr,
            database="postgres",
            user="postgres",
            password="alloydb-hackathon-password"
        )
        conn.autocommit = True
        cursor = conn.cursor()
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        sys.exit(1)

    # 1. Run DDL setup (as postgres superuser, so it can drop any existing table)
    try:
        print("🚧 [1/3] Creating table schema and enabling extensions (alloydb_setup.sql)...")
        with open("alloydb_setup.sql", "r") as f:
            setup_sql = f.read()
        cursor.execute(setup_sql)
        print("✅ Schema setup completed.")
    except Exception as e:
        print(f"❌ Schema creation failed: {e}")
        sys.exit(1)

    # 2. Reclaim ownership to the active IAM user (or fallback role) so they can build indexes
    owner_role = active_user if active_user else "alloydbsuperuser"
    try:
        print(f"👤 [2/3] Transferring table ownership to role: \"{owner_role}\"...")
        # Role names must be double-quoted to support special characters like @ and .
        cursor.execute(f'ALTER TABLE "public"."property_listings" OWNER TO "{owner_role}";')
        print(f"✅ Ownership transferred successfully to \"{owner_role}\".")
    except Exception as e:
        # Fallback to alloydbsuperuser group role if specific user fails
        if owner_role != "alloydbsuperuser":
            try:
                print(f"⚠ Transfer failed. Falling back to group role \"alloydbsuperuser\"...")
                cursor.execute('ALTER TABLE "public"."property_listings" OWNER TO "alloydbsuperuser";')
                print("✅ Ownership transferred successfully to \"alloydbsuperuser\".")
            except Exception as fallback_err:
                print(f"❌ Fallback ownership transfer failed: {fallback_err}")
                sys.exit(1)
        else:
            print(f"❌ Ownership transfer failed: {e}")
            sys.exit(1)

    # 3. Run listings insertion (as postgres, which can write to tables owned by others)
    try:
        print("📥 [3/3] Ingesting property listing records (4.3MB)...")
        with open("insert_listings.sql", "r") as f:
            insert_sql = f.read()
        cursor.execute(insert_sql)
        print("✅ Data ingestion completed.")
    except Exception as e:
        print(f"❌ Data ingestion failed: {e}")
        sys.exit(1)

    cursor.close()
    conn.close()
    print("=================================================================")
    print("✔ Database seeding completed successfully!")
    print("=================================================================")

if __name__ == "__main__":
    main()
