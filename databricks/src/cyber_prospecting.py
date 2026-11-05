# Databricks notebook source
# MAGIC %md
# MAGIC # Cyber Prospecting on Azure Databricks
# MAGIC
# MAGIC The laptop pipeline (`ingest.py` → Parquet → `build.py` in DuckDB → Streamlit), rebuilt as a lakehouse:
# MAGIC
# MAGIC | Layer | Table | What it holds | Laptop equivalent |
# MAGIC |---|---|---|---|
# MAGIC | Bronze | `bronze_scan_raw` | Raw JSON lines, untouched | the `.json.zst` file |
# MAGIC | Silver | `silver_scan_rows` | One row per (service, company) with the signals | `ingest.py` output Parquet |
# MAGIC | Silver | `silver_latest` | The latest scan of each service only (re-scans and old months dropped) | — |
# MAGIC | Silver | `silver_providers`, `silver_infra_domains` | Infrastructure learned from the data | rules 1–2c in `build.py` |
# MAGIC | Gold | `gold_companies` | Scored, explainable companies | `companies.parquet` |
# MAGIC | Gold | `gold_llm_hosting_labels` | LLM verdict: real org vs hosting/ISP | `llm_classify.py` |
# MAGIC
# MAGIC Plus: back-test AUC and weights logged to **MLflow**, and the classifier prompt in the **MLflow prompt registry**.
# MAGIC
# MAGIC **Run cells top to bottom.** Choose the data source in cell 2 (`raw` sample or your existing Parquet).

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Settings
# MAGIC Widgets appear at the top of the notebook. In Databricks Free Edition the catalog is usually `workspace`.

# COMMAND ----------

dbutils.widgets.text("catalog", "")  # leave blank to use this workspace's default catalog
dbutils.widgets.text("schema", "cyber")
dbutils.widgets.dropdown("source", "raw", ["raw", "parquet"])
dbutils.widgets.text("llm_endpoint", "databricks-meta-llama-3-3-70b-instruct")
dbutils.widgets.dropdown("run_llm", "false", ["false", "true"])  # section 8 needs a model serving endpoint

print("Catalogs you can use:", [r[0] for r in spark.sql("SHOW CATALOGS").collect()])
CATALOG = dbutils.widgets.get("catalog").strip() or spark.sql("SELECT current_catalog()").first()[0]
SCHEMA = dbutils.widgets.get("schema")
SOURCE = dbutils.widgets.get("source")
LLM_ENDPOINT = dbutils.widgets.get("llm_endpoint")
RUN_LLM = dbutils.widgets.get("run_llm") == "true"
print("Using catalog:", CATALOG)

spark.sql(f"CREATE SCHEMA IF NOT EXISTS `{CATALOG}`.{SCHEMA}")
spark.sql(f"USE `{CATALOG}`.{SCHEMA}")

if CATALOG == "hive_metastore":
    # No Unity Catalog on this workspace: volumes don't exist, so files land in DBFS instead.
    VOL = f"dbfs:/FileStore/{SCHEMA}/landing"
    VOL_LOCAL = f"/dbfs/FileStore/{SCHEMA}/landing"  # same folder, as seen by plain Python
    print("No Unity Catalog here: using DBFS. Upload files with Catalog → Add data → DBFS, or the CLI.")
else:
    spark.sql(f"CREATE VOLUME IF NOT EXISTS `{CATALOG}`.{SCHEMA}.landing")
    VOL = VOL_LOCAL = f"/Volumes/{CATALOG}/{SCHEMA}/landing"
for d in ["raw", "parquet", "labels", "_checkpoints"]:
    dbutils.fs.mkdirs(f"{VOL}/{d}")
