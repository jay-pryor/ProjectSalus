# DroneShield DroneSentry-X Mk2 (Detection Mode)

**Manufacturer:** DroneShield
**Last Updated:** March 2026
**Vendor Research:** `../../VendorResearch/DroneShield/products_and_specs.md`

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | 8000 | estimated | Uses same RFAI engine as RfOne Mk2. Range not separately published. |
| **min_range_m** | 0 | estimated | Passive sensor |
| **sensitivity_dbm** | -103 | estimated | Same RFAI engine as RfOne Mk2. Back-calculated: 8 km, 2.4 GHz, 23 dBm Tx. See EstimationModels.md. Slider: -90 to -130 dBm. |
| **frequency_bands** | ISM bands | datasheet | "Full hemispheric" detection |
| **frequency_range_mhz** | | | Not published |
| **azimuth_coverage_deg** | 360 | datasheet | Full hemispheric coverage |
| **elevation_coverage_deg** | 180 | datasheet | Hemispheric |
| **mounting_height_m** | 3 | estimated | Vehicle roof rack or tripod mast |
| **requires_los** | false | estimated | Passive RF |

## Detection Capabilities

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **can_identify_protocol** | true | datasheet | RFAI engine |
| **can_geolocate_drone** | true | datasheet | DroneLocator technology — real-time drone and controller coordinates, altitude, velocity |
| **can_geolocate_operator** | true | datasheet | DroneLocator provides controller position |
| **direction_finding** | true | datasheet | Directional (cardinal) bearing target identification |
| **classification_capability** | make/model ID | datasheet | RFAI engine, 150+ drone models |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | 46 | datasheet | Including brackets |
| **dimensions** | 710 x 710 x 532 mm | datasheet | Antenna-mounted height |
| **power_requirement_w** | | | Not published |
| **ip_rating** | IP67 | datasheet | |
| **operating_temp_c** | -20 to +55 | datasheet | |
| **cost_aud** | | | Not published |

## Notes

- Combined detect + defeat in single unit (defeat specs in Effectors/RF_Jammer/)
- RFAI-ATK technology for electronic countermeasure
- Simultaneous multi-band receive and transmit
- DroneLocator provides real-time drone AND controller geolocation
- Available in detect-only or detect+defeat variants
- Deployment: vehicle roofs, vessels, unmanned platforms, fixed-site on tripod/tower
- MOSA (Modular Open Systems Approach) for third-party integration
- Human-in-the-loop, autonomous, and remote operational modes
