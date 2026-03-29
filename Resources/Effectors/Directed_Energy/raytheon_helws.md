# Raytheon HELWS (High Energy Laser Weapon System)

**Manufacturer:** Raytheon / RTX
**Last Updated:** March 2026
**Vendor Research:** `../../VendorResearch/Raytheon_RTX/products_and_specs.md`

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **de_type** | HEL | datasheet | High Energy Laser |
| **max_range_m** | 3000 | datasheet | "Up to 3 km" |
| **min_range_m** | 50 | estimated | |
| **engagement_arc_deg** | 360 | datasheet | |
| **elevation_arc_deg** | | | Not published |
| **mounting_height_m** | 3 | estimated | Vehicle-mounted |
| **requires_los** | true | fixed | Always true for HEL |

## Engagement Parameters

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **beam_dwell_time_s** | 3 | estimated | "Seconds to neutralise a UAS target" — varies with power level |
| **reaction_time_s** | 2 | estimated | MTS sensor provides targeting |
| **simultaneous_engagements** | 1 | estimated | Single beam |
| **reload_time_s** | 2 | estimated | Re-acquire time |
| **magazine_capacity** | unlimited | datasheet | Power-limited, not ammo-limited. "Unlimited shots" with generator. |
| **defeat_probability** | 0.85 | estimated | |
| **defeat_mechanism** | Structural burn-through / component destruction | estimated | |
| **weather_sensitivity** | Rain, fog, dust degrade performance | estimated | Standard HEL limitation |
| **cost_per_engagement_aud** | 5 | estimated | Electricity cost |

## System Specifications

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **laser_power_kw** | 10-100 | datasheet | Scalable from 10 kW to 100 kW |
| **slew_speed** | | | Not published |
| **target_lock_time_s** | | | Not published |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | | | Not published |
| **dimensions** | | | Palletised on Polaris MRZR (USAF) or Stryker (Army) |
| **power_requirement_w** | | | Standard 220V outlet or generator |
| **mounting_type** | Vehicle (MRZR, Stryker) or palletised | datasheet | |
| **ip_rating** | | | Not published |
| **operating_temp_c** | | | Not published |
| **cost_aud** | | | Not published |

## Notes

- Multi-spectral Targeting System (MTS) EO/IR sensor for targeting
- 25,000+ operational hours deployed overseas (USAF)
- 400+ targets destroyed
- 40,000+ testing hours
- Threat set: UAS, rockets, artillery, mortars (C-RAM capable)
- 50 kW DE M-SHORAD variant on Stryker vehicle
