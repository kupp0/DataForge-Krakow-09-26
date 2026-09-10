/*
===================================================================================
ALLOYDB AI: DATABASE & SCHEMA BOOTSTRAP
===================================================================================

This script initializes the foundation for the Semantic Search Demo.
It performs the following critical operations:

1. SCHEMA SETUP: Uses the default "public" schema for clean alignment with GDA.
2. EXTENSIONS: Enables Google ML, Vector, ScaNN, and AI Natural Language extensions.
3. TABLE DDL: Creates the `property_listings` table with:
   - Automatic Text Embeddings (using `gemini-embedding-001` via fully-qualified database trigger).
   - Placeholder for Image Embeddings (populated later via Python).
4. DATA LOAD: Inserts sample real estate data for Switzerland.
5. INDEXING: Creates high-performance ScaNN indexes.
   * NOTE: Uses MANUAL mode because the dataset is small (<10k rows).

PRE-REQUISITES:
- Ensure the Vertex AI API is enabled in your Google Cloud Project.
- Ensure the AlloyDB Service Account has "Vertex AI User" permissions.
===================================================================================
*/

-- 1. SCHEMA INITIALIZATION
-- ===================================================================================

DROP TABLE IF EXISTS "public"."property_listings" CASCADE;

-- 2. EXTENSION MANAGEMENT
-- ===================================================================================

-- Enable the Google ML Integration (Bridge to Vertex AI)
CREATE EXTENSION IF NOT EXISTS "google_ml_integration" WITH SCHEMA "public" CASCADE;

-- Enable pgvector (Base vector data type support)
CREATE EXTENSION IF NOT EXISTS "vector" WITH SCHEMA "public" CASCADE;

-- Enable AlloyDB ScaNN (High-performance vector indexing)
CREATE EXTENSION IF NOT EXISTS "alloydb_scann" WITH SCHEMA "public" CASCADE;

-- Enable Parameterized Views (Required for Toolbox)
CREATE EXTENSION IF NOT EXISTS "parameterized_views" WITH SCHEMA "public" CASCADE;

-- Enable Natural Language Support
-- Removed ALTER EXTENSION ... UPDATE as it requires superuser/owner privileges and is usually unnecessary for fresh setups
CREATE EXTENSION IF NOT EXISTS "alloydb_ai_nl" WITH SCHEMA "public" CASCADE;

-- VERIFICATION: Check integration status
SELECT "extname", "extversion" FROM "pg_catalog"."pg_extension" WHERE "extname" = 'google_ml_integration';
SHOW google_ml_integration.enable_model_support;

-- TEST: Sanity check the embedding connection to Gemini
SELECT "google_ml"."embedding"(
   'gemini-embedding-001',
   'Sanity check for Vertex AI connection'
) AS "test_vector";

-- 3. TABLE CREATION
-- ===================================================================================

CREATE TABLE "public"."property_listings" (
    "id" SERIAL PRIMARY KEY,
    "title" VARCHAR(255) NOT NULL,
    "description" TEXT,
    "price" DECIMAL(12, 2) NOT NULL,
    "bedrooms" INT,
    "city" VARCHAR(100),
    "image_gcs_uri" TEXT,
    "country" VARCHAR(100) DEFAULT 'Switzerland',
    "canton" VARCHAR(100),
    -- COLUMN A: Text Embeddings (Managed by Database)
    "description_embedding" VECTOR(3072),
    -- COLUMN B: Image Embeddings (Managed by Application)
    "image_embedding" VECTOR(1408) 
);

