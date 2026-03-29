# Anduril Anvil

**Manufacturer:** Anduril
**Last Updated:** March 2026
**Vendor Research:** `../../VendorResearch/Anduril_Australia/products_and_specs.md`

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | 3000 | estimated | Interceptor drone — range depends on flight endurance |
| **min_range_m** | 50 | estimated | Needs distance to acquire and intercept |
| **engagement_arc_deg** | 360 | estimated | Autonomous drone — can fly any direction |
| **elevation_arc_deg** | 180 | estimated | Full hemisphere |
| **elevation_min_deg** | 0 | estimated | |
| **elevation_max_deg** | 90 | estimated | |
| **projectile_type** | Interceptor drone (ram-to-kill) | datasheet | Kinetic impact |
| **mounting_height_m** | 1 | estimated | Launch box on ground |
| **requires_los** | true | fixed | Needs to physically reach target |

## Engagement Parameters

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **reaction_time_s** | 10 | estimated | Launch + acquire time |
| **slew_rate_deg_s** | N/A | | Autonomous flight |
| **simultaneous_engagements** | 1 | estimated | Per interceptor. Multiple Anvils from launch box. |
| **reload_time_s** | 15 | estimated | Next interceptor launch |
| **magazine_capacity** | | | Not published. Launch box holds multiple units. |
| **defeat_probability** | 0.8 | estimated | Computer vision guided ram-to-kill |
| **defeat_mechanism** | Kinetic ram-to-kill (physical collision) | datasheet | |
| **collateral_risk** | Low | estimated | Small interceptor, no explosives, debris falls |
| **cost_per_engagement_aud** | | | Not published. Consumable interceptor. |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | 5.3 | datasheet | ~11.6 lbs |
| **dimensions** | | | Not published |
| **power_requirement_w** | | | Battery powered interceptor |
| **mounting_type** | Launch box | datasheet | Launch box weight: ~115 kg (253 lbs) |
| **ip_rating** | | | Not published |
| **operating_temp_c** | | | Not published |
| **cost_aud** | | | Not published |

## Notes

- Maximum speed: up to 320 km/h (200 mph)
- Guidance: computer vision + Lattice AI
- Target types: Group 1 and Group 2 UAS
- Low collateral damage — no explosives, just kinetic impact
- Part of Anduril Counter-UAS Fly-Away Kit
