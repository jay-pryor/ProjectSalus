# DroneShield RfOne Mk2

**Manufacturer:** DroneShield
**Last Updated:** March 2026
**Vendor Research:** `../../VendorResearch/DroneShield/products_and_specs.md`

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | 8000 | datasheet | "Up to 8 km" |
| **min_range_m** | 0 | estimated | Passive sensor, no blind zone |
| **sensitivity_dbm** | -103 | estimated | Back-calculated: 8 km at 2.4 GHz, 23 dBm Tx, FSPL ~126 dB. See EstimationModels.md. Slider: -90 to -130 dBm. |
| **frequency_bands** | ISM bands, WiFi | datasheet | Specific bands not enumerated. SDR-based, likely covers 433 MHz, 900 MHz, 2.4 GHz, 5.8 GHz. |
| **frequency_range_mhz** | | | Not published. "ISM bands" implies at minimum 2.4 GHz and 5.8 GHz. |
| **azimuth_coverage_deg** | 90 | datasheet | 4 units required for 360° coverage |
| **elevation_coverage_deg** | | | Not published |
| **mounting_height_m** | 5 | estimated | Mast mounted typical |
| **requires_los** | false | estimated | Passive RF — does not require LOS |

## Detection Capabilities

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **can_identify_protocol** | true | datasheet | RFAI detection database identifies drone make/model |
| **can_geolocate_drone** | false | estimated | Single unit provides direction only. Multiple units enable triangulation. |
| **can_geolocate_operator** | false | estimated | Triangulation with multiple installations possible |
| **direction_finding** | true | datasheet | "RF direction-finding with high accuracy" |
| **classification_capability** | make/model ID | datasheet | RFAI database identifies 150+ drone models |

## Range by Environment

| Environment | Detection Range | Source |
|-------------|----------------|--------|
| Open field | Up to 8 km | datasheet |
| Rural | | Not published |
| Urban | | Not published |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | | | Not published |
| **dimensions** | | | Not published |
| **power_requirement_w** | | | Not published. External power (not battery). |
| **ip_rating** | | | Not published. "Built for wide range of environmental conditions." |
| **operating_temp_c** | | | Not published |
| **cost_aud** | | | Not published |

## Notes

- Completely passive / non-emitting — no spectrum approvals required
- Powered by DroneShield's proprietary RFAI detection database (subscription-based updates)
- Daisy-chain power and data connectors between sensors
- Integrates with DroneSentry-C2 or third-party C2 via common APIs
- Advanced scanning: customisable per-device scanning patterns (AI-powered RF, WiFi, other emissions)
- Ideal for aviation environments where active RF emissions are restricted
