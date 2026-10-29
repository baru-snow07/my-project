# Dev log: how this was built with AI

Built in one working session with **Claude Code** (Claude Opus 5.5) as pair programmer. The loop
every round was the same: **look at the output → find what's wrong → write a rule → measure it on
known good and bad examples → re-run → check the top of the list again.** Nothing was accepted
because it looked plausible; each step below records what was checked and what it showed.

## Round 0: understand the data before writing the pipeline

Profiled 50k–200k records with throwaway scripts (`explore/`) before any pipeline code.

| Finding | Evidence | Consequence |
|---|---|---|
| It's Shodan banner data, one record = one service on one IP:port | First record: `jamasoftware.com:443`, Cloudflare challenge page | Companies must be inferred |
| `_shodan.module` is the probe tried, not the result | `orcus-rat` / `automated-tank-gauge` records on Incapsula IPs returned HTTP 400 or a TLS alert | Only count a service when its parsed protocol block exists |
| ~50% of records are CDN/cloud edges | Incapsula 32%, Google 20%, Cloudflare 7% of the sample | Port/CVE signals never count on edges |
| CVEs carry `kev` and `ransomware_campaign` flags and EPSS | Field census of 245k CVE entries | Weight by exploit likelihood, not count |
| `compromised` marks ransomed databases | Elasticsearch with a `read_me` index | Ground truth for evaluation |

## Round 1: first scoring on a 300k sample

- **What came out:** the top 25 were Tencent, Huawei Cloud, Telecom Italia: ISPs and clouds known only by network owner.
- **Fix:** rank only domain-identified companies (an org-only entry has nobody to call).
- **Second issue:** CVE-2023-44487 (HTTP/2 Rapid Reset, on CISA KEV) was matched to almost every nginx host from the version banner alone.
- **Fix:** measure each KEV CVE's prevalence; any on ≥5% of vulnerable hosts is down-weighted (25 → 6 points).
  Data picked three: CVE-2023-44487, CVE-2021-40438, CVE-2024-38475.

## Round 2: hosting providers' domains

- **What came out:** `nazwa.pl`, `dreamhost.com`, `leaseweb.com`, `ptr.network` near the top.
- **Fix:** data-driven provider rules instead of a blocklist: machine-generated hostnames (digits, hex, `ip-`, `static-`),
  orgs hosting ≥10 other companies' domains, a provider's own brand domain.

## Round 3: full file (14.6M records, ~10 min at ~25k records/s)

- **What came out:** 456k companies, but the top still had `vnpt.vn`, `starlink.com`, `websitewelcome.com`.
- **Hypothesis:** ISPs attach their domain to customers' machines via reverse DNS, but those machines' certificates
  and websites name the *customer*.
- **Checked before building:** share of certificates/websites naming the domain. Hosting/ISP domains
  (`scw.cloud`, `t-ipconnect.de`, `kasserver.com`): **0–4%**. Real organisations (`wisc.edu`, `ringana.com`, `hotmart.com`): **85–100%**.
- **Fix:** the ownership check (`claimed` field), plus a full re-ingest. Infrastructure domains removed: 27k → 60k.
- **Also:** anonymous FTP split from "breached" (often an intentional public mirror). The breached tier went 160 → 3 companies.

## Round 4: subdomain platforms

- **Checked:** orgs per IP for 24 known domains. Dynamic DNS (`ddns.net` 0.70, `hopto.org` 0.64) vs real orgs
  (Microsoft 0.07, Berkeley 0.02); share of cPanel/Plesk for shared hosts (0.15–0.29) vs real orgs (≤0.02).
- **Fix:** two thresholds taken from those measurements.
- **Result:** the top 25 became Berkeley, MIT, RIT, Keio, USP, CNR, GRNET, HPE, the Jordanian government; about half
  clear end-organisations. The remaining error class (hosting businesses with their own name on their servers) is documented, not over-fitted.

## Round 5: evaluation, and a bug in my own evaluation

- **Back-test:** score every server without the breach signals; do the warning signs find the 56 breached servers?
- First result: **AUC 0.70**. Cross-checking with scikit-learn gave **0.80** for the same scores.
- **Cause:** the SQL used `rank()`, which gives tied scores the lowest rank. Most servers share scores like 0 or 8, so it
  understated the AUC. Fixed with average ranks, and now matches scikit-learn exactly (0.803).

