# Cyber Prospecting

A small sales-intelligence tool that ranks companies by how urgently their internet-facing
systems need security help, so a cybersecurity sales team knows who to call first and what to say.

- **App:** https://cyber-prospecting.streamlit.app/
- **Pipeline:** `pipeline/ingest.py` (stream → Parquet) and `pipeline/build.py` (DuckDB → scored companies)
- **Exploration notes:** [`explore/FINDINGS.md`](explore/FINDINGS.md)
- **Evaluation:** [`eval/report.md`](eval/report.md), [`eval/weights.md`](eval/weights.md)
- **How it was built with AI:** [`DEVLOG.md`](DEVLOG.md)

## How a salesperson uses it

1. Filter by *why now* (breached, actively exploited CVE, exposed critical service...), sector, country and size.
2. Pick an account and read the plain-English reasons, each with the points it contributed.
3. Check the **evidence table**: the actual servers behind the score (port, software version, issues),
   worst first. Every claim traces back to a scan record. IPs are masked (`128.32.x.x`) so the
   public app is not a target list.
4. Use the suggested opening line, which is built from the strongest reason. No LLM is needed, so it costs nothing and can't hallucinate.
5. Export the filtered list as CSV for the CRM.

The app's **How it works** tab walks through the data, traps, scoring weights and back-test results.

## The data

One file is a Shodan-style internet scan: 17.6 GB of zstd-compressed JSON lines, each record
being **one service on one IP and port**. Companies are not given; they have to be inferred.

## Approach

### 1. Understand the data before automating it
I profiled samples by hand (`explore/`) before writing the pipeline. Four traps would have
produced a confident but wrong ranking if the file had been handed straight to an LLM:

| Trap | What it looks like | What I did |
|---|---|---|
| `_shodan.module` is the probe tried, not the result | Records labelled `orcus-rat`, `automated-tank-gauge` that only got an HTTP 400 back | Exposure only counts when the protocol's parsed block (`rdp_encryption`, `mongodb`, `smb`...) exists, i.e. the service really answered |
| CDN / cloud edges | ~half the sample is Incapsula, Google, Cloudflare IPs answering on every port | Port and CVE signals never count on CDN edge records; only web hygiene is attributed to the tenant |
| Provider reverse DNS looks like a company | `ip-51-79-39.net`, `t-ipconnect.de`, `your-server.de` | Data-driven rules (below) instead of a hand list that can't keep up |
| Version-matched CVEs are noisy | CVE-2023-44487 matched to nearly every nginx host, incl. distro-patched ones | Down-weight KEV CVEs that appear on ≥5% of vulnerable hosts |
| Honeypots | Fake-vulnerable hosts | Dropped |

