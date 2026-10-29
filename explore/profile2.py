"""Second pass: tags, vuln structure, SSL cert health, malware/ICS modules, and org/domain ownership."""
import sys, io, json, collections, datetime, zstandard

path, N = sys.argv[1], int(sys.argv[2])
tags, comps, cloud = collections.Counter(), collections.Counter(), collections.Counter()
expired = selfsigned = ssl_n = 0
examples = {}
n = 0
with open(path, 'rb') as fh:
    text = io.TextIOWrapper(zstandard.ZstdDecompressor(max_window_size=2**31).stream_reader(fh), encoding='utf-8', errors='replace')
    for line in text:
        try: r = json.loads(line)
        except ValueError: continue
        n += 1
        tags.update(r.get('tags') or [])
        cloud[(r.get('cloud') or {}).get('provider')] += 1
        comps.update(((r.get('http') or {}).get('components') or {}).keys())
        s = r.get('ssl')
        if s:
            ssl_n += 1; c = s.get('cert') or {}
            if c.get('expired'): expired += 1
            if (s.get('trust') or {}).get('revoked') is None and c.get('issuer') == c.get('subject'): selfsigned += 1
        m = (r.get('_shodan') or {}).get('module')
        for key, cond in [('rat', m and 'rat' in m), ('vulns', bool(r.get('vulns'))), ('tank', m == 'automated-tank-gauge'), ('dicom', m == 'dicom'), ('ssl', bool(s))]:
            if cond and key not in examples: examples[key] = r
        if n >= N: break
print(f"records {n}; ssl {ssl_n}; expired certs {expired}; self-signed {selfsigned}")
print("\nTAGS:", tags.most_common(40))
print("\nCLOUD:", cloud.most_common(10))
print("\nHTTP COMPONENTS (tech stack):", comps.most_common(30))
def short(r):
    keep = {k: r.get(k) for k in ('ip_str', 'port', 'org', 'isp', 'domains', 'hostnames', 'tags', 'product', 'version', 'cpe23', 'timestamp')}
    keep['module'] = r['_shodan']['module']; keep['location'] = (r.get('location') or {}).get('country_code')
    if r.get('vulns'): v = r['vulns']; k0 = next(iter(v)); keep['vulns_count'] = len(v); keep['vuln_example'] = {k0: v[k0]}
    if r.get('ssl'): c = r['ssl'].get('cert') or {}; keep['ssl_cert'] = {k: c.get(k) for k in ('expired', 'expires', 'issuer', 'subject')}; keep['ssl_versions'] = r['ssl'].get('versions')
    keep['data'] = (r.get('data') or '')[:300]
    return keep
for k, r in examples.items():
    print(f"\n=== EXAMPLE {k} ===\n", json.dumps(short(r), indent=1, default=str)[:2500])
