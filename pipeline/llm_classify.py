"""Use Claude to tell real organisations from hosting / ISP businesses, and measure if it is right.

The rules in build.py leave some hosting companies (nazwa.pl, keymachine.de) in the top list.
This asks Claude to classify the top N companies from the evidence we already have, logs the
exact token usage and cost, and scores the answers against a human-labelled sample.

    python pipeline/llm_classify.py label-sheet            # 1. write eval/human_labels.csv to fill in by hand
    python pipeline/llm_classify.py classify --dry-run     # 2. show the prompt and estimated cost, no API call
    python pipeline/llm_classify.py classify               # 3. run it (needs ANTHROPIC_API_KEY)
    python pipeline/llm_classify.py score                  # 4. accuracy vs human labels, cost per 1,000 domains

Options: --top N (default 500), --model (default claude-opus-5-5; claude-haiku-5-5 is the cheap option).
"""
import argparse, csv, json, os, sys, time
from typing import Literal

import pandas as pd
from pydantic import BaseModel

ROOT = os.path.join(os.path.dirname(__file__), '..')
COMPANIES = os.path.join(ROOT, 'app', 'data', 'companies.parquet')
EVIDENCE = os.path.join(ROOT, 'app', 'data', 'evidence.parquet')
OUT = os.path.join(ROOT, 'eval', 'llm_labels.csv')
HUMAN = os.path.join(ROOT, 'eval', 'human_labels.csv')
USAGE = os.path.join(ROOT, 'eval', 'llm_usage.json')

# USD per million tokens (input, output), Anthropic first-party API, as of 2026-10.
PRICES = {'claude-opus-5-5': (4.00, 20.00), 'claude-sonnet-5-5': (2.00, 10.00), 'claude-haiku-5-5': (0.10, 0.50)}

SYSTEM = """You classify internet domains for a cybersecurity sales team.
Decide whether the domain belongs to an END ORGANISATION that runs its own systems (a company, university,
government body, hospital, non-profit), or to a HOSTING / ISP business whose servers mostly belong to its
customers (web hosts, VPS/cloud providers, ISPs, telecoms, dynamic-DNS services, domain parking).
A hosting company's own corporate site still counts as hosting_or_isp.
Use only the evidence given. If the evidence is too thin to tell, answer "unsure"."""


class Verdict(BaseModel):
    label: Literal['end_organisation', 'hosting_or_isp', 'unsure']
    confidence: Literal['high', 'medium', 'low']
    reason: str  # one short sentence citing the evidence


def candidates(top):
    df = pd.read_parquet(COMPANIES, columns=['company', 'risk_score', 'network_org', 'country', 'ips', 'web_title', 'tech'])
    df = df.sort_values('risk_score', ascending=False).head(top)
    ev = pd.read_parquet(EVIDENCE)
    software = ev.groupby('company')['software'].apply(lambda s: sorted(set(s.dropna()))[:6])
    df['software'] = df['company'].map(software)
    return df


def prompt_for(row):
    sw = row['software'] if isinstance(row['software'], list) else []
    return (f"Domain: {row['company']}\n"
            f"Network owner of most of its IPs: {row['network_org']}\n"
            f"Country: {row['country']}\n"
            f"Internet-facing IPs seen: {int(row['ips'])}\n"
            f"A website title on its servers: {row['web_title'] if isinstance(row['web_title'], str) else '(none)'}\n"
            f"Web technologies seen: {', '.join(list(row['tech'])[:10]) or '(none)'}\n"
            f"Server software seen: {', '.join(sw) or '(none)'}")


def label_sheet(top, n=60):
    """A random sample of the top N for a human to label, blind to the LLM's answers."""
    df = candidates(top).sample(n, random_state=7)
    df.assign(human_label='')[['company', 'network_org', 'country', 'ips', 'web_title', 'human_label']].to_csv(HUMAN, index=False)
    print(f'wrote {HUMAN}: fill human_label with end_organisation / hosting_or_isp / unsure for each row.\n'
          'Tip: open each domain\'s website. Do not look at eval/llm_labels.csv first.')


