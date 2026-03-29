# [Drone Name]

**Manufacturer:** [Vendor]
**Last Updated:** [Date]

---

## Flight Performance

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_speed_ms** | | | |
| **typical_speed_ms** | | | Cruise speed |
| **min_speed_ms** | | | Stall speed — fixed-wing can't hover |
| **typical_altitude_m** | | | Often higher than multirotors: 100-500m |
| **endurance_min** | | | Often 60-180+ min |
| **weight_kg** | | | |
| **wingspan_m** | | | Affects visual detection range |

## Radar Signature

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **rcs_m2** | | | Larger than multirotors: 0.05-2 m² |

## RF Signature

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **rf_protocol** | | | MAVLink / proprietary / military datalink |
| **rf_frequency_mhz** | | | |
| **transmit_power_dbm** | | | |
| **autonomous_capable** | | | Often yes — pre-programmed waypoints |
| **gnss_required** | | | Most autopilots are GPS-dependent |

## Other Signatures

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **visual_signature** | | | Medium to Large depending on wingspan |
| **acoustic_signature** | | | Prop: Medium. Electric pusher: Quiet. Jet: Loud. |
| **acoustic_detection_range_factor** | | | Prop ≈ 0.8-1.0, electric ≈ 0.5-0.7, jet ≈ 1.5-2.0 |

## Threat Assessment

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **evasion_capability** | | | "none" / "basic" / "advanced" |
| **category** | fixed_wing | fixed | |

## Notes

-
