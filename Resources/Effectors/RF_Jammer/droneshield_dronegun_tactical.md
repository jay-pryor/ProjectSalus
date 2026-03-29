# DroneShield DroneGun Tactical

**Manufacturer:** DroneShield
**Last Updated:** March 2026
**Vendor Research:** `../../VendorResearch/DroneShield/products_and_specs.md`

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | 2500 | datasheet | "Up to 2.5 km" |
| **min_range_m** | 0 | estimated | |
| **engagement_arc_deg** | 30 | estimated | Directional rifle-style, estimated 30° cone |
| **elevation_arc_deg** | 30 | estimated | Matched to azimuth for directional antenna |
| **frequency_bands_jammed** | 433 MHz, 915 MHz, GNSS L2, GNSS L1, 2.4 GHz, 5.8 GHz | datasheet | 5 selectable bands |
| **jam_gnss** | true | datasheet | GNSS L1 (1575-1605 MHz) and L2 (1227-1251 MHz) |
| **jam_c2** | true | datasheet | ISM bands |
| **jam_video** | true | estimated | 5.8 GHz band covers video downlinks |
| **mounting_height_m** | 1.5 | estimated | Handheld at shoulder height |
| **requires_los** | true | estimated | Directional — must point at target |

## Engagement Parameters

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **reaction_time_s** | 5 | estimated | Manual operation — operator must aim |
| **simultaneous_engagements** | 1 | estimated | Directional, single target |
| **reload_time_s** | 2 | estimated | Electronic, re-aim required |
| **defeat_probability** | 0.8 | estimated | Against commercial drones with known protocols |
| **defeat_mechanism** | C2 + GNSS disruption — forces failsafe (RTH/hover/land) | datasheet | |
| **erp_dbm** | | | Not published |

## Legal / Regulatory

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **legal_restrictions** | Not FCC authorized; US sales restricted to government agencies | datasheet | Export controlled |
| **mounting_type** | Handheld (rifle-style) | datasheet | |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | 7.3 | datasheet | Including 2x batteries |
| **dimensions** | Shipping: 1422 x 450 x 203 mm | datasheet | |
| **power_requirement_w** | | | Battery powered, 14.4 VDC |
| **ip_rating** | IP54 | datasheet | |
| **operating_temp_c** | -20 to +55 | datasheet | |
| **cost_aud** | | | Not published |

## Notes

- NATO Stock Number: 5865661650137
- Battery life: 2+ hours aggregate operational time
- 5 selectable frequency bands
- Internal aluminium frame
- MIL-STD 1913 rails for scope mounting
- Shipping weight: 18 kg including packaging
