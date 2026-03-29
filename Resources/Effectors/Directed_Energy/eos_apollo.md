# EOS Apollo High Energy Laser

**Manufacturer:** Electro Optic Systems (EOS)
**Last Updated:** March 2026
**Vendor Research:** `../../VendorResearch/EOS_Defence/products_and_specs.md`

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **de_type** | HEL | datasheet | High Energy Laser |
| **max_range_m** | 3000 | datasheet | Hard-kill: 50m to 3 km. Optical sensor denial: up to 15 km. |
| **min_range_m** | 50 | datasheet | |
| **engagement_arc_deg** | 360 | estimated | Turret-based |
| **elevation_arc_deg** | 90 | estimated | |
| **mounting_height_m** | 3 | estimated | Container or vehicle-based |
| **requires_los** | true | fixed | Always true for HEL |

## Engagement Parameters

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **beam_dwell_time_s** | 1.3 | datasheet | "~1.3 seconds for Group 1 UAS at 50 kW" |
| **reaction_time_s** | 1.3 | datasheet | Slew: 60° in ~700 ms. Target lock: ~600 ms. Total acquire ≈ 1.3s. |
| **simultaneous_engagements** | 1 | estimated | Single beam |
| **reload_time_s** | 1.3 | estimated | Re-acquire time for new target (slew + lock) |
| **magazine_capacity** | 200 | datasheet | Over 200 UAS kills independent operation. Unlimited with external power + cooling. |
| **defeat_probability** | 0.9 | estimated | At optimal range and clear weather |
| **defeat_mechanism** | Structural burn-through (motor/propeller/airframe damage) | estimated | |
| **weather_sensitivity** | Rain, fog, dust degrade performance significantly | estimated | Standard HEL limitation |
| **cost_per_engagement_aud** | 5 | estimated | Electricity cost only — pennies per shot |

## System Specifications

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **laser_power_kw** | 50-150 | datasheet | Scalable |
| **slew_speed** | 60° in ~700 ms | datasheet | |
| **target_lock_time_s** | 0.6 | datasheet | ~600 ms |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | | | Not published |
| **dimensions** | 20-foot ISO container | datasheet | Also option for 8x8 vehicle chassis |
| **power_requirement_w** | | | Not published. HEL at 50-150 kW needs significant power. |
| **mounting_type** | Container or vehicle | datasheet | |
| **ip_rating** | | | Not published |
| **operating_temp_c** | | | Not published |
| **cost_aud** | | | Not published. EUR 71.4M order for multiple units. |

## Notes

- Kill rate: >20 Group 1 UAS per minute at 150 kW
- Setup time: under 2 hours by experienced crew
- Target types: Group 1-3 UAS
- Optical sensor denial range extends to 15 km (dazzle/blind cameras)
- ITAR-free; all technology and IP wholly owned by EOS
- Continuous fire possible with external electrical power and cooling
- NATO air defence C2 integration
- Contracts: EUR 71.4M European NATO member, USD 80M conditional South Korea (100 kW class)
