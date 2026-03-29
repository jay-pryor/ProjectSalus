# [Product Name]

**Manufacturer:** [Vendor]
**Last Updated:** [Date]
**Vendor Research:** [Link to VendorResearch file]

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **de_type** | | | "HEL" (laser) or "HPM" (microwave) |
| **max_range_m** | | | |
| **min_range_m** | | | |
| **engagement_arc_deg** | | | |
| **elevation_arc_deg** | | | |
| **mounting_height_m** | | | |
| **requires_los** | | | HEL: always true. HPM: depends on directionality. |

## Engagement Parameters

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **beam_dwell_time_s** | | | HEL: time on target to achieve defeat |
| **reaction_time_s** | | | Time from command to beam on target (includes slew + acquire) |
| **simultaneous_engagements** | | | Usually 1 |
| **reload_time_s** | | | HEL: thermal cooldown. HPM: capacitor recharge. |
| **magazine_capacity** | | | HEL: "unlimited" (power-limited). HPM: duty cycle. |
| **defeat_probability** | | | |
| **defeat_mechanism** | | | e.g. "Structural burn-through" / "Electronic disruption" |
| **weather_sensitivity** | | | HEL degrades in rain/fog/dust |
| **cost_per_engagement_aud** | | | Typically very low (electricity) |

## System Specifications

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **laser_power_kw** | | | For HEL systems |
| **slew_speed** | | | |
| **target_lock_time_s** | | | |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | | | |
| **dimensions** | | | |
| **power_requirement_w** | | | DE systems are very power-hungry |
| **mounting_type** | | | Container / vehicle / fixed |
| **ip_rating** | | | |
| **operating_temp_c** | | | |
| **cost_aud** | | | |

## Notes

-
