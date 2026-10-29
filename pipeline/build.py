"""Reduce step: turn every Parquet file in data/rows/ into one scored table of companies.

    python pipeline/build.py [--sample]

Writes app/data/companies.parquet (what the app reads) and prints a short summary.
All weights live in WEIGHTS so the scoring can be explained, tuned and tested.
"""
import argparse, os
import duckdb

ROOT = os.path.join(os.path.dirname(__file__), '..')
OUT = os.path.join(ROOT, 'app', 'data', 'companies.parquet')

# Points per signal. Urgent = something is wrong right now; exposure = an open door attackers
# scan for; hygiene = nobody is maintaining it; maturity = they likely already have a vendor.
WEIGHTS = {
    'compromised': 40,       # tagged compromised (e.g. database wiped and ransom note left)
    'unauth_data': 30,       # MongoDB / Redis / Elasticsearch readable without a password
    'anon_ftp': 6,           # anonymous FTP: often an intentional public mirror, so weak
    'kev': 25,               # CVE on CISA's Known Exploited Vulnerabilities list, and rare in the data
    'kev_common': 6,         # KEV CVE matched on so many hosts it is mostly version-banner noise
    'ransomware_cve': 15,    # CVE used in known ransomware campaigns
    'high_epss': 10,         # CVE with >=10% chance of exploitation in the next 30 days
    'remote_access': 12,     # RDP / SMB / Telnet / VNC reachable from the internet
    'database': 10,          # database port reachable from the internet
    'industrial': 15,        # Modbus / S7 / BACnet / DNP3 control systems exposed
    'open_dir': 8,           # web server lists its files
    'ntlm_leak': 5,          # Windows service leaks internal domain / machine names
    'eol': 8,                # software or OS past end-of-life
    'cert_expired': 6,
    'legacy_tls': 5,         # still accepts SSLv3 / TLS 1.0 / 1.1
    'self_signed': 3,
    'no_hsts': 2,
    'waf': -8,               # already behind a web application firewall
    'security_txt': -10,     # publishes a security contact: has a security function
    'pqc': -3,               # post-quantum TLS: a modern, well-run stack
}
INFRA_NAME_RE = (r'(host|server|vps|cloud|hosting|ptr|reverse|static|dedi|colo|datacent|broadband|dsl|cable|fiber|fibra'
                 r'|telecom|telekom|isp\b|netvigator|\.internal$|\.local$|\.lan$|\.arpa$|^test\.|^localhost)')
REMOTE = ['rdp', 'smb', 'telnet', 'vnc']
DATABASES = ['mysql', 'mongodb', 'redis', 'elasticsearch', 'postgresql', 'mssql']
INDUSTRIAL = ['modbus', 'siemens_s7', 'bacnet', 'dnp3']


