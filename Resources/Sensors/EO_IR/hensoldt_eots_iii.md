# HENSOLDT EOTS III SHORAD

**Manufacturer:** HENSOLDT
**Last Updated:** March 2026
**Vendor Research:** `../../VendorResearch/HENSOLDT_Australia/products_and_specs.md`

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | 10000 | estimated | SHORAD-class EO/IR targeting system. Exact detection range vs UAS not published. |
| **max_range_recognition_m** | 5000 | estimated | |
| **max_range_identification_m** | 3000 | estimated | |
| **min_range_m** | 0 | estimated | |
| **sensor_modality** | EO/IR | datasheet | Visible + NIR + colour daylight sensor AND MWIR IR sensor |
| **azimuth_coverage_deg** | 360 | datasheet | "n x 360 degrees" — continuous rotation |
| **is_ptz** | true | datasheet | Targeting turret — continuous rotation but narrow FOV at any moment |
| **instantaneous_fov_h_deg** | 1.5 | datasheet | Minimum (zoomed). Max FOV: 26 degrees. |
| **instantaneous_fov_v_deg** | | | Not published separately |
| **elevation_coverage_deg** | 110 | datasheet | -20° to +90° |
| **day_night_capability** | day and night | datasheet | Dual EO + MWIR |
| **mounting_height_m** | 3 | estimated | Vehicle-mounted turret |
| **requires_los** | true | fixed | Always true for EO/IR |

## Detection Capabilities

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **resolution_megapixels** | 2 | datasheet | 1920 x 1080 daylight sensor |
| **frame_rate_fps** | | | Not published |
| **has_autotracker** | true | estimated | SHORAD targeting system — auto-tracking implied |
| **has_ai_detection** | | | Not specified |

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

- Elevation: -20° to +90° — full overhead coverage
- Stabilisation error: <0.05 mrad RMS — very precise
- Daylight sensor: Visible + NIR + colour, 1920 x 1080, FOV 1.5-26°
- IR sensor: MWIR, 1280 x 1080
- Video interface: 3G-SDI and HD-SDI
- Laser rangefinder: up to 20 Hz pulse rate
- NGVA-ready
- This is a targeting/fire control sensor, not a search sensor — best used with radar cueing
