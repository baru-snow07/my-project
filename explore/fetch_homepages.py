"""Fetch the homepage title / description of each sampled domain: independent evidence for labelling."""
import concurrent.futures as cf, csv, html, re, sys
import urllib.request

def fetch(domain):
    for url in (f'https://www.{domain}', f'https://{domain}', f'http://{domain}'):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (research; homepage title check)'})
            raw = urllib.request.urlopen(req, timeout=12).read(200_000).decode('utf-8', 'replace')
            title = re.search(r'<title[^>]*>(.*?)</title>', raw, re.S | re.I)
            desc = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)', raw, re.I)
            text = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', re.sub(r'(?is)<(script|style).*?</\1>', ' ', raw)))
            clean = lambda s: html.unescape(re.sub(r'\s+', ' ', s or '')).strip()[:200]
            return domain, url, clean(title.group(1) if title else ''), clean(desc.group(1) if desc else ''), clean(text)[:200]
        except Exception as e:
            err = type(e).__name__
    return domain, '', '', '', f'unreachable ({err})'

domains = [r['company'] for r in csv.DictReader(open(sys.argv[1], encoding='utf-8'))]
with cf.ThreadPoolExecutor(16) as ex, open(sys.argv[2], 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f); w.writerow(['company', 'url', 'title', 'description', 'text'])
    for row in ex.map(fetch, domains):
        w.writerow(row)
