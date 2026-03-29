# Dedrone DedroneDefender 2

**Manufacturer:** Dedrone (Axon)
**Last Updated:** March 2026
**Vendor Research:** `../../VendorResearch/Dedrone_Axon/products_and_specs.md`

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | 300 | datasheet | "300+ meters" |
| **min_range_m** | 0 | estimated | |
| **engagement_arc_deg** | 20 | datasheet | "20 degree targeting cone" |
| **elevation_arc_deg** | 20 | estimated | Matched to targeting cone |
| **frequency_bands_jammed** | RF control, GNSS | datasheet | Broadband + narrowband + GNSS |
| **jam_gnss** | true | datasheet | |
| **jam_c2** | true | datasheet | |
| **jam_video** | true | estimated | Broadband capability |
| **mounting_height_m** | 1.5 | estimated | Handheld |
| **requires_los** | true | estimated | Directional — must point at target |

## Engagement Parameters

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **reaction_time_s** | 1 | estimated | AI-powered — faster target acquisition than manual |
| **simultaneous_engagements** | 3 | datasheet | "Multi-drone simultaneous neutralisation" |
| **reload_time_s** | 0 | estimated | AI-powered continuous |
| **defeat_probability** | 0.8 | estimated | AI-powered smart jammer — more effective than brute-force |
| **defeat_mechanism** | AI-powered broadband + narrowband jamming + GNSS disruption | datasheet | |
| **erp_dbm** | | | Not published |

## Legal / Regulatory

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **legal_restrictions** | Requires regulatory authorisation | estimated | |
| **mounting_type** | Handheld | datasheet | |

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

- AI-powered — next generation of DedroneDefender
- Multi-drone simultaneous neutralisation from a handheld device
- Combines broadband and narrowband jamming modes
- 20-degree targeting cone
