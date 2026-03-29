# [Product Name]

**Manufacturer:** [Vendor]
**Last Updated:** [Date]
**Vendor Research:** [Link to VendorResearch file]

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | | | |
| **min_range_m** | | | Minimum safe engagement distance |
| **engagement_arc_deg** | | | 360 for turret, limited for fixed mount |
| **elevation_arc_deg** | | | Can it engage overhead? |
| **elevation_min_deg** | | | |
| **elevation_max_deg** | | | |
| **projectile_type** | | | Net / airburst / HE / KE / interceptor drone |
| **mounting_height_m** | | | |
| **requires_los** | true | fixed | Always true for kinetic |

## Engagement Parameters

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **reaction_time_s** | | | Time from track to first shot/launch (includes slew) |
| **slew_rate_deg_s** | | | Turret traverse speed |
| **simultaneous_engagements** | | | Usually 1 for guns |
| **reload_time_s** | | | Between engagements |
| **magazine_capacity** | | | Total rounds/interceptors before resupply |
| **defeat_probability** | | | Per-engagement Pk |
| **defeat_mechanism** | | | e.g. "Proximity-fused airburst fragmentation" |
| **collateral_risk** | | | Low (nets) / Medium (guided) / High (unguided HE) |
| **cost_per_engagement_aud** | | | Per round/net/interceptor |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | | | |
| **dimensions** | | | |
| **power_requirement_w** | | | |
| **mounting_type** | | | Fixed turret / vehicle / tripod / handheld |
| **ip_rating** | | | |
| **operating_temp_c** | | | |
| **cost_aud** | | | Unit cost |

## Notes

-
