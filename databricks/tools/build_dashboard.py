"""Generate the AI/BI (Lakeview) dashboard definition from readable Python.

    python databricks/tools/build_dashboard.py   ->  databricks/src/cyber_prospecting.lvdash.json

Then `databricks bundle deploy` publishes it. Keeping the design here (not hand-edited JSON) means every
query, chart and layout choice is reviewable in a diff.
"""
import json, os

# Must match the bundle's catalog/schema variables (the dashboard JSON has no variable substitution).
T = f"{os.environ.get('CYBER_CATALOG', 'databricks_demo_ws')}.{os.environ.get('CYBER_SCHEMA', 'cyber')}"
OUT = os.path.join(os.path.dirname(__file__), '..', 'src', 'cyber_prospecting.lvdash.json')

# Brand: the same teal as the Streamlit app, one warm accent for "breached".
TEAL, AMBER, RED, SLATE = '#0B6E8A', '#C47F17', '#B3261E', '#56636F'

SIGNALS = [  # score column -> what a salesperson would call it
    ('s_compromised', 'Already compromised'), ('s_unauth_data', 'Data open without password'),
    ('s_kev', 'Known-exploited CVE'), ('s_ransomware', 'Ransomware-linked CVE'),
    ('s_high_epss', 'Likely-exploited CVE (EPSS)'), ('s_remote', 'Remote access exposed'),
    ('s_database', 'Database exposed'), ('s_industrial', 'Industrial control exposed'),
    ('s_open_dir', 'Open directory'), ('s_ntlm', 'Leaks internal names'), ('s_eol', 'End-of-life software'),
    ('s_cert', 'Expired certificate'), ('s_legacy_tls', 'Old TLS versions'), ('s_self_signed', 'Self-signed certs'),
    ('s_no_hsts', 'No HSTS'),
]
EVAL_W = {'kev': 25, 'high_epss': 10, 'remote': 12, 'eol': 8, 'cert_expired': 6, 'legacy_tls': 5,
          'self_signed': 3, 'anon_ftp': 6, 'ntlm': 5, 'waf': -8, 'security_txt': -10}
EVAL_NAMES = {'kev': 'Known-exploited CVE', 'high_epss': 'Likely-exploited CVE', 'remote': 'Remote access exposed',
              'eol': 'End-of-life software', 'cert_expired': 'Expired certificate', 'legacy_tls': 'Old TLS versions',
              'self_signed': 'Self-signed certs', 'anon_ftp': 'Anonymous FTP', 'ntlm': 'Leaks internal names',
              'waf': 'Behind a WAF', 'security_txt': 'Publishes security.txt'}

top_reason = ('CASE greatest(' + ', '.join(c for c, _ in SIGNALS) + ') '
              + ' '.join(f"WHEN {c} THEN '{n}'" for c, n in SIGNALS) + ' END')
sector = ("CASE WHEN company RLIKE '\\\\.edu|\\\\.ac\\\\.|univ|school|college' THEN 'Education' "
          "WHEN company RLIKE '\\\\.gov|\\\\.gob\\\\.|\\\\.go\\\\.|\\\\.mil' THEN 'Government' "
          "WHEN company RLIKE 'health|hospital|clinic|medic|pharma' THEN 'Healthcare' "
          "WHEN company RLIKE 'bank|financ|insur|invest|credit' THEN 'Finance' ELSE 'Business' END")
business_type = ("CASE h.ai_business_type WHEN 'end_organisation' THEN 'Real organisation' "
                 "WHEN 'hosting_or_isp' THEN 'Hosting / ISP' ELSE 'Not sure' END")
eval_score = ' + '.join(f'{v} * coalesce({k}, false)::INT' for k, v in EVAL_W.items())

