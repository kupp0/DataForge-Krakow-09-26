# Lab 2: Disneyland Spanner Leaderboard & Telemetry Guide

This document defines the operational architecture, scoring rules, business heuristics, and monitoring telemetry powering the central **Lab 2: Disneyland Spanner Global Leaderboard**.

---

## 1. Purpose & Overview

The Admin Leaderboard is a centralized, real-time observability and gamification platform designed to track and score 25 concurrent participant teams during the Disneyland Spanner Hackathon.

### Key Objectives
* **Automated Progress Tracking**: Concurrently probes Cloud Spanner instances across all 25 project sandboxes (`dataforge26krk-6701` to `dataforge26krk-6725`) to verify table provisioning and graph schema compilation.
* **Workload & Throughput Telemetry**: Monitors real-time write ingestion rates (`Runs/sec`), compute capacity (`Processing Units`), and resource contention (`CPU Utilization`).
* **Economic Simulation**: Evaluates participant business logic through an empirical price-elasticity demand curve, penalizing unrealistic pricing and rewarding volume optimization.
* **AI Announcer HUD**: Dynamically calls `gemini-3.8-flash` to roast participant performance, highlight bottlenecks, and broadcast humorous rhymes to keep the event engaging.

---

## 2. Scoring System & Weightings

Each participant team competes for a base score of **1,000 Points** plus up to **100 Speed Velocity Bonus Points** (Max Composite Score: **1,100 Points**). Points are calculated deterministically across 8 distinct dimensions:

| Category | Max Points | Measurement Target | Evaluation Logic |
| :--- | :---: | :--- | :--- |
| **Core DDL** | **300** | Standard relational schema | 100 pts each for `DisneylandPark`, `Attraction`, and `Path` tables. |
| **Spanner Graph DDL** | **100** | Property Graph definition | 100 pts if `DisneylandGraph` is defined in `INFORMATION_SCHEMA.PROPERTY_GRAPHS`. |
| **Data Population** | **100** | Row volume in core tables | Scaled linearly up to 50 rows (`min(100, (rows / 50) * 100)`). |
| **Challenge DDL** | **100** | Telemetry ingestion table | 100 pts if `AttractionRun`, `RideExecution`, or `ParkRun` table exists with write activity. |
| **Compute Scaling** | **100** | Spanner cluster sizing | Based on Spanner Processing Units (PUs):<br>• 100 PUs (Baseline) = 25 pts<br>• 200–400 PUs = 50 pts<br>• 500–900 PUs = 75 pts<br>• $\ge$ 1,000 PUs (1+ Node) = 100 pts |
| **Ingestion Velocity** | **100** | Real-time write throughput | Scaled linearly up to 200 runs/sec (`min(100, (qps / 200) * 100)`). |
| **Revenue Optimization**| **200** | Net business profit | Scaled relative to the highest park profit in the event (`(revenue / max_revenue) * 200`). |
| **Speed Velocity Bonus**| **+100** | TrueTime pipeline commit speed | Additive bonus based on `MIN(RunTimestamp)`. 100 bonus pts for the earliest finisher, decaying by 2.5 pts/min elapsed from first finisher. Eliminates 100% ties. |
| **TOTAL** | **1,100** | **Comprehensive Hackathon Score** | |

---

## 3. Business Simulation & Price Elasticity Heuristics

The challenge task requires participants to simulate ride operations (`AttractionRun` records). Revenue is not computed naively from `runs * price`; the dashboard applies a **price elasticity model**:

```
Demand Factor = max(0.0, min(1.25, 1.0 - 0.04 * (TicketPrice - 15.0)))
```

