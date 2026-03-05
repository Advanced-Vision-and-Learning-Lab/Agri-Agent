# Discovery Report (Sorghum over time)

## Summary
- **Timepoints:** 14
- **Date range:** 2024-12-04 → 2025-05-08
- **Signals used:** morph_area_cm2, morph_height_cm, morph_skeleton_cm, veg_NDRE_mean, veg_NDVI_mean, tex_lac1_mean, tex_ehd_mean

## Evidence overview
- **evidence_timeseries_csv**: discovery_output_sorghumO_chatgpt/evidence_timeseries.csv
- **agent_transcript_jsonl**: discovery_output_sorghumO_chatgpt/agent_transcript.jsonl

## QC flags (top)
No QC flags.

## Change points (top)
| date | column | kind | magnitude | z |
|---|---|---|---|---|
| 2025-01-13 | veg__NDVI__statistics__mean | drop | -0.05946142096314069 | -11.370739394251517 |
| 2025-03-03 | veg__NDVI__statistics__mean | rise | 0.037377485050015896 | 7.147653635450799 |
| 2025-03-24 | veg__NDVI__statistics__mean | drop | -0.031195227157323868 | -5.96542754284814 |
| 2024-12-16 | veg__NDVI__statistics__mean | drop | -0.028638379319977092 | -5.47648446079082 |
| 2025-01-13 | morph__area_cm2 | drop | -860.4890329499999 | -5.409985862393965 |
| 2025-01-24 | veg__NDRE__statistics__mean | rise | 0.01808273582642339 | 4.914775234279737 |
| 2025-03-03 | veg__NDRE__statistics__mean | drop | -0.017419794022906457 | -4.734591771502345 |
| 2025-01-24 | morph__area_cm2 | drop | -645.0128720549997 | -4.055264373232795 |
| 2025-01-13 | morph__height_cm | rise | 15.289799999999985 | 3.985681818181756 |
| 2025-03-03 | morph__skeleton_length_cm | drop | -204.61349999999993 | -3.808941176470589 |
| 2025-03-03 | morph__area_cm2 | drop | -605.2746593700001 | -3.8054260131950977 |
| 2025-03-03 | tex__pca__statistics__ehd_map__mean | rise | 0.08747842776729353 | 3.6813276729559123 |
| 2025-05-08 | tex__pca__statistics__lac1__mean | drop | -14.398169679742672 | -3.506210701001454 |

## Lag relationships (top)
| lead_signal | response_signal | lag_days | corr | n |
|---|---|---|---|---|
| NDVI_mean | d/dt height_cm | 5 | -0.7326398398656955 | 145 |
| NDVI_mean | d/dt area_cm2 | 3 | 0.6363276175447318 | 147 |
| NDRE_mean | d/dt area_cm2 | -10 | -0.6256587402836026 | 140 |
| NDRE_mean | d/dt skeleton_cm | 9 | -0.38509175593430445 | 141 |
| NDVI_mean | d/dt skeleton_cm | -6 | -0.32393889018989164 | 144 |
| NDRE_mean | d/dt height_cm | -2 | 0.1963397272510769 | 148 |

## Agent lab outputs
- **LLM available:** True

### QC Agent (round1)
- **Drop in NDVI Mean** (conf=0.85)
  - A significant drop in the NDVI mean was observed on 2025-01-13, which may indicate a potential issue with vegetation health or mask quality.
- **Drop in Morph Area** (conf=0.75)
  - A notable drop in morph area was recorded on 2025-01-13, which could suggest extraction failure or mask issues.
- **Drop in NDVI Mean on 2025-03-24** (conf=0.75)
  - Another drop in NDVI mean was observed on 2025-03-24, which may indicate ongoing issues with vegetation health.

### Event Discovery Agent (round1)
- **Stress Onset Detected** (conf=0.85)
  - A significant drop in NDVI mean was observed on 2025-01-13, indicating a potential stress onset.
- **Recovery Phase Indicated** (conf=0.75)
  - A rise in NDVI mean was observed on 2025-03-03, suggesting a recovery phase.
- **Phase Transition Detected** (conf=0.7)
  - A drop in NDVI mean was noted on 2025-03-24, indicating a potential phase transition.

### Mechanism Agent (round1)
- **NDVI_mean leads d/dt height_cm** (conf=0.7326)
  - NDVI_mean is consistent with leading d/dt height_cm by 5 days with a correlation of -0.7326.
- **NDVI_mean leads d/dt area_cm2** (conf=0.6363)
  - NDVI_mean is consistent with leading d/dt area_cm2 by 3 days with a correlation of 0.6363.
- **NDRE_mean leads d/dt area_cm2** (conf=0.6257)
  - NDRE_mean is consistent with leading d/dt area_cm2 by -10 days with a correlation of -0.6257.

### Reporter Agent (round2)
- **Significant Drop in NDVI Mean on 2025-01-13** (conf=0.85)
  - A significant drop in NDVI mean was observed on 2025-01-13, indicating potential stress onset in vegetation health.
- **Drop in Morph Area on 2025-01-13** (conf=0.75)
  - A notable drop in morph area was recorded on 2025-01-13, which may suggest extraction failure or mask issues.
- **Drop in NDVI Mean on 2025-03-24** (conf=0.75)
  - Another drop in NDVI mean was observed on 2025-03-24, indicating ongoing issues with vegetation health.

## Next steps
- If any QC flags exist, manually inspect overlay.png for those dates and consider re-running segmentation.
- Increase sampling density (more dates) to improve change-point and lag detection reliability.
- Add a robustness check: recompute lags after dropping one timepoint at a time.