def classify(top, model, dry_run):
    df = candidates(top)
    price_in, price_out = PRICES[model]
    if dry_run:
        example = prompt_for(df.iloc[0])
        est_in = (len(SYSTEM) + len(example)) / 4 + 150  # ~4 chars per token, plus schema overhead
        est_out = 400  # short JSON verdict plus thinking (thinking is always on for Opus 5.5)
        print(f'model {model}, {len(df)} domains\n\n--- system ---\n{SYSTEM}\n\n--- example user message ---\n{example}\n')
        print(f'estimated ~{est_in:.0f} input + ~{est_out} output tokens per domain')
        print(f'estimated cost: ${len(df) * (est_in * price_in + est_out * price_out) / 1e6:.2f} for {len(df)} domains '
              f'(${1000 * (est_in * price_in + est_out * price_out) / 1e6:.2f} per 1,000)')
        return

    import anthropic
    client = anthropic.Anthropic()
    done = set(pd.read_csv(OUT)['company']) if os.path.exists(OUT) else set()
    usage = json.load(open(USAGE)) if os.path.exists(USAGE) else {'model': model, 'input_tokens': 0, 'output_tokens': 0, 'calls': 0}
    new_file = not os.path.exists(OUT)
    with open(OUT, 'a', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(['company', 'label', 'confidence', 'reason'])
        for i, (_, row) in enumerate(df.iterrows()):
            if row['company'] in done:
                continue  # resumable: skip domains already classified
            try:
                resp = client.messages.parse(
                    model=model, max_tokens=4000,
                    output_config={'effort': 'low'},
                    system=SYSTEM,
                    messages=[{'role': 'user', 'content': prompt_for(row)}],
                    output_format=Verdict,
                )
            except anthropic.RateLimitError:
                time.sleep(30); continue
            except anthropic.APIStatusError as e:
                print(f"{row['company']}: API error {e.status_code}"); continue
            usage['input_tokens'] += resp.usage.input_tokens
            usage['output_tokens'] += resp.usage.output_tokens
            usage['calls'] += 1
            if resp.stop_reason == 'refusal' or resp.parsed_output is None:
                w.writerow([row['company'], 'unsure', 'low', f'no answer ({resp.stop_reason})'])
            else:
                v = resp.parsed_output
                w.writerow([row['company'], v.label, v.confidence, v.reason])
            f.flush()
            if i % 25 == 0:
                print(f'{i}/{len(df)}')
    usage['cost_usd'] = round((usage['input_tokens'] * price_in + usage['output_tokens'] * price_out) / 1e6, 4)
    usage['cost_per_1000_domains'] = round(usage['cost_usd'] / max(usage['calls'], 1) * 1000, 2)
    with open(USAGE, 'w') as f:
        json.dump(usage, f, indent=1)
    print(json.dumps(usage, indent=1))


def score():
    llm = pd.read_csv(OUT)
    human = pd.read_csv(HUMAN, dtype={'human_label': str}).dropna(subset=['human_label'])
    human = human.assign(human_label=human['human_label'].str.strip().str.lower())
    human = human[human['human_label'] != '']
    m = human.merge(llm, on='company')
    if m.empty:
        sys.exit('No overlap yet: fill eval/human_labels.csv and run classify first.')
    confident = m[m['label'] != 'unsure']
    acc = (confident['label'] == confident['human_label']).mean()
    usage = json.load(open(USAGE)) if os.path.exists(USAGE) else {}
    report = [
        '# LLM classifier: end organisation vs hosting / ISP\n',
        f"Model: `{usage.get('model', '?')}`, {usage.get('calls', '?')} domains classified.\n",
        f'- Human-labelled sample: **{len(m)}** domains',
        f"- LLM answered (not \"unsure\") on **{len(confident)}** ({len(confident) / len(m):.0%})",
        f'- Accuracy where it answered: **{acc:.0%}**',
        f"- Cost: **${usage.get('cost_usd', 0):.2f}** total, **${usage.get('cost_per_1000_domains', 0):.2f} per 1,000 domains** "
        + (f"({usage['input_tokens']:,} input + {usage['output_tokens']:,} output tokens)" if 'input_tokens' in usage
         else f"({usage.get('context_tokens_used', 0):,} tokens in a Claude Code session)"),
        f"- Note: {usage['note']}\n" if usage.get('note') else '',
        '## Confusion (rows = human, columns = LLM)\n',
        pd.crosstab(m['human_label'], m['label']).to_markdown(), '\n',
        '## Disagreements\n',
        m[m['label'] != m['human_label']][['company', 'human_label', 'label', 'reason']].to_markdown(index=False),
    ]
    path = os.path.join(ROOT, 'eval', 'llm_report.md')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report) + '\n')
    print('\n'.join(report))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('step', choices=['label-sheet', 'classify', 'score'])
    ap.add_argument('--top', type=int, default=500)
    ap.add_argument('--model', default='claude-opus-5-5', choices=list(PRICES))
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    if a.step == 'label-sheet': label_sheet(a.top)
    elif a.step == 'classify': classify(a.top, a.model, a.dry_run)
    else: score()