### Elasticity & Capacity Mechanics
* **Benchmark Price**: \$15.00 yields standard turnout (80 visitors per run on a 100-person capacity attraction).
* **Discount Pricing (\$5.00)**: Turnout hits maximum attraction capacity (100 visitors/run). Low margins require high run volumes to cover operating costs.
* **Mid-Tier Pricing (\$25.00)**: Visitor turnout drops to 48 visitors/run.
* **Luxury Extortion ($\ge$ \$40.00)**: Demand collapses to 0. Empty rides generate \$0 revenue while continuing to accrue operational overhead.
* **Physical Park Capacity**: Capped at **85,000 daily guests** per park, bounding admission revenue to a realistic **\$1.5M to \$3.5M** window. High run volumes beyond capacity yield an operational efficiency micro-bonus (\$0.025/run).
* **Operational Cost**: Base facility overhead of \$120,000 + marginal variable cost of \$0.50 per ride execution (`$120,000 + runs * 0.50`). Profit = `Revenue - Operating Costs`.

---

## 4. Achievement Badges

Badges highlight specific engineering decisions or operational failure modes:

| Badge | Title | Condition | Strategic Meaning |
| :---: | :--- | :--- | :--- |
| 🏰 | **Castle Architect** | 3 core tables + Property Graph deployed | Foundations complete. |
| 🎢 | **Rollercoaster Tycoon** | Total rows in Spanner $\ge$ 50 | Comprehensive park data populated. |
| ⚡ | **Hyperscale Operator** | Spanner scaled to $\ge$ 500 PUs | Scaled cluster capacity for high concurrency. |
| 🚀 | **Throughput Titan** | Ingestion velocity $\ge$ 100 runs/sec | Heavy concurrent write pipeline active. |
| 🔥 | **Spanner Meltdown** | CPU utilization > 50% | Heavy query or transaction contention. |
| 💎 | **Luxury Trap** | Average ticket price > \$35.00 | Overpriced tickets resulting in empty rides. |
| 🏷️ | **Bargain Basement** | 0 < Ticket Price < \$8.00 | Underpriced tickets leaving gross margin on the table. |
| ⚡ | **Speed Demon** | Speed Bonus $\ge$ 75 pts | Earliest pipeline write velocity milestone achieved. |
| 💤 | **Sleeping Beauty** | 0 core tables deployed | Team has not applied base Terraform/DDL. |

---

## 5. Dashboard Architecture & Features

The dashboard is built with Streamlit and organized into 5 primary views:

### Tab 1: 🏆 City Leaderboard & Awards
* **Global Standings**: Ranked table sorted by Total Score with Speed Bonus and component columns.
* **Progress Badges**: Visual display of earned achievement badges.
* **Component Breakdown**: Granular scores for Core DDL, Graph, Rows, Extended DDL, Scaling, Throughput, Profit, and Speed Bonus.

### Tab 2: 📈 Business & Ride Execution Analytics
* **Revenue vs. Cost Comparison**: Bar charts showing gross ticket revenue against operating expenses.
* **Net Profit**: Tracks which teams identified the sweet spot on the price elasticity curve.
* **Visitor Volume**: Measures total simulated park guests.

### Tab 3: ⚡ Spanner Telemetry & Compute Scale
* **Processing Units**: Real-time cluster sizing per project.
* **Ingestion Velocity**: Current write throughput (`Runs/sec`).
* **Resource Utilization**: Max CPU utilization (%) and total storage (MB) pulled via the Cloud Monitoring API.

### Tab 4: 🛠️ Schema & Graph Inspector
* **Table Verification**: Table presence indicators (`DisneylandPark`, `Attraction`, `Path`, `AttractionRun`).
* **Property Graph State**: Live validation of `DisneylandGraph` property graph catalog.

