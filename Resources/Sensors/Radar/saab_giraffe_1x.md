# SAAB Giraffe 1X

**Manufacturer:** SAAB
**Last Updated:** March 2026
**Vendor Research:** `../../VendorResearch/SAAB_Australia/products_and_specs.md`

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | 75000 | datasheet | Instrumented range. Actual UAS detection range much shorter — not published. |
| **min_range_m** | 100 | estimated | |
| **reference_rcs_m2** | 5.0 | estimated | Instrumented range (75 km) assumed against ~5 m² aircraft. See EstimationModels.md for UAS range derivation. Slider: 1-10 m². |
| **azimuth_coverage_deg** | 360 | datasheet | |
| **elevation_coverage_deg** | | | Not published |
| **elevation_min_deg** | -1 | estimated | Air defence AESA. See EstimationModels.md. Slider: -3 to 0. |
| **elevation_max_deg** | 70 | estimated | Air defence radar. See EstimationModels.md. Slider: +60 to +90. |
| **frequency_band** | X-band | datasheet | 8-12 GHz, NATO I-band |
| **frequency_ghz** | 10 | estimated | X-band centre |
| **mounting_height_m** | 5 | estimated | Vehicle/trailer mounted |
| **requires_los** | true | fixed | Always true for radar |

## Detection Performance

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **scan_type** | AESA | datasheet | 3D AESA, GaN semiconductor |
| **scan_rate_rpm** | N/A | datasheet | Electronic scan |
| **track_capacity** | | | Not published |
| **update_rate_hz** | 1 | datasheet | Full search volume every 1 second |
| **detection_probability** | | | Not published |
| **false_alarm_rate** | | | Not published |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | 150 | datasheet | Total system <150 kg. Topside unit ~100 kg. |
| **dimensions** | | | Not published |
| **power_requirement_w** | | | Not published |
| **ip_rating** | | | Not published |
| **operating_temp_c** | | | Not published |
| **cost_aud** | | | Not published |

## Notes

- GaN (Gallium Nitride) semiconductor technology
- Transportable by pickup truck, helicopter, or towed trailer
- Part of SAAB MSHORAD solution (with RBS 70 NG)
- Max detection ~180 km for large aircraft; small UAS detection range not explicitly published
- Needs UAS-specific range data from vendor engagement or estimation via radar range equation
