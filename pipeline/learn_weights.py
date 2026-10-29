"""Can the scoring weights be learned from the data instead of set by hand?

Fits a logistic regression on per-server signals against the only ground truth in the data
(servers already breached: compromised tag or open database), with 5-fold cross-validation,
and compares its out-of-fold AUC to the hand-set weights from build.py. Writes eval/weights.md.

    python pipeline/learn_weights.py
"""
import os
import duckdb
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold

ROOT = os.path.join(os.path.dirname(__file__), '..')
ROWS = os.path.join(ROOT, 'data', 'rows', '*[0-9].parquet').replace('\\', '/')
OUT = os.path.join(ROOT, 'eval', 'weights.md')

# Same signals and hand weights as evaluate.py / build.py (breach signals excluded: they are the label).
HAND = {'kev': 25, 'high_epss': 10, 'remote': 12, 'eol': 8, 'cert_expired': 6, 'legacy_tls': 5,
        'self_signed': 3, 'anon_ftp': 6, 'ntlm': 5, 'waf': -8, 'security_txt': -10}

hosts = duckdb.sql(f"""
    SELECT bool_or(compromised OR unauth_data)::INT AS y,
        bool_or(n_kev > 0)::INT AS kev, bool_or(n_high_epss > 0)::INT AS high_epss,
        bool_or(len(list_intersect(exposed, ['rdp', 'smb', 'telnet', 'vnc'])) > 0)::INT AS remote,
        bool_or(eol)::INT AS eol, bool_or(cert_expired)::INT AS cert_expired, bool_or(legacy_tls)::INT AS legacy_tls,
        bool_or(self_signed)::INT AS self_signed, bool_or(anon_ftp)::INT AS anon_ftp, bool_or(ntlm_leak)::INT AS ntlm,
        bool_or(waf IS NOT NULL)::INT AS waf, bool_or(security_txt)::INT AS security_txt
    FROM (SELECT DISTINCT ON (ip, port) * FROM '{ROWS}' WHERE NOT edge) GROUP BY ip""").df()

X, y = hosts[list(HAND)].to_numpy(float), hosts['y'].to_numpy()
hand_score = X @ np.array(list(HAND.values()), float)

# Out-of-fold predictions: each server is scored by a model that never saw it.
oof = np.zeros(len(y))
folds = StratifiedKFold(5, shuffle=True, random_state=42)
for train, test in folds.split(X, y):
    m = LogisticRegression(class_weight='balanced', C=0.5, max_iter=1000).fit(X[train], y[train])
    oof[test] = m.decision_function(X[test])
hand_auc, learned_auc = roc_auc_score(y, hand_score), roc_auc_score(y, oof)

full = LogisticRegression(class_weight='balanced', C=0.5, max_iter=1000).fit(X, y)
coef = dict(zip(HAND, full.coef_[0]))
# Rescale learned coefficients to the same points scale as the hand weights (largest = 25).
scale = 25 / max(abs(v) for v in coef.values())

lines = ['# Hand-set vs learned weights\n',
         f'Ground truth: {int(y.sum())} breached servers out of {len(y):,} (compromised tag or open database).\n',
         '| | AUC |', '|---|---|',
         f'| Hand-set weights (used in the app) | **{hand_auc:.3f}** |',
         f'| Logistic regression, 5-fold out-of-fold | **{learned_auc:.3f}** |\n',
         '| signal | hand points | learned points (rescaled) |', '|---|---:|---:|']
lines += [f'| {k} | {HAND[k]:+d} | {coef[k] * scale:+.0f} |' for k in sorted(HAND, key=lambda k: -coef[k])]
lines += ['\nLearned points are the full-data model\'s coefficients rescaled so the largest is 25.']
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines) + '\n')
print('\n'.join(lines))