### Tab 5: 🎪 Disneyland Park Closing Ceremony
* **Interactive Step Controller**: Stepper interface (`[⏮️ Reset Freeze]`, `[◀ Prev Event]`, `[Next Event ▶]`, `[⚡ Execute Live DML]`).
* **5 Dramatic Park Disaster & Fortune Rounds**:
  1. **🌧️ Monsoon over the Magic Kingdom**: 10% emergency discount on outdoor rides + 3% extortion fine on ticket prices $> \$25$.
  2. **💥 Space Mountain Glitch**: 5% run deletion on Space Mountain (#40) (-5% rev) and 2% urgent engineering repair fee on 25% of parks.
  3. **🕵️ Antitrust Price Gouging Audit**: 15% fine on Luxury Trap operators ($TicketPrice > $30); 5% tourism grant on family-friendly pricing ($10 - $18).
  4. **⚡ Regional Spanner Power Brownout**: Audits compute sizing (1,000 PUs with < 50 runs/sec penalized -90 pts and 3% carbon tax; lean high-throughput rewarded +90 pts and 3% rebate).
  5. **🎆 Mickey Centenary Jubilee Finale**: +20% score surge and +8% parade revenue boost for parks with active `DisneylandGraph` property graph and catalog depth.
* **Kahoot-Style Round Analytics & Visualizations**:
  - *KPI Scorecard*: Real-time badges showing Parks Impacted (%), Highest Climber (rank jump), Net Financial Swing ($), and Leaderboard Position Shifts.
  - *Podium Cards*: Top 3 leaders displayed in gold, silver, and bronze cards with rank change chips.
  - *Plotly Rank Movement Chart*: Horizontal bar chart highlighting ranks gained (`🟢 ▲`) or lost (`🔴 ▼`) for every park.
  - *Plotly Financial Impact Chart*: Visualizing the exact dollar loss/gain distribution across the network.
  - *Damage & Safety Inspector*: Filter breakdown separating damaged parks from safe/subsidized parks.
* **Architecture Lessons & DML**: Displays the database concept and SQL statement for each round to bridge lab learning with gameplay.
* **Dual Execution**: Computes animated in-memory rank shifts (`▲ +2`, `▼ -1`) while optionally dispatching live DML to participant Spanner databases.
* **Grand Champion Crowning**: Automatic balloon animation and royal banner celebrating the final winner.

---

## 6. Live AI Roast Announcer HUD

To maintain high participant engagement, the dashboard incorporates an automated AI commentator:

* **Engine**: Google Vertex AI `gemini-3.8-flash` in `global` location.
* **Cadence**: Broadcasts every 4 minutes (240-second cycle) and stays visible for 60 seconds.
* **Format**:
  * Identifies an underperforming, hyper-scaled, or mispriced city.
  * Produces an entertaining roast summarizing their technical bottleneck.
  * Delivers a sharp 2-line rhyming couplet mocking their operational decisions.
* **UI Delivery**: Rendered as a floating neon toast card in the bottom right corner with a 60-second animated progress bar. Hovering pauses the countdown.
* **Admin Overrides**: Facilitators can start or stop the announcer completely using the sidebar toggle (`Enable AI Roaster Announcer`), force a live re-roll (`🎭 Roast A Park Now`), or toggle persistent visibility (`Always Show Roast HUD`).

---

## 7. Data Ingestion & Technical Mechanics

### Direct Spanner Metadata Inspection
The leaderboard uses a `ThreadPoolExecutor(max_workers=25)` to query each project's Spanner instance concurrently:
1. `information_schema.tables`: Detects core and extension tables.
2. `information_schema.property_graphs`: Detects graph catalogs.
3. Row Counts: Executes `SELECT COUNT(1)` on core tables.
4. Run Telemetry: Computes throughput and ticket pricing:
   ```sql
   SELECT 
     COUNT(1), 
     AVG(TicketPrice), 
     TIMESTAMP_DIFF(MAX(RunTimestamp), MIN(RunTimestamp), SECOND),
     COUNTIF(RunTimestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 2 MINUTE))
   FROM AttractionRun;
   ```

### Cloud Monitoring Integration
Pulls rolling 5-minute telemetry intervals using `MetricServiceClient`:
* Metric: `spanner.googleapis.com/instance/cpu/utilization`
* Metric: `spanner.googleapis.com/instance/storage/total_bytes`

---

## 8. Deployment & Administration

* **Start Dashboard**:
  ```bash
  ./labs/lab02_spanner_disneyland/leaderboard/dashboard/run.sh 8501
  ```
* **Federated Infrastructure**:
  The admin project hosts a BigQuery dataset (`admin_leaderboard`) with external federated connections to each participant's Cloud Spanner instance, provisioned dynamically via Terraform in `labs/lab02_spanner_disneyland/leaderboard/infra/` using `./labs/lab02_spanner_disneyland/leaderboard/deploy_admin.sh`.
