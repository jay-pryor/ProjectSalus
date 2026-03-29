# [Product Name]

**Manufacturer:** [Vendor]
**Last Updated:** [Date]
**Vendor Research:** [Link to VendorResearch file]

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | | | Range in what conditions? (open field / urban / rural) |
| **min_range_m** | | | |
| **sensitivity_dbm** | | | Receiver sensitivity. CRITICAL for RF model. If not published, back-calculate from stated range + FSPL. |
| **frequency_bands** | | | List: 433 MHz, 900 MHz, 2.4 GHz, 5.8 GHz, etc. |
| **frequency_range_mhz** | | | Min-max coverage in MHz |
| **azimuth_coverage_deg** | | | 360 for omni, 90-120 for directional |
| **elevation_coverage_deg** | | | Often not specified for RF |
| **mounting_height_m** | | | Antenna height AGL |
| **requires_los** | false | estimated | Usually false for passive RF. True only for directional DF sensors. |

## Detection Capabilities

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **can_identify_protocol** | | | Can it ID the drone make/model? |
| **can_geolocate_drone** | | | AOA / TDOA geolocation? |
| **can_geolocate_operator** | | | Operator location? |
| **direction_finding** | | | Bearing to source? |
| **classification_capability** | | | "detect only" / "protocol ID" / "make/model ID" |

## Range by Environment (if available)

| Environment | Detection Range | Source |
|-------------|----------------|--------|
| Open field | | |
| Rural | | |
| Urban | | |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | | | |
| **dimensions** | | | |
| **power_requirement_w** | | | |
| **ip_rating** | | | |
| **operating_temp_c** | | | |
| **cost_aud** | | | |

## Notes

-