DATASETS = {
    'prospects': ('Prospects', f"""
        SELECT company, tier, risk_score AS score, {sector} AS sector, country, ips, network_org,
               {top_reason} AS top_reason,
               array_join(exposed_services, ', ') AS exposed_services,
               array_join(slice(kev_list, 1, 3), ', ') AS known_exploited_cves,
               {business_type} AS business_type
        FROM {T}.gold_prospects LEFT JOIN {T}.gold_hosting_predictions h USING (company)
        WHERE tier <> 'Low signal'"""),
    'kpis': ('Headline counts', f"""
        SELECT count(*) AS accounts,
               count_if(tier = 'Breached / data exposed') AS breached,
               count_if(tier = 'Actively exploited CVE') AS exploited,
               count_if(tier = 'Exposed critical service') AS exposed
        FROM {T}.gold_prospects WHERE tier <> 'Low signal'"""),
    'tiers': ('Accounts by tier', f"""
        SELECT tier, count(*) AS companies FROM {T}.gold_prospects GROUP BY tier"""),
    'countries': ('Top countries', f"""
        SELECT country, count(*) AS companies FROM {T}.gold_prospects
        WHERE tier <> 'Low signal' AND country IS NOT NULL GROUP BY country ORDER BY companies DESC LIMIT 15"""),
    'signals': ('Companies per signal', ' UNION ALL '.join(
        f"SELECT '{n}' AS signal, count_if({c} > 0) AS companies FROM {T}.gold_prospects" for c, n in SIGNALS)),
    'services': ('Exposed services', f"""
        SELECT service, count(*) AS companies
        FROM {T}.gold_prospects LATERAL VIEW explode(exposed_services) s AS service
        GROUP BY service ORDER BY companies DESC LIMIT 12"""),
    'cves': ('Known-exploited CVEs', f"""
        SELECT cve, count(*) AS companies
        FROM {T}.gold_prospects LATERAL VIEW explode(kev_list) c AS cve
        GROUP BY cve ORDER BY companies DESC LIMIT 15"""),
    'quality': ('Back-test', f"""
        WITH h AS (SELECT breached, {eval_score} AS score FROM {T}.gold_eval_hosts),
             r AS (SELECT breached, rank() OVER (ORDER BY score) + (count(*) OVER (PARTITION BY score) - 1) / 2.0 AS rk FROM h)
        SELECT round(try_divide(sum(rk) FILTER (WHERE breached) - count_if(breached) * (count_if(breached) + 1) / 2.0,
                                count_if(breached) * count_if(NOT breached)), 3) AS auc,
               count_if(breached) AS breached_servers, count(*) AS servers
        FROM r"""),
    'lift': ('Lift per signal', ' UNION ALL '.join(
        f"SELECT '{EVAL_NAMES[k]}' AS signal, round(try_divide(avg(breached::INT) FILTER (WHERE {k}), avg(breached::INT)), 2) AS lift "
        f"FROM {T}.gold_eval_hosts" for k in EVAL_W)),
    'removed': ('Infrastructure removed', f"""
        SELECT CASE rule WHEN 'generated_hostnames' THEN 'Reverse-DNS domains'
                         WHEN 'not_claimed' THEN 'Failed ownership check'
                         WHEN 'subdomain_platform' THEN 'Dynamic DNS / shared hosting'
                         ELSE 'Provider brand or name' END AS reason, count(*) AS domains
        FROM {T}.silver_infra_domains GROUP BY rule
        UNION ALL SELECT 'Network providers (orgs)', count(*) FROM {T}.silver_providers"""),
    'ai_eval': ('AI: student vs teacher', f"""
        SELECT CASE WHEN model LIKE 'student%' THEN 'Small model (free)' ELSE 'Claude (paid once)' END AS model,
               answered_pct, accuracy_where_both_decided_pct AS accuracy_pct,
               concat(hosting_caught, ' / ', hosting_total) AS hosting_caught, domains
        FROM {T}.gold_hosting_eval"""),
    'ai_kpis': ('AI: headline', f"""
        SELECT max(accuracy_where_both_decided_pct) FILTER (WHERE model LIKE 'student%') AS student_accuracy,
               max(accuracy_where_both_decided_pct) FILTER (WHERE model LIKE 'teacher%') AS teacher_accuracy,
               (SELECT count_if(ai_business_type <> 'unsure') FROM {T}.gold_prospects
                JOIN {T}.gold_hosting_predictions USING (company)) AS prospects_classified
        FROM {T}.gold_hosting_eval"""),
    'ai_mix': ('AI: business type of prospects', f"""
        SELECT {business_type} AS business_type, count(*) AS prospects
        FROM {T}.gold_prospects LEFT JOIN {T}.gold_hosting_predictions h USING (company)
        WHERE h.ai_business_type <> 'unsure' GROUP BY 1"""),
}


def q(dataset, *fields, agg=False):
    return [{'name': 'main_query', 'query': {
        'datasetName': dataset, 'disaggregated': not agg,
        'fields': [{'name': f, 'expression': f'`{f}`'} for f in fields]}}]


def frame(title, desc=None):
    f = {'showTitle': True, 'title': title}
    if desc:
        f.update(showDescription=True, description=desc)
    return f


def text(name, md, x, y, w, h):
    return {'widget': {'name': name, 'multilineTextboxSpec': {'lines': md.strip().splitlines()}},
            'position': {'x': x, 'y': y, 'width': w, 'height': h}}


