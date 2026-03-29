# [Drone Name]

**Manufacturer:** [Vendor]
**Last Updated:** [Date]

---

## Flight Performance

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_speed_ms** | | | |
| **typical_speed_ms** | | | |
| **typical_altitude_m** | | | Often 1000-5000m+ AGL — above most cUAS systems |
| **endurance_min** | | | Often 600+ min (10+ hours) |
| **weight_kg** | | | 25-1500+ kg |

## Radar Signature

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **rcs_m2** | | | 0.5-10+ m² |

## RF Signature

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **rf_protocol** | | | Military datalinks, often encrypted/frequency-hopping |
| **rf_frequency_mhz** | | | Military bands, may be classified |
| **transmit_power_dbm** | | | Higher power: 30-40+ dBm |
| **autonomous_capable** | | | Yes — standard for military |
| **gnss_required** | | | INS/GPS hybrid. GNSS jamming degrades accuracy but INS provides fallback. |

## Other Signatures

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **visual_signature** | | | Large |
| **acoustic_signature** | | | Prop/turboprop: Loud. Jet: Very loud. |
| **acoustic_detection_range_factor** | | | |

## Threat Assessment

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **evasion_capability** | | | "advanced" — military countermeasures |
| **category** | group3_plus | fixed | |

## Applicability Note

Most cUAS effectors in the MVP database cannot engage Group 3+ at typical operating altitudes. Include for completeness and to demonstrate coverage limitations in reports.

## Notes

-
