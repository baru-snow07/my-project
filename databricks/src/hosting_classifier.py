# Databricks notebook source
# MAGIC %md
# MAGIC # Hosting classifier: an LLM as teacher, a small model as student
# MAGIC
# MAGIC **Problem.** Some top "prospects" are hosting companies or ISPs: their servers belong to their customers,
# MAGIC so they are not the buyer. The rules in the main notebook catch most of them, not all.
# MAGIC
# MAGIC **Approach (no paid AI calls).**
# MAGIC 1. *Teacher:* Claude already labelled 500 top domains as `end_organisation` / `hosting_or_isp` / `unsure`
# MAGIC    (`eval/llm_labels.csv`, done once in a Claude Code session).
# MAGIC 2. *Student:* a small scikit-learn model learns that judgement from facts already in `gold_companies`.
# MAGIC 3. *Grade:* on 90 labels taken from each domain's About/Contact page (`heldout_labels.csv`,
# MAGIC    `reference_labels.csv`). Those domains are **removed from training**, and the labels are not Claude's,
# MAGIC    so the grade is independent of the teacher.
# MAGIC 4. *Apply:* score every domain in Gold (the LLM covered 500), log to MLflow, register in Unity Catalog.
# MAGIC
# MAGIC | Output | Holds |
# MAGIC |---|---|
# MAGIC | `gold_hosting_predictions` | Every domain: probability it is hosting/ISP and the label (`unsure` in the middle band) |
# MAGIC | `gold_hosting_eval` | Student vs teacher on the same held-out domains |
# MAGIC | model `hosting_classifier` | Registered in Unity Catalog, alias `champion` |

# COMMAND ----------

dbutils.widgets.text("catalog", "")
dbutils.widgets.text("schema", "cyber")
CATALOG = dbutils.widgets.get("catalog").strip() or spark.sql("SELECT current_catalog()").first()[0]
SCHEMA = dbutils.widgets.get("schema")
spark.sql(f"USE `{CATALOG}`.{SCHEMA}")
LABELS = f"/Volumes/{CATALOG}/{SCHEMA}/landing/labels"

