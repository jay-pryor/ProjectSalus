# Anduril WISP (Wide-Area Infrared Sensing with Persistence)

**Manufacturer:** Anduril
**Last Updated:** March 2026
**Vendor Research:** `../../VendorResearch/Anduril_Australia/products_and_specs.md`

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | 16000 | datasheet | Autonomous UAV detection: 3-10 miles (5-16 km). Using upper bound. |
| **max_range_recognition_m** | 8000 | estimated | ~50% of detection range |
| **max_range_identification_m** | 5000 | estimated | ~30% of detection range |
| **min_range_m** | 0 | estimated | |
| **sensor_modality** | IR | datasheet | Passive infrared only |
| **azimuth_coverage_deg** | 360 | datasheet | |
| **is_ptz** | false | datasheet | Staring/panoramic — 360° simultaneous |
| **instantaneous_fov_h_deg** | 360 | datasheet | Full panoramic |
| **instantaneous_fov_v_deg** | 125 | datasheet | |
| **elevation_coverage_deg** | 125 | datasheet | |
| **day_night_capability** | day and night | datasheet | IR works in all lighting |
| **mounting_height_m** | 5 | estimated | Tower/mast mounted |
| **requires_los** | true | fixed | Always true for EO/IR |

## Detection Capabilities

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **resolution_megapixels** | | | Not published |
| **frame_rate_fps** | | | Not published |
| **has_autotracker** | true | datasheet | AI-powered autonomous detection |
| **has_ai_detection** | true | datasheet | Real-time AI for automated threat detection and classification |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | | | Not published |
| **dimensions** | 38 x 38 x 56 cm | datasheet | Sensor unit: 15 x 15 x 22 inches |
| **power_requirement_w** | | | Not published |
| **ip_rating** | | | Not published |
| **operating_temp_c** | | | Not published |
| **cost_aud** | | | Not published |

## Notes

- Zero RF emissions — fully passive, covert operation, undetectable
- Processor unit: 48 x 20 x 66 cm (19 x 8 x 26 inches)
- Commercial aircraft detection: ~150 km at 12,000 ft altitude
- Part of Anduril Counter-UAS Fly-Away Kit
- 360° x 125° simultaneous staring coverage is exceptional — most EO/IR sensors are narrow FOV
