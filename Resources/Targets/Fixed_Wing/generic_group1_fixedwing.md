# Generic Group 1 Fixed-Wing UAS

**Manufacturer:** Generic
**Last Updated:** March 2026

---

## Flight Performance

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_speed_ms** | 30 | estimated | ~108 km/h typical for small electric fixed-wing |
| **typical_speed_ms** | 20 | estimated | ~72 km/h cruise |
| **min_speed_ms** | 10 | estimated | ~36 km/h stall speed |
| **typical_altitude_m** | 200 | estimated | Higher than multirotors, typical ISR altitude |
| **endurance_min** | 90 | estimated | 60-120 min for battery electric small fixed-wing |
| **weight_kg** | 5 | estimated | Group 1: <20 lbs (<9 kg). Typical 2-8 kg. |
| **wingspan_m** | 1.5 | estimated | 1-2m typical for Group 1 |

## Radar Signature

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **rcs_m2** | 0.1 | estimated | Larger than multirotor due to wingspan. Composite construction keeps it moderate. |

## RF Signature

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **rf_protocol** | MAVLink | estimated | ArduPilot/PX4 open-source autopilots common |
| **rf_frequency_mhz** | [900] | estimated | 900 MHz telemetry link typical for range |
| **transmit_power_dbm** | 27 | estimated | 500 mW telemetry radio typical |
| **autonomous_capable** | true | estimated | Pre-programmed waypoint missions standard for fixed-wing |
| **gnss_required** | true | estimated | Autopilot GPS-dependent for navigation |

## Other Signatures

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **visual_signature** | Medium | estimated | 1-2m wingspan visible at distance |
| **acoustic_signature** | Medium | estimated | Electric pusher prop |
| **acoustic_detection_range_factor** | 0.7 | estimated | Quieter than multirotors at altitude |

## Threat Assessment

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **evasion_capability** | none | estimated | Pre-programmed straight-line approach for MVP |
| **category** | fixed_wing | fixed | |

## Notes

- Group 1 UAS: <20 lbs, <1200 ft AGL (US DoD classification)
- Long endurance enables persistent ISR / loitering over target area
- Autonomous operation (waypoints) means RF detection may only see telemetry link, not continuous C2
- GNSS jamming is typically effective against autopilot-dependent fixed-wing
- SYPAQ Corvo PPDS is an example: 2.4 kg empty, 3 kg payload, 120 km range, GPS-independent capable