def build(sample):
    con = duckdb.connect()
    pattern = os.path.join(ROOT, 'data', 'rows', '*-sample.parquet' if sample else '*[0-9].parquet').replace('\\', '/')
    con.execute(f"CREATE VIEW rows AS SELECT * FROM read_parquet('{pattern}')")
    w = WEIGHTS
    lst = lambda xs: '[' + ','.join(f"'{x}'" for x in xs) + ']'

    # 1. Network providers: an org that many other companies' domains live on is a host, not a prospect.
    con.execute("""
        CREATE TABLE providers AS
        SELECT org FROM rows WHERE key_type = 'domain' AND NOT edge
        GROUP BY org HAVING count(DISTINCT company) >= 10""")
    # 2. Provider domains: mostly machine-generated hostnames spread over many IPs (reverse DNS).
    con.execute("""
        CREATE TABLE infra_domains AS
        SELECT company FROM rows WHERE key_type = 'domain'
        GROUP BY company HAVING count(DISTINCT ip) >= 3 AND avg(generated_host::INT) >= 0.5""")
    # 2a. Ownership: if the domain's hosts present certificates / websites, a real company's carry
    #     its own name; an ISP's reverse DNS on customer machines carries the customers' names.
    #     With no identity at all, fall back to whether it mostly sits on provider networks.
    con.execute("""
        INSERT INTO infra_domains
        SELECT company FROM rows WHERE key_type = 'domain'
        GROUP BY company HAVING count(DISTINCT ip) >= 3 AND (
            (count(*) FILTER (WHERE has_identity) >= 3
             AND avg(claimed::INT) FILTER (WHERE has_identity) < 0.2)
            OR (NOT bool_or(claimed) AND avg((org IN (SELECT org FROM providers))::INT) > 0.5))""")
    # 2c. Subdomain platforms. Dynamic DNS (ddns.net, hopto.org) hands names to anyone, so its
    #     hosts sit on a different network almost every time (real companies: <0.15 orgs per IP).
    #     Shared web hosts show cPanel / Plesk on a large share of their services.
    con.execute("""
        INSERT INTO infra_domains
        SELECT company FROM rows WHERE key_type = 'domain'
        GROUP BY company HAVING
            (count(DISTINCT org) >= 20 AND count(DISTINCT org) / count(DISTINCT ip) >= 0.4)
            OR (count(*) >= 10 AND avg((list_has_any(tech, ['cPanel', 'Plesk', 'DirectAdmin', 'ISPConfig'])
                                        OR port IN (2082, 2083, 2086, 2087, 2222))::INT) >= 0.15)""")
    # 2b. The provider's own brand domain (leaseweb.com on LeaseWeb's network), hosting/ISP-style
    #     names, and internal-only TLDs that leak into reverse DNS.
    con.execute(f"""
        INSERT INTO infra_domains
        SELECT company FROM rows WHERE key_type = 'domain'
        GROUP BY company HAVING
            regexp_matches(company, '{INFRA_NAME_RE}')
            OR bool_or(org IN (SELECT org FROM providers)
                       AND contains(lower(replace(org, ' ', '')), split_part(company, '.', 1)))""")

    # 3. CVE prevalence: version-banner matching flags every host running a common version, even
    #    when the distro patched it without bumping the number. A KEV CVE on >=5% of vulnerable
    #    hosts tells a salesperson nothing about *this* company, so it is down-weighted.
    common = [c for (c,) in con.execute("""
        WITH hosts AS (SELECT DISTINCT ip, unnest(kev_cves) AS cve FROM rows WHERE NOT edge AND n_cves > 0),
             total AS (SELECT count(DISTINCT ip) n FROM rows WHERE NOT edge AND n_cves > 0)
        SELECT cve FROM hosts, total GROUP BY cve, total.n HAVING count(*) >= 0.05 * total.n""").fetchall()]
    print('common KEV CVEs (down-weighted):', common)

    con.execute(f"""
        CREATE TABLE companies AS
        WITH r AS (
            SELECT * FROM rows
            WHERE NOT (key_type = 'domain' AND company IN (SELECT company FROM infra_domains))
              AND NOT (key_type = 'org' AND company IN (SELECT org FROM providers))
        ),
        -- Port / CVE signals only count on the company's own hosts, never on a shared CDN edge.
        own AS (SELECT * FROM r WHERE NOT edge)
        SELECT
            r.key_type, r.company,
            mode(r.org) AS network_org, mode(r.country) AS country, mode(r.city) AS city,
            count(DISTINCT r.ip) AS ips, count(*) AS services,
            any_value(r.title) FILTER (WHERE r.title IS NOT NULL AND r.http_status = 200) AS web_title,
            list_distinct(flatten(list(r.tech)))[:12] AS tech,
            coalesce(bool_or(o.compromised), false) AS compromised,
            coalesce(bool_or(o.unauth_data), false) AS unauth_data,
            coalesce(bool_or(o.anon_ftp), false) AS anon_ftp,
            round(avg(r.claimed::INT) FILTER (WHERE r.has_identity), 2) AS ownership,
            list_distinct(flatten(list(o.kev_cves))) AS kev_list,
            coalesce(max(o.n_ransomware_cves), 0) AS ransomware_cves,
            count(DISTINCT o.ip) FILTER (WHERE o.n_high_epss > 0) AS hosts_high_epss,
            coalesce(max(o.max_epss), 0) AS max_epss, coalesce(max(o.max_cvss), 0) AS max_cvss,
            list_distinct(flatten(list(o.top_cves)))[:5] AS top_cves,
            list_distinct(flatten(list(o.exposed))) AS exposed_services,
            count(DISTINCT o.ip) FILTER (WHERE len(list_intersect(o.exposed, {lst(REMOTE)})) > 0) AS hosts_remote_access,
            count(DISTINCT o.ip) FILTER (WHERE len(list_intersect(o.exposed, {lst(DATABASES)})) > 0) AS hosts_database,
            count(DISTINCT o.ip) FILTER (WHERE len(list_intersect(o.exposed, {lst(INDUSTRIAL)})) > 0) AS hosts_industrial,
            coalesce(bool_or(list_contains(o.exposed, 'open_directory')), false) AS open_dir,
            coalesce(bool_or(o.ntlm_leak), false) AS ntlm_leak,
            count(DISTINCT o.ip) FILTER (WHERE o.eol) AS hosts_eol,
            bool_or(r.cert_expired) AS cert_expired, bool_or(r.legacy_tls) AS legacy_tls,
            bool_or(r.self_signed) AS self_signed,
            bool_or(r.is_web) AS has_web,
            bool_or(r.is_web) AND NOT bool_or(r.hsts) AS no_hsts,
            any_value(r.waf) FILTER (WHERE r.waf IS NOT NULL) AS waf,
            bool_or(r.security_txt) AS security_txt, bool_or(r.pqc) AS pqc,
            bool_and(r.edge) AS cdn_only,
            max(r.ts) AS last_seen
        FROM r LEFT JOIN own o ON o.company = r.company AND o.key_type = r.key_type
             AND o.ip = r.ip AND o.port = r.port AND o.ts = r.ts
        GROUP BY r.key_type, r.company""")

    con.execute(f"""
        CREATE TABLE scored AS SELECT *,
            -- breakdown kept per company so every score can be explained to a salesperson
            {w['compromised']} * compromised::INT AS s_compromised,
            {w['unauth_data']} * unauth_data::INT AS s_unauth_data,
            {w['anon_ftp']} * anon_ftp::INT AS s_anon_ftp,
            CASE WHEN kev_cves > 0 THEN {w['kev']} WHEN len(kev_list) > 0 THEN {w['kev_common']} ELSE 0 END AS s_kev,
            {w['ransomware_cve']} * (ransomware_cves > 0)::INT AS s_ransomware,
            {w['high_epss']} * least(hosts_high_epss, 3) AS s_high_epss,
            {w['remote_access']} * least(hosts_remote_access, 3) AS s_remote,
            {w['database']} * least(hosts_database, 3) AS s_database,
            {w['industrial']} * least(hosts_industrial, 2) AS s_industrial,
            {w['open_dir']} * open_dir::INT AS s_open_dir,
            {w['ntlm_leak']} * ntlm_leak::INT AS s_ntlm,
            {w['eol']} * least(hosts_eol, 3) AS s_eol,
            {w['cert_expired']} * cert_expired::INT AS s_cert,
            {w['legacy_tls']} * legacy_tls::INT AS s_legacy_tls,
            {w['self_signed']} * self_signed::INT AS s_self_signed,
            {w['no_hsts']} * no_hsts::INT AS s_no_hsts,
            {w['waf']} * (waf IS NOT NULL)::INT AS s_waf,
            {w['security_txt']} * security_txt::INT AS s_security_txt,
            {w['pqc']} * pqc::INT AS s_pqc
        FROM (SELECT *, len(list_filter(kev_list, lambda x: NOT list_contains({lst(common) if common else '[]::VARCHAR[]'}, x))) AS kev_cves
              FROM companies)""")
    cols = [c for (c,) in con.execute("SELECT column_name FROM (DESCRIBE scored) WHERE column_name LIKE 's\\_%' ESCAPE '\\'").fetchall()]
    con.execute(f"""
        CREATE TABLE final AS SELECT *,
            {' + '.join(cols)} AS risk_score,
            CASE WHEN compromised OR unauth_data THEN 'Breached / data exposed'
                 WHEN kev_cves > 0 THEN 'Actively exploited CVE'
                 WHEN hosts_remote_access + hosts_database + hosts_industrial > 0 THEN 'Exposed critical service'
                 WHEN hosts_high_epss > 0 OR hosts_eol > 0 THEN 'Vulnerable software'
                 WHEN cert_expired OR legacy_tls OR self_signed THEN 'Poor hygiene'
                 ELSE 'Low signal' END AS tier
        FROM scored""")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    # Only domain-identified companies are actionable: an org-only entry is an ISP or cloud
    # customer we cannot name, so a salesperson has nobody to contact.
    con.execute(f"COPY (SELECT * FROM final WHERE key_type = 'domain' AND risk_score > 0 ORDER BY risk_score DESC) TO '{OUT.replace(chr(92), '/')}' (FORMAT parquet, COMPRESSION zstd)")

    print(con.sql("SELECT (SELECT count(*) FROM providers) providers, (SELECT count(*) FROM infra_domains) infra_domains, count(*) FILTER (WHERE key_type = 'domain') domain_companies, count(*) FILTER (WHERE key_type = 'domain' AND risk_score > 0) scored FROM final"))
    print(con.sql("SELECT tier, count(*) n FROM final WHERE key_type = 'domain' AND risk_score > 0 GROUP BY ALL ORDER BY 2 DESC"))
    print(con.sql("SELECT company, country, ips, risk_score, tier, exposed_services, kev_cves, top_cves FROM final WHERE key_type = 'domain' ORDER BY risk_score DESC LIMIT 25").df().to_string())


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--sample', action='store_true', help='build from the -sample.parquet files')
    build(ap.parse_args().sample)
