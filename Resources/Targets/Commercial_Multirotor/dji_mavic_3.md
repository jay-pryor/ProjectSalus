# DJI Mavic 3 Pro

**Manufacturer:** DJI
**Last Updated:** March 2026

---

## Flight Performance

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_speed_ms** | 21 | datasheet | 75.6 km/h in Sport mode |
| **typical_speed_ms** | 15 | estimated | Cruise ~54 km/h |
| **max_altitude_m** | 120 | datasheet | Software-limited. Can be unlocked/modded. |
| **typical_altitude_m** | 50 | estimated | Typical ISR/surveillance altitude |
| **endurance_min** | 43 | datasheet | Max hover time with standard battery |
| **weight_kg** | 0.958 | datasheet | MTOW |
| **payload_capacity_kg** | 0 | datasheet | No external payload capability (stock) |

## Radar Signature

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **rcs_m2** | 0.01 | estimated | Typical for DJI Mavic class. Consistent with Echodyne EchoGuard range table (900m detection). |
| **rcs_band** | | | No per-band data available |

## RF Signature

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **rf_protocol** | DJI OcuSync 3+ | datasheet | |
| **rf_frequency_mhz** | [2400, 5800] | datasheet | 2.4 GHz and 5.8 GHz |
| **transmit_power_dbm** | 26 | estimated | DJI typically 20-26 dBm (100-400 mW) EIRP. Using upper end for Mavic 3. |
| **rf_emission_continuous** | true | estimated | OcuSync maintains continuous link |
| **autonomous_capable** | true | datasheet | Waypoint mission mode. Can fly pre-programmed route without active C2. |
| **gnss_required** | true | datasheet | GPS/GLONASS/Galileo/BeiDou. Required for position hold and waypoints. |

## Other Signatures

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **visual_signature** | Small | estimated | <400mm diagonal |
| **thermal_signature** | Medium | estimated | Battery + motors warm, visible on IR |
| **acoustic_signature** | Medium | estimated | Standard folding props |
| **acoustic_detection_range_factor** | 1.0 | estimated | Baseline reference drone |

## Threat Assessment

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **evasion_capability** | none | estimated | Straight-line for MVP. Operator could deviate but not modelled. |
| **category** | commercial_multirotor | fixed | |

## Notes

- The DJI Mavic 3 is the de facto reference target for cUAS system specifications
- Most vendor detection ranges are quoted against this class of drone
- OcuSync 3+ has frequency hopping but is well-characterised by RF detection systems
- DJI AeroScope (now deprecated) provided Remote ID — newer DJI drones support standard Remote ID