print(f"Upload files into {VOL}/raw (scan sample .jsonl.gz) or {VOL}/parquet (existing data/rows/*.parquet)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Bronze: land raw scan records with Auto Loader
# MAGIC
# MAGIC Auto Loader remembers which files it has already processed (in the checkpoint), so next month you just drop
# MAGIC new files into the folder and re-run. That is the same idea as `ingest.py` skipping files it has already
# MAGIC converted, but managed by the platform and scalable to any number of files.
# MAGIC
# MAGIC Bronze keeps each record **as raw text**. If the parsing logic changes later, Silver can be rebuilt
# MAGIC from Bronze without re-uploading anything.

# COMMAND ----------

from pyspark.sql import functions as F

if SOURCE == "raw":
    (spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "text")
        .load(f"{VOL}/raw")
        .select(F.col("value").alias("raw_json"),
                F.col("_metadata.file_path").alias("source_file"),
                F.current_timestamp().alias("ingested_at"))
        .writeStream
        .option("checkpointLocation", f"{VOL}/_checkpoints/bronze_scan_raw")
        .trigger(availableNow=True)
        .toTable("bronze_scan_raw")
        .awaitTermination())
    display(spark.sql("SELECT source_file, count(*) AS records FROM bronze_scan_raw GROUP BY ALL"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Silver: parse each record into per-company signal rows
# MAGIC
# MAGIC This is `extract()` from `ingest.py`, unchanged in logic. On the laptop it ran in a process pool;
# MAGIC here Spark runs it on every core of the cluster. Same function, distributed.
# MAGIC
# MAGIC It applies the record-level traps: honeypots dropped, probe vs real answer (`EXPOSED_SERVICES` only counts
# MAGIC parsed protocol blocks), CDN edges never attributed by their own certificate.

# COMMAND ----------

import json, re
from pyspark.sql import types as T

INFRA_DOMAINS = {
    'incapdns.net', 'googleusercontent.com', 'amazonaws.com', 'cloudfront.net', 'akamaitechnologies.com',
    'akamaiedge.net', 'cloudflare.com', 'linodeusercontent.com', 'your-server.de', 'contaboserver.net',
    'unifiedlayer.com', 'vultrusercontent.com', 'digitaloceanspaces.com', 'azure.com', 'cloudapp.net',
    'bc.googleusercontent.com', 'secureserver.net', 'hwclouds-dns.com', 'aliyun.com', 'ovh.net',
    'hostwindsdns.com', 'static.cnode.io', 'fastly.net', 'edgecastcdn.net', 'r.cloudfront.net',
    'cloudflare.net', 'awsglobalaccelerator.com', '1e100.net', 'imperva.com', 'incapsula.com',
    'example.com', 'example.org', 'localdomain', 'local', 'notexist.com', 'sl-reverse.com',
}
TWO_LEVEL_SUFFIXES = {'co.uk', 'com.au', 'co.jp', 'com.br', 'co.in', 'com.cn', 'co.kr', 'com.sg', 'co.nz',
                      'com.mx', 'co.za', 'com.tr', 'com.tw', 'com.hk', 'or.jp', 'ne.jp', 'ac.uk', 'org.uk', 'gov.uk'}
EXPOSED_SERVICES = {
    'rdp_encryption': 'rdp', 'smb': 'smb', 'telnet': 'telnet', 'vnc': 'vnc', 'ftp': 'ftp',
    'mysql': 'mysql', 'mongodb': 'mongodb', 'redis': 'redis', 'elastic': 'elasticsearch',
    'postgresql': 'postgresql', 'ms_sql': 'mssql', 'kubernetes': 'kubernetes', 'docker': 'docker',
    'open_dir': 'open_directory', 'snmp': 'snmp', 'modbus': 'modbus', 's7': 'siemens_s7',
    'bacnet': 'bacnet', 'dnp3': 'dnp3',
}
LEGACY_TLS = {'SSLv2', 'SSLv3', 'TLSv1', 'TLSv1.1'}
GENERATED_WORDS = re.compile(r'^(ip|host|server|srv|vps|vm|static|dyn|dhcp|pool|client|customer|cust|dsl|adsl|cable|ptr|rev|node|unassigned)[-_.]?\d')


def registered_domain(host):
    parts = host.lower().strip('.').lstrip('*.').split('.')
    if len(parts) < 2 or not re.search('[a-z]', parts[-1]):
        return None
    n = 3 if '.'.join(parts[-2:]) in TWO_LEVEL_SUFFIXES else 2
    return '.'.join(parts[-n:]) if len(parts) >= n else None


def embeds_ip(hostname, ip):
    if not ip or '.' not in ip:
        return False
    a, b, c, d = ip.split('.')[:4]
    return any(p in hostname for p in (f'{c}.{d}', f'{c}-{d}', f'{b}-{c}', f'{a}-{b}', f'{d}.{c}'))


def generated(hostname, ip):
    first = hostname.split('.')[0]
    return (embeds_ip(hostname, ip) or sum(ch.isdigit() for ch in first) >= 3 or bool(re.search(r'[0-9a-f]{8}', first))
            or bool(GENERATED_WORDS.search(first)))


def company_keys(r, tags):
    ip = r.get('ip_str')
    hostnames = r.get('hostnames') or []
    keys = []
    for dom in r.get('domains') or []:
        if dom in INFRA_DOMAINS or '.' not in dom:
            continue
        under = [h for h in hostnames if h.endswith(dom)]
        if under and all(embeds_ip(h, ip) for h in under):
            continue
        keys.append(('domain', dom, bool(under) and all(generated(h, ip) for h in under)))
    if not keys and 'cdn' not in tags:
        cn = ((r.get('ssl') or {}).get('cert') or {}).get('subject', {}).get('CN')
        dom = registered_domain(cn) if isinstance(cn, str) else None
        if dom and dom not in INFRA_DOMAINS:
            keys.append(('domain', dom, False))
    if not keys and not ({'cdn', 'cloud'} & tags) and r.get('org'):
        keys.append(('org', r['org'], False))
    return keys


def extract(r):
    tags = set(r.get('tags') or [])
    if 'honeypot' in tags:
        return []
    keys = company_keys(r, tags)
    if not keys:
        return []
    loc = r.get('location') or {}
    http = r.get('http') or {}
    ssl = r.get('ssl') or {}
    cert = ssl.get('cert') or {}
    headers = {k.lower() for k in (http.get('headers') or {})}
    versions = ssl.get('versions') or []
    vulns = r.get('vulns') or {}
    kev = ransom = high_epss = 0
    max_cvss = max_epss = 0.0
    scored, kev_list = [], []
    for cve, v in vulns.items():
        epss = v.get('epss') or 0.0
        cvss = v.get('cvss') or 0.0
        kev += bool(v.get('kev'))
        if v.get('kev'):
            kev_list.append(cve)
        ransom += bool(v.get('ransomware_campaign'))
        high_epss += epss >= 0.1
        max_cvss, max_epss = max(max_cvss, cvss), max(max_epss, epss)
        scored.append((bool(v.get('kev')), epss, cvss, cve))
    top_cves = [c for *_, c in sorted(scored, reverse=True)[:3]]
    exposed = [name for key, name in EXPOSED_SERVICES.items() if r.get(key)]
    unauth_db = ((r.get('mongodb') or {}).get('authentication') is False
                 or (r.get('redis') or {}).get('authentication_required') is False
                 or bool((r.get('elastic') or {}).get('indices')))
    cn = cert.get('subject', {}).get('CN') if isinstance(cert.get('subject'), dict) else None
    cert_domain = registered_domain(cn) if isinstance(cn, str) else None
    web_host = (http.get('host') or '').lower()
    ntlm = r.get('ntlm') or {}
    components = http.get('components') or {}
    base = {
        'ip': r.get('ip_str') or r.get('ipv6'), 'port': r.get('port'), 'ts': r.get('timestamp'),
        'org': r.get('org'), 'country': loc.get('country_code'), 'city': loc.get('city'),
        'edge': 'cdn' in tags, 'cloud': 'cloud' in tags,
        'product': r.get('product'), 'version': r.get('version'),
        'exposed': exposed, 'unauth_data': unauth_db, 'anon_ftp': bool((r.get('ftp') or {}).get('anonymous')),
        'ntlm_leak': bool(ntlm.get('netbios_domain_name') or ntlm.get('dns_domain_name')),
        'compromised': 'compromised' in tags, 'eol': bool({'eol-product', 'eol-os'} & tags), 'self_signed': 'self-signed' in tags,
        'n_cves': len(vulns), 'n_kev': kev, 'n_ransomware_cves': ransom, 'n_high_epss': high_epss,
        'max_cvss': max_cvss, 'max_epss': max_epss, 'top_cves': top_cves, 'kev_cves': kev_list,
        'is_web': bool(http), 'http_status': http.get('status'), 'title': (http.get('title') or '')[:120] or None,
        'waf': http.get('waf'), 'hsts': 'strict-transport-security' in headers, 'csp': 'content-security-policy' in headers,
        'security_txt': bool(http.get('securitytxt')),
        'tech': list(components)[:15],
        'has_tls': bool(ssl), 'cert_expired': bool(cert.get('expired')), 'cert_expires': cert.get('expires'),
        'legacy_tls': any(v in LEGACY_TLS for v in versions), 'pqc': 'pqc' in tags,
    }
    return [dict(base, key_type=kt, company=k, generated_host=g,
                 claimed=(cert_domain == k) or (bool(web_host) and (web_host == k or web_host.endswith('.' + k))),
                 has_identity=bool(cert_domain or (web_host and not re.match(r'^[\d.:\[\]]+$', web_host))))
            for kt, k, g in keys]


S, B, I, Fl, L = T.StringType(), T.BooleanType(), T.IntegerType(), T.DoubleType(), T.ArrayType(T.StringType())
ROW_FIELDS = [
    ('key_type', S), ('company', S), ('generated_host', B), ('claimed', B), ('has_identity', B), ('anon_ftp', B),
    ('ip', S), ('port', I), ('ts', S), ('org', S), ('country', S), ('city', S), ('edge', B), ('cloud', B),
    ('product', S), ('version', S), ('exposed', L), ('unauth_data', B), ('ntlm_leak', B),
    ('compromised', B), ('eol', B), ('self_signed', B),
    ('n_cves', I), ('n_kev', I), ('n_ransomware_cves', I), ('n_high_epss', I),
    ('max_cvss', Fl), ('max_epss', Fl), ('top_cves', L), ('kev_cves', L),
    ('is_web', B), ('http_status', I), ('title', S), ('waf', S),
    ('hsts', B), ('csp', B), ('security_txt', B), ('tech', L),
    ('has_tls', B), ('cert_expired', B), ('cert_expires', S), ('legacy_tls', B), ('pqc', B),
]
ROW_TYPE = T.StructType([T.StructField(n, t) for n, t in ROW_FIELDS])
NAMES = [n for n, _ in ROW_FIELDS]


def _coerce(v, t):
    """Scan data is messy (a port as a string, a version as a number); make each value fit its column."""
    if v is None:
        return None
    try:
        if t is I: return int(v)
        if t is Fl: return float(v)
        if t is B: return bool(v)
        if t is S: return v if isinstance(v, str) else str(v)
        return [str(x) for x in v]
    except (TypeError, ValueError):
        return None


@F.udf(T.ArrayType(ROW_TYPE))
def extract_udf(line):
    try:
        rows = extract(json.loads(line))
    except (ValueError, AttributeError, TypeError):
        return []  # a malformed record is skipped, as in ingest.py
    return [tuple(_coerce(row.get(n), t) for n, t in ROW_FIELDS) for row in rows]

# COMMAND ----------

if SOURCE == "raw":
    silver = (spark.table("bronze_scan_raw")
              .select(F.explode(extract_udf("raw_json")).alias("r"))
              .select("r.*"))
else:
    # Option B: reuse the Parquet ingest.py already produced on your laptop (data/rows/*.parquet).
    # Full scale, so the back-test reproduces the published AUC. Same columns, so everything below is identical.
    # Only full runs: ingest.py also writes *-sample.parquet test files, which would double-count.
    silver = (spark.read.option("pathGlobFilter", "*[0-9].parquet").parquet(f"{VOL}/parquet")
              .select(*NAMES))

silver.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("silver_scan_rows")

# Keep only the latest scan of each service. One file already re-scans ~14% of services, and with monthly
# files an issue fixed last month must not keep counting against the company.
spark.sql("""
    CREATE OR REPLACE TABLE silver_latest AS
    SELECT * EXCEPT (rn) FROM (
        SELECT *, row_number() OVER (PARTITION BY ip, port, key_type, company ORDER BY ts DESC) AS rn
        FROM silver_scan_rows)
    WHERE rn = 1""")
display(spark.sql("""
    SELECT (SELECT count(*) FROM silver_scan_rows) AS all_rows, count(*) AS latest_rows,
           count(DISTINCT company) AS companies, count(DISTINCT ip) AS ips,
           round(avg(edge::INT), 3) AS share_cdn_edge
    FROM silver_latest"""))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Silver: learn the infrastructure from the data
# MAGIC
# MAGIC These are the data-driven attribution rules from `build.py`. None of them is a hand-made list;
# MAGIC each threshold is computed across all files, so the rules get *more* accurate as data grows.

# COMMAND ----------

INFRA_NAME_RE = (r'(host|server|vps|cloud|hosting|ptr|reverse|static|dedi|colo|datacent|broadband|dsl|cable|fiber|fibra'
                 r'|telecom|telekom|isp\b|netvigator|\.internal$|\.local$|\.lan$|\.arpa$|^test\.|^localhost)')
INFRA_NAME_SQL = INFRA_NAME_RE.replace('\\', '\\\\')  # Spark SQL string literals treat backslash as an escape

# Rule 1: an org that 10+ different companies' domains live on is a network provider (a landlord).
spark.sql("""
    CREATE OR REPLACE TABLE silver_providers AS
    SELECT org FROM silver_latest WHERE key_type = 'domain' AND NOT edge AND org IS NOT NULL
    GROUP BY org HAVING count(DISTINCT company) >= 10""")

# Flag rows that sit on a provider network once, so the rules below can use it inside aggregates.
spark.sql("""
    CREATE OR REPLACE TEMP VIEW rows_p AS
    SELECT r.*, CASE WHEN r.org IS NULL THEN NULL ELSE p.org IS NOT NULL END AS provider_org
    FROM silver_latest r LEFT JOIN silver_providers p ON r.org = p.org""")

spark.sql(f"""
    CREATE OR REPLACE TABLE silver_infra_domains AS
    SELECT DISTINCT company, rule FROM (
        -- Rule 2: machine-made hostnames spread over 3+ IPs = reverse DNS of a provider
        SELECT company, 'generated_hostnames' AS rule FROM rows_p WHERE key_type = 'domain'
        GROUP BY company HAVING count(DISTINCT ip) >= 3 AND avg(generated_host::INT) >= 0.5
        UNION ALL
        -- Rule 2a: ownership. A real company's certs/websites carry its own name; an ISP's customers' don't.
        SELECT company, 'not_claimed' FROM rows_p WHERE key_type = 'domain'
        GROUP BY company HAVING count(DISTINCT ip) >= 3 AND (
            (count(*) FILTER (WHERE has_identity) >= 3
             AND avg(claimed::INT) FILTER (WHERE has_identity) < 0.2)
            OR (NOT bool_or(claimed) AND avg(provider_org::INT) > 0.5))
        UNION ALL
        -- Rule 2c: dynamic DNS / shared web hosting platforms
        SELECT company, 'subdomain_platform' FROM rows_p WHERE key_type = 'domain'
        GROUP BY company HAVING
            (count(DISTINCT org) >= 20 AND count(DISTINCT org) / count(DISTINCT ip) >= 0.4)
            OR (count(*) >= 10 AND avg((arrays_overlap(tech, array('cPanel', 'Plesk', 'DirectAdmin', 'ISPConfig'))
                                        OR port IN (2082, 2083, 2086, 2087, 2222))::INT) >= 0.15)
        UNION ALL
        -- Rule 2b: hosting-style names, internal TLDs, and the provider's own brand (leaseweb.com on LeaseWeb)
        SELECT company, 'provider_brand_or_name' FROM rows_p WHERE key_type = 'domain'
        GROUP BY company HAVING
            company RLIKE '{INFRA_NAME_SQL}'
            OR bool_or(provider_org AND contains(lower(replace(org, ' ', '')), split_part(company, '.', 1)))
    )""")

display(spark.sql("""
    SELECT rule, count(*) AS domains_removed FROM silver_infra_domains GROUP BY rule
    UNION ALL SELECT 'network providers (orgs)', count(*) FROM silver_providers"""))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Down-weight noisy CVEs
# MAGIC A known-exploited CVE matched on 5%+ of vulnerable hosts is usually a version-banner guess, not a real finding.

# COMMAND ----------

common = [r.cve for r in spark.sql("""
    WITH hosts AS (SELECT DISTINCT ip, cve FROM silver_latest LATERAL VIEW explode(kev_cves) t AS cve
                   WHERE NOT edge AND n_cves > 0),
         total AS (SELECT count(DISTINCT ip) AS n FROM silver_latest WHERE NOT edge AND n_cves > 0)
    SELECT cve FROM hosts CROSS JOIN total GROUP BY cve, total.n HAVING count(*) >= 0.05 * total.n""").collect()]
COMMON_SQL = ("array(" + ", ".join(f"'{c}'" for c in common) + ")") if common else "CAST(array() AS ARRAY<STRING>)"
print("Common KEV CVEs (down-weighted):", common)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Gold: one explainable score per company
# MAGIC
# MAGIC `own` signals (ports, CVEs) only count on the company's own servers, never on a shared CDN edge.
# MAGIC Every `s_*` column is kept, so any score can be explained line by line to a salesperson.

# COMMAND ----------

WEIGHTS = {
    'compromised': 40, 'unauth_data': 30, 'anon_ftp': 6, 'kev': 25, 'kev_common': 6, 'ransomware_cve': 15,
    'high_epss': 10, 'remote_access': 12, 'database': 10, 'industrial': 15, 'open_dir': 8, 'ntlm_leak': 5,
    'eol': 8, 'cert_expired': 6, 'legacy_tls': 5, 'self_signed': 3, 'no_hsts': 2,
    'waf': -8, 'security_txt': -10, 'pqc': -3,
}
arr = lambda xs: "array(" + ", ".join(f"'{x}'" for x in xs) + ")"
REMOTE, DATABASES, INDUSTRIAL = ['rdp', 'smb', 'telnet', 'vnc'], ['mysql', 'mongodb', 'redis', 'elasticsearch', 'postgresql', 'mssql'], ['modbus', 'siemens_s7', 'bacnet', 'dnp3']
OWN = "CASE WHEN NOT r.edge THEN {} END"  # value only from the company's own (non-CDN) servers
OWN_OPEN_DIR = OWN.format("array_contains(r.exposed, 'open_directory')")
w = WEIGHTS

spark.sql(f"""
    CREATE OR REPLACE TEMP VIEW companies AS
    SELECT
        r.key_type, r.company,
        mode(r.org) AS network_org, mode(r.country) AS country, mode(r.city) AS city,
        count(DISTINCT r.ip) AS ips, count(*) AS services,
        max(CASE WHEN r.http_status = 200 THEN r.title END) AS web_title,
        slice(array_distinct(flatten(collect_list(r.tech))), 1, 12) AS tech,
        coalesce(bool_or({OWN.format('r.compromised')}), false) AS compromised,
        coalesce(bool_or({OWN.format('r.unauth_data')}), false) AS unauth_data,
        coalesce(bool_or({OWN.format('r.anon_ftp')}), false) AS anon_ftp,
        round(avg(CASE WHEN r.has_identity THEN r.claimed::INT END), 2) AS ownership,
        array_distinct(flatten(collect_list({OWN.format('r.kev_cves')}))) AS kev_list,
        coalesce(max({OWN.format('r.n_ransomware_cves')}), 0) AS ransomware_cves,
        count(DISTINCT CASE WHEN NOT r.edge AND r.n_high_epss > 0 THEN r.ip END) AS hosts_high_epss,
        coalesce(max({OWN.format('r.max_epss')}), 0) AS max_epss,
        coalesce(max({OWN.format('r.max_cvss')}), 0) AS max_cvss,
        slice(array_distinct(flatten(collect_list({OWN.format('r.top_cves')}))), 1, 5) AS top_cves,
        array_distinct(flatten(collect_list({OWN.format('r.exposed')}))) AS exposed_services,
        count(DISTINCT CASE WHEN NOT r.edge AND arrays_overlap(r.exposed, {arr(REMOTE)}) THEN r.ip END) AS hosts_remote_access,
        count(DISTINCT CASE WHEN NOT r.edge AND arrays_overlap(r.exposed, {arr(DATABASES)}) THEN r.ip END) AS hosts_database,
        count(DISTINCT CASE WHEN NOT r.edge AND arrays_overlap(r.exposed, {arr(INDUSTRIAL)}) THEN r.ip END) AS hosts_industrial,
        coalesce(bool_or({OWN_OPEN_DIR}), false) AS open_dir,
        coalesce(bool_or({OWN.format('r.ntlm_leak')}), false) AS ntlm_leak,
        count(DISTINCT CASE WHEN NOT r.edge AND r.eol THEN r.ip END) AS hosts_eol,
        bool_or(r.cert_expired) AS cert_expired, bool_or(r.legacy_tls) AS legacy_tls,
        bool_or(r.self_signed) AS self_signed, bool_or(r.is_web) AS has_web,
        bool_or(r.is_web) AND NOT bool_or(r.hsts) AS no_hsts,
        max(r.waf) AS waf, bool_or(r.security_txt) AS security_txt, bool_or(r.pqc) AS pqc,
        bool_and(r.edge) AS cdn_only, max(r.ts) AS last_seen
    FROM silver_latest r
    LEFT ANTI JOIN silver_infra_domains i ON r.key_type = 'domain' AND r.company = i.company
    LEFT ANTI JOIN silver_providers p ON r.key_type = 'org' AND r.company = p.org
    GROUP BY r.key_type, r.company""")

SIGNALS = {
    's_compromised': f"{w['compromised']} * compromised::INT",
    's_unauth_data': f"{w['unauth_data']} * unauth_data::INT",
    's_anon_ftp': f"{w['anon_ftp']} * anon_ftp::INT",
    's_kev': f"CASE WHEN kev_cves > 0 THEN {w['kev']} WHEN size(kev_list) > 0 THEN {w['kev_common']} ELSE 0 END",
    's_ransomware': f"{w['ransomware_cve']} * (ransomware_cves > 0)::INT",
    's_high_epss': f"{w['high_epss']} * least(hosts_high_epss, 3)",
    's_remote': f"{w['remote_access']} * least(hosts_remote_access, 3)",
    's_database': f"{w['database']} * least(hosts_database, 3)",
    's_industrial': f"{w['industrial']} * least(hosts_industrial, 2)",
    's_open_dir': f"{w['open_dir']} * open_dir::INT",
    's_ntlm': f"{w['ntlm_leak']} * ntlm_leak::INT",
    's_eol': f"{w['eol']} * least(hosts_eol, 3)",
    's_cert': f"{w['cert_expired']} * coalesce(cert_expired, false)::INT",
    's_legacy_tls': f"{w['legacy_tls']} * coalesce(legacy_tls, false)::INT",
    's_self_signed': f"{w['self_signed']} * coalesce(self_signed, false)::INT",
    's_no_hsts': f"{w['no_hsts']} * coalesce(no_hsts, false)::INT",
    's_waf': f"{w['waf']} * (waf IS NOT NULL)::INT",
    's_security_txt': f"{w['security_txt']} * coalesce(security_txt, false)::INT",
    's_pqc': f"{w['pqc']} * coalesce(pqc, false)::INT",
}
spark.sql(f"""
    CREATE OR REPLACE TABLE gold_companies AS
    SELECT *, {' + '.join(SIGNALS)} AS risk_score,
        CASE WHEN compromised OR unauth_data THEN 'Breached / data exposed'
             WHEN kev_cves > 0 THEN 'Actively exploited CVE'
             WHEN hosts_remote_access + hosts_database + hosts_industrial > 0 THEN 'Exposed critical service'
             WHEN hosts_high_epss > 0 OR hosts_eol > 0 THEN 'Vulnerable software'
             WHEN cert_expired OR legacy_tls OR self_signed THEN 'Poor hygiene'
             ELSE 'Low signal' END AS tier
    FROM (
        SELECT *, {', '.join(f'{v} AS {k}' for k, v in SIGNALS.items())}
        FROM (SELECT *, size(filter(kev_list, x -> NOT array_contains({COMMON_SQL}, x))) AS kev_cves FROM companies)
    )""")

# What sales sees: only domain-identified companies (an org-only entry has nobody to call).
spark.sql("""CREATE OR REPLACE VIEW gold_prospects AS
             SELECT * FROM gold_companies WHERE key_type = 'domain' AND risk_score > 0""")
display(spark.sql("SELECT tier, count(*) AS companies FROM gold_prospects GROUP BY tier ORDER BY companies DESC"))
display(spark.sql("""SELECT company, country, ips, risk_score, tier, exposed_services, top_cves
                     FROM gold_prospects ORDER BY risk_score DESC LIMIT 25"""))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Evaluate: back-test against real breaches, log to MLflow
# MAGIC
# MAGIC Label = server tagged `compromised` or with a database open to anyone. The score **excludes** those signals,
# MAGIC otherwise the model would be graded on the answer key (data leakage).
# MAGIC
# MAGIC **On a small raw sample there will be very few breached servers**, so the AUC will be noisy or missing.
# MAGIC Use `source = parquet` with your full `data/rows` output to reproduce the published 0.80.

# COMMAND ----------

EVAL_W = {'kev': 25, 'high_epss': 10, 'remote': 12, 'eol': 8, 'cert_expired': 6, 'legacy_tls': 5,
          'self_signed': 3, 'anon_ftp': 6, 'ntlm': 5, 'waf': -8, 'security_txt': -10}
spark.sql(f"""
    CREATE OR REPLACE TABLE gold_eval_hosts AS
    SELECT ip,
        bool_or(compromised OR unauth_data) AS breached,
        bool_or(n_kev > 0) AS kev, bool_or(n_high_epss > 0) AS high_epss,
        bool_or(arrays_overlap(exposed, {arr(REMOTE)})) AS remote,
        bool_or(eol) AS eol, bool_or(cert_expired) AS cert_expired, bool_or(legacy_tls) AS legacy_tls,
        bool_or(self_signed) AS self_signed, bool_or(anon_ftp) AS anon_ftp, bool_or(ntlm_leak) AS ntlm,
        bool_or(waf IS NOT NULL) AS waf, bool_or(security_txt) AS security_txt
    FROM (SELECT *, row_number() OVER (PARTITION BY ip, port ORDER BY ts DESC) AS rn
          FROM silver_latest WHERE NOT edge)
    WHERE rn = 1 GROUP BY ip""")
hosts = spark.sql(f"""SELECT *, {' + '.join(f'{v} * coalesce({k}, false)::INT' for k, v in EVAL_W.items())} AS score
                      FROM gold_eval_hosts""")
hosts.createOrReplaceTempView("hosts")

n_pos, n_neg = spark.sql("SELECT count_if(breached), count_if(NOT breached) FROM hosts").first()
print(f"breached servers: {n_pos:,} of {n_pos + n_neg:,}")

auc = top_lift = None
if n_pos and n_neg:
    # AUC with the rank-sum formula. Tied scores share their average rank (the bug fixed in DEVLOG round 5).
    auc = spark.sql("""
        WITH r AS (SELECT breached, rank() OVER (ORDER BY score) + (count(*) OVER (PARTITION BY score) - 1) / 2.0 AS rk FROM hosts)
        SELECT (sum(rk) FILTER (WHERE breached) - count_if(breached) * (count_if(breached) + 1) / 2.0)
               / (count_if(breached) * count_if(NOT breached)) FROM r""").first()[0]
    top_lift = spark.sql("""
        SELECT avg(breached::INT) FILTER (WHERE rn <= 10000) / avg(breached::INT)
        FROM (SELECT breached, row_number() OVER (ORDER BY score DESC) AS rn FROM hosts)""").first()[0]
    # Cross-check with scikit-learn: never trust one implementation of a metric.
    try:
        from sklearn.metrics import roc_auc_score
        pdf = hosts.select("breached", "score").toPandas()
        print(f"AUC (SQL) = {auc:.3f}   AUC (sklearn) = {roc_auc_score(pdf.breached, pdf.score):.3f}   top-10k lift = {top_lift:.1f}x")
    except ImportError:
        print(f"AUC (SQL) = {auc:.3f}   top-10k lift = {top_lift:.1f}x   (scikit-learn not installed: cross-check skipped)")
    if n_pos < 30:
        print("Warning: fewer than 30 breached servers, so treat this AUC as directional only.")

lift = spark.sql(" UNION ALL ".join(
    f"SELECT '{s}' AS signal, count_if({s}) AS hosts, try_divide(avg(breached::INT) FILTER (WHERE {s}), avg(breached::INT)) AS lift FROM hosts"
    for s in EVAL_W) + " ORDER BY lift DESC NULLS LAST")
display(lift)

# COMMAND ----------

import mlflow

user = spark.sql("SELECT current_user()").first()[0]
mlflow.set_experiment(f"/Users/{user}/cyber-prospecting")
with mlflow.start_run(run_name=f"hand-weights-{SOURCE}"):
    mlflow.log_params({f"w_{k}": v for k, v in WEIGHTS.items()})
    mlflow.log_params({"source": SOURCE, "common_kev_cves": len(common)})
    mlflow.log_metrics({"breached_hosts": n_pos, "hosts": n_pos + n_neg,
                        "prospects": spark.table("gold_prospects").count()})
    if auc is not None:
        mlflow.log_metrics({"auc": auc, "top10k_lift": top_lift})
    mlflow.log_table(lift.toPandas(), artifact_file="signal_lift.json")
print("Logged. Open Experiments in the left sidebar to compare runs (e.g. hand weights vs learned weights).")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8. AI step: is this a real organisation or a hosting/ISP business?
# MAGIC
# MAGIC The rules still leave some hosting companies in the top list. `llm_classify.py` asked Claude through the API;
# MAGIC here the same prompt runs **inside SQL** with `ai_query`, over the top 50 prospects in one query.
# MAGIC `responseFormat` forces a fixed schema, so there's no free text to parse.
# MAGIC
# MAGIC Check the endpoint name under **Serving** in the sidebar and set the `llm_endpoint` widget to match.
# MAGIC This step uses pay-per-token Foundation Model APIs (a few cents for 50 rows); skip it if your workspace has none.

# COMMAND ----------

if not RUN_LLM:
    # Everything below is the optional AI step; the scored Gold tables above are complete without it.
    dbutils.notebook.exit("Done (AI step skipped: set run_llm = true to classify hosting vs real organisations)")

SYSTEM = """You classify internet domains for a cybersecurity sales team.
Decide whether the domain belongs to an END ORGANISATION that runs its own systems (a company, university,
government body, hospital, non-profit), or to a HOSTING / ISP business whose servers mostly belong to its
customers (web hosts, VPS/cloud providers, ISPs, telecoms, dynamic-DNS services, domain parking).
A hosting company's own corporate site still counts as hosting_or_isp.
Use only the evidence given. If the evidence is too thin to tell, answer "unsure".
Answer with label (end_organisation, hosting_or_isp or unsure), confidence (high, medium or low) and a one-sentence reason."""

VERDICT_DDL = "label STRING, confidence STRING, reason STRING"
RESPONSE_FORMAT = "STRUCT<label: STRING, confidence: STRING, reason: STRING>"
raw = spark.sql(f"""
    SELECT company, risk_score,
        ai_query('{LLM_ENDPOINT}',
            concat(:system, '\\n\\nDomain: ', company,
                   '\\nNetwork owner of most of its IPs: ', coalesce(network_org, '(unknown)'),
                   '\\nCountry: ', coalesce(country, '(unknown)'),
                   '\\nInternet-facing IPs seen: ', ips,
                   '\\nA website title on its servers: ', coalesce(web_title, '(none)'),
                   '\\nWeb technologies seen: ', coalesce(nullif(array_join(tech, ', '), ''), '(none)')),
            responseFormat => '{RESPONSE_FORMAT}') AS verdict
    FROM (SELECT * FROM gold_prospects ORDER BY risk_score DESC LIMIT 50)""",
    args={"system": SYSTEM})
# Depending on runtime version the structured answer comes back as JSON text or as a struct; handle both.
if isinstance(raw.schema["verdict"].dataType, T.StringType):
    raw = raw.withColumn("verdict", F.from_json("verdict", VERDICT_DDL))
raw.select("company", "risk_score", "verdict.*").write.mode("overwrite").saveAsTable("gold_llm_hosting_labels")
display(spark.sql("SELECT label, count(*) AS n FROM gold_llm_hosting_labels GROUP BY label"))
display(spark.table("gold_llm_hosting_labels"))

# COMMAND ----------

# MAGIC %md
# MAGIC ### Does it agree with your earlier Claude labels?
# MAGIC Upload `eval/llm_labels.csv` (Claude's answers) and `eval/reference_labels.csv` (homepage-based labels)
# MAGIC from the repo into `landing/labels`. Agreement between two models is not accuracy, but disagreements are
# MAGIC exactly the rows worth a human look.

# COMMAND ----------

import os
for name, col in [("llm_labels.csv", "label"), ("reference_labels.csv", "human_label")]:
    path = f"{VOL}/labels/{name}"
    if not os.path.exists(f"{VOL_LOCAL}/labels/{name}"):
        print(f"skip: {name} not uploaded")
        continue
    ref = spark.read.option("header", True).csv(path).select("company", F.col(col).alias("other_label"))
    m = spark.table("gold_llm_hosting_labels").join(ref, "company").where("label != 'unsure' AND other_label != 'unsure'")
    n = m.count()
    if n:
        agree = m.where("label = other_label").count() / n
        print(f"{name}: {n} overlapping domains, agreement {agree:.0%}")
        display(m.groupBy("label").pivot("other_label").count())  # confusion matrix
    else:
        print(f"{name}: no overlapping decided domains")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Version the prompt (MLflow prompt registry)
# MAGIC Prompts change like code. Registering each version means a regression can be traced to the exact prompt
# MAGIC that caused it, which is the same idea as the LLM regression-detection project.

# COMMAND ----------

try:
    p = mlflow.genai.register_prompt(
        name=f"{CATALOG}.{SCHEMA}.hosting_classifier",
        template=SYSTEM + "\n\n{{evidence}}",
        commit_message="v1: ported from llm_classify.py")
    print(f"Registered {p.name} version {p.version}")
except Exception as e:  # registry availability varies by workspace and MLflow version
    print(f"Prompt registry not available here ({type(e).__name__}: {e}). The prompt is still in this notebook.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 9. How to talk about this in the interview
# MAGIC
# MAGIC - **Bronze keeps raw text**: parsing bugs are fixed by rebuilding Silver, never by re-scraping.
# MAGIC - **Auto Loader + checkpoint** = incremental: new monthly files are picked up, old ones skipped.
# MAGIC - **Rules are learned from the data** (`silver_providers`, `silver_infra_domains`) and improve with volume.
# MAGIC - **Gold is explainable**: every `s_*` column is a reason a salesperson can read.
# MAGIC - **Evaluation before trust**: back-test excludes the label signals (no leakage), metric cross-checked
# MAGIC   with sklearn, results tracked in MLflow so weight changes can be compared run by run.
# MAGIC - **LLM only where rules run out** (hosting vs real org), structured output, measured against labels,
# MAGIC   prompt versioned. Scoring itself stays deterministic: no per-row cost, nothing to hallucinate.
# MAGIC - **Production next steps**: schedule as a Databricks Job (bronze → silver → gold tasks), Unity Catalog
# MAGIC   grants on `gold_prospects` for the sales app, and Lakehouse Monitoring on score drift month to month.
