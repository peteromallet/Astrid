# Deep Assessment — 215 Judgeable Scenarios (25-agent swarm)

13 fields per scenario. Folded into workflow_scenarios_master.json → `assessment` key per entry.

## Headline stats

- avg difficulty: **4.4/10** (median 4)
- avg answer confidence: **6.2/10** (median 7)
- problem clarity avg: 7.2/10
- solution specificity avg: 5.9/10

## Grade-ability (how you'd evaluate answers)

| grade mode | count | use |
|---|---|--- |
| strict | 65 | confirmed answer = assert exact fix |
| rubric | 105 | direction stated — grade reasonableness |
| weak | 45 | thin signal — use only for realism, not scoring |

## Modality

| modality | count |
|---|--- |
| video | 95 |
| infra | 59 |
| image | 46 |
| multi | 6 |
| image+video | 4 |
| audio+video | 2 |
| video+audio | 1 |
| text | 1 |
| audio | 1 |

## Nodes type

| nodes | count |
|---|--- |
| custom-nodes | 99 |
| core-comfy | 60 |
| unclear | 42 |
| mixed | 14 |

## Failure class

| class | count |
|---|--- |
| software-bug | 73 |
| version-regression | 30 |
| wrong-setting | 24 |
| request | 23 |
| hardware-limit | 14 |
| wrong-wiring | 14 |
| quality-mystery | 14 |
| missing-component | 13 |
| unclear | 10 |

## Tech freshness

| freshness | count |
|---|--- |
| current | 195 |
| aging | 19 |
| legacy | 1 |
