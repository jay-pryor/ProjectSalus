# [Drone Name]

**Manufacturer:** [Vendor]
**Last Updated:** [Date]

---

## Flight Performance

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_speed_ms** | | | |
| **typical_speed_ms** | | | Cruise speed, usually 50-70% of max |
| **max_altitude_m** | | | Software-limited? Can be unlocked? |
| **typical_altitude_m** | | | Default for corridor analysis |
| **endurance_min** | | | Flight time |
| **weight_kg** | | | MTOW |
| **payload_capacity_kg** | | | |

## Radar Signature

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **rcs_m2** | | | At what frequency/band? |
| **rcs_band** | | | Per-band if available: "X-band: 0.01, Ku-band: 0.008" |

## RF Signature

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **rf_protocol** | | | DJI OcuSync / Lightbridge / MAVLink / WiFi / etc. |
| **rf_frequency_mhz** | | | C2 + video link frequencies |
| **transmit_power_dbm** | | | CRITICAL for RF detection model |
| **rf_emission_continuous** | | | Continuous or burst/hopping? |
| **autonomous_capable** | | | Can fly without C2 link? If yes, RF sensors may miss it. |
| **gnss_required** | | | If no, GNSS jamming is ineffective |

## Other Signatures

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **visual_signature** | | | Small (< 250mm) / Medium (250-600mm) / Large (> 600mm) |
| **thermal_signature** | | | Low / Medium / High |
| **acoustic_signature** | | | Quiet / Medium / Loud |
| **acoustic_detection_range_factor** | | | Multiplier on sensor base range. Quiet ≈ 0.5, standard ≈ 1.0, loud ≈ 1.5 |

## Threat Assessment

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **evasion_capability** | | | "none" / "basic" / "advanced" |
| **category** | commercial_multirotor | fixed | |

## Notes

-
