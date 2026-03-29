# SAAB Giraffe 4A

**Manufacturer:** SAAB
**Last Updated:** March 2026
**Vendor Research:** `../../VendorResearch/SAAB_Australia/products_and_specs.md`

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | 400000 | datasheet | Instrumented range (land variant). Not a cUAS-relevant range. |
| **min_range_m** | | | Not published |
| **reference_rcs_m2** | 5.0 | estimated | Instrumented range (400 km) assumed against ~5 m² aircraft. See EstimationModels.md. Slider: 1-10 m². |
| **azimuth_coverage_deg** | 360 | datasheet | Or sector mode |
| **elevation_coverage_deg** | 70 | datasheet | Greater than 70° |
| **elevation_min_deg** | -1 | estimated | Air defence radar. See EstimationModels.md. Slider: -3 to 0. |
| **elevation_max_deg** | 70 | datasheet | |
| **frequency_band** | S-band | datasheet | |
| **frequency_ghz** | 3 | estimated | S-band centre |
| **mounting_height_m** | 8 | estimated | Vehicle/trailer with mast |
| **requires_los** | true | fixed | Always true for radar |

## Detection Performance

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **scan_type** | AESA | datasheet | 3D AESA, GaN |
| **scan_rate_rpm** | 30-60 | datasheet | 30 or 60 rpm |
| **track_capacity** | 1000 | datasheet | Sea variant: >1000 air + >500 surface |
| **update_rate_hz** | 1-8 | datasheet | 1s in 360° mode, up to 8 Hz in sector mode |
| **detection_probability** | | | Not published |
| **false_alarm_rate** | | | Not published |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | | | Not published (airliftable in single C-130) |
| **dimensions** | | | Not published |
| **power_requirement_w** | 40000 | datasheet | Sea variant: 40 kW |
| **ip_rating** | | | Not published |
| **operating_temp_c** | | | Not published |
| **cost_aud** | | | Not published |

## Notes

- Deployment time: <10 minutes with 2 personnel
- Airliftable in a single C-130 load
- GaN semiconductor technology
- Data interface: Ethernet
- This is an air defence radar — likely overkill for cUAS-only sites but relevant for layered defence configurations
- Sea Giraffe 4A variant: 350 km instrumented range
