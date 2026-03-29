# Dedrone DedroneSensor RF-360

**Manufacturer:** Dedrone (Axon)
**Last Updated:** March 2026
**Vendor Research:** `../../VendorResearch/Dedrone_Axon/products_and_specs.md`

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | 5000 | datasheet | Maximum. Typical: 2,000 m. |
| **min_range_m** | 0 | estimated | Passive sensor |
| **sensitivity_dbm** | -99 | estimated | Back-calculated: 5 km at 2.4 GHz, 23 dBm Tx, FSPL ~122 dB. See EstimationModels.md. Slider: -90 to -130 dBm. |
| **frequency_bands** | Broad range, dual-radio | datasheet | Specific bands not enumerated |
| **frequency_range_mhz** | | | Not published explicitly |
| **azimuth_coverage_deg** | 360 | datasheet | With direction finding |
| **elevation_coverage_deg** | | | Not published |
| **mounting_height_m** | 5 | estimated | Pole/mast mounted |
| **requires_los** | false | estimated | Passive RF |

## Detection Capabilities

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **can_identify_protocol** | true | datasheet | DedroneDNA library: 600+ drone models from 150+ manufacturers |
| **can_geolocate_drone** | false | estimated | Direction finding only |
| **can_geolocate_operator** | false | estimated | |
| **direction_finding** | true | datasheet | +/- 5° mean error |
| **classification_capability** | make/model ID | datasheet | 600+ models |

## Range by Environment

| Environment | Detection Range | Source |
|-------------|----------------|--------|
| Typical | 2,000 m | datasheet |
| Maximum | 5,000 m | datasheet |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | 7.0 | datasheet | |
| **dimensions** | 300 x 300 x 405 mm | datasheet | |
| **power_requirement_w** | 60 | datasheet | PoE IEEE 802.3bt (60 W) or AC 100-240V |
| **ip_rating** | IP65 | datasheet | |
| **operating_temp_c** | -20 to +55 | datasheet | |
| **cost_aud** | | | Not published |

## Notes

- Dual-radio design
- Single Ethernet connection (PoE+)
- Integrated LTE and GPS
- Direction finding accuracy: +/- 5 degrees mean error
- 99.7% detection accuracy (DedroneTracker.AI platform)
- Deployed at 65+ active sites across Australia