def counter(name, dataset, field, title, x, y, w=1, h=2):
    return {'widget': {'name': name, 'queries': q(dataset, field),
                       'spec': {'version': 2, 'widgetType': 'counter',
                                'encodings': {'value': {'fieldName': field, 'displayName': title}},
                                'frame': frame(title)}},
            'position': {'x': x, 'y': y, 'width': w, 'height': h}}


def hbar(name, dataset, cat, val, title, x, y, w, h, color=TEAL, desc=None):
    return {'widget': {'name': name, 'queries': q(dataset, cat, val),
                       'spec': {'version': 3, 'widgetType': 'bar',
                                'encodings': {
                                    'x': {'fieldName': val, 'scale': {'type': 'quantitative'}, 'displayName': val.replace('_', ' ').capitalize()},
                                    'y': {'fieldName': cat, 'scale': {'type': 'categorical', 'sort': {'by': 'x-reversed'}},
                                          'displayName': cat.replace('_', ' ').capitalize()},
                                    'label': {'show': True}},
                                'mark': {'colors': [color]},
                                'frame': frame(title, desc)}},
            'position': {'x': x, 'y': y, 'width': w, 'height': h}}


def table(name, dataset, cols, title, x, y, w, h, desc=None):
    return {'widget': {'name': name, 'queries': q(dataset, *[c for c, _ in cols]),
                       'spec': {'version': 1, 'widgetType': 'table',
                                'encodings': {'columns': [{'fieldName': c, 'title': t, 'displayName': t} for c, t in cols]},
                                'frame': frame(title, desc)}},
            'position': {'x': x, 'y': y, 'width': w, 'height': h}}


def multi_filter(name, dataset, field, title, x, y, w=2, h=1):
    return {'widget': {'name': name,
                       'queries': [{'name': f'{name}_q', 'query': {'datasetName': dataset, 'disaggregated': False,
                                                                     'fields': [{'name': field, 'expression': f'`{field}`'}]}}],
                       'spec': {'version': 2, 'widgetType': 'filter-multi-select',
                                'encodings': {'fields': [{'fieldName': field, 'displayName': title, 'queryName': f'{name}_q'}]},
                                'frame': frame(title)}},
            'position': {'x': x, 'y': y, 'width': w, 'height': h}}


prospects_page = [
    text('intro', """
## Cyber Prospecting
Companies ranked by how urgently their internet-facing systems need security help, from **14.6M internet-scan records**.
Every score is the sum of named signals, so each account comes with its reason to call. IPs are never shown.
""", 0, 0, 6, 2),
    counter('k_accounts', 'kpis', 'accounts', 'Accounts worth a call', 0, 2, 2),
    counter('k_breached', 'kpis', 'breached', 'Breached / data exposed', 2, 2, 1),
    counter('k_exploited', 'kpis', 'exploited', 'Actively exploited CVE', 3, 2, 2),
    counter('k_exposed', 'kpis', 'exposed', 'Exposed critical service', 5, 2, 1),
    hbar('b_tiers', 'tiers', 'tier', 'companies', 'Why now: accounts by tier', 0, 4, 3, 5,
         desc='Tier = the single strongest reason. Breached beats exploited beats exposed.'),
    hbar('b_countries', 'countries', 'country', 'companies', 'Top countries', 3, 4, 3, 5, color=SLATE),
    multi_filter('f_tier', 'prospects', 'tier', 'Why now', 0, 9),
    multi_filter('f_sector', 'prospects', 'sector', 'Sector', 2, 9),
    multi_filter('f_country', 'prospects', 'country', 'Country', 4, 9),
    multi_filter('f_business', 'prospects', 'business_type', 'Business type (AI)', 0, 10),
    text('f_business_note', """
**Business type (AI)**: a small model's guess at whether the domain is a real organisation or a hosting/ISP business
(whose servers belong to its customers). It answers only for domains with 6+ servers. See the *AI classifier* page.
""", 2, 10, 4, 1),
    table('t_prospects', 'prospects', [
        ('company', 'Company'), ('score', 'Score'), ('tier', 'Why now'), ('top_reason', 'Top reason'),
        ('business_type', 'Business type (AI)'), ('sector', 'Sector'), ('country', 'Country'), ('ips', 'IPs'),
        ('exposed_services', 'Exposed services'), ('known_exploited_cves', 'Known-exploited CVEs'),
        ('network_org', 'Network owner')],
        'Accounts to call first', 0, 11, 6, 10, desc='Sorted by score; filter above. Click a column to re-sort.'),
]

