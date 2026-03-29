# Raytheon Coyote Block 2+

**Manufacturer:** Raytheon / RTX
**Last Updated:** March 2026
**Vendor Research:** `../../VendorResearch/Raytheon_RTX/products_and_specs.md`

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | 15000 | datasheet | 10-15 km engagement range |
| **min_range_m** | 500 | estimated | Guided missile needs minimum flight distance |
| **engagement_arc_deg** | 360 | estimated | Missile — can fly any direction |
| **elevation_arc_deg** | 180 | estimated | |
| **elevation_min_deg** | 0 | estimated | |
| **elevation_max_deg** | 90 | estimated | |
| **projectile_type** | Guided missile (proximity-fused tungsten fragmentation) | datasheet | |
| **mounting_height_m** | 3 | estimated | Vehicle-mounted launcher |
| **requires_los** | true | fixed | Missile needs to reach target (datalink guided) |

## Engagement Parameters

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **reaction_time_s** | 10 | estimated | Launch + flight time to target |
| **slew_rate_deg_s** | N/A | | Missile flight |
| **simultaneous_engagements** | 1 | estimated | Per missile |
| **reload_time_s** | 30 | estimated | Next missile from launcher |
| **magazine_capacity** | 4 | datasheet | Standard. Stalker XR variant: 12 rounds. |
| **defeat_probability** | 0.85 | estimated | Guided with proximity fuze. 170+ confirmed kills. |
| **defeat_mechanism** | Tungsten fragmentation warhead, proximity-fused | datasheet | Forward-firing, low collateral blast |
| **collateral_risk** | Medium | estimated | Fragmentation warhead, but low collateral blast design |
| **cost_per_engagement_aud** | 150000 | estimated | ~$100,000 USD per round ≈ ~$150K AUD |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | 5.9 | datasheet | ~13 lb (Block 1 reference) |
| **dimensions** | | | Not published |
| **power_requirement_w** | | | Self-propelled (rocket booster + turbine) |
| **mounting_type** | Vehicle-mounted launcher | datasheet | Part of LIDS (M-ATV) |
| **ip_rating** | | | Not published |
| **operating_temp_c** | | | Not published |
| **cost_aud** | | | Not published |

## Notes

- Speed: 555-595 km/h
- Flight time: up to ~4 minutes
- Guidance: C-band datalink + onboard seeker + proximity fuze for terminal phase
- Target set: Group 1-3 UAS
- 170+ confirmed kills in combat
- Deployed at 36+ sites outside the United States
- Stalker XR variant: 12 rounds per launcher
- Block 3NK variant is non-kinetic (EW/jamming) — reusable
