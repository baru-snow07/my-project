"""Held-out reference evidence: each domain's About / Contact / Legal page (not its homepage text).

Finds a link on the homepage whose URL or text looks like about/company/contact/imprint/legal, fetches
that page, and keeps its title and the start of its text. The homepage content itself is NOT kept, so the
reference labels come from different evidence than the classifier's homepage input.
"""
import concurrent.futures as cf, csv, html, re, sys
import urllib.parse, urllib.request

KEYWORDS = re.compile(r'about|company|who-we-are|contact|impressum|imprint|legal|mentions|o-nas|chi-siamo|'
                      r'quienes|sobre|uber-uns|ueber-uns|kontakt|kontakty|about-us|corporate|profile|history', re.I)
UA = {'User-Agent': 'Mozilla/5.0 (research; about page check)'}

def get(url):
    raw = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=12)
    return raw.geturl(), raw.read(300_000).decode('utf-8', 'replace')

def text_of(page):
    t = re.search(r'<title[^>]*>(.*?)</title>', page, re.S | re.I)
    body = re.sub(r'(?is)<(script|style|nav|header|footer).*?</\1>', ' ', page)
    clean = lambda s: html.unescape(re.sub(r'\s+', ' ', s or '')).strip()
    return clean(t.group(1) if t else ''), clean(re.sub(r'<[^>]+>', ' ', body))[:400]

def fetch(domain):
    for base in (f'https://www.{domain}', f'https://{domain}', f'http://{domain}'):
        try:
            final, home = get(base)
        except Exception:
            continue
        links = re.findall(r'<a[^>]+href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', home, re.S | re.I)
        for href, label in links:
            if KEYWORDS.search(href) or KEYWORDS.search(re.sub(r'<[^>]+>', '', label)):
                url = urllib.parse.urljoin(final, href)
                if urllib.parse.urlparse(url).netloc.endswith(domain):
                    try:
                        _, page = get(url)
                        title, text = text_of(page)
                        return domain, url, title, text
                    except Exception:
                        pass
        return domain, '', '', 'no about/contact/legal page found'
    return domain, '', '', 'unreachable'

domains = [l.strip() for l in open(sys.argv[1], encoding='utf-8') if l.strip()]
with cf.ThreadPoolExecutor(16) as ex, open(sys.argv[2], 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f); w.writerow(['company', 'url', 'title', 'text'])
    for row in ex.map(fetch, domains):
        w.writerow(row)
