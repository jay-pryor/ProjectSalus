# Anduril Roadrunner

**Manufacturer:** Anduril
**Last Updated:** March 2026
**Vendor Research:** `../../VendorResearch/Anduril_Australia/products_and_specs.md`

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | 15000 | estimated | "10x one-way effective range" of Anvil. High subsonic twin-jet. |
| **min_range_m** | 500 | estimated | Jet-powered — needs distance to manoeuvre |
| **engagement_arc_deg** | 360 | estimated | Autonomous air vehicle |
| **elevation_arc_deg** | 180 | estimated | Full hemisphere |
| **elevation_min_deg** | 0 | estimated | |
| **elevation_max_deg** | 90 | estimated | |
| **projectile_type** | Autonomous jet-powered interceptor (kinetic kill or HE warhead) | datasheet | |
| **mounting_height_m** | 1 | estimated | Containerised "Nest" launcher |
| **requires_los** | false | estimated | Autonomous — finds and engages target independently |

## Engagement Parameters

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **reaction_time_s** | 15 | estimated | Launch + climb + acquire |
| **slew_rate_deg_s** | N/A | | Autonomous flight |
| **simultaneous_engagements** | 1 | estimated | Per vehicle. Single operator can control multiple squadrons. |
| **reload_time_s** | 30 | estimated | Next launch from Nest |
| **magazine_capacity** | | | Not published. Containerised "Nest" holds multiple units. |
| **defeat_probability** | 0.85 | estimated | Onboard sensors + high-G manoeuvrability |
| **defeat_mechanism** | Kinetic intercept (collision) or HE warhead | datasheet | Roadrunner-M: up to 33 lbs warhead |
| **collateral_risk** | Medium-High | estimated | Jet-powered vehicle with optional HE warhead |
| **cost_per_engagement_aud** | 300000 | estimated | "Low hundreds of thousands" of dollars USD |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | | | Not published |
| **dimensions** | | | Not published |
| **power_requirement_w** | | | Jet fuel powered |
| **mounting_type** | Containerised "Nest" launcher | datasheet | |
| **ip_rating** | | | Not published |
| **operating_temp_c** | | | Not published |
| **cost_aud** | | | "Low hundreds of thousands" USD |

## Notes

- Twin jet engines, high subsonic speed
- High-G manoeuvring capability
- Reusable: if target not engaged, returns to base for refuelling
- Containerised "Nest" enclosure for rapid deployment
- Single operator can control multiple Roadrunner squadrons
- Target range: Group 1 through Group 5 UAS, cruise missiles, and full-sized aircraft
- Roadrunner-M (munitions variant): up to 33 lbs warhead (comparable to AGM-114 Hellfire)
- "3x warhead payload capacity, 10x one-way effective range, 3x more manoeuvrable" vs competitors
- This is a high-end system — more air defence interceptor than point cUAS
