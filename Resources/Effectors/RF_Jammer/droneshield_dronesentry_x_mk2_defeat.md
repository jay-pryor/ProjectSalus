# DroneShield DroneSentry-X Mk2 (Defeat Mode)

**Manufacturer:** DroneShield
**Last Updated:** March 2026
**Vendor Research:** `../../VendorResearch/DroneShield/products_and_specs.md`

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | 2000 | estimated | Combined detect+defeat system. Defeat range not separately published. |
| **min_range_m** | 0 | estimated | |
| **engagement_arc_deg** | 360 | datasheet | "Adaptive omnidirectional" |
| **elevation_arc_deg** | 180 | estimated | Hemispheric |
| **frequency_bands_jammed** | ISM bands, GNSS | datasheet | Simultaneous multi-band receive and transmit |
| **jam_gnss** | true | datasheet | "Disrupts satellite navigation" |
| **jam_c2** | true | datasheet | RFAI-ATK electronic countermeasure |
| **jam_video** | true | estimated | Multi-band |
| **mounting_height_m** | 3 | estimated | Vehicle roof / tripod mast |
| **requires_los** | false | estimated | Omnidirectional |

## Engagement Parameters

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **reaction_time_s** | 1 | estimated | AI-driven RFAI-ATK — fast automated response |
| **simultaneous_engagements** | 20 | estimated | Omnidirectional — all drones in range |
| **reload_time_s** | 0 | estimated | Continuous |
| **defeat_probability** | 0.85 | estimated | RFAI-ATK is adaptive — may be more effective than brute-force jamming |
| **defeat_mechanism** | AI-driven adaptive RF disruption via RFAI-ATK | datasheet | |
| **erp_dbm** | | | Not published |

## Legal / Regulatory

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **legal_restrictions** | Requires regulatory authorisation | estimated | |
| **mounting_type** | Vehicle / vessel / tripod / tower | datasheet | |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | 46 | datasheet | Including brackets (combined detect+defeat unit) |
| **dimensions** | 710 x 710 x 532 mm | datasheet | |
| **power_requirement_w** | | | Not published |
| **ip_rating** | IP67 | datasheet | |
| **operating_temp_c** | -20 to +55 | datasheet | |
| **cost_aud** | | | Not published |

## Notes

- Industry's first RFAI-ATK (AI-driven electronic countermeasure) platform
- Combined detect + defeat in single self-contained unit
- Detection specs in Sensors/RF/droneshield_dronesentry_x_mk2.md
- Supports automatic or manual disruption modes
- Human-in-the-loop, autonomous, and remote operational modes
- MOSA for third-party sensor/effector/C2 integration
