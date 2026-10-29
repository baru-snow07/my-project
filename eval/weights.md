# Hand-set vs learned weights

Ground truth: 56 breached servers out of 3,350,096 (compromised tag or open database).

| | AUC |
|---|---|
| Hand-set weights (used in the app) | **0.803** |
| Logistic regression, 5-fold out-of-fold | **0.785** |

| signal | hand points | learned points (rescaled) |
|---|---:|---:|
| eol | +8 | +10 |
| high_epss | +10 | +2 |
| cert_expired | +6 | +1 |
| anon_ftp | +6 | -1 |
| self_signed | +3 | -3 |
| security_txt | -10 | -4 |
| kev | +25 | -5 |
| ntlm | +5 | -14 |
| remote | +12 | -15 |
| waf | -8 | -22 |
| legacy_tls | +5 | -25 |

Learned points are the full-data model's coefficients rescaled so the largest is 25.