import os
need = ["llm_labels.csv", "heldout_labels.csv", "reference_labels.csv"]
missing = [f for f in need if not os.path.exists(f"{LABELS}/{f}")]
if missing:
    dbutils.notebook.exit(f"Skipped: upload {missing} from the repo's eval/ folder into {LABELS}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Features: facts about each domain, already in Gold
# MAGIC Each one is a clue a person would use: does the network owner's name match the domain? Does the website
# MAGIC title talk about hosting? Is there a hosting control panel (cPanel, Plesk)? Is it a `.edu` or `.gov`?

# COMMAND ----------

INFRA_WORDS = r"(host|server|vps|cloud|hosting|dedi|colo|datacent|broadband|dsl|cable|fiber|fibra|telecom|telekom|isp([^a-z]|$))"
ORG_WORDS = r"(host|server|vps|cloud|datacent|colo|telecom|telekom|broadband|communications|internet|network|isp([^a-z]|$)|online)"
# No backslashes in these: Spark SQL string literals would turn "\b" into a control character.
TITLE_WORDS = r"(hosting|vps|server|cpanel|plesk|domain|reseller|dedicated|cloud|webmail|whm|directadmin)"
INSTITUTION_WORDS = r"(universi|college|school|academ|institut|hospital|health|ministr|government|gouv|gobierno|council|bank)"
PANELS = ["cPanel", "Plesk", "DirectAdmin", "ISPConfig", "Webmin"]

FEATURES = ["log_ips", "log_services", "services_per_ip", "ownership", "no_identity", "org_matches_domain",
            "infra_word_in_domain", "infra_org_owned", "org_institution", "hosting_word_in_title", "no_title", "panel_tech",
            "n_tech", "edu_gov", "dot_net", "dot_org", "dot_com", "has_web", "cdn_only", "self_signed"]

features = spark.sql(f"""
    WITH g AS (
        SELECT *, lower(split(company, '\\\\.')[0]) AS stem,
               lower(regexp_replace(coalesce(network_org, ''), '[^A-Za-z0-9]', '')) AS org_clean
        FROM gold_companies WHERE key_type = 'domain')
    SELECT company,
        ln(1 + ips)                                                    AS log_ips,
        ln(1 + services)                                               AS log_services,
        coalesce(try_divide(services, ips), 0)                         AS services_per_ip,
        coalesce(ownership, 0)                                         AS ownership,
        CAST(ownership IS NULL AS INT)                                 AS no_identity,
        CAST(length(stem) >= 4 AND instr(org_clean, stem) > 0 AS INT)  AS org_matches_domain,
        CAST(company RLIKE '{INFRA_WORDS}' AS INT)                     AS infra_word_in_domain,
        -- v2: an infrastructure-sounding network counts only when the domain OWNS it. Renting a server from
        -- "XYZ Hosting" makes a company a hosting customer, not a host (v1 used the raw clue and flagged 72k prospects).
        CAST(length(stem) >= 4 AND instr(org_clean, stem) > 0
             AND lower(coalesce(network_org, '')) RLIKE '{ORG_WORDS}' AS INT) AS infra_org_owned,
        CAST(lower(coalesce(network_org, '')) RLIKE '{INSTITUTION_WORDS}' AS INT) AS org_institution,
        CAST(lower(coalesce(web_title, '')) RLIKE '{TITLE_WORDS}' AS INT) AS hosting_word_in_title,
        CAST(web_title IS NULL AS INT)                                 AS no_title,
        CAST(arrays_overlap(coalesce(tech, array()), array({", ".join(f"'{p}'" for p in PANELS)})) AS INT) AS panel_tech,
        coalesce(size(tech), 0)                                        AS n_tech,
        CAST(company RLIKE '\\\\.(edu|gov|gob|gouv|mil)(\\\\.[a-z]{{2}})?$|\\\\.(ac|gov|gob|gouv|edu)\\\\.[a-z]{{2}}$' AS INT) AS edu_gov,
        CAST(company RLIKE '\\\\.net$' AS INT)                         AS dot_net,
        CAST(company RLIKE '\\\\.org$' AS INT)                         AS dot_org,
        CAST(company RLIKE '\\\\.com$' AS INT)                         AS dot_com,
        CAST(coalesce(has_web, false) AS INT)                          AS has_web,
        CAST(coalesce(cdn_only, false) AS INT)                         AS cdn_only,
        CAST(coalesce(self_signed, false) AS INT)                      AS self_signed
    FROM g""")
features.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("silver_hosting_features")
X_all = spark.table("silver_hosting_features").toPandas()
print(f"{len(X_all):,} domains with features")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Training and held-out sets

# COMMAND ----------

import numpy as np
import pandas as pd
teacher = pd.read_csv(f"{LABELS}/llm_labels.csv")
held = pd.concat([pd.read_csv(f"{LABELS}/heldout_labels.csv"), pd.read_csv(f"{LABELS}/reference_labels.csv")])
held = held[["company", "human_label"]].drop_duplicates("company")

train = (teacher[~teacher.company.isin(held.company) & (teacher.label != "unsure")]
         .merge(X_all, on="company"))
X, y = train[FEATURES].astype(float), (train.label == "hosting_or_isp").astype(int)
print(f"Training on {len(train)} Claude labels ({y.sum()} hosting, {len(y) - y.sum()} end organisation); "
      f"{len(held)} held-out domains kept aside")

# Only answer where the model has seen similar domains. The teacher labelled top prospects (median 10 servers),
# but most prospects have 1 server. Below the training set's 25th percentile the student was guessing:
# v2 (no limit) called ~50k one-server sites "hosting"; v3 (5th percentile, 2 servers) was right about half the time
# in a spot check. Domains smaller than this get "unsure".
MIN_IPS = int(round(np.expm1(train.log_ips.quantile(0.25))))
def in_range(df):
    return np.expm1(df.log_ips).round() >= MIN_IPS
print(f"Model gives a verdict only for domains with {MIN_IPS}+ servers")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Choose a model by cross-validation on the training set only

# COMMAND ----------

try:
    import sklearn
except ImportError:  # some serverless environments ship without it
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "scikit-learn"])
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

CANDIDATES = {
    "logistic_regression": make_pipeline(StandardScaler(), LogisticRegression(class_weight="balanced", max_iter=1000)),
    "random_forest": RandomForestClassifier(n_estimators=300, min_samples_leaf=3, class_weight="balanced", random_state=42),
}
cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
cv_auc = {name: cross_val_score(m, X, y, cv=cv, scoring="roc_auc").mean() for name, m in CANDIDATES.items()}
best = max(cv_auc, key=cv_auc.get)
print({k: round(v, 3) for k, v in cv_auc.items()}, "→ chosen:", best)
model = CANDIDATES[best].fit(X, y)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Grade student and teacher on the same held-out domains
# MAGIC Probabilities between 0.35 and 0.65 become `unsure`, like the LLM's own `unsure`, so both are graded the same way:
# MAGIC how often each one commits to an answer, and how often that answer matches the About/Contact page.

