# Raytheon KuRFS (Ku-band Radio Frequency Sensor)

**Manufacturer:** Raytheon / RTX
**Last Updated:** March 2026
**Vendor Research:** `../../VendorResearch/Raytheon_RTX/products_and_specs.md`

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | 16000 | datasheet | Against Class I UAS |
| **min_range_m** | 50 | estimated | AESA radar |
| **reference_rcs_m2** | 0.01 | estimated | "Class I UAS" — small drone class |
| **azimuth_coverage_deg** | 360 | datasheet | Persistent 360° coverage |
| **elevation_coverage_deg** | | | Not published |
| **elevation_min_deg** | -1 | estimated | Long-range air defence AESA. See EstimationModels.md. Slider: -3 to 0. |
| **elevation_max_deg** | 70 | estimated | Air defence radar. See EstimationModels.md. Slider: +60 to +90. |
| **frequency_band** | Ku-band | datasheet | 12-18 GHz range |
| **frequency_ghz** | 15 | estimated | Ku-band centre |
| **mounting_height_m** | 6 | estimated | Mast-mounted in M-LIDS config |
| **requires_los** | true | fixed | Always true for radar |

## Detection Performance

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **scan_type** | AESA | datasheet | Active Electronically Scanned Array |
| **scan_rate_rpm** | N/A | datasheet | Electronic scan |
| **track_capacity** | 30 | datasheet | Successfully tracked 30+ target swarms |
| **update_rate_hz** | | | Not published |
| **detection_probability** | | | Not published |
| **false_alarm_rate** | | | Not published |

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

- Can detect objects as small as a 9mm bullet
- Setup time within 30 minutes
- Fixed location or vehicle-mounted deployment
- Integrated with 15+ weapon systems including Coyote, Phalanx, Phaser HPM, HELWS
- Core sensor for LIDS (both FS-LIDS and M-LIDS)
