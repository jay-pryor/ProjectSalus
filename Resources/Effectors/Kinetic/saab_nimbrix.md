# SAAB Nimbrix

**Manufacturer:** SAAB
**Last Updated:** March 2026
**Vendor Research:** `../../VendorResearch/SAAB_Australia/products_and_specs.md`

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | 5000 | datasheet | "Up to 5 km" |
| **min_range_m** | 100 | estimated | |
| **engagement_arc_deg** | 360 | estimated | Vehicle-mounted launcher |
| **elevation_arc_deg** | 80 | estimated | |
| **elevation_min_deg** | 0 | estimated | |
| **elevation_max_deg** | 80 | estimated | |
| **projectile_type** | Fire-and-forget missile with active seeker + air-burst warhead | datasheet | |
| **mounting_height_m** | 3 | estimated | Vehicle-mounted |
| **requires_los** | false | datasheet | Fire-and-forget — does not need continuous LOS after launch |

## Engagement Parameters

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **reaction_time_s** | 3 | estimated | Fire-and-forget — faster than beam-riding (no continuous guidance needed) |
| **slew_rate_deg_s** | | | Not published |
| **simultaneous_engagements** | 4 | estimated | 3-4 missiles per side on M-SHORAD Trackfire turret. Fire-and-forget allows ripple fire. |
| **reload_time_s** | 2 | estimated | Ripple fire from multi-missile launcher |
| **magazine_capacity** | 8 | estimated | 3-4 per side on turret |
| **defeat_probability** | 0.8 | estimated | Active seeker + air-burst for UAS |
| **defeat_mechanism** | Hard-kill warhead with air-burst mode for UAS / swarm engagement | datasheet | |
| **collateral_risk** | Medium | estimated | Designed as low-cost with small footprint |
| **cost_per_engagement_aud** | 30000 | estimated | "Low cost" — designed for affordability against drone threats |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | | | Not published |
| **dimensions** | Small footprint | datasheet | |
| **power_requirement_w** | | | Not published |
| **mounting_type** | Vehicle or fixed | datasheet | M-SHORAD Trackfire turret |
| **ip_rating** | | | Not published |
| **operating_temp_c** | | | Not published |
| **cost_aud** | | | Not published. "Low cost" designed for affordability. |

## Notes

- Fire-and-forget with active seeker — major advantage over beam-riding (RBS 70) for multi-target
- Air-burst mode specifically designed for UAS swarm engagement
- Small footprint — designed to be cheap enough to use against drones
- First deliveries targeted for 2026
- Mounting: 3-4 missiles per side on M-SHORAD Trackfire turret
- Purpose-built counter-drone missile (vs RBS 70 which is adapted from air defence)
