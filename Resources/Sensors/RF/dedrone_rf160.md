# Dedrone DedroneSensor RF-160

**Manufacturer:** Dedrone (Axon)
**Last Updated:** March 2026
**Vendor Research:** `../../VendorResearch/Dedrone_Axon/products_and_specs.md`

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | 5000 | datasheet | Maximum. Average: 1,600 m. |
| **min_range_m** | 0 | estimated | Passive sensor |
| **sensitivity_dbm** | -99 | estimated | Back-calculated: 5 km max at 2.4 GHz, 23 dBm Tx, FSPL ~122 dB. See EstimationModels.md. Slider: -90 to -130 dBm. |
| **frequency_bands** | 2.4 GHz, 5.8 GHz | datasheet | Primary bands. Advanced antenna config for out-of-band detection. |
| **frequency_range_mhz** | | | Not published |
| **azimuth_coverage_deg** | 360 | estimated | Omni, but no direction finding |
| **elevation_coverage_deg** | | | Not published |
| **mounting_height_m** | 5 | estimated | |
| **requires_los** | false | estimated | Passive RF |

## Detection Capabilities

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **can_identify_protocol** | true | datasheet | ~300 drone types |
| **can_geolocate_drone** | false | datasheet | No direction finding |
| **can_geolocate_operator** | false | datasheet | |
| **direction_finding** | false | datasheet | No DF capability — key difference from RF-360 |
| **classification_capability** | make/model ID | datasheet | 300 drone types |

## Range by Environment

| Environment | Detection Range | Source |
|-------------|----------------|--------|
| Average | 1,600 m | datasheet |
| Maximum | Up to 5,000 m | datasheet |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | | | Not published |
| **dimensions** | | | Not published |
| **power_requirement_w** | | | Not published. Integrated LTE. |
| **ip_rating** | | | Not published |
| **operating_temp_c** | | | Not published |
| **cost_aud** | 17250 | estimated | ~$11,500 USD (2024 ref.) converted at ~1.5 AUD/USD |

## Notes

- Lower-cost sensor than RF-360 — no direction finding capability
- Integrated LTE for automatic cloud connection
- Good for detection/alerting in distributed networks (DedroneCity)
