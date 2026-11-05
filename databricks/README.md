# Cyber Prospecting on Azure Databricks

The laptop pipeline rebuilt as a lakehouse, deployed as code with a **Databricks Asset Bundle**:
one serverless job builds Bronze → Silver → Gold Delta tables and the back-test, and an **AI/BI dashboard**
shows the results to sales and to anyone asking "does the score work?".

## What's here

| Path | What it is |
|---|---|
| `databricks.yml` | Bundle definition: workspace, catalog/schema/warehouse variables |
| `resources/pipeline.job.yml` | Serverless job, triggered when a new file lands in the volume (trigger starts paused) |
| `resources/dashboard.yml` | The AI/BI dashboard resource |
| `src/cyber_prospecting.py` | The pipeline notebook: Auto Loader Bronze, Silver signals, learned infrastructure rules, Gold scoring, back-test to MLflow, optional `ai_query` classifier |
| `src/cyber_prospecting.lvdash.json` | Dashboard definition, **generated** by `tools/build_dashboard.py` |
| `tools/build_dashboard.py` | The dashboard design as readable Python: queries, charts, layout, colours |
| `tools/sql.py` | Run a SQL statement on the warehouse from the terminal (used to test every dashboard query) |

## Lakehouse layers

| Layer | Table | Holds | Laptop equivalent |
|---|---|---|---|
| Landing | volume `landing/raw`, `landing/parquet` | Raw `.json(.zst)` files, or `ingest.py` Parquet | `Downloads/`, `data/rows/` |
| Bronze | `bronze_scan_raw` | Raw JSON lines via Auto Loader (incremental) | the scan file |
| Silver | `silver_scan_rows` | One row per (service, company) with the signals | `ingest.py` output |
| Silver | `silver_providers`, `silver_infra_domains` | Infrastructure learned from the data | `build.py` rules |
| Gold | `gold_companies`, view `gold_prospects` | Scored, explainable companies | `companies.parquet` |
| Gold | `gold_eval_hosts` | Per-server back-test features | `evaluate.py` |

## Dashboard

Three pages:
1. **Prospects:** headline counts, accounts by "why now" tier, top countries, and a filterable table of accounts to call,
   each with its top reason, exposed services and known-exploited CVEs. IPs are never shown.
2. **Signals:** companies per signal, services exposed to the internet, the most common known-exploited CVEs.
3. **Does it work:** the back-test AUC computed live in SQL, lift per signal, and the infrastructure removed before scoring.

## Run it

```bash
databricks auth login --host https://adb-7405616568941532.12.azuredatabricks.net --profile cyber
python tools/build_dashboard.py            # regenerate the dashboard JSON after design changes
cd databricks
databricks bundle validate -p cyber
databricks bundle deploy -p cyber
databricks bundle run cyber_prospecting_pipeline -p cyber
```

The job reads `landing/parquet` (the full 14.6M-record run, produced on the laptop by `pipeline/ingest.py`).
Set the notebook's `source` to `raw` to ingest scan files through Auto Loader instead.

## Results: same answers as the laptop pipeline

| | Laptop (DuckDB) | Databricks (Spark SQL) |
|---|---|---|
| Silver rows | 6,196,731 | 6,196,731 |
| Back-test AUC | 0.803 | **0.803** |
| Breached servers (labels) | 56 | 56 |
| Top account | berkeley.edu, 162 | berkeley.edu, 162 |
| Prospects with a signal | 228,997 | 229,247 (+0.1%) |
| Network providers / infra domains | 3,578 / ~55,000 | 3,577 / 54,743 |

The small differences come from how the two engines break ties in `mode()` and treat NULL organisations
in the provider rule. Scores, tiers and the back-test are unchanged.

## Cost

- **Job:** serverless, under 2 minutes for the full 6.2M rows.
- **Dashboard:** a serverless 2X-Small SQL warehouse that auto-stops after 10 idle minutes, so it costs only while
  someone is looking at the dashboard.
- **AI step (optional, `run_llm = true`):** pay-per-token `ai_query` over the top 50 prospects, a few cents per run.
