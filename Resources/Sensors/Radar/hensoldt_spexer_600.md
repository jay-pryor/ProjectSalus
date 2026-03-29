# HENSOLDT Spexer 600

**Manufacturer:** HENSOLDT
**Last Updated:** March 2026
**Vendor Research:** `../../VendorResearch/HENSOLDT_Australia/products_and_specs.md`

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | 6000 | estimated | ~6 km against walking person. UAV-specific range not published. |
| **min_range_m** | 30 | estimated | |
| **reference_rcs_m2** | 0.5 | estimated | "Walking person" class |
| **azimuth_coverage_deg** | 120 | datasheet | Per panel |
| **elevation_coverage_deg** | | | Not published |
| **elevation_min_deg** | -3 | estimated | Mid-range AESA. See EstimationModels.md. Slider: -5 to 0. |
| **elevation_max_deg** | 45 | estimated | Mid-range between Spexer 500 and 2000. Slider: +30 to +60. |
| **frequency_band** | X-band | datasheet | AESA with SharpEye solid-state transceiver |
| **frequency_ghz** | 9.5 | estimated | X-band centre |
| **mounting_height_m** | 5 | estimated | |
| **requires_los** | true | fixed | Always true for radar |

## Detection Performance

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **scan_type** | AESA | datasheet | With SharpEye solid-state transceiver |
| **scan_rate_rpm** | N/A | datasheet | Electronic scan |
| **track_capacity** | 500 | datasheet | >500 tracks |
| **update_rate_hz** | | | Not published |
| **detection_probability** | | | Not published |
| **false_alarm_rate** | | | Not published |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | | | Not published |
| **dimensions** | | | Not published |
| **power_requirement_w** | | | Not published |
| **ip_rating** | | | Not published. Ruggedised to Mil-Std. |
| **operating_temp_c** | | | Not published |
| **cost_aud** | | | Not published |

## Notes

- MTBF: >30,000 hours
- Automatic classification in all modes
- Ruggedised to Mil-Std
- Mid-range between Spexer 500 (short range) and Spexer 2000 3D (long range)
