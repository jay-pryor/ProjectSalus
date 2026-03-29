# [Product Name]

**Manufacturer:** [Vendor]
**Last Updated:** [Date]
**Vendor Research:** [Link to VendorResearch file]

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | | | Detection range. Against what target size? |
| **max_range_recognition_m** | | | Recognition range (DRI criteria) |
| **max_range_identification_m** | | | Identification range (DRI criteria) |
| **min_range_m** | | | |
| **sensor_modality** | | | "EO" / "IR" / "EO/IR" / "SWIR" |
| **azimuth_coverage_deg** | | | Fixed FOV or pan range? See is_ptz. |
| **is_ptz** | | | If true, use instantaneous_fov not azimuth_coverage for coverage modelling |
| **instantaneous_fov_h_deg** | | | Actual FOV at any moment. CRITICAL if PTZ. |
| **instantaneous_fov_v_deg** | | | Vertical FOV |
| **elevation_coverage_deg** | | | Total elevation range |
| **day_night_capability** | | | "day only" / "night only" / "day and night" |
| **mounting_height_m** | | | |
| **requires_los** | true | fixed | Always true for EO/IR |

## Detection Capabilities

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **resolution_megapixels** | | | |
| **frame_rate_fps** | | | |
| **has_autotracker** | | | Automatic target tracking? |
| **has_ai_detection** | | | AI-based drone detection? |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | | | |
| **dimensions** | | | |
| **power_requirement_w** | | | |
| **ip_rating** | | | |
| **operating_temp_c** | | | |
| **cost_aud** | | | |

## Notes

-
