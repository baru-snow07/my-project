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
| `src/hosting_classifier.py` | Second job task: a small model learns Claude's "real organisation vs hosting/ISP" labels, graded on held-out labels, registered in Unity Catalog |
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
| Silver | `silver_hosting_features` | Per-domain clues for the AI classifier | — |
| Gold | `gold_hosting_predictions`, `gold_hosting_eval` | AI business type per domain; student vs teacher grades | `llm_classify.py` |

## Dashboard

Four pages:
1. **Prospects:** headline counts, accounts by "why now" tier, top countries, and a filterable table of accounts to call,
   each with its top reason, exposed services and known-exploited CVEs. IPs are never shown.
2. **Signals:** companies per signal, services exposed to the internet, the most common known-exploited CVEs.
3. **Does it work:** the back-test AUC computed live in SQL, lift per signal, and the infrastructure removed before scoring.
4. **AI classifier:** the small model against Claude on the same held-out labels, and what it says about prospects.
   The Prospects page also gets a *Business type (AI)* column and filter.

## AI classifier: Claude as teacher, a small model as student (no paid AI calls)

**Problem.** Hosting companies and ISPs score high because their *customers'* servers are insecure, but they are not
the buyer. The rules remove most of them, not all.

**Approach.**
1. *Teacher:* Claude labelled 500 top domains once (`eval/llm_labels.csv`, in a Claude Code session, $0 API spend).
2. *Student:* a scikit-learn model learns that judgement from 20 clues already in Gold, for example: does the network
   owner's name match the domain, is it a university or government network, does the website title mention hosting,
   is there a hosting control panel. Logistic regression and random forest are compared by 5-fold cross-validation on
   the training set; logistic regression won.
3. *Grade:* on 90 labels from each domain's About/Contact page (`heldout_labels.csv` + `reference_labels.csv`). All 90
   are **removed from training**, and they are not Claude's labels, so the grade is independent of the teacher.
4. *Run:* second task of the job, so it re-scores every refresh. Logged to MLflow; registered as
   `databricks_demo_ws.cyber.hosting_classifier`, alias `@champion`.

**Results on the 90 held-out domains** (2026-11-06). Every version is shown, not just the best:

