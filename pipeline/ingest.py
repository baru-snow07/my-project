"""Stream a Shodan-style .json.zst scan file into a compact Parquet table of per-company rows.

Map step of a map/reduce pipeline: each input file becomes one Parquet file in data/rows/,
one row per (scan record, company it belongs to), holding only the signals we score on.
Files already converted are skipped, so new monthly files can be dropped in and re-run.

    python pipeline/ingest.py <file.json.zst> [<file2> ...] [--limit N] [--workers N]
"""
import argparse, io, os, re, sys, time
from multiprocessing import Pool

import orjson
import pyarrow as pa
import pyarrow.parquet as pq
import zstandard

OUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'rows')
BATCH = 5000

# Domains that belong to hosting / CDN / ISP infrastructure, never to a prospect.
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

# Protocol blocks Shodan only fills in when the service really answered (unlike _shodan.module,
# which is just the probe that was attempted).
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
    """True for reverse-DNS style names like 1-2-3-4.host.net or ip-51-79-39.net."""
    if not ip or '.' not in ip:
        return False
    a, b, c, d = ip.split('.')[:4]
    return any(p in hostname for p in (f'{c}.{d}', f'{c}-{d}', f'{b}-{c}', f'{a}-{b}', f'{d}.{c}'))


def generated(hostname, ip):
    """Machine-made names (reverse DNS, hex-encoded IPs) rather than a host someone chose to name."""
    first = hostname.split('.')[0]
    return (embeds_ip(hostname, ip) or sum(ch.isdigit() for ch in first) >= 3 or bool(re.search(r'[0-9a-f]{8}', first))
            or bool(GENERATED_WORDS.search(first)))


def company_keys(r, tags):
    """Return [(key_type, company, generated_hostname)] for the companies this record belongs to."""
    ip = r.get('ip_str')
    hostnames = r.get('hostnames') or []
    keys = []
    for dom in r.get('domains') or []:
        if dom in INFRA_DOMAINS or '.' not in dom:
            continue
        under = [h for h in hostnames if h.endswith(dom)]
        if under and all(embeds_ip(h, ip) for h in under):
            continue  # only reverse-DNS names: this is the hosting provider, not a company
        keys.append(('domain', dom, bool(under) and all(generated(h, ip) for h in under)))
    if not keys and 'cdn' not in tags:  # a CDN edge with no SNI presents the CDN's own certificate
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
    unauth_db = (
        (r.get('mongodb') or {}).get('authentication') is False
        or (r.get('redis') or {}).get('authentication_required') is False
        or bool((r.get('elastic') or {}).get('indices'))
    )
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
    # claimed: a certificate or website on this host names the company, i.e. the company really
    # operates it (an ISP's reverse DNS on a customer's machine never does).
    return [dict(base, key_type=kt, company=k, generated_host=g,
                 claimed=(cert_domain == k) or (bool(web_host) and (web_host == k or web_host.endswith('.' + k))),
                 has_identity=bool(cert_domain or (web_host and not re.match(r'^[\d.:\[\]]+$', web_host))))
            for kt, k, g in keys]


def parse_batch(lines):
    rows = []
    for line in lines:
        try:
            rows.extend(extract(orjson.loads(line)))
        except (orjson.JSONDecodeError, AttributeError, TypeError, ValueError):
            continue
    return rows, len(lines)


def read_batches(path, limit):
    n, batch = 0, []
    with open(path, 'rb') as fh:
        stream = io.BufferedReader(zstandard.ZstdDecompressor(max_window_size=2**31).stream_reader(fh), 1 << 24)
        for line in stream:
            batch.append(line)
            n += 1
            if len(batch) >= BATCH or (limit and n >= limit):
                yield batch
                batch = []
                if limit and n >= limit:
                    return
    if batch:
        yield batch


def ingest(path, limit, workers):
    stem = os.path.basename(path).split('.json')[0].replace(':', '-')
    out = os.path.join(OUT_DIR, f'{stem}{"-sample" if limit else ""}.parquet')
    if os.path.exists(out):
        print(f'skip {path}: {out} exists')
        return
    os.makedirs(OUT_DIR, exist_ok=True)
    tmp, writer, seen, kept, buf = out + '.tmp', None, 0, 0, []
    t0 = time.time()
    with Pool(workers) as pool:
        for rows, n in pool.imap(parse_batch, read_batches(path, limit), chunksize=1):
            seen += n
            buf.extend(rows)
            if len(buf) >= 200_000:
                writer = flush(buf, tmp, writer)
                kept += len(buf); buf = []
            if seen % 500_000 < BATCH:
                print(f'  {seen:>11,} records  {kept:>11,} rows  {seen / (time.time() - t0):,.0f} rec/s', flush=True)
    if buf:
        writer = flush(buf, tmp, writer); kept += len(buf)
    if writer:
        writer.close()
        os.replace(tmp, out)
    print(f'done {path}: {seen:,} records -> {kept:,} rows in {time.time() - t0:,.0f}s -> {out}')


def flush(rows, tmp, writer):
    table = pa.Table.from_pylist(rows, schema=SCHEMA)
    writer = writer or pq.ParquetWriter(tmp, SCHEMA, compression='zstd')
    writer.write_table(table)
    return writer


SCHEMA = pa.schema([
    ('key_type', pa.string()), ('company', pa.string()), ('generated_host', pa.bool_()),
    ('claimed', pa.bool_()), ('has_identity', pa.bool_()), ('anon_ftp', pa.bool_()),
    ('ip', pa.string()), ('port', pa.int32()), ('ts', pa.string()), ('org', pa.string()),
    ('country', pa.string()), ('city', pa.string()), ('edge', pa.bool_()), ('cloud', pa.bool_()),
    ('product', pa.string()), ('version', pa.string()),
    ('exposed', pa.list_(pa.string())), ('unauth_data', pa.bool_()), ('ntlm_leak', pa.bool_()),
    ('compromised', pa.bool_()), ('eol', pa.bool_()), ('self_signed', pa.bool_()),
    ('n_cves', pa.int32()), ('n_kev', pa.int32()), ('n_ransomware_cves', pa.int32()), ('n_high_epss', pa.int32()),
    ('max_cvss', pa.float32()), ('max_epss', pa.float32()), ('top_cves', pa.list_(pa.string())),
    ('kev_cves', pa.list_(pa.string())),
    ('is_web', pa.bool_()), ('http_status', pa.int32()), ('title', pa.string()), ('waf', pa.string()),
    ('hsts', pa.bool_()), ('csp', pa.bool_()), ('security_txt', pa.bool_()), ('tech', pa.list_(pa.string())),
    ('has_tls', pa.bool_()), ('cert_expired', pa.bool_()), ('cert_expires', pa.string()),
    ('legacy_tls', pa.bool_()), ('pqc', pa.bool_()),
])

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('files', nargs='+')
    ap.add_argument('--limit', type=int, default=0, help='only read the first N records (writes a -sample file)')
    ap.add_argument('--workers', type=int, default=max(1, (os.cpu_count() or 2) - 1))
    a = ap.parse_args()
    for f in a.files:
        ingest(f, a.limit, a.workers)