## Round 6: can the weights be learned instead of hand-set?

- Logistic regression, 5-fold cross-validation, on the same 11 signals (`pipeline/learn_weights.py`).
- **Result:** learned weights scored **0.785** out-of-fold vs **0.803** for the hand weights, and gave nonsense signs
  (Remote Desktop exposure *negative*) because 56 positives is too few. **Decision:** keep explainable hand weights;
  re-fit as labelled breaches accumulate across monthly files. Full table: [`eval/weights.md`](eval/weights.md).

## Round 7: shipping, and a production bug

- The hosted app crashed for new visitors. The first guess (memory) was **measured and ruled out**: ~350 MB
  per session, steady across sessions, under the 1 GB limit.
- The Streamlit Cloud log showed the real cause: `ValueError` when filters matched **zero** companies
  (`DataFrame.apply` on an empty frame returns a frame, not a column). Rolled back to a known-good version,
  fixed, verified the empty search live, then restored the new features.

## Smaller AI mistakes caught along the way

- `python -I` (isolated mode, used for safety on untrusted data) silently ignores `PYTHONIOENCODING`, which caused Windows console crashes. Switched to `-X utf8`.
- DuckDB 2.0 rejects the `x -> expr` lambda syntax; caught on the first run.
- A `.gitignore` rule `data/` also hid `app/data/`, so the app's data wasn't committed; caught at `git status`.
- The first deploy check passed in one browser session while new visitors failed; testing in a private window is now the release check.

## Where an LLM is used in the product, and how it is checked

The app itself makes **no LLM calls**: scores, reasons and opening lines are deterministic, cost nothing per
account and can't hallucinate. One task does benefit from judgment: telling hosting companies from end
organisations. `pipeline/llm_classify.py` does that with structured output, and it is checked two ways:

1. **Accuracy:** reference labels for a random sample, compared to the LLM's answers
   (`llm_classify.py score` → `eval/llm_report.md`, with every disagreement listed).
2. **Cost:** exact token usage logged per run (`eval/llm_usage.json`). Dry-run estimate for the top 500: **$4.76 with
   Claude Opus 5.5** ($9.53 per 1,000 domains) or **$0.12 with Claude Haiku 5.5** ($0.24 per 1,000).

## Round 8: running the classifier, and grading it honestly

- **Run:** with no API key available, the top 500 domains were classified inside the Claude Code session,
  with the same prompt, the same evidence and the same output schema as the script. Result: 257 end organisations,
  176 hosting/ISP, 67 unsure. Cost: **65,363 tokens** (~131 per domain) on the Pro plan, no API spend.
- **Reference labels:** labelling the sample with the same scan evidence would just measure self-agreement. So the
  reference labels came from **independent evidence: each domain's live homepage** (title and description,
  `explore/fetch_homepages.py`), which the classifier never saw. 41 of 60 homepages loaded, and 40 were labelled.
  The 19 unreachable domains were left out rather than labelled from background knowledge. These reference labels
  are AI-made, not human, and are kept separate (`eval/reference_labels.csv`) from `eval/human_labels.csv`,
  which is still open for a human check.
- **Result:** the classifier answered 88% of the time; where it answered, it agreed with the homepage label
  **74%** of the time (26/35). Three of its nine misses are domains whose homepage was itself too vague to label;
  excluding them gives ~81%.
- **What the errors say:** the main failure is **hosting companies taken for end organisations** (5 of 18): a game-server
  host, a cloud/DR provider, a telecom brand, a university network that is really an ISP. Server banners show *what a
  company runs*, not *what it sells*. **Next step:** add the homepage title/description to the classifier's evidence;
  it's one cheap HTTP request per domain and is exactly the signal the errors were missing.
- **A mistake of mine during this round:** a test of the scoring step wrote fake labels into `eval/human_labels.csv`
  and then crashed. It was restored from a backup immediately (verified identical to the committed file), and the
  test was re-run against a temporary copy.

## What building it cost

- **Claude Code:** Claude Pro subscription. The whole project used about 6% of one week's allowance; the main
  conversation was ~350k tokens. No API spend during development.
- **Compute:** ~10 minutes of an 8-core laptop per 17.6 GB input file; scoring 450k companies takes ~12 seconds.
- **Hosting:** Streamlit Community Cloud, free tier.
