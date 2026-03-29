# Dedrone DedroneDefender

**Manufacturer:** Dedrone (Axon)
**Last Updated:** March 2026
**Vendor Research:** `../../VendorResearch/Dedrone_Axon/products_and_specs.md`

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | 500 | estimated | Handheld narrowband jammer. Legacy Battelle DroneDefender demonstrated 400m. |
| **min_range_m** | 0 | estimated | |
| **engagement_arc_deg** | 20 | estimated | Directional handheld |
| **elevation_arc_deg** | 20 | estimated | |
| **frequency_bands_jammed** | RF control frequencies, GPS, GLONASS, BeiDou, Galileo, SBAS, QZSS | datasheet | |
| **jam_gnss** | true | datasheet | GPS, GLONASS, BeiDou, Galileo, SBAS, QZSS |
| **jam_c2** | true | datasheet | RF control frequencies |
| **jam_video** | true | estimated | |
| **mounting_height_m** | 1.5 | estimated | Handheld |
| **requires_los** | true | estimated | Directional — must point at target |

## Engagement Parameters

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **reaction_time_s** | 0.1 | datasheet | Cold start time: <0.1 seconds |
| **simultaneous_engagements** | 1 | estimated | Directional |
| **reload_time_s** | 1 | estimated | Re-aim |
| **defeat_probability** | 0.75 | estimated | Narrowband/"comb" jamming — more targeted than broadband |
| **defeat_mechanism** | Narrowband/comb jamming — disrupts specific RF control + GNSS | datasheet | |
| **erp_dbm** | | | Not published |

## Legal / Regulatory

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **legal_restrictions** | Requires regulatory authorisation | estimated | |
| **mounting_type** | Handheld | datasheet | |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | 3.4 | datasheet | |
| **dimensions** | 560 x 127 x 254 mm | datasheet | |
| **power_requirement_w** | | | Battery powered |
| **ip_rating** | | | MIL-STD-810H rated |
| **operating_temp_c** | | | MIL-STD-810H |
| **cost_aud** | | | Not published |

## Notes

- Narrowband/"comb" jamming — more targeted than broadband, potentially less collateral interference
- Continuous operation: ~1 hour on battery
- MIL-STD-810H rated
- Legacy: based on Battelle DroneDefender (700+ units sold to allied military forces)
