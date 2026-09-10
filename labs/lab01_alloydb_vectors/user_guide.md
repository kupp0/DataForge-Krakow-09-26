# 🧪 Lab 1: One Million Vectors, Zero Loops — Generating Embeddings at Scale with AlloyDB

Welcome, future Vector Wizards! 🧙‍♂️ 

In this lab, you will build a high-performance Knowledge Base search database application. Forget about managing slow, complex ETL pipelines, spinning up custom Python scripts, or waiting hours for loops to generate vector embeddings. Instead, you'll harness the native raw power of **AlloyDB AI** to handle embedding generation directly inside the database using a single, elegant SQL command.

---

## 🎯 Lab Objectives
* **⚙️ Instance Verification**: Make sure the database engines are revved up and extensions are active.
* **📊 Synthetic Data Influx**: Inject a massive dataset (100,000+ rows) instantly using database SQL queries.
* **💥 Bulk Backfill**: Generate vector embeddings for the entire dataset using native **Batch Processing** in seconds.
* **📡 Real-Time Triggers**: Set up database triggers to auto-embed new articles the second they are inserted.
* **🔍 Hybrid Search**: Run lightning-fast semantic lookups combined with standard SQL filters.

---

## 🔍 Phase 1: Verify Database Flags

AlloyDB AI integration requires specific database flags to be enabled on the primary instance. In this summit environment, these flags have been **pre-configured** via Terraform during the infrastructure deployment. 

Before proceeding, let's verify that the flags are active.

### 🔐 Verification via SQL (AlloyDB Studio)