# COMMAND ----------

LOW, HIGH = 0.35, 0.65

def to_label(p):
    return "hosting_or_isp" if p >= HIGH else "end_organisation" if p <= LOW else "unsure"

def grade(df, col):
    answered = df[df[col] != "unsure"]
    decided = answered[answered.human_label != "unsure"]
    hosting = df[df.human_label == "hosting_or_isp"]
    return {"domains": len(df),
            "answered_pct": round(100 * len(answered) / len(df)),
            "accuracy_where_both_decided_pct": round(100 * (decided[col] == decided.human_label).mean()),
            "both_decided": len(decided),
            "hosting_caught": int((hosting[col] == "hosting_or_isp").sum()),
            "hosting_total": len(hosting)}

ev = held.merge(X_all, on="company").merge(teacher[["company", "label"]].rename(columns={"label": "teacher"}), on="company", how="left")
ev["p_hosting"] = model.predict_proba(ev[FEATURES].astype(float))[:, 1]
ev["student"] = ev.p_hosting.map(to_label)
ev.loc[~in_range(ev), "student"] = "unsure"  # same rule as when scoring everything
ev["teacher"] = ev.teacher.fillna("unsure")
results = pd.DataFrame([{"model": f"student: {best} (free)", **grade(ev, "student")},
                        {"model": "teacher: Claude (paid once, 500 domains)", **grade(ev, "teacher")}])
spark.createDataFrame(results).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("gold_hosting_eval")
display(results)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Score every domain, log to MLflow, register the model

# COMMAND ----------

X_all["p_hosting"] = model.predict_proba(X_all[FEATURES].astype(float))[:, 1].round(3)
ok = in_range(X_all)
X_all["ai_business_type"] = np.where(ok, X_all.p_hosting.map(to_label), "unsure")
X_all["ai_note"] = np.where(ok, "", f"fewer than {MIN_IPS} servers: outside what the model learned from")
print(f"Model answers for domains with {MIN_IPS}+ servers: {ok.sum():,} of {len(X_all):,}")
(spark.createDataFrame(X_all[["company", "p_hosting", "ai_business_type", "ai_note"]])
    .write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("gold_hosting_predictions"))
display(spark.sql("SELECT ai_business_type, count(*) AS domains FROM gold_hosting_predictions GROUP BY 1 ORDER BY 2 DESC"))

# COMMAND ----------

import mlflow
from mlflow.models import infer_signature
mlflow.set_registry_uri("databricks-uc")
MODEL_NAME = f"{CATALOG}.{SCHEMA}.hosting_classifier"
student = results.iloc[0]
with mlflow.start_run(run_name=f"hosting-classifier-{best}"):
    mlflow.log_params({"model": best, "train_rows": len(train), "features": len(FEATURES),
                       "unsure_band": f"{LOW}-{HIGH}", "min_servers": MIN_IPS, "teacher": "llm_labels.csv"})
    mlflow.log_metrics({f"cv_auc_{k}": v for k, v in cv_auc.items()})
    mlflow.log_metrics({"heldout_answered_pct": student.answered_pct,
                        "heldout_accuracy_pct": student.accuracy_where_both_decided_pct,
                        "heldout_hosting_caught": student.hosting_caught})
    mlflow.log_table(results, artifact_file="student_vs_teacher.json")
    info = mlflow.sklearn.log_model(model, artifact_path="model", registered_model_name=MODEL_NAME,
                                    signature=infer_signature(X.head(5), model.predict_proba(X.head(5))),
                                    input_example=X.head(3))
version = info.registered_model_version
mlflow.MlflowClient().set_registered_model_alias(MODEL_NAME, "champion", version)
print(f"Registered {MODEL_NAME} version {version} as @champion")

# COMMAND ----------

# Which clues matter most (helps explain a prediction to a salesperson).
imp = (model[-1].coef_[0] if best == "logistic_regression" else model.feature_importances_)
display(pd.DataFrame({"feature": FEATURES, "weight": imp}).sort_values("weight", key=abs, ascending=False))
dbutils.notebook.exit(f"Done: {best}, held-out accuracy {student.accuracy_where_both_decided_pct}% "
                      f"on {student.both_decided} decided domains, answered {student.answered_pct}%")
