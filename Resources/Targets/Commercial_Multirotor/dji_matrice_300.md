# DJI Matrice 300 RTK

**Manufacturer:** DJI
**Last Updated:** March 2026

---

## Flight Performance

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_speed_ms** | 23 | datasheet | 82 km/h |
| **typical_speed_ms** | 15 | estimated | |
| **max_altitude_m** | 7000 | datasheet | Max service ceiling (altitude-limited, not software-limited like consumer drones) |
| **typical_altitude_m** | 100 | estimated | Typical operational altitude |
| **endurance_min** | 55 | datasheet | Without payload |
| **weight_kg** | 9.0 | datasheet | MTOW with dual batteries and payload |
| **payload_capacity_kg** | 2.7 | datasheet | |

## Radar Signature

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **rcs_m2** | 0.05 | estimated | Larger airframe than Mavic. Consistent with Echodyne range table (Matrice 600 = 0.05 m² at 1.4 km). |
| **rcs_band** | | | No per-band data |

## RF Signature

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **rf_protocol** | DJI OcuSync 2 | datasheet | |
| **rf_frequency_mhz** | [2400, 5800] | datasheet | |
| **transmit_power_dbm** | 26 | estimated | DJI enterprise-grade, likely higher end: 26 dBm EIRP |
| **rf_emission_continuous** | true | estimated | |
| **autonomous_capable** | true | datasheet | Waypoint, mapping, and SDK-programmable missions |
| **gnss_required** | true | datasheet | GPS/GLONASS/BeiDou/Galileo + RTK positioning |

## Other Signatures

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **visual_signature** | Medium | estimated | 600mm+ class |
| **thermal_signature** | Medium | estimated | |
| **acoustic_signature** | Medium-Loud | estimated | Larger props than Mavic |
| **acoustic_detection_range_factor** | 1.3 | estimated | Louder than Mavic |

## Threat Assessment

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **evasion_capability** | none | estimated | MVP: straight-line |
| **category** | commercial_multirotor | fixed | |

## Notes

- Enterprise/industrial drone — commonly used for mapping, inspection, and ISR
- Significant payload capacity (2.7 kg) makes it a credible threat for payload delivery
- RTK positioning provides centimetre-level accuracy for autonomous operation
- IP45 rated — operates in rain
- Hot-swappable dual battery system
- Successor: DJI Matrice 350 RTK (similar specs, OcuSync 3 Enterprise)
