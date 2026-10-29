# Data exploration notes

Source: `2026-10-26T12:00:00.json.zst` (17.6 GB compressed, SHA-1 verified).
Sample: first 50,000 records (`explore/profile.py`, `explore/profile2.py`).

## What the data is

Shodan-style internet scan banners, one JSON object per line. Each record is
**one service on one IP and port**, not one company. A company appears as many
records spread across its IPs, ports and domains.

Useful fields (share of records where non-empty):

| Field | Coverage | Use |
|---|---|---|
| `domains`, `hostnames` | 71% | Map a record to a company |
| `org`, `isp`, `asn` | 100% | Who owns the IP block (often a cloud/CDN, not the company) |
| `location` | 100% | Country / city for territory filters |
| `tags` | 71% | `cdn`, `cloud`, `honeypot`, `eol-product`, `self-signed`, `database`, `open-dir`, `compromised`... |
| `http` | 33% | Status, title, server, WAF, tech stack (`components`), headers, security.txt |
| `product`, `version`, `cpe23` | 23% | Exact software and version |
| `ssl` | 7% | Cert expiry, issuer, TLS versions offered |
| `vulns` | 3% | CVEs with CVSS + EPSS; avg 42 per record that has them |

## Traps (why "just hand it to an LLM" fails)

1. **`_shodan.module` is the probe Shodan tried, not what it found.** Records with
   `orcus-rat` / `automated-tank-gauge` modules on Incapsula IPs just got an HTTP 400
   or a TLS alert back. Counting modules as detections would flag CDNs as malware hosts.
2. **About half the sample is CDN/cloud edge IPs** (Incapsula 32%, Google 20%,
   Cloudflare 7%). They answer on every port, so they inflate "open ports" and
   their `domains` are infrastructure (`incapdns.net`, `googleusercontent.com`),
   not customers. These need filtering or attributing via the cert/host name.
3. **`vulns` are inferred from version banners** (`"verified": false`), not
   confirmed exploits. Weight by EPSS (exploit probability) and CVSS, and count
   distinct high-EPSS CVEs rather than raw totals.
4. **Honeypots** (`honeypot` tag, ~1.6%) pretend to be vulnerable. Exclude them.

## Candidate signals (to validate on the full file)

- **Exposure**: risky services reachable from the internet (RDP, SMB, databases,
  Telnet, VNC, open directories, admin panels, cameras, ICS / medical like DICOM).
- **Hygiene**: expired or self-signed certs, legacy TLS (TLSv1/1.1 enabled),
  end-of-life software (`eol-product`, `eol-os`), missing security headers (HSTS, CSP).
- **Known-vulnerable software**: CVEs with high EPSS on the company's own hosts.
- **Already breached**: `compromised` tag, confirmed malware/C2 responses.
- **No protection in front**: no WAF / CDN on a public web app.
- **Maturity (negative signal)**: has `security.txt`, WAF, HSTS, post-quantum TLS (`pqc`)
  — likely already has a security team or vendor.
