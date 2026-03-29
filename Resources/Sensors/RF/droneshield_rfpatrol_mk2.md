# DroneShield RfPatrol Mk2

**Manufacturer:** DroneShield
**Last Updated:** March 2026
**Vendor Research:** `../../VendorResearch/DroneShield/products_and_specs.md`

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | 4000 | datasheet | Rural. Urban: 1 km. |
| **min_range_m** | 0 | estimated | Passive sensor |
| **sensitivity_dbm** | -97 | estimated | Back-calculated: 4 km at 2.4 GHz, 23 dBm Tx, FSPL ~120 dB. See EstimationModels.md. Slider: -90 to -130 dBm. |
| **frequency_bands** | ISM bands, WiFi, custom protocols | datasheet | Integrated SDR |
| **frequency_range_mhz** | | | Not published |
| **azimuth_coverage_deg** | 360 | datasheet | Omni-directional |
| **elevation_coverage_deg** | | | Not published |
| **mounting_height_m** | 1.5 | estimated | Wearable — body height |
| **requires_los** | false | estimated | Passive RF |

## Detection Capabilities

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **can_identify_protocol** | true | datasheet | SDR scanning technology |
| **can_geolocate_drone** | false | datasheet | Detection and classification only, no geolocation |
| **can_geolocate_operator** | false | datasheet | |
| **direction_finding** | false | estimated | Omni antenna, no DF capability stated |
| **classification_capability** | protocol ID | datasheet | Identifies drone signals |

## Range by Environment

| Environment | Detection Range | Source |
|-------------|----------------|--------|
| Rural | Up to 4 km | datasheet |
| Urban | Up to 1 km | datasheet |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | 0.8 | datasheet | 800 g body, ~1.2 kg with accessories |
| **dimensions** | 156.8 x 92 x 48.8 mm | datasheet | Excluding antennas and battery |
| **power_requirement_w** | | | Battery powered |
| **ip_rating** | | | Not published |
| **operating_temp_c** | | | Not published |
| **cost_aud** | | | Not published |

## Notes

- Wearable form factor — body-mounted passive detection
- Battery life: up to 8 hours continuous
- Alert modes: visual, haptic, audible
- Operating modes: "Stealth" and "Glimpse"
- Omni-directional ISM band antenna supplied
- NATO-standard military-grade rechargeable lithium-ion battery
- No intentional RF emissions (passive operation)
- Data feed output for BMS integration
- Part of Immediate Response Kit (IRK) paired with DroneGun Mk4
