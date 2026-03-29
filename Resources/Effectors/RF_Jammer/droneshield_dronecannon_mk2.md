# DroneShield DroneCannon Mk2

**Manufacturer:** DroneShield
**Last Updated:** March 2026
**Vendor Research:** `../../VendorResearch/DroneShield/products_and_specs.md`

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | 2000 | estimated | Fixed-site jammer. Range not published. Estimated from XPELLER jammer (1.5 km confirmed, 10.4 km demonstrated). |
| **min_range_m** | 0 | estimated | |
| **engagement_arc_deg** | 90 | datasheet | Per unit. 360° with 4 units on single mast. |
| **elevation_arc_deg** | | | Not published |
| **frequency_bands_jammed** | Multiple ISM bands, GNSS | datasheet | Simultaneous multi-band |
| **jam_gnss** | true | datasheet | "Interrupts navigation for controlled descent" |
| **jam_c2** | true | datasheet | |
| **jam_video** | true | datasheet | "Immediate cessation of video link to controller" |
| **mounting_height_m** | 8 | estimated | Mast-mounted fixed site |
| **requires_los** | false | estimated | 90° sector suggests directional but not precision-aimed |

## Engagement Parameters

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **reaction_time_s** | 0.5 | datasheet | "Instant RF disruption" |
| **simultaneous_engagements** | 20 | estimated | Sector jammer — all drones in sector affected. Set to saturation cap. |
| **reload_time_s** | 0 | estimated | Continuous jammer, no reload concept |
| **defeat_probability** | 0.8 | estimated | Against commercial drones with known protocols |
| **defeat_mechanism** | RF disruption — forces UAS to ground or return-to-home | datasheet | Non-lethal, non-kinetic |
| **erp_dbm** | | | Not published |

## Legal / Regulatory

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **legal_restrictions** | Requires national regulatory authorisation for operational use | datasheet | |
| **mounting_type** | Fixed (mast-mounted) | datasheet | |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | | | Not published |
| **dimensions** | | | Not published |
| **power_requirement_w** | | | Not published |
| **ip_rating** | | | Not published |
| **operating_temp_c** | | | Not published |
| **cost_aud** | | | Not published |

## Notes

- Part of DroneSentry fixed-site system or standalone
- Pairs with RfOne Mk2 via DroneSentry-C2 for autonomous operation (no man-in-the-loop required)
- Integrated into Lockheed Martin Australia's Agile Shield programme
- In operational use in Ukraine
- Selected/recommended by U.S. DoD for base protection
