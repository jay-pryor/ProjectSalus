# HENSOLDT Spexer 500

**Manufacturer:** HENSOLDT
**Last Updated:** March 2026
**Vendor Research:** `../../VendorResearch/HENSOLDT_Australia/products_and_specs.md`

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | 5000 | datasheet | Against walking person. UAV range not explicitly stated. |
| **min_range_m** | 100 | datasheet | 0.1 km instrumented minimum |
| **reference_rcs_m2** | 0.01 | datasheet | Minimum detectable RCS: <0.01 m² |
| **azimuth_coverage_deg** | 120 | datasheet | No mechanical movement |
| **elevation_coverage_deg** | | | Not published |
| **elevation_min_deg** | -5 | estimated | Short-range cUAS AESA. See EstimationModels.md. Slider: -10 to 0. |
| **elevation_max_deg** | 60 | estimated | cUAS-optimised, needs overhead. See EstimationModels.md. Slider: +45 to +75. |
| **frequency_band** | X-band | datasheet | FMCW |
| **frequency_ghz** | 9.5 | estimated | X-band centre |
| **mounting_height_m** | 5 | estimated | |
| **requires_los** | true | fixed | Always true for radar |

## Detection Performance

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **scan_type** | AESA (digital beamforming) | datasheet | FMCW with flat phased-array antenna |
| **scan_rate_rpm** | N/A | datasheet | Electronic scan, no rotation |
| **track_capacity** | | | Not published |
| **update_rate_hz** | 0.67 | datasheet | <1.5s for 120° sector |
| **detection_probability** | | | Not published |
| **false_alarm_rate** | | | Not published |

## Range Table

| Target Type | RCS (m²) | Detection Range |
|-------------|----------|-----------------|
| Walking person | ~0.5 | ~5,000 m |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | | | Not published |
| **dimensions** | | | Not published |
| **power_requirement_w** | | | Not published |
| **ip_rating** | | | Not published |
| **operating_temp_c** | | | Not published |
| **cost_aud** | | | Not published |

## Notes

- Instrumented range: 0.1-9 km
- Key component of HENSOLDT XPELLER system (with 4W RF output variant)
- Minimum detectable RCS <0.01 m² makes it suitable for small drone detection