To access the query editor:
1. Navigate to [AlloyDB Clusters](https://console.cloud.google.com/alloydb/clusters) in the Google Cloud Console.
2. Select your cluster (e.g., `search-cluster`).
3. Click **AlloyDB Studio** in the left navigation menu.

<img src="assets/alloydb_studio_menu.png" alt="AlloyDB Studio Menu Navigation" width="280" />

> [!NOTE]
> **AlloyDB Studio Login Credentials**:
> When logging in to the **AlloyDB Studio**, use the following connection parameters:
> * **Database**: `postgres`
> * **Authentication method**: `Built-in database authentication`
> * **User**: `postgres`
> * **Password**: `alloydb-hackathon-password`
> 
> <img src="assets/alloydb_studio_login.png" alt="AlloyDB Studio Login Example" width="350" />

Connect to your database cluster inside the **AlloyDB Studio** and execute these commands to verify the configurations:

```sql
-- Check that Google ML Model support is active
SHOW google_ml_integration.enable_model_support;
-- Expected Output: 'on'

-- Check that Faster Embedding Generation is active
SHOW google_ml_integration.enable_faster_embedding_generation;
-- Expected Output: 'on'
```

> [!TIP]
> **Self-Service Fix**: If either of these flags outputs `off`, you can quickly enable them yourself using this command in your Google Cloud Shell:
> ```bash
> gcloud alloydb instances update search-primary \
>   --cluster=search-cluster \
>   --region=europe-west3 \
>   --database-flags=google_ml_integration.enable_model_support=on,google_ml_integration.enable_faster_embedding_generation=on
> ```

---

## 🏗️ Phase 2: Schema Setup & Extension Activation

Log into your **AlloyDB Studio** using the database credentials (default user: `postgres`). Run the following DDL commands to register the required PostgreSQL extensions:

```sql
-- Enable pgvector, ML integration, and ScaNN index extensions
CREATE EXTENSION IF NOT EXISTS google_ml_integration CASCADE;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS alloydb_scann CASCADE;
```

### 🔎 Verify Extension Version
Ensure that `google_ml_integration` is at version **1.5.2 or higher**:
```sql
SELECT extversion FROM pg_extension WHERE extname = 'google_ml_integration';
```
> [!NOTE]
> If your version is lower, you can upgrade it by running:
> `ALTER EXTENSION google_ml_integration UPDATE;`

---

## 📊 Phase 3: Generate Synthetic Data at Scale

Instead of loading a heavy CSV, generate 50,000 rows of synthetic customer support articles instantly using SQL:

```sql
-- 1. Create the help_articles table
CREATE TABLE help_articles (
    id SERIAL PRIMARY KEY,
    title TEXT,
    category TEXT,
    product_version TEXT,
    content_body TEXT,
    embedding vector(768) -- 768 dimension for text-embedding-005
);

-- 2. Generate 100,000 rows of synthetic data
INSERT INTO help_articles (title, category, product_version, content_body)
SELECT
    'Help Article ' || i,
    CASE 
        WHEN i % 3 = 0 THEN 'Billing' 
        WHEN i % 3 = 1 THEN 'Technical' 
        ELSE 'General' 
    END,
    CASE 
        WHEN i % 2 = 0 THEN '2.0' 
        ELSE '1.0' 
    END,
    'This article covers common issues regarding ' || 
    CASE 
        WHEN i % 3 = 0 THEN 'payment failures, invoice disputes, and credit card updates.'
        WHEN i % 3 = 1 THEN 'connection timeouts, latency issues, and API errors.'
        ELSE 'account profile settings, password resets, and user roles.' 
    END
FROM generate_series(1, 100000) AS i;
```

Verify the row count:
```sql
SELECT count(*) FROM help_articles;
-- Output should be exactly 100000
```

---

## 💥 Phase 4: Zero-Loop "One-Shot" Vector Generation

Now, perform a bulk generation of embeddings for all 100,000 rows natively in the database. This process completely eliminates the need for complex, fragile external ETL loops, Kafka queues, or Python background workers!

> [!IMPORTANT]
> **The Operational Edge (Transactional Mode)**: By specifying `incremental_refresh_mode => 'transactional'`, AlloyDB automatically configures live database triggers. This transactional synchronization is exceptionally powerful for production-grade operational vector search applications, because any future DML writes are vectorized **automatically** inside the same transaction, guaranteeing your search index remains 100% synchronized with zero operational lag!

> [!TIP]
> **Performance Benchmark**: In standard summit environments, backfilling the entire **100,000 rows** dataset completes in just **230.9 seconds** (processing over **430 rows per second**)! This highlights the superior speed and efficiency of database-native batch processing over traditional external application-driven loops. Imagine operating 100k individual Gemini Agent Platform (formerly VertexAI) API calls row by row. 

By leveraging database-native automatic embedding generation, you eliminate external scheduler loops and background pipeline infrastructure, drastically reducing code maintenance debt. AlloyDB natively manages optimal batch sizes and automatically recovers from transient model quota limit errors, reducing API token overhead and guaranteeing transactional data remains continuously in sync.

### 🔑 1. Grant Progress Management Permissions
```sql
GRANT INSERT, UPDATE, DELETE ON google_ml.embed_gen_progress TO postgres;
GRANT EXECUTE ON FUNCTION embedding TO postgres;
```

### 🚀 2. Initialize Embeddings Call
Run the native bulk initialization using an optimized batch size of **100** to maximize throughput:
```sql
CALL ai.initialize_embeddings(
  model_id => 'text-embedding-005',
  table_name => 'help_articles',
  content_column => 'content_body',
  embedding_column => 'embedding',
  incremental_refresh_mode => 'transactional',
  batch_size => 100 -- Bulk optimization: groups 100 rows per Vertex AI API call
);
```

> [!NOTE]
> **Tuning Batch Size & Payload Limits**: 
> By default, AlloyDB uses a batch size of 50. While increasing the batch size to 100 delivers up to a 2.5x speedup (running in 90.7s), it increases request sizes.
> If your text columns contain extremely large text blocks, large batch sizes can hit Vertex AI's maximum payload limit, resulting in the error: `AutoEmbeddingGeneration: Request size is greater than 4MB`. In those scenarios, you can optimize performance by scaling down the `batch_size` (e.g. to `25` or `50`) to stay under the 4MB limit.

### 📈 3. Monitor Real-Time Embedding Progress
Since backfilling 100,000 rows is a large operational task, you can monitor the real-time progress, elapsed time, and estimated completion time of the bulk generation by querying the built-in **`ai.embedding_progress_view`**:

```sql
SELECT * FROM ai.embedding_progress_view;
```
*This returns columns detailing percentage completed, total rows processed, success rates, and any transient errors encountered.*

### 🧪 4. Verify Population
Confirm the embeddings are fully populated once the monitoring progress reaches 100%:
```sql
SELECT id, left(content_body, 30), substring(embedding::text, 1, 30) AS vector_partial 
FROM help_articles 
LIMIT 5;
```

---

## 📡 Phase 5: Verify Real-Time Triggers

Because `incremental_refresh_mode` was set to `'transactional'`, AlloyDB automatically configures internal triggers to auto-embed new records immediately.

Let's test this zero-loop automation:
```sql
-- Insert a new row without providing an embedding vector
INSERT INTO help_articles (title, category, product_version, content_body)
VALUES ('New Scaling Guide', 'Technical', '2.0', 'How to scale AlloyDB to millions of transactions.');

-- Check immediately if the vector was auto-generated
SELECT embedding 
FROM help_articles 
WHERE title = 'New Scaling Guide';
```

---

## 🔍 Phase 6: Flexing Context / Hybrid Search

We will perform a **Hybrid Search** that combines semantic context understanding (vector similarity) with structured relational logic (SQL filters).

Query to find **Billing** issues relating to "Invoice did not go through" specifically for **Product Version 2.0**:

```sql
SELECT
  title,
  left(content_body, 100) AS content_snippet,
  1 - (embedding <=> embedding('text-embedding-005', 'Invoice did not go through')::vector) AS relevance
FROM help_articles
WHERE category = 'Billing'        -- Structured business filter
  AND product_version = '2.0'     -- Structured version filter
ORDER BY embedding <=> embedding('text-embedding-005', 'Invoice did not go through')::vector ASC
LIMIT 5;
```

---

## ⚡ Phase 7: High-Scale Optimization with ScaNN Index

While traditional indexes (like `HNSW` or `IVFFlat`) are standard, AlloyDB AI introduces native support for Google's state-of-the-art **ScaNN (Scalable Nearest Neighbors)** index. ScaNN is built specifically for ultra-fast vector search at massive scale (millions of rows), delivering up to **double the Queries Per Second (QPS)** and higher recall accuracy.

### 📐 1. Understand Distance Metrics
Before creating an index, it is essential to understand the 3 core vector distance functions supported by pgvector and ScaNN:

* **L2 Distance (`l2` / `<->`)**: Measures the straight physical distance between two vector coordinate points. *Best used when vector magnitude is significant (e.g., image pixel comparison).*
* **Dot Product (`dot_product` / `<#>`)**: Measures the angle and direction of vectors. *Best used when vectors are pre-normalized to unit length, offering the fastest mathematical execution.*
* **Cosine Distance (`cosine` / `<=>`)**: Measures solely the angle difference between vectors, completely ignoring vector length/magnitude. *The industry standard for text similarity and RAG, ensuring word repetition or document length differences do not skew the search results.*

### 🎛️ 2. Create an Auto-Tuned ScaNN Index
Instead of manually calculating leaves and quantization clusters (which is mathematically complex and hard to maintain as data scales), AlloyDB AI introduces **Automatically-Tuned ScaNN indexes** (`mode='AUTO'`).

AlloyDB continuously analyzes the table row counts and vector dimensionality, dynamically re-tuning leaves and index trees behind the scenes to ensure optimal Queries Per Second (QPS) and recall performance.

Run the DDL command below to create an auto-tuned ScaNN index optimized for **Cosine** distance:
```sql
CREATE INDEX help_articles_scann_idx 
ON help_articles 
USING scann (embedding cosine)
WITH (mode='AUTO',
      auto_maintenance=true);
```
> [!NOTE]
> * `mode='AUTO'` - The optimal configuration for the ScaNN index is automatically chosen based on the number of rows in the table. 
> * `auto_maintenance=true` - The index will be automatically maintained by AlloyDB, including periodic rebalancing and optimization.

---

## 🔬 Verification & Troubleshooting

> [!IMPORTANT]
> **Prerequisite for ScaNN Index Queries**: 
> To successfully query an AlloyDB ScaNN index, you **MUST** set the session parameter **`scann.max_allowed_num_levels = 3`** in your active Query Editor tab. If this flag is not set to 3 (or higher), the query planner will **never** choose the ScaNN index and will always fallback to a sequential scan.
> 
> Execute this command in your editor session before running the verification queries:
> ```sql
> SET scann.max_allowed_num_levels = 3;
> ```

> [!TIP]
> **Confirming Index Usage**:
> To verify that your queries are successfully using the ScaNN index instead of performing slow sequential scans, prefix your hybrid search query with `EXPLAIN ANALYZE`:
> ```sql
> EXPLAIN ANALYZE
> SELECT
>   title,
>   left(content_body, 100) AS content_snippet,
>   1 - (embedding <=> embedding('text-embedding-005', 'Invoice did not go through')::vector) AS relevance
> FROM help_articles
> WHERE category = 'Billing'
>   AND product_version = '2.0'
> ORDER BY embedding <=> embedding('text-embedding-005', 'Invoice did not go through')::vector ASC
> LIMIT 5;
> ```
> *In the output execution plan, look for the **`Index Scan`** (or custom **`scann`** scan) row referencing `help_articles_scann_idx`. This confirms AlloyDB is successfully utilizing ScaNN approximate nearest neighbor lookups.*

---

## 🎉 Congratulations!

You have successfully completed **Lab 1: One Million Vectors, Zero Loops**! 

### What you've achieved:
* Automated bulk and transactional database-native vector embedding generation via AlloyDB AI and Vertex AI.
* Set up and verified dynamic pre-filtering semantic search queries.
* Built an automatically-tuned Google ScaNN index to authorize sub-millisecond high-scale approximate nearest neighbor searches.

### Next Steps:
You are now invited to continue with the second track:
👉 **[Proceed to Lab 2: Spanner Disneyland Agentic Codelab](../02_spanner_disneyland/user_guide.md)**
