# [Product Name]

**Manufacturer:** [Vendor]
**Last Updated:** [Date]
**Vendor Research:** [Link to VendorResearch file, e.g. `../../VendorResearch/Echodyne/products_and_specs.md`]

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | | | Range against what RCS? |
| **min_range_m** | | | Blind zone |
| **reference_rcs_m2** | | | RCS target that max_range is quoted against |
| **azimuth_coverage_deg** | | | 360 for rotating, 90-120 for sector |
| **elevation_coverage_deg** | | | Total vertical span |
| **elevation_min_deg** | | | Below horizon |
| **elevation_max_deg** | | | Above horizon |
| **frequency_band** | | | X-band, Ku-band, S-band, etc. |
| **frequency_ghz** | | | Centre frequency |
| **mounting_height_m** | | | Typical install height AGL |
| **requires_los** | true | fixed | Always true for radar |

## Detection Performance

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **scan_type** | | | Mechanical / AESA / PESA / hybrid |
| **scan_rate_rpm** | | | For rotating radars |
| **track_capacity** | | | Max simultaneous tracks |
| **update_rate_hz** | | | Track update rate |
| **detection_probability** | | | Pd at max range vs reference RCS |
| **false_alarm_rate** | | | Pfa |

## Range Table (if available)

| Target Type | RCS (m²) | Detection Range |
|-------------|----------|-----------------|
| | | |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | | | |
| **dimensions** | | | |
| **power_requirement_w** | | | |
| **ip_rating** | | | |
| **operating_temp_c** | | | Min to max |
| **cost_aud** | | | |

## Notes

-
