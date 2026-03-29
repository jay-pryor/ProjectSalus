# L3Harris VAMPIRE

**Manufacturer:** L3Harris
**Last Updated:** March 2026
**Vendor Research:** `../../VendorResearch/L3Harris/products_and_specs.md`

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | 5000 | datasheet | "Up to 5 km" |
| **min_range_m** | 200 | estimated | Guided rocket needs minimum distance |
| **engagement_arc_deg** | 360 | estimated | Turret-style mount |
| **elevation_arc_deg** | 80 | estimated | |
| **elevation_min_deg** | -10 | estimated | |
| **elevation_max_deg** | 70 | estimated | |
| **projectile_type** | Laser-guided rocket (BAE APKWS — 2.75-inch/70mm Hydra-70) | datasheet | Proximity fuse |
| **mounting_height_m** | 3 | estimated | Vehicle-mounted |
| **requires_los** | true | fixed | Always true for kinetic |

## Engagement Parameters

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **reaction_time_s** | 5 | estimated | EO/IR acquire + laser designate + launch |
| **slew_rate_deg_s** | | | Not published |
| **simultaneous_engagements** | 1 | estimated | One rocket per engagement |
| **reload_time_s** | 10 | estimated | Next rocket from tube |
| **magazine_capacity** | 4 | datasheet | Standard. Stalker XR: 12 rounds. |
| **defeat_probability** | 0.8 | estimated | Laser-guided with proximity fuze |
| **defeat_mechanism** | Laser-guided semi-active homing rocket with proximity fuze | datasheet | |
| **collateral_risk** | Medium | estimated | 2.75-inch rocket warhead |
| **cost_per_engagement_aud** | 30000 | estimated | APKWS ~$20K USD per round |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | | | Not published |
| **dimensions** | | | Not published |
| **power_requirement_w** | | | Not published |
| **mounting_type** | Vehicle-mounted | datasheet | Technical vehicle (e.g. Toyota Hilux) |
| **ip_rating** | | | Not published |
| **operating_temp_c** | | | Not published |
| **cost_aud** | | | Not published |

## Notes

- Sensor: L3Harris WESCAM MX-10D RSTA EO/IR targeting sensor
- Software: Widow mission management software
- Guidance: semi-active laser homing (APKWS)
- L3Harris proximity fuze
- Stalker XR variant: 12-round magazine
- Designed to be mounted on non-military vehicles (technicals)
- Widely supplied to Ukraine