ai_page = [
    text('ai_intro', """
## AI classifier: is this a real organisation, or a hosting company?
Hosting companies and ISPs score high because their *customers'* servers are insecure, but they are not the buyer.
**Teacher:** Claude labelled 500 top domains once. **Student:** a small model learned that judgement from facts in the
data, and now runs on every refresh at no AI cost. Both are graded on **90 labels from each domain's About/Contact page**,
which the student never trained on.
""", 0, 0, 6, 3),
    counter('k_student', 'ai_kpis', 'student_accuracy', 'Small model: % correct (free)', 0, 3, 2),
    counter('k_teacher', 'ai_kpis', 'teacher_accuracy', 'Claude: % correct (paid once)', 2, 3, 2),
    counter('k_classified', 'ai_kpis', 'prospects_classified', 'Prospects classified by the small model', 4, 3, 2),
    table('t_ai_eval', 'ai_eval', [
        ('model', 'Model'), ('answered_pct', 'Answers given (%)'), ('accuracy_pct', 'Correct when it answers (%)'),
        ('hosting_caught', 'Hosting companies caught'), ('domains', 'Held-out domains')],
        'Graded on the same held-out domains', 0, 5, 4, 3,
        desc='"Not sure" answers are not counted as wrong; "Answers given" shows how often each one commits.'),
    hbar('b_ai_mix', 'ai_mix', 'business_type', 'prospects', 'What the small model says about prospects', 4, 5, 2, 3,
         color=SLATE),
    text('ai_limits', """
**Limits, stated plainly.** Claude is clearly better: more often correct, and it answers far more often. The small model only
answers for domains with 6+ servers, because it learned from top prospects (median 10 servers). On one-server sites it
was guessing, so they are left as *Not sure*. Covering them would need labels for small domains.
""", 0, 8, 6, 2),
]

signals_page = [
    text('sig_intro', """
## What the signals say
Counts of prospects showing each signal. Urgent signals (breached, exploited) score most; hygiene signals score least.
""", 0, 0, 6, 1),
    hbar('b_signals', 'signals', 'signal', 'companies', 'Companies per signal', 0, 1, 3, 8),
    hbar('b_services', 'services', 'service', 'companies', 'Services exposed to the internet', 3, 1, 3, 8, color=AMBER,
         desc='Counted only when the protocol actually answered, never from the probe name.'),
    hbar('b_cves', 'cves', 'cve', 'companies', 'Most common known-exploited CVEs', 0, 9, 6, 7, color=RED,
         desc='CVEs on 5%+ of vulnerable hosts are mostly version-number false matches and are down-weighted in the score.'),
]

quality_page = [
    text('q_intro', """
## Does the score work?
Back-test: every server is scored **without** the breach signals, then we check whether servers that were actually
breached (compromised tag or open database) rank higher. AUC 0.5 = random, 1.0 = perfect.
""", 0, 0, 6, 2),
    counter('k_auc', 'quality', 'auc', 'AUC (back-test)', 0, 2, 2),
    counter('k_breached_servers', 'quality', 'breached_servers', 'Breached servers (labels)', 2, 2, 2),
    counter('k_servers', 'quality', 'servers', 'Servers scored', 4, 2, 2),
    hbar('b_lift', 'lift', 'signal', 'lift', 'How much more often servers with each signal were breached', 0, 4, 3, 7,
         desc='1.0 = no effect. Only ~56 labelled breaches, so read as direction, not precision.'),
    hbar('b_removed', 'removed', 'reason', 'domains', 'Infrastructure removed before scoring', 3, 4, 3, 7, color=SLATE,
         desc='Rules learned from the data, not a blocklist: they get more accurate as more files arrive.'),
]

dashboard = {
    'datasets': [{'name': k, 'displayName': d, 'queryLines': [' '.join(sql.split())]} for k, (d, sql) in DATASETS.items()],
    'pages': [
        {'name': 'prospects', 'displayName': 'Prospects', 'layout': prospects_page},
        {'name': 'signals', 'displayName': 'Signals', 'layout': signals_page},
        {'name': 'quality', 'displayName': 'Does it work', 'layout': quality_page},
        {'name': 'ai', 'displayName': 'AI classifier', 'layout': ai_page},
    ],
}
with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(dashboard, f, indent=1)
print(f'wrote {os.path.normpath(OUT)}: {len(DATASETS)} datasets, '
      f'{sum(len(p["layout"]) for p in dashboard["pages"])} widgets on {len(dashboard["pages"])} pages')
