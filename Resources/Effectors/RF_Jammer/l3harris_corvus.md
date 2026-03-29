# L3Harris CORVUS-RAVEN / ICN

**Manufacturer:** L3Harris
**Last Updated:** March 2026
**Vendor Research:** `../../VendorResearch/L3Harris/products_and_specs.md`

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | 4000 | datasheet | Detection range "up to 4 km". Jamming range likely similar or shorter. |
| **min_range_m** | 0 | estimated | |
| **engagement_arc_deg** | 360 | estimated | |
| **elevation_arc_deg** | | | Not published |
| **frequency_bands_jammed** | 20 MHz - 6 GHz | datasheet | CORVUS ICN EW solutions |
| **jam_gnss** | true | estimated | 20 MHz - 6 GHz covers GNSS bands |
| **jam_c2** | true | datasheet | |
| **jam_video** | true | estimated | 5.8 GHz within range |
| **mounting_height_m** | 3 | estimated | Portable/vehicle |
| **requires_los** | false | estimated | |

## Engagement Parameters

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **reaction_time_s** | 2 | estimated | |
| **simultaneous_engagements** | 5 | estimated | |
| **reload_time_s** | 0 | estimated | Continuous |
| **defeat_probability** | 0.75 | estimated | |
| **defeat_mechanism** | RF jamming to disrupt drone control links and navigation | datasheet | |
| **erp_dbm** | | | Not published |

## Legal / Regulatory

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **legal_restrictions** | Military use | estimated | |
| **mounting_type** | Portable / vehicle | datasheet | Lightweight, portable |

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

- Core technology: Individual CORVUS Node (ICN)
- Also has passive RF detection capability (dual-role detect+defeat)
- Target set: primarily Class 1 UAS
- Also integrated into Drone Guardian system
- CORVUS ICN EW solutions cover 20 MHz to 6 GHz — very wide band coverage
- VAMPIRE Killcode is the EW variant of the VAMPIRE kinetic system
