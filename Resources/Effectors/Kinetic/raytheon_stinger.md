# Raytheon Stinger (FIM-92)

**Manufacturer:** Raytheon / RTX
**Last Updated:** March 2026
**Vendor Research:** `../../VendorResearch/Raytheon_RTX/products_and_specs.md`

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | 4800 | datasheet | Targeting range. Kinematic range: ~8,000 m. |
| **min_range_m** | 200 | estimated | IR seeker needs acquisition distance |
| **engagement_arc_deg** | 360 | estimated | MANPADS — operator can aim any direction |
| **elevation_arc_deg** | 90 | estimated | |
| **elevation_min_deg** | 0 | estimated | |
| **elevation_max_deg** | 90 | estimated | Engagement altitude: up to 3,800 m |
| **projectile_type** | IR-homing missile (hit-to-kill) | datasheet | |
| **mounting_height_m** | 1.5 | estimated | Shoulder-launched |
| **requires_los** | true | fixed | IR seeker needs LOS to target thermal signature |

## Engagement Parameters

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **reaction_time_s** | 5 | estimated | Manual: acquire, lock tone, launch |
| **slew_rate_deg_s** | N/A | | Manual aim |
| **simultaneous_engagements** | 1 | estimated | Single missile |
| **reload_time_s** | 30 | estimated | Manual missile tube reload |
| **magazine_capacity** | 1 | datasheet | One missile per gripstock |
| **defeat_probability** | 0.7 | estimated | IR homing against small UAS is challenging — low thermal signature. Better against larger/hotter targets. |
| **defeat_mechanism** | 3 kg penetrating hit-to-kill warhead with impact fuze and self-destruct timer | datasheet | |
| **collateral_risk** | High | estimated | Missile with 3 kg warhead + self-destruct |
| **cost_per_engagement_aud** | 60000 | estimated | ~$38K USD per missile ≈ ~$57K AUD |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | 15.2 | datasheet | ~34 lb system weight including launcher, gripstock, and IFF |
| **dimensions** | Missile: 1.52 m length, 70 mm diameter | datasheet | Fins: 100 mm |
| **power_requirement_w** | 0 | datasheet | Self-contained |
| **mounting_type** | Shoulder-launched (MANPADS) | datasheet | |
| **ip_rating** | | | Military standard |
| **operating_temp_c** | | | Not published |
| **cost_aud** | | | Not published |

## Notes

- Maximum speed: Mach 2.54 (864 m/s)
- Missile weight: 10.1 kg (22 lb)
- Guidance: IR homing (proportional navigation + airframe tracking)
- Two-stage solid-fuel propulsion
- Engagement altitude: up to 3,800 m
- Self-destruct timer for safety
- Limited effectiveness against small commercial drones (low IR signature)
- More effective against larger/hotter targets (Group 2-3 UAS, fixed-wing with engines)
- Widely fielded — proven combat record