| Version | Change | Answers given | Correct when it answers | Hosting caught | Prospects it labels hosting |
|---|---|---|---|---|---|
| v1 | first model | 77% | 81% | 17/29 | 71,810 |
| v2 | "hosting-sounding network" counts only if the domain owns it; university/government clue | 81% | 81% | 20/29 | 58,590 |
| v3 | answers only for domains with 2+ servers | 81% | 81% | 20/29 | 8,775 |
| **v4 (current)** | answers only for domains with 6+ servers (training set's 25th percentile) | **61%** | **85%** | 16/29 | 1,098 |
| Claude (teacher) | — | 96% | 93% | 26/29 | (500 domains only) |

Why v3 and v4: the teacher labelled top prospects (median 10 servers), but 89% of prospects have one server. A spot
check of v2/v3 found small businesses on Amazon, a Japanese temple and a Chilean university called "hosting": the
model was guessing on domains unlike anything it learned from. v4 says *Not sure* for those instead.
The v4 cut-off was chosen after seeing held-out results, so its 85% is slightly optimistic; the reasoning
(stay inside the training data) does not depend on the held-out set.

**What this shows.** Learning from an LLM's labels gives a free model that runs on every refresh, but here it is
narrower and less accurate than the LLM. It classifies 2,292 prospects (the larger ones, which are also the top of the
call list). To cover small domains it would need labels for small domains, which means paying for more LLM labels or
labelling by hand.

```bash
databricks bundle run cyber_prospecting_pipeline -p cyber --only hosting_classifier
```

## Run it

```bash
databricks auth login --host https://adb-7405616568941532.12.azuredatabricks.net --profile cyber
python tools/build_dashboard.py            # regenerate the dashboard JSON after design changes
cd databricks
databricks bundle validate -p cyber
databricks bundle deploy -p cyber
databricks bundle run cyber_prospecting_pipeline -p cyber
```

## How data gets in (Bronze)

Every run, **Auto Loader** picks up new scan files in `landing/raw` and appends them to `bronze_scan_raw`:
one row per raw JSON line, plus the source file and load time. The checkpoint in `landing/_checkpoints` records
which files are done, so a re-run loads only new files. Only `*.json*` files are read.

Silver then reads one of two sources (`source` parameter):

| `source` | Silver reads | Used for |
|---|---|---|
| `parquet` (the job's default) | `landing/parquet`: the full 14.6M-record file, already parsed on the laptop by `pipeline/ingest.py` | The published results: avoids re-uploading the 16 GB file over a slow connection |
| `raw` | `bronze_scan_raw`, parsed with the same `extract()` logic | The true lakehouse path for new monthly files |

**Verified end to end on 2026-11-05** with a 50,000-record sample of the real scan file (`*-sample50k.json.zst`),
in a separate schema `cyber_raw_e2e` so the dashboard's numbers were not touched:

| Step | Result |
|---|---|
| Bronze | 50,000 records from 1 file |
| Silver | 21,593 rows: **identical** to the laptop parser on the same 50,000 records |
| Gold | 7,944 companies, 1,792 prospects with a signal |
| Re-run | 0 new records loaded (checkpoint works) |

The main schema's Bronze holds the same sample, while its Silver and Gold come from the full Parquet.

Earlier, a notebook file had been uploaded into `landing/raw` by mistake and loaded as 625 rows. It was not used by
any result (the job reads Parquet). The file, the old table (now `zz_archive_bronze_stray_notebook_20261101`) and its
checkpoint are kept in `landing/_archive/` and can be deleted.

```bash
databricks bundle run cyber_prospecting_pipeline -p cyber --notebook-params schema=cyber_raw_e2e,source=raw
```

## Results: same answers as the laptop pipeline

| | Laptop (DuckDB) | Databricks (Spark SQL) |
|---|---|---|
| Silver rows | 6,196,731 | 6,196,731 (5,305,341 after keeping the latest scan per service) |
| Back-test AUC | 0.803 | **0.803** |
| Breached servers (labels) | 56 | 56 |
| Top account | berkeley.edu, 162 | berkeley.edu, 162 |
| Prospects with a signal | 228,997 | 229,319 (+0.1%) |
| Network providers / infra domains | 3,578 / ~55,000 | 3,577 / 54,589 |

The small differences come from how the two engines break ties in `mode()` and treat NULL organisations
in the provider rule. Scores, tiers and the back-test are unchanged.

## Review for future runs

Checked against the live workspace on 2026-11-05. Fixed:

| Issue | Evidence | Fix |
|---|---|---|
| Repeated scans counted twice | 6,196,731 rows but 5,305,341 unique (server, port, company); ~14% are re-scans in one file, and every new month adds more | `silver_latest` keeps only the latest scan of each service; all downstream steps read it. ~180 accounts had a known-exploited CVE only in an older scan. AUC unchanged (0.803) |
| Division by zero fails the job | Databricks SQL raises `DIVIDE_BY_ZERO` (ANSI mode); the lift query divides by the breached share, so a month with no breaches would fail the run | `try_divide` in the notebook and in the dashboard's back-test and lift queries |
| Test files double-counted | `ingest.py` also writes `*-sample.parquet` | Silver reads only `*[0-9].parquet` |
| Long queries abandoned | `tools/sql.py` gave up after the API's 50 s wait | Polls until the statement finishes (10 min limit) |
| Non-scan files loaded into Bronze | A notebook in `landing/raw` became 625 Bronze rows | Bronze reads only `*.json*` files and runs on every job, whatever Silver's source |
| Catalog hard-coded in the dashboard | Dashboard JSON can't use bundle variables | `CYBER_CATALOG` / `CYBER_SCHEMA` settings in `build_dashboard.py` |

Verified working: raw `.json.zst` files are decompressed natively (`read_files(..., format => 'text')` read all 1,000
lines of a test file), so the Auto Loader path works for real scan files.

Known, not changed:
- **One large `.zst` file is read by a single worker** (zstd isn't splittable). Many smaller files process in parallel.
- **Silver is rebuilt from all of Bronze on every run.** Fine at this size; at hundreds of files a month, switch to an
  incremental `MERGE` keyed on (ip, port, company).
- **If `bronze_scan_raw` is ever dropped, delete `landing/_checkpoints/bronze_scan_raw` too**, or Auto Loader will skip
  files it thinks it already loaded.
- **`mode(org)` breaks ties arbitrarily**, so the network owner shown can differ between runs for a few companies.
- **The `ai_query` step (`run_llm = true`) has not been run in this workspace**: it is billed per token, so the free
  classifier above is used instead.
- **The AI classifier's dashboard note says "6+ servers"**: that number comes from the training data and is written into
  the dashboard text, so update `build_dashboard.py` if the labels change.
- **The job has no failure alerts or retries.** Add `email_notifications` before relying on the file-arrival trigger.
- **The laptop pipeline (`pipeline/build.py`) still counts repeated scans.** Its published numbers are from a single
  file and match this run's AUC; apply the same latest-scan rule there before processing more than one file.

## Cost

- **Job:** serverless, under 2 minutes for the full 6.2M rows.
- **Dashboard:** a serverless 2X-Small SQL warehouse that auto-stops after 10 idle minutes, so it costs only while
  someone is looking at the dashboard.
- **AI classifier:** no AI calls; about 1.5 minutes of the same serverless compute per run.
- **AI step (optional, `run_llm = true`):** pay-per-token `ai_query` over the top 50 prospects, a few cents per run. Off.
