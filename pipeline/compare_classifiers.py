"""Compare classifier versions on the same held-out reference labels. Writes eval/llm_v1_vs_v2.md.

    python pipeline/compare_classifiers.py
"""
import os
import pandas as pd

ROOT = os.path.join(os.path.dirname(__file__), '..', 'eval')
REF = pd.read_csv(os.path.join(ROOT, 'heldout_labels.csv'))
VERSIONS = {'v1: scan evidence only': 'llm_labels_v1.csv', 'v2: scan + homepage': 'llm_labels_v2.csv'}


def grade(path):
    m = REF.merge(pd.read_csv(os.path.join(ROOT, path)), on='company')
    answered = m[m['label'] != 'unsure']
    decided = answered[answered['human_label'] != 'unsure']  # both sides gave a definite answer
    return {
        'held-out domains': len(m),
        'answered (not unsure)': f"{len(answered) / len(m):.0%}",
        'accuracy where answered': f"{(answered['label'] == answered['human_label']).mean():.0%}",
        'accuracy where both decided': f"{(decided['label'] == decided['human_label']).mean():.0%} ({(decided['label'] == decided['human_label']).sum()}/{len(decided)})",
        'hosting caught (recall)': f"{((m['human_label'] == 'hosting_or_isp') & (m['label'] == 'hosting_or_isp')).sum()}/{(m['human_label'] == 'hosting_or_isp').sum()}",
    }, m


rows, merged = {}, {}
for name, path in VERSIONS.items():
    rows[name], merged[name] = grade(path)
table = pd.DataFrame(rows)
a, b = merged['v1: scan evidence only'], merged['v2: scan + homepage']
diff = a[['company', 'human_label', 'label']].merge(b[['company', 'label']], on='company', suffixes=('_v1', '_v2'))
diff = diff[diff['label_v1'] != diff['label_v2']]

lines = ['# Classifier v1 vs v2 on held-out labels\n',
         'Reference labels: `heldout_labels.csv`, from each domain\'s About/Contact page (committed before v2 existed).\n',
         table.to_markdown(), '\n## Domains where v2 changed the answer\n', diff.to_markdown(index=False)]
with open(os.path.join(ROOT, 'llm_v1_vs_v2.md'), 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines) + '\n')
print('\n'.join(lines))
