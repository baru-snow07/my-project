"""Inspect nested structures the ingest relies on: cert names, CVE entry keys, protocol blocks."""
import sys, io, json, collections, zstandard
path, N = sys.argv[1], int(sys.argv[2])
cert_keys, vuln_keys, ssl_versions = collections.Counter(), collections.Counter(), collections.Counter()
proto = {}
n = 0
with open(path, 'rb') as fh:
    for line in io.TextIOWrapper(zstandard.ZstdDecompressor(max_window_size=2**31).stream_reader(fh), encoding='utf-8', errors='replace'):
        r = json.loads(line); n += 1
        c = (r.get('ssl') or {}).get('cert')
        if c: cert_keys.update(c.keys()); ssl_versions.update(r['ssl'].get('versions') or [])
        for v in (r.get('vulns') or {}).values(): vuln_keys.update(v.keys())
        for k in ('rdp_encryption', 'smb', 'mysql', 'vnc', 'telnet', 'ftp', 'open_dir', 'kubernetes', 'ntlm', 'mongodb', 'redis', 'elastic', 'postgresql', 'ms_sql'):
            if r.get(k) and k not in proto: proto[k] = (r['port'], r['_shodan']['module'], r.get('org'), r.get('tags'), r.get('domains'), str(r[k])[:200])
        if 'compromised' in (r.get('tags') or []) and 'compromised' not in proto: proto['compromised'] = (r['port'], r['_shodan']['module'], r.get('org'), r.get('domains'), (r.get('data') or '')[:300], str(r.get('http', {}).get('title')))
        if n >= N: break
print("cert keys:", cert_keys.most_common()); print("vuln keys:", vuln_keys.most_common()); print("ssl versions:", ssl_versions.most_common())
for k, v in proto.items(): print(f"\n[{k}]", v)
