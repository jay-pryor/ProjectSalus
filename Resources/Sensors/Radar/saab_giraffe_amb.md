# SAAB Giraffe AMB

**Manufacturer:** SAAB
**Last Updated:** March 2026
**Vendor Research:** `../../VendorResearch/SAAB_Australia/products_and_specs.md`

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | 100000 | estimated | Not published for land variant. Sea variant freq: 5.4-5.85 GHz, output power 25 kW. Range likely 60-120 km for aircraft. |
| **min_range_m** | 200 | estimated | |
| **reference_rcs_m2** | 5.0 | estimated | Instrumented range (~100 km) assumed against ~5 m² aircraft. See EstimationModels.md. Slider: 1-10 m². |
| **azimuth_coverage_deg** | 360 | datasheet | Rotating |
| **elevation_coverage_deg** | 70 | datasheet | 0-70 degrees |
| **elevation_min_deg** | 0 | datasheet | |
| **elevation_max_deg** | 70 | datasheet | |
| **frequency_band** | C-band | datasheet | G/H-band. Sea variant: 5.4-5.85 GHz. |
| **frequency_ghz** | 5.6 | datasheet | Sea variant: 5.4-5.85 GHz |
| **mounting_height_m** | 12 | datasheet | Hydraulically operated mast, 12m above ground |
| **requires_los** | true | fixed | Always true for radar |

## Detection Performance

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **scan_type** | Agile multi-beam (mechanical rotation + electronic elevation) | datasheet | |
| **scan_rate_rpm** | 30-60 | datasheet | 60 and 30 rpm |
| **track_capacity** | | | Not published for land variant |
| **update_rate_hz** | 1 | datasheet | 1 second target update rate |
| **detection_probability** | | | Not published |
| **false_alarm_rate** | | | Not published |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | | | Not published. Housed in 20ft ISO container. |
| **dimensions** | 20ft ISO container | datasheet | Fully self-contained cabin |
| **power_requirement_w** | | | Not published. Sea variant output power: 25 kW. |
| **ip_rating** | | | Not published |
| **operating_temp_c** | | | Not published |
| **cost_aud** | | | Not published |

## Notes

- 12 simultaneous receiver beams in elevation (Sea variant)
- Deployment time: <10 minutes
- Teardown time: <5 minutes
- Combat record: 150,000+ hours in full operation
- Hydraulically operated 12m mast
- This is a medium-range air defence radar — large system, more suited to GBAD than point cUAS
