"""Stream the first N records and report how often each field is present, plus top values."""
import sys, io, json, collections, zstandard

path, N = sys.argv[1], int(sys.argv[2])
keys, sub = collections.Counter(), collections.defaultdict(collections.Counter)
ports, modules, products, orgs, countries = (collections.Counter() for _ in range(5))
n = with_domain = with_vulns = vuln_total = 0
cves = collections.Counter()
with open(path, 'rb') as fh:
    text = io.TextIOWrapper(zstandard.ZstdDecompressor(max_window_size=2**31).stream_reader(fh), encoding='utf-8', errors='replace')
    for line in text:
        try: r = json.loads(line)
        except ValueError: continue
        n += 1
        keys.update(k for k, v in r.items() if v not in (None, [], {}, ''))
        for k in ('ssl', 'http', 'opts', '_shodan', 'location'):
            if isinstance(r.get(k), dict):
                sub[k].update(kk for kk, vv in r[k].items() if vv not in (None, [], {}, ''))
        ports[r.get('port')] += 1
        modules[(r.get('_shodan') or {}).get('module')] += 1
        products[r.get('product')] += 1
        orgs[r.get('org')] += 1
        countries[(r.get('location') or {}).get('country_code')] += 1
        if r.get('domains'): with_domain += 1
        v = r.get('vulns') or (r.get('opts') or {}).get('vulns')
        if v:
            with_vulns += 1; vuln_total += len(v)
            cves.update(v if isinstance(v, list) else v.keys())
        if n >= N: break

pct = lambda c: f"{100*c/n:5.1f}%"
print(f"records: {n}   with domain: {pct(with_domain)}   with vulns: {pct(with_vulns)} (avg {vuln_total/max(with_vulns,1):.1f} CVEs)")
print("\nTOP-LEVEL FIELDS (non-empty):"); [print(f"  {pct(c)} {k}") for k, c in keys.most_common(60)]
for k, c in sub.items():
    print(f"\n{k}.* fields:"); [print(f"  {pct(cc)} {kk}") for kk, cc in c.most_common(25)]
for name, c in [('ports', ports), ('modules', modules), ('products', products), ('orgs', orgs), ('countries', countries), ('CVEs', cves)]:
    print(f"\nTOP {name}:", c.most_common(20))
