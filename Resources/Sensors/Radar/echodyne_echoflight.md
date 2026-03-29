# Echodyne EchoFlight

**Manufacturer:** Echodyne
**Last Updated:** March 2026
**Vendor Research:** `../../VendorResearch/Echodyne/products_and_specs.md`

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | 750 | datasheet | Against small quadcopter. 2 km against Cessna class. |
| **min_range_m** | 10 | estimated | MESA type |
| **reference_rcs_m2** | 0.01 | estimated | "Small quadcopter" |
| **azimuth_coverage_deg** | 120 | estimated | Same MESA technology as EchoGuard |
| **elevation_coverage_deg** | 80 | estimated | Same MESA technology |
| **elevation_min_deg** | -5 | estimated | Airborne MESA, same family as EchoGuard. Slider: -10 to 0. |
| **elevation_max_deg** | 70 | estimated | ~80° total FOV estimated from EchoGuard. Slider: +60 to +80. |
| **frequency_band** | K-band | estimated | Same MESA family as EchoGuard |
| **frequency_ghz** | 24.5 | estimated | Same band as EchoGuard |
| **mounting_height_m** | 0 | estimated | Airborne — mounted on drone platform |
| **requires_los** | true | fixed | Always true for radar |

## Detection Performance

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **scan_type** | AESA (MESA) | datasheet | |
| **scan_rate_rpm** | N/A | datasheet | Electronic scan |
| **track_capacity** | | | Not published |
| **update_rate_hz** | | | Not published |
| **detection_probability** | | | Not published |
| **false_alarm_rate** | | | Not published |

## Range Table

| Target Type | RCS (m²) | Detection Range |
|-------------|----------|-----------------|
| Small quadcopter | ~0.01 | 750 m |
| Small aircraft (Cessna) | ~1.0 | 2,000 m |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | 0.817 | datasheet | Natural convection cooling |
| **dimensions** | 18.7 x 12 x 4 cm | datasheet | |
| **power_requirement_w** | 45 | datasheet | Operating. <10 W hot standby. |
| **ip_rating** | IP67 | datasheet | |
| **operating_temp_c** | -40 to +75 | datasheet | |
| **cost_aud** | | | Not published |

## Notes

- Designed for airborne platforms (interceptor drones, DAA systems)
- Fitted on AATI AiRanger UAS wings
- Used as targeting radar on airborne interceptor platforms
- Smallest/lightest in MESA family
- Input voltage: +12V to +28V DC
- Relevant for modelling interceptor drone cueing (e.g. Anvil-class systems)
