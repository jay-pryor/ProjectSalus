# Anduril Pulsar

**Manufacturer:** Anduril
**Last Updated:** March 2026
**Vendor Research:** `../../VendorResearch/Anduril_Australia/products_and_specs.md`

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | 3000 | estimated | Software-defined EW. Range not published. Estimated from similar military-grade EW systems. |
| **min_range_m** | 0 | estimated | |
| **engagement_arc_deg** | 360 | estimated | Fixed variant uses directional antennas; Pulsar-V vehicle-mounted likely has wider coverage |
| **elevation_arc_deg** | | | Not published |
| **frequency_bands_jammed** | Wide range | estimated | "Electronic Support (ESM), Electronic Attack (EA/jamming)" — frequencies not published |
| **jam_gnss** | true | estimated | Military-grade EW platform |
| **jam_c2** | true | estimated | |
| **jam_video** | true | estimated | |
| **mounting_height_m** | 3 | estimated | Vehicle/tripod/airborne depending on variant |
| **requires_los** | false | estimated | EW platform — depends on variant |

## Engagement Parameters

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **reaction_time_s** | 1 | estimated | AI/ML-powered real-time threat identification |
| **simultaneous_engagements** | 10 | estimated | Software-defined — can address multiple threats |
| **reload_time_s** | 0 | estimated | Continuous electronic |
| **defeat_probability** | 0.8 | estimated | ML-powered adaptive jamming |
| **defeat_mechanism** | Software-defined electronic attack — AI-driven adaptive jamming | datasheet | |
| **erp_dbm** | | | Not published |

## Legal / Regulatory

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **legal_restrictions** | Military use | estimated | |
| **mounting_type** | Multiple variants — see notes | datasheet | |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | 11.3 | datasheet | Pulsar-L (Lite): <25 lbs (11.3 kg) |
| **dimensions** | Shoebox-sized | datasheet | Pulsar-L |
| **power_requirement_w** | | | Not published |
| **ip_rating** | | | Not published |
| **operating_temp_c** | | | Not published |
| **cost_aud** | | | Not published |

## Notes

- Variants: Pulsar-V (vehicle), Pulsar Alpha (airborne), Pulsar (fixed), Pulsar-L (man-portable)
- Pulsar-L: <25 lbs, shoebox-sized, operational in as little as 2 minutes
- Functions: ESM, EA (jamming), Direction Finding, Geolocation, Communications
- Modular "Lego block" design with four core components
- Software-defined with rapid reprogramming
- ML at the tactical edge for real-time threat identification
- Concept to deployment in 8 months
- Part of Anduril Counter-UAS Fly-Away Kit
