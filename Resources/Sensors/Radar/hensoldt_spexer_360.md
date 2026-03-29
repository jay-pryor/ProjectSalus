# HENSOLDT Spexer 360

**Manufacturer:** HENSOLDT
**Last Updated:** March 2026
**Vendor Research:** `../../VendorResearch/HENSOLDT_Australia/products_and_specs.md`

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | 1600 | datasheet | Against micro-UAV (0.03 m² RCS) |
| **min_range_m** | 20 | estimated | Pulsed radar |
| **reference_rcs_m2** | 0.03 | datasheet | Micro-UAV category |
| **azimuth_coverage_deg** | 360 | estimated | Rotating radar implied by name |
| **elevation_coverage_deg** | 22 | datasheet | -3dB beamwidth |
| **elevation_min_deg** | -2 | estimated | Ground surveillance radar. See EstimationModels.md. Slider: -5 to 0. |
| **elevation_max_deg** | 20 | estimated | 22° beamwidth centred near horizon. See EstimationModels.md. Slider: +15 to +30. |
| **frequency_band** | X-band | datasheet | Pulsed, coherent |
| **frequency_ghz** | 9.5 | estimated | X-band centre |
| **mounting_height_m** | 5 | estimated | |
| **requires_los** | true | fixed | Always true for radar |

## Detection Performance

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **scan_type** | Mechanical rotating | estimated | Implied by 360° coverage and azimuth beamwidth spec |
| **scan_rate_rpm** | | | Not published |
| **track_capacity** | | | Not published |
| **update_rate_hz** | | | Not published |
| **detection_probability** | | | Not published |
| **false_alarm_rate** | | | Not published |

## Range Table

| Target Type | RCS (m²) | Detection Range |
|-------------|----------|-----------------|
| Micro-UAV | 0.03 | 1,600 m |
| Walking person | ~0.5 | 5,600 m |
| Small vehicle | ~2.0 | 10,000 m |
| Larger vehicle | ~5.0 | 12,000 m |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | 20 | datasheet | Excluding mounting kit |
| **dimensions** | | | Not published |
| **power_requirement_w** | 150 | datasheet | Typical |
| **ip_rating** | | | Not published |
| **operating_temp_c** | | | Not published |
| **cost_aud** | | | Not published |

## Notes

- Azimuth beamwidth: ≤4.0° (-3dB)
- Peak RF power: ~80 W
- Power-up time: 25 seconds (5 seconds from standby)
- Output interface: Gigabit Ethernet
