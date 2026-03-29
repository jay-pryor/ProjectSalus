# EOS Slinger

**Manufacturer:** Electro Optic Systems (EOS)
**Last Updated:** March 2026
**Vendor Research:** `../../VendorResearch/EOS_Defence/products_and_specs.md`

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | 800 | datasheet | "Demonstrated beyond 800 m in live fire" — actual max likely higher |
| **min_range_m** | 50 | estimated | Airburst fragmentation needs safe arming distance |
| **engagement_arc_deg** | 360 | estimated | Turret-based weapon station |
| **elevation_arc_deg** | 80 | estimated | Based on R400 lineage, typical RWS elevation |
| **elevation_min_deg** | -10 | estimated | |
| **elevation_max_deg** | 70 | estimated | |
| **projectile_type** | Programmable airburst (RF proximity-fused HE/fragmentation) | datasheet | 30x113 mm |
| **mounting_height_m** | 3 | estimated | Vehicle-mounted turret |
| **requires_los** | true | fixed | Always true for kinetic |

## Engagement Parameters

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **reaction_time_s** | 3 | estimated | Automated turret with integrated radar cueing (Echodyne MESA) |
| **slew_rate_deg_s** | | | Not published. "Sub-milliradian pointing precision" suggests fast. |
| **simultaneous_engagements** | 1 | estimated | Single barrel |
| **reload_time_s** | 0.3 | estimated | 200 rpm max = 1 round per 0.3s. Selectable: single-shot, 100 rpm, 200 rpm. |
| **magazine_capacity** | 150 | datasheet | 150 rounds RF proximity-fused HE/frag (ready) |
| **defeat_probability** | 0.7 | estimated | Airburst against small drones. Sub-mrad precision aids accuracy. |
| **defeat_mechanism** | Proximity-fused airburst fragmentation (30x113 mm) | datasheet | |
| **collateral_risk** | Medium | estimated | HE fragmentation — not suitable for populated areas |
| **cost_per_engagement_aud** | 155-1550 | datasheet | $155-$1,550 per engagement |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | 376 | datasheet | Configuration with M230LF and 150 ready rounds |
| **dimensions** | | | Not published |
| **power_requirement_w** | | | Not published |
| **mounting_type** | Vehicle-mounted turret | datasheet | On M113 APCs and Practika 4x4 MRAPs |
| **ip_rating** | | | Not published |
| **operating_temp_c** | | | Not published |
| **cost_aud** | 2325000 | datasheet | Less than $1.55M USD ≈ ~$2.325M AUD |

## Notes

- Weapon: M230LF 30x113 mm chain gun
- Rate of fire selectable: single-shot, 100 rpm, or 200 rpm
- Four-axis stabilised mount (on-the-move fires)
- Sighting: four-axis day and thermal sight, sensor moves independently of gun
- Integrated 4D electronically steered radar (Echodyne MESA)
- AI-enabled Aided Target Recognition (ATR) with selectable autonomy levels
- Differentiates birds vs drones, friendly vs hostile
- 160 units ordered for Ukraine (Sep 2023)
- Built on R400 Remote Weapon Station lineage
