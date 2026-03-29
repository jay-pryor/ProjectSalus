# DroneShield DroneGun Mk4

**Manufacturer:** DroneShield
**Last Updated:** March 2026
**Vendor Research:** `../../VendorResearch/DroneShield/products_and_specs.md`

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | 1000 | estimated | "Enhanced over Mk3" (Mk3 = 500m). Exact range classified. |
| **min_range_m** | 0 | estimated | |
| **engagement_arc_deg** | 30 | estimated | Directional pistol-form factor |
| **elevation_arc_deg** | 30 | estimated | |
| **frequency_bands_jammed** | ISM bands, GNSS | datasheet | "Wide range of ISM bands + GNSS frequency bands" |
| **jam_gnss** | true | datasheet | |
| **jam_c2** | true | datasheet | |
| **jam_video** | true | estimated | ISM bands include 5.8 GHz video |
| **mounting_height_m** | 1.5 | estimated | Handheld |
| **requires_los** | true | estimated | Directional — must point at target |

## Engagement Parameters

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **reaction_time_s** | 3 | datasheet | Startup time <3 seconds |
| **simultaneous_engagements** | 1 | estimated | Directional, single target |
| **reload_time_s** | 2 | estimated | Electronic |
| **defeat_probability** | 0.8 | estimated | Against commercial drones. Effective against COTS comms (e.g. Russian Orlan-10). |
| **defeat_mechanism** | C2 + GNSS disruption — forces failsafe | datasheet | Non-kinetic jamming only |
| **erp_dbm** | | | Not published (classified) |

## Legal / Regulatory

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **legal_restrictions** | Not FCC authorized; US sales restricted to government agencies | datasheet | |
| **mounting_type** | Handheld (pistol-form) | datasheet | Single-hand operation |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | 3.2 | datasheet | Including battery |
| **dimensions** | 660 x 356 x 213 mm | datasheet | |
| **power_requirement_w** | | | Battery powered (NATO-standard lithium-ion) |
| **ip_rating** | IP67 | datasheet | |
| **operating_temp_c** | -20 to +55 | datasheet | |
| **cost_aud** | | | Not published |

## Notes

- Battery life: 1+ hour continuous operation
- Picatinny rails (top/bottom), QD sling points, safety selector switch
- Part of Immediate Response Kit (IRK) paired with RfPatrol Mk2
- Effective against commercial and military UAS using COTS communications
