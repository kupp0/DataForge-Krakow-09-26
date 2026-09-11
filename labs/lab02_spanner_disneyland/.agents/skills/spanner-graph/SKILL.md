---
name: spanner-graph
description: A generalized, end-to-end architectural capability for Google Cloud Spanner Property Graphs. This skill provides structural rules for schema configuration (DDL), relationship mutations (DML), and native ISO GQL graph pathfinding queries (GQL) without requiring external web lookups.
---
# Unified Spanner Graph DDL, DML, and GQL Engine

## 1. Schema Lifecycle Definitions (DDL)
When creating or altering a property graph structure, map the environment's tabular context to this strict configuration layout:

```sql
-- Step 1: Baseline Entity Tables (Nodes)
CREATE TABLE {NODE_TABLE} (
    {NODE_PRIMARY_ID} {DATATYPE} NOT NULL,
    -- Entity properties (e.g., name, category, descriptions)
) PRIMARY KEY ({NODE_PRIMARY_ID});

-- Step 2: Relationship Topology Tables (Edges)
CREATE TABLE {EDGE_TABLE} (
    {SOURCE_FOREIGN_ID} {DATATYPE} NOT NULL,
    {DESTINATION_FOREIGN_ID} {DATATYPE} NOT NULL,
    -- Edge properties (e.g., weights, latency, distance, metrics)
    FOREIGN KEY ({SOURCE_FOREIGN_ID}) REFERENCES {NODE_TABLE} ({NODE_PRIMARY_ID}),
    FOREIGN KEY ({DESTINATION_FOREIGN_ID}) REFERENCES {NODE_TABLE} ({NODE_PRIMARY_ID})
) PRIMARY KEY ({SOURCE_FOREIGN_ID}, {DESTINATION_FOREIGN_ID});

-- Step 3: Graph Construction
CREATE PROPERTY GRAPH {GRAPH_NAME}
  NODE TABLES (
    {NODE_TABLE}
      KEY ({NODE_PRIMARY_ID})
      LABEL {NODE_LABEL_NAME}
  )
  EDGE TABLES (
    {EDGE_TABLE}
      KEY ({SOURCE_FOREIGN_ID}, {DESTINATION_FOREIGN_ID})
      SOURCE KEY ({SOURCE_FOREIGN_ID}) REFERENCES {NODE_TABLE} ({NODE_PRIMARY_ID})
      DESTINATION KEY ({DESTINATION_FOREIGN_ID}) REFERENCES {NODE_TABLE} ({NODE_PRIMARY_ID})
      LABEL {EDGE_LABEL_NAME}
  );
```

---

## 2. Relationship Data Mutations (DML)

When inserting or updating nodes and edges into the underlying graph tables, use standard transactional Spanner DML patterns:

```sql
-- Populate or Update Nodes
INSERT OR UPDATE INTO {NODE_TABLE} ({NODE_PRIMARY_ID}, {ATTRIBUTE_1}, {ATTRIBUTE_2}) 
VALUES ({VAL_ID}, '{VAL_1}', '{VAL_2}');

-- Populate or Update Directed Edges
INSERT OR UPDATE INTO {EDGE_TABLE} ({SOURCE_FOREIGN_ID}, {DESTINATION_FOREIGN_ID}, {WEIGHT_ATTRIBUTE}) 
VALUES ({START_ID}, {END_ID}, {WEIGHT_VALUE});
```

---

## 3. Native Graph Traversals & Pathfinding (GQL)

When building query layers, API endpoints, or supplying commands to Model Context Protocol (MCP) data tools, format all lookup requests inside a `GRAPH_TABLE` table-valued function within standard SQL queries:

### Pattern A: 1-Hop Neighbor Discovery (Direct Connections)

Use this structure to find direct dependencies, adjacent rides, or direct connections:

```sql
SELECT dst.{ATTRIBUTE_NAME} AS connected_node, e.{WEIGHT_ATTRIBUTE} AS edge_metric
FROM GRAPH_TABLE({GRAPH_NAME}
  MATCH (src:{NODE_LABEL_NAME})-[e:{EDGE_LABEL_NAME}]->(dst:{NODE_LABEL_NAME})
  WHERE src.{ATTRIBUTE_NAME} = '{FILTER_VALUE}'
  RETURN dst.{ATTRIBUTE_NAME}, e.{WEIGHT_ATTRIBUTE}
);
```

### Pattern B: Variable-Length Pathfinding (Degrees of Separation / Routes)

Use this structure when navigating multi-hop networks, computing routing paths, or finding structural pipelines from point A to point B:

```sql
SELECT origin, destination, path_nodes
FROM GRAPH_TABLE({GRAPH_NAME}
  MATCH p = (src:{NODE_LABEL_NAME})-[:{EDGE_LABEL_NAME}]->{1,{MAX_HOPS}}(dst:{NODE_LABEL_NAME})
  WHERE src.{ATTRIBUTE_NAME} = '{START_VALUE}' AND dst.{ATTRIBUTE_NAME} = '{END_VALUE}'
  RETURN 
    src.{ATTRIBUTE_NAME} AS origin, 
    dst.{ATTRIBUTE_NAME} AS destination, 
    ARRAY(SELECT n.{ATTRIBUTE_NAME} FROM UNNEST(nodes(p)) AS n) AS path_nodes
);
```

### Pattern C: Topologically Sorted Neighbors by Distance/Weight

Use this structure to sort neighbors dynamically by physical proximity or edge cost:

```sql
SELECT dst.{ATTRIBUTE_NAME} AS connected_node, e.{WEIGHT_ATTRIBUTE} AS edge_metric
FROM GRAPH_TABLE({GRAPH_NAME}
  MATCH (src:{NODE_LABEL_NAME})-[e:{EDGE_LABEL_NAME}]->(dst:{NODE_LABEL_NAME})
  WHERE src.{ATTRIBUTE_NAME} = '{FILTER_VALUE}'
  RETURN dst.{ATTRIBUTE_NAME}, e.{WEIGHT_ATTRIBUTE}
  ORDER BY e.{WEIGHT_ATTRIBUTE} ASC
  LIMIT {LIMIT_COUNT}
);
```


---

## 4. Application Integration (Python SDKs)

* **Direct Data Endpoints (`/api/navigate`, `/api/paths`, `/api/attractions`)**:
  Execute SQL and GQL queries directly using the official `google.cloud.spanner` client library for sub-millisecond, deterministic responses:
  ```python
  from google.cloud import spanner
  client = spanner.Client(project=PROJECT_ID)
  db = client.instance("disneyland").database("agent-lab")
  with db.snapshot() as snapshot:
      results = list(snapshot.execute_sql(gql_query))
  ```

* **Conversational AI Agent Endpoint (`/api/chat`)**:
  Refer to `vertex-config` skill for the verified `google.adk` Agent and Runner pattern, supplying a `query_spanner` tool to avoid schema serialization overhead.

---

## Execution Guidelines

* **Zero Hallucination Constraints:** Treat capitalized terms (`CREATE PROPERTY GRAPH`, `NODE TABLES`, `EDGE TABLES`, `MATCH GRAPH_PATH`) as reserved structural constants.
* **Strict Variable Substitution:** Dynamically replace `{GRAPH_NAME}`, `{NODE_TABLE}`, `{EDGE_TABLE}`, `{NODE_LABEL_NAME}`, and `{EDGE_LABEL_NAME}` based purely on the workspace user configurations provided during the runtime initialization step.
