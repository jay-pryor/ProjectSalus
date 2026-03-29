# HENSOLDT TAROSS

**Manufacturer:** HENSOLDT
**Last Updated:** March 2026
**Vendor Research:** `../../VendorResearch/HENSOLDT_Australia/products_and_specs.md`

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | 5000 | estimated | Target acquisition system. Range varies by variant. Not published for UAS. |
| **max_range_recognition_m** | 3000 | estimated | |
| **max_range_identification_m** | 1500 | estimated | |
| **min_range_m** | 0 | estimated | |
| **sensor_modality** | EO/IR | datasheet | All variants have Full HD daylight + thermal |
| **azimuth_coverage_deg** | 360 | estimated | Targeting turret, assumed continuous rotation |
| **is_ptz** | true | estimated | Targeting turret |
| **instantaneous_fov_h_deg** | 20 | estimated | Similar military sighting systems: 15-30° wide FOV. See EstimationModels.md. Slider: 5-30°. |
| **instantaneous_fov_v_deg** | 15 | estimated | Typically ~75% of horizontal FOV. Slider: 3-25°. |
| **elevation_coverage_deg** | 90 | estimated | Target acquisition turret, -10 to +80° assumed. Slider: 60-120°. |
| **day_night_capability** | day and night | datasheet | Daylight + thermal on all variants |
| **mounting_height_m** | 3 | estimated | Vehicle-mounted |
| **requires_los** | true | fixed | Always true for EO/IR |

## Detection Capabilities

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **resolution_megapixels** | 2 | datasheet | Full HD |
| **frame_rate_fps** | | | Not published |
| **has_autotracker** | true | estimated | Target acquisition system |
| **has_ai_detection** | | | Not specified |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | 10.5 | datasheet | 9-12 kg across all variants |
| **dimensions** | | | Not published |
| **power_requirement_w** | | | Not published |
| **ip_rating** | | | Not published |
| **operating_temp_c** | | | Not published |
| **cost_aud** | | | Not published |

## Notes

- Three variants: Short Range, Medium Range, Long Range
- Short/Medium range: uncooled LWIR thermal
- Long range: cooled MWIR thermal (better performance, higher cost)
- All variants include laser rangefinder
- NGVA-ready (all variants)
- Mass: 9-12 kg — lightweight enough for small vehicles
