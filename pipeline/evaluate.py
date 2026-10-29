"""Measure whether the ranking works. Reads app/data/companies.parquet and writes eval/report.md.

1. Back-test: companies already breached (compromised tag or open database) are the closest thing
   to ground truth in the data. Score everyone WITHOUT those two signals and check the breached
   companies still rank high (AUC: 0.5 = random, 1.0 = perfect).
2. Per-signal lift: how much more likely a company with each signal is to be breached.
3. Spot-check lists (top 25 and a random 25) for a human to label as real prospect or not.
"""
import os
import duckdb

ROOT = os.path.join(os.path.dirname(__file__), '..')
DATA = os.path.join(ROOT, 'app', 'data', 'companies.parquet').replace('\\', '/')
OUT = os.path.join(ROOT, 'eval', 'report.md')

ROWS = os.path.join(ROOT, 'data', 'rows', '*[0-9].parquet').replace('\\', '/')
con = duckdb.connect()
con.execute(f"CREATE VIEW c AS SELECT * FROM '{DATA}'")

# Back-test per server (IP), not per company: open databases mostly sit on anonymous cloud IPs,
# so there are far more labelled examples at host level. Label = compromised or open database.
# Predictors exclude anything that is part of the label (database exposure itself).
con.execute(f"""
    CREATE TABLE hosts AS SELECT ip,
        bool_or(compromised OR unauth_data) AS breached,
        bool_or(n_kev > 0) AS kev, bool_or(n_high_epss > 0) AS high_epss,
        bool_or(len(list_intersect(exposed, ['rdp', 'smb', 'telnet', 'vnc'])) > 0) AS remote,
        bool_or(eol) AS eol, bool_or(cert_expired) AS cert_expired, bool_or(legacy_tls) AS legacy_tls,
        bool_or(self_signed) AS self_signed, bool_or(anon_ftp) AS anon_ftp, bool_or(ntlm_leak) AS ntlm,
        bool_or(waf IS NOT NULL) AS waf, bool_or(security_txt) AS security_txt
    FROM (SELECT DISTINCT ON (ip, port) * FROM '{ROWS}' WHERE NOT edge) GROUP BY ip""")
w = {'kev': 25, 'high_epss': 10, 'remote': 12, 'eol': 8, 'cert_expired': 6, 'legacy_tls': 5,
     'self_signed': 3, 'anon_ftp': 6, 'ntlm': 5, 'waf': -8, 'security_txt': -10}  # same weights as build.py
con.execute(f"ALTER TABLE hosts ADD COLUMN score INT; UPDATE hosts SET score = {' + '.join(f'{v} * {k}::INT' for k, v in w.items())}")

# AUC via the rank-sum (Mann-Whitney) formula, computed in SQL.
auc, n_pos, n_neg = con.execute("""
    WITH r AS (SELECT breached, rank() OVER (ORDER BY score) AS rk FROM hosts)
    SELECT (sum(rk) FILTER (WHERE breached) - count(*) FILTER (WHERE breached) * (count(*) FILTER (WHERE breached) + 1) / 2.0)
           / (count(*) FILTER (WHERE breached) * count(*) FILTER (WHERE NOT breached)),
           count(*) FILTER (WHERE breached), count(*) FILTER (WHERE NOT breached) FROM r""").fetchone()
top_share = con.execute("""
    SELECT avg(breached::INT) FILTER (WHERE rn <= 10000) / avg(breached::INT)
    FROM (SELECT breached, row_number() OVER (ORDER BY score DESC) rn FROM hosts)""").fetchone()[0]

lift = con.execute(' UNION ALL '.join(
    f"SELECT '{s}' signal, count(*) FILTER (WHERE {s}) hosts, "
    f"avg(breached::INT) FILTER (WHERE {s}) / avg(breached::INT) lift FROM hosts" for s in w)
    + ' ORDER BY lift DESC').df()

cols = 'company, tier, risk_score, country, ips, ownership, network_org, web_title'
top = con.execute(f"SELECT {cols} FROM c ORDER BY risk_score DESC LIMIT 25").df()
rand = con.execute(f"SELECT {cols} FROM c USING SAMPLE 25 ROWS (reservoir, 42)").df()
tiers = con.execute("SELECT tier, count(*) n FROM c GROUP BY 1 ORDER BY 2 DESC").df()

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, 'w', encoding='utf-8') as f:
    f.write('# Evaluation report\n\n')
    f.write(f'## Back-test: do the warning signs find servers that were actually breached?\n\n'
            f'- Breached servers (compromised tag or open database): {n_pos:,} of {n_pos + n_neg:,}\n'
            f'- AUC of the score without breach signals: **{auc:.3f}** (0.5 = random, 1.0 = perfect)\n'
            f'- Breached servers are **{top_share:.1f}x** over-represented in the 10,000 highest-scoring servers\n\n')
    f.write('## Lift: how much more often servers with each signal are breached (1.0 = no effect)\n\n' + lift.to_markdown(index=False, floatfmt='.2f') + '\n\n')
    f.write('## Accounts per tier\n\n' + tiers.to_markdown(index=False) + '\n\n')
    f.write('## Spot check: top 25\n\n' + top.to_markdown(index=False) + '\n\n')
    f.write('## Spot check: random 25\n\n' + rand.to_markdown(index=False) + '\n')
print(open(OUT, encoding='utf-8').read()[:2500])
