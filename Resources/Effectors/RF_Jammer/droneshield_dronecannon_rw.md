# DroneShield DroneCannon RW

**Manufacturer:** DroneShield
**Last Updated:** March 2026
**Vendor Research:** `../../VendorResearch/DroneShield/products_and_specs.md`

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | 1500 | estimated | Vehicle-mounted soft-kill. Range not published. |
| **min_range_m** | 0 | estimated | |
| **engagement_arc_deg** | 360 | estimated | Remote weapon station mount — likely full traverse |
| **elevation_arc_deg** | | | Not published |
| **frequency_bands_jammed** | ISM bands, GNSS | datasheet | "Wide range of drone ISM bands + GNSS" |
| **jam_gnss** | true | datasheet | |
| **jam_c2** | true | datasheet | |
| **jam_video** | true | estimated | ISM bands cover video |
| **mounting_height_m** | 3 | estimated | Vehicle RWS mount |
| **requires_los** | false | estimated | Omnidirectional jammer |

## Engagement Parameters

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **reaction_time_s** | 1 | estimated | Electronic, vehicle-mounted |
| **simultaneous_engagements** | 20 | estimated | Omnidirectional — all drones in range affected |
| **reload_time_s** | 0 | estimated | Continuous jammer |
| **defeat_probability** | 0.8 | estimated | Against commercial drones |
| **defeat_mechanism** | Soft-kill — forces drones into fail-safe mode (hover or slow descent) | datasheet | |
| **erp_dbm** | | | Not published |

## Legal / Regulatory

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **legal_restrictions** | Requires regulatory authorisation | estimated | |
| **mounting_type** | Vehicle RWS (Remote Weapon Station) | datasheet | Any remote weapon station |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | 10 | datasheet | Per module |
| **dimensions** | | | Not published |
| **power_requirement_w** | | | 28V DC |
| **ip_rating** | | | Not published |
| **operating_temp_c** | | | Not published |
| **cost_aud** | | | Not published |

## Notes

- Designed for mounting on any remote weapon station
- Lightweight chassis with shock/vibration isolators for mobile operations
- "Defeats UAVs at any speed, including swarms"
- Available in Desert Tan and Black
