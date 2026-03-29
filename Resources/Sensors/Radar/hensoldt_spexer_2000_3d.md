# HENSOLDT Spexer 2000 3D MkIII

**Manufacturer:** HENSOLDT
**Last Updated:** March 2026
**Vendor Research:** `../../VendorResearch/HENSOLDT_Australia/products_and_specs.md`

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | 9000 | datasheet | Against small UAV (0.2 m² RCS) |
| **min_range_m** | 50 | estimated | Pulsed AESA, estimated |
| **reference_rcs_m2** | 0.2 | datasheet | "Small UAV" category |
| **azimuth_coverage_deg** | 120 | datasheet | Per panel; 360° with 4 panels |
| **elevation_coverage_deg** | 90 | datasheet | Per panel |
| **elevation_min_deg** | -2 | estimated | Medium-range AESA, 90° total. See EstimationModels.md. Slider: -5 to 0. |
| **elevation_max_deg** | 85 | estimated | 90° total coverage. See EstimationModels.md. Slider: +80 to +90. |
| **frequency_band** | X-band | datasheet | 9.2-10 GHz |
| **frequency_ghz** | 9.6 | estimated | Centre of 9.2-10 GHz range |
| **mounting_height_m** | 5 | estimated | Mast/vehicle typical |
| **requires_los** | true | fixed | Always true for radar |

## Detection Performance

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **scan_type** | AESA | datasheet | Pulse-Doppler |
| **scan_rate_rpm** | N/A | datasheet | Electronic scan |
| **track_capacity** | 300 | datasheet | Per 120° sector |
| **update_rate_hz** | 3.3 | datasheet | Fastest: 0.3s update rate |
| **detection_probability** | | | Not published |
| **false_alarm_rate** | | | Not published |

## Range Table

| Target Type | RCS (m²) | Detection Range |
|-------------|----------|-----------------|
| Small UAV | 0.2 | ~9 km |
| Pedestrian | 0.5 | ~18-20 km |
| Small boat | 1.5 | ~20 km |
| Light vehicle | 2.0 | ~22 km |
| Light aircraft | 3.0 | ~27 km |
| Low-flying aircraft | 5.0 | ~36 km |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | 35 | datasheet | MkIII antenna only. GPU unit adds 40 kg. |
| **dimensions** | 600 x 500 x 200 mm | datasheet | MkIII antenna. Previous gen: 1000 x 700 x 200 mm (73 kg). |
| **power_requirement_w** | | | Not published |
| **ip_rating** | | | Not published |
| **operating_temp_c** | | | Not published |
| **cost_aud** | | | Not published |

## Notes

- Bandwidth: 15 MHz, >100 channels
- Up to 16 simultaneous beams (max instrumented range of 2.5 km in this mode, vs 40 km single beam)
- Scan on the move capability
- GPU (RFU + Radar Processor): 600 x 400 x 300 mm, 40 kg
- Key component of HENSOLDT XPELLER and Elysion C-UAS systems
