# Raytheon Phaser High-Power Microwave

**Manufacturer:** Raytheon / RTX
**Last Updated:** March 2026
**Vendor Research:** `../../VendorResearch/Raytheon_RTX/products_and_specs.md`

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **de_type** | HPM | datasheet | High-Power Microwave |
| **max_range_m** | 500 | estimated | Not published. HPM systems typically effective 100-500m. |
| **min_range_m** | 10 | estimated | |
| **engagement_arc_deg** | 120 | estimated | "Wide, conical microwave energy beam" + reflector antenna — sector coverage |
| **elevation_arc_deg** | 60 | estimated | Conical beam |
| **mounting_height_m** | 3 | estimated | Trailer-mounted |
| **requires_los** | true | estimated | Directional HPM needs approximate LOS |

## Engagement Parameters

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **beam_dwell_time_s** | 0.001 | datasheet | "Milliseconds" engagement speed |
| **reaction_time_s** | 2 | estimated | Cueing from radar/EO-IR required |
| **simultaneous_engagements** | 3 | datasheet | "2-3 at a time" demonstrated. Wide beam affects multiple drones. |
| **reload_time_s** | 5 | estimated | Capacitor/vacuum tube recharge time |
| **magazine_capacity** | unlimited | datasheet | |
| **defeat_probability** | 0.7 | estimated | Electronics disruption is probabilistic — depends on drone hardening |
| **defeat_mechanism** | Electronic disruption (fries drone electronics/flight controller) | datasheet | "Disrupt" mode and "Destroy" mode |
| **weather_sensitivity** | Low | estimated | HPM less affected by weather than HEL |
| **cost_per_engagement_aud** | 0.1 | datasheet | "Cents per firing" |

## System Specifications

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **laser_power_kw** | N/A | | HPM, not laser |
| **slew_speed** | | | Not published |
| **target_lock_time_s** | | | Not published |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | | | Not published |
| **dimensions** | 20-foot trailer | datasheet | Containerised |
| **power_requirement_w** | | | Internal diesel generator |
| **mounting_type** | Trailer (20-foot) | datasheet | |
| **ip_rating** | | | Not published |
| **operating_temp_c** | | | Not published |
| **cost_aud** | | | Not published |

## Notes

- Anti-swarm capability demonstrated: 33 drones downed in single exercise
- Vacuum tube microwave generation with reflector antenna
- Two modes: "Disrupt" (temporary loss of control) and "Destroy" (permanent electronics damage)
- Wide beam is ideal for swarm defeat — affects multiple drones per shot
- Targeting sensors: radar and EO/IR cameras for cueing
- Key advantage over kinetic: near-zero cost per engagement, unlimited magazine
