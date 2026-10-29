# Classifier v1 vs v2 on held-out labels

Reference labels: `heldout_labels.csv`, from each domain's About/Contact page (committed before v2 existed).

|                             | v1: scan evidence only   | v2: scan + homepage   |
|:----------------------------|:-------------------------|:----------------------|
| held-out domains            | 50                       | 50                    |
| answered (not unsure)       | 94%                      | 98%                   |
| accuracy where answered     | 79%                      | 76%                   |
| accuracy where both decided | 92% (37/40)              | 90% (37/41)           |
| hosting caught (recall)     | 9/11                     | 9/11                  |

## Domains where v2 changed the answer

| company         | human_label      | label_v1         | label_v2         |
|:----------------|:-----------------|:-----------------|:-----------------|
| mobismarter.com | end_organisation | unsure           | end_organisation |
| ritesim.com     | unsure           | unsure           | hosting_or_isp   |
| teambox.fr      | end_organisation | end_organisation | hosting_or_isp   |
| imatel.es       | unsure           | end_organisation | hosting_or_isp   |
