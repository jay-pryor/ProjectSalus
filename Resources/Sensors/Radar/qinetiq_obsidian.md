# QinetiQ Obsidian Counter-Drone Radar

**Manufacturer:** QinetiQ
**Last Updated:** March 2026
**Vendor Research:** `../../VendorResearch/QinetiQ/products_and_specs.md`

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | 2000 | datasheet | Against UAVs <20 kg. Extended range up to 3,500 m. |
| **min_range_m** | 20 | datasheet | |
| **reference_rcs_m2** | 0.01 | estimated | "UAVs <20 kg" — DJI Mavic class |
| **azimuth_coverage_deg** | 180 | datasheet | Per unit. 360° with paired radars. |
| **elevation_coverage_deg** | 90 | datasheet | With paired radars |
| **elevation_min_deg** | -2 | estimated | Ground-based staring array. See EstimationModels.md. Slider: -5 to 0. |
| **elevation_max_deg** | 45 | estimated | 90° paired (45° per unit). See EstimationModels.md. Slider: +30 to +60. |
| **frequency_band** | X-band | datasheet | FMCW |
| **frequency_ghz** | 9.5 | estimated | X-band centre |
| **mounting_height_m** | 3 | estimated | Ground-based system |
| **requires_los** | true | fixed | Always true for radar |

## Detection Performance

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **scan_type** | Staring array | datasheet | 80+ static antenna beams, no spinning or electronic scanning |
| **scan_rate_rpm** | N/A | datasheet | Staring — all beams active simultaneously |
| **track_capacity** | 100 | datasheet | 100+ simultaneous targets |
| **update_rate_hz** | 2 | datasheet | 0.5 second update rate |
| **detection_probability** | | | Not published |
| **false_alarm_rate** | | | Not published |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | 45 | datasheet | <45 kg per unit |
| **dimensions** | 80 x 49 x 56.5 cm | datasheet | Per unit (W x D x H) |
| **power_requirement_w** | | | Not published |
| **ip_rating** | | | Not published |
| **operating_temp_c** | -46 to unknown | datasheet | Min steady-state: -46°C, cold start: -40°C. Max not published. |
| **cost_aud** | | | Not published |

## Notes

- Minimum detectable velocity: 0.5 m/s
- Staring array architecture is unique — no moving parts or electronic beam steering
- 7 km detection bubble diameter with paired radars
- Optimised for detecting small motor/rotor blade Doppler signatures
