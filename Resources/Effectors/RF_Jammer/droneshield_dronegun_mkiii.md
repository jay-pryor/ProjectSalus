# DroneShield DroneGun MkIII

**Manufacturer:** DroneShield
**Last Updated:** March 2026
**Vendor Research:** `../../VendorResearch/DroneShield/products_and_specs.md`

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | 500 | datasheet | |
| **min_range_m** | 0 | estimated | |
| **engagement_arc_deg** | 30 | estimated | Directional pistol-form |
| **elevation_arc_deg** | 30 | estimated | |
| **frequency_bands_jammed** | ISM bands | estimated | Not detailed. Assumed similar to Mk4. |
| **jam_gnss** | true | estimated | |
| **jam_c2** | true | estimated | |
| **jam_video** | true | estimated | |
| **mounting_height_m** | 1.5 | estimated | Handheld |
| **requires_los** | true | estimated | Directional |

## Engagement Parameters

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **reaction_time_s** | 5 | estimated | Manual |
| **simultaneous_engagements** | 1 | estimated | |
| **reload_time_s** | 2 | estimated | |
| **defeat_probability** | 0.7 | estimated | Shorter range than Mk4 |
| **defeat_mechanism** | RF disruption — forces failsafe | estimated | |
| **erp_dbm** | | | Not published |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | 1.95 | datasheet | Lightest in the DroneGun line |
| **dimensions** | 630 x 400 x 200 mm | datasheet | |
| **power_requirement_w** | | | Battery powered |
| **ip_rating** | | | Not published |
| **operating_temp_c** | | | Not published |
| **cost_aud** | | | Not published |

## Notes

- Ultra-lightweight handheld (1.95 kg)
- Single-hand operation
- Battery life: 1 hour
- Largely superseded by DroneGun Mk4 (better range/power at moderate weight increase)
- Released 2019