### 2. Who is the company?
Each record maps to a registered domain from `domains`, falling back to the TLS certificate
name (never on CDN edges, which show the CDN's own cert). Infrastructure is removed with rules
that learn from the data rather than a fixed list:

- **Network providers:** an org that ≥10 other companies' domains live on is a host, not a prospect.
- **Generated hostnames:** a domain spread over ≥3 IPs whose hostnames are mostly machine-made (digits, hex, `ip-`, `static-`) is reverse DNS.
- **Provider's own brand:** a domain whose name is in its provider org's name (`leaseweb.com` on LeaseWeb).

Records with only an org (no domain) are kept in the pipeline but left out of the app: a
salesperson can't act on "a customer of China Telecom".

### 3. Signals and scoring
Every weight is in `WEIGHTS` in `pipeline/build.py`, and every company keeps its per-signal
breakdown, so any score can be explained line by line.

| Group | Signals | Why it matters to sales |
|---|---|---|
| **Urgent (why now)** | compromised tag, unauthenticated database/FTP/search index, rare CISA-KEV CVE, ransomware-linked CVE, high-EPSS CVE | Something is wrong *today*: strongest reason to call |
| **Exposure** | RDP/SMB/Telnet/VNC, databases, industrial control protocols, open directories, NTLM info leaks | The doors attackers scan for first |
| **Hygiene** | end-of-life software, expired cert, legacy TLS, self-signed, no HSTS | Nobody is maintaining it, so likely more problems |
| **Maturity (negative)** | WAF, `security.txt`, post-quantum TLS | Probably already has a security vendor or team |

Counts are capped per signal (e.g. at most 3 hosts) so one large network can't win on volume alone.
Each company also gets a **tier**, the single strongest reason, which is what the sales team filters on.

## Scaling to hundreds of files a month
- **Map:** `ingest.py` streams the compressed file (never decompressed to disk) through a
  process pool and writes one small Parquet file per input. Already-processed files are
  skipped, so new monthly files are just added. _Throughput: ~25k records/s on an 8-core laptop._
- **Reduce:** `build.py` is plain DuckDB SQL over `data/rows/*.parquet`. The provider and CVE-prevalence
  rules get *more* accurate as more files arrive, because they are computed across all of them.
- Next step for production: run ingest per file in parallel workers (one file per container),
  write to object storage, and keep the latest snapshot per company to track changes over time.

## Results on the provided file

| | |
|---|---|
| Records streamed | 14,608,407 (17.6 GB compressed) in ~10 min on an 8-core laptop |
| Rows kept after attribution | 6.2M (honeypots, unattributable CDN/cloud records dropped) |
| Network providers detected | 3,578 orgs |
| Infrastructure domains removed | ~60k |
| Domain-identified companies | 427,216 |
| Companies with ≥1 risk signal (in the app) | 228,997 |
| Scoring all companies (`build.py`) | ~12 s |

## How I measured whether it works

Full output: [`eval/report.md`](eval/report.md) (`python pipeline/evaluate.py`).

**1. Back-test against real breaches.** The data contains servers that were already hit:
tagged `compromised` (e.g. a database wiped with a ransom note) or a database open to anyone.
I scored every server with the same weights **but without** those breach signals, and checked
whether the warning signs alone rank the breached servers higher.

- AUC **0.80** (0.5 = random): the warning signs do separate breached servers from the rest.
  (An earlier version reported 0.70 because of a tie-ranking bug in the SQL; it was caught by
  cross-checking against scikit-learn. See [`DEVLOG.md`](DEVLOG.md), round 5.)
- Breached servers are **6×** over-represented in the top 10,000 scored servers.
- Strongest single predictor: **end-of-life software (15× lift)**, then high-EPSS CVEs (2.4×)
  and KEV CVEs (1.9×). Self-signed certs carried no signal (0.7×).
- Caveat: only 56 labelled breached servers survive attribution (most open databases sit on
  anonymous cloud IPs with no domain), so per-signal lifts are directional, not precise.

**2. Noise removed by each rule.** Every rule was added after looking at what it removed. For
example, the ownership check (does any certificate or website on these hosts name the domain?)
separates hosting/ISP domains (0–4% claimed) from real organisations (85–100% claimed).

**3. Hand check of the top 25.** About half are clear end-organisations that a security
vendor would want: Berkeley, MIT, RIT, Keio, USP, CNR (Italy's research council), GRNET,
Hewlett Packard Enterprise, the Jordanian government. The rest are mostly hosting/ISP businesses
(`nazwa.pl`, `keymachine.de`) whose servers do carry their own name. These are arguably prospects
themselves, but their risk is partly their customers'. Before rules: the top 25 were almost
entirely CDNs, ISPs and clouds.

**4. Hand-set vs learned weights.** A logistic regression fitted to the breach labels with 5-fold
cross-validation scored **0.785** vs **0.803** for the hand weights, and gave Remote Desktop exposure
a *negative* weight: 56 positives is too few to learn from. The hand weights stay, to be re-fitted as
labels accumulate. See [`eval/weights.md`](eval/weights.md).

### Known limitations and next steps
- Hosting businesses still leak into the top list. A Claude classifier flags them at 74% agreement with
  homepage-based labels (see AI usage below). Adding homepage text to its evidence is the next improvement,
  and its flag is not yet wired into the app's ranking.
- One snapshot shows state, not change. Trigger events ("RDP newly exposed this week",
  "certificate just expired") would be stronger sales signals once files arrive monthly.
- Sector is guessed from the domain name; enriching with firmographics (size, industry) would
  let sales filter to their ideal customer profile.

## Running it

```bash
pip install -r requirements-pipeline.txt
python pipeline/ingest.py path/to/*.json.zst      # map: one Parquet per input file, skips done files
python pipeline/build.py                           # reduce + score -> app/data/companies.parquet
python pipeline/evaluate.py                        # -> eval/report.md
python pipeline/learn_weights.py                   # -> eval/weights.md (hand vs learned weights)
streamlit run app/app.py
```

## AI usage

The whole build was done with **Claude Code** as a pair programmer: exploring the data,
writing the pipeline, and iterating on the rules. How I kept it honest:

- **Data first, agent second.** The first scripts (`explore/`) only profiled the raw data, and
  every rule came from something seen there. The four traps above are things a model handed the
  raw file would have taken at face value.
- **Every rule was checked against output.** After each change, the top of the ranking was
  re-inspected. Three rounds of "the top 25 are still ISPs/hosters" led to the provider,
  ownership and platform rules, each validated with a small query comparing known real
  organisations against known infrastructure before it went in.
- **A measurable test instead of trust.** `evaluate.py` back-tests the score against servers
  that were actually breached, so the weights are judged by data, not by how plausible they sound.
- **Cross-checking the AI's own numbers.** The evaluation's first AUC (0.70) disagreed with
  scikit-learn (0.80); the cause was a tie-ranking bug, now fixed. A guessed cause for the hosted-app
  crash (memory) was measured and ruled out before the log revealed the real bug.
- **No LLM at runtime.** Scoring, reasons and the opening line are deterministic SQL/Python.
  The app makes zero API calls: no per-account cost, nothing to hallucinate, and every claim
  traces back to a scan field.

The full round-by-round record, with what was wrong each time and how it was measured, is in
**[`DEVLOG.md`](DEVLOG.md)**.

### Where an LLM earns its place: hosting vs real organisation

`pipeline/llm_classify.py` asks Claude (structured output, one JSON verdict per domain) whether each
top-ranked domain is an end organisation or a hosting/ISP business, from the evidence already
collected. How we know it's right, and what it costs:

| Step | Command | Output |
|---|---|---|
| Blind human labels for 60 random domains | `llm_classify.py label-sheet` | `eval/human_labels.csv` |
| Prompt + cost estimate, no API call | `llm_classify.py classify --dry-run` | Opus 5.5: ~$4.76 per 500 domains; Haiku 5.5: ~$0.12 |
| Classify (resumable, logs exact tokens) | `llm_classify.py classify [--model ...]` | `eval/llm_labels.csv`, `eval/llm_usage.json` |
| Accuracy vs reference labels, confusion matrix, every disagreement | `llm_classify.py score [--labels ...]` | `eval/llm_report.md` |

**Result on the top 500** (run inside Claude Code, as no API key was available; same prompt and schema):
257 end organisations, 176 hosting/ISP, 67 unsure, for **65k tokens on the Pro plan, no API spend**.

**Is it right?** Reference labels for 40 sampled domains came from **independent evidence, their live
homepages**, which the classifier never saw. These labels are AI-made, so `eval/human_labels.csv` stays open
for a human check. Where the classifier answered (88%), it agreed **74%** of the time, or ~81% excluding domains
whose homepage was itself ambiguous. The dominant error is hosting companies read as end organisations: scan
data shows what a company *runs*, not what it *sells*. The fix is to add the homepage title to the
classifier's evidence. Full report: [`eval/llm_report.md`](eval/llm_report.md); details in DEVLOG round 8.

### Cost

- **Development:** Claude Code on a Claude Pro subscription. The whole project used about 6% of one
  week's allowance (main conversation ~350k tokens). No API spend.
- **Pipeline:** compute only, ~10 min of an 8-core laptop per 17.6 GB file; scoring ~12 s.
- **LLM classifier:** measured per run in `eval/llm_usage.json` (estimates above).
- **Hosting:** Streamlit Community Cloud, free.
