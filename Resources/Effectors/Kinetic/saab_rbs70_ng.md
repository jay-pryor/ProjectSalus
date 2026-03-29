# SAAB RBS 70 NG

**Manufacturer:** SAAB
**Last Updated:** March 2026
**Vendor Research:** `../../VendorResearch/SAAB_Australia/products_and_specs.md`

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | 9000 | datasheet | BOLIDE missile |
| **min_range_m** | 200 | estimated | Guided missile minimum |
| **engagement_arc_deg** | 360 | estimated | Tripod-mounted, manual traverse |
| **elevation_arc_deg** | 90 | estimated | |
| **elevation_min_deg** | 0 | estimated | |
| **elevation_max_deg** | 90 | estimated | Height coverage: 5,000 m |
| **projectile_type** | Laser beam-riding missile (BOLIDE) | datasheet | Combined shaped-charge and pre-fragmented warhead |
| **mounting_height_m** | 1.5 | estimated | Tripod/ground mounted |
| **requires_los** | true | fixed | Laser beam-riding requires continuous LOS |

## Engagement Parameters

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **reaction_time_s** | 5 | estimated | Manual operator — acquire, track, launch |
| **slew_rate_deg_s** | | | Manual traverse |
| **simultaneous_engagements** | 1 | estimated | Single missile guided at a time |
| **reload_time_s** | 15 | estimated | Manual missile reload |
| **magazine_capacity** | 1 | datasheet | One missile loaded at a time |
| **defeat_probability** | 0.85 | estimated | Laser beam-riding is highly accurate against slow targets. Mach 2 missile speed. |
| **defeat_mechanism** | Combined shaped-charge and pre-fragmented warhead — kinetic kill | datasheet | |
| **collateral_risk** | High | estimated | Missile warhead designed for aircraft |
| **cost_per_engagement_aud** | 200000 | estimated | ~$130K USD per BOLIDE missile |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | 15 | datasheet | Missile weight: 15 kg. System includes sight and tripod. |
| **dimensions** | 132 cm missile length | datasheet | Diameter: 10.6 cm. Fin span: 32 cm. |
| **power_requirement_w** | | | Not published |
| **mounting_type** | Tripod (man-portable) or RWS | datasheet | 1 operator, 3 for portability |
| **ip_rating** | | | Not published |
| **operating_temp_c** | | | Not published |
| **cost_aud** | | | Not published |

## Notes

- NG sight includes integrated high-resolution thermal imager
- Maximum missile velocity: Mach 2 (BOLIDE)
- Height coverage: 5,000 m
- Earlier variants (Mk1/Mk2): 5,000-6,000 m range, 3,000 m ceiling
- Operators: 1 for operation, 3 for portability
- Part of SAAB MSHORAD integrated solution with Giraffe 1X
- Also available as Remote Weapon Station (RWS) variant
- This is a VSHORAD system — designed for low-altitude air defence including drones
