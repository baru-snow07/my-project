# LLM classifier: end organisation vs hosting / ISP

Model: `claude-opus-5-5 (via Claude Code session, not the API)`, 500 domains classified.

- Reference labels: `reference_labels.csv`, **40** domains
- LLM answered (not "unsure") on **35** (88%)
- Accuracy where it answered: **74%**
- Cost: **$0.00** total, **$0.00 per 1,000 domains** (65,363 tokens in a Claude Code session)
- Note: Covered by the Claude Pro subscription; no API spend. The unattended API path (llm_classify.py classify) is estimated at $9.53 per 1,000 domains on Opus 5.5 or $0.24 on Haiku 5.5.

## Confusion (rows = human, columns = LLM)

| human_label      |   end_organisation |   hosting_or_isp |   unsure |
|:-----------------|-------------------:|-----------------:|---------:|
| end_organisation |                 14 |                1 |        3 |
| hosting_or_isp   |                  5 |               12 |        1 |
| unsure           |                  1 |                2 |        1 |


## Disagreements

| company              | human_label      | label            | reason                                                                    |
|:---------------------|:-----------------|:-----------------|:--------------------------------------------------------------------------|
| sargasso.net         | hosting_or_isp   | end_organisation | Pricing portal company                                                    |
| noraina.net          | hosting_or_isp   | unsure           | Small company network, default pages only                                 |
| visualconscience.com | unsure           | end_organisation | Small company site                                                        |
| sbin.bj              | hosting_or_isp   | end_organisation | Benin national digital infrastructure company                             |
| travel-b2b.com       | hosting_or_isp   | end_organisation | Travel B2B company                                                        |
| default.com          | end_organisation | hosting_or_isp   | Placeholder "site created" pages on Oracle Cloud, not a real organisation |
| ucsd.edu             | end_organisation | unsure           | Hosts on OVH with a gambling site: likely domain misattribution           |
| sos.org              | end_organisation | unsure           | Default pages only                                                        |
| all2all.org          | unsure           | hosting_or_isp   | Community independent network                                             |
| physgun.com          | hosting_or_isp   | end_organisation | Small game-server company                                                 |
| renu.ac.ug           | hosting_or_isp   | end_organisation | Uganda research and education network                                     |
| cybcom.net           | unsure           | hosting_or_isp   | Bulgarian provider                                                        |
| nkwintertrade.com    | end_organisation | unsure           | Single support login on a telecom network                                 |
