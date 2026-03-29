# Echodyne EchoGuard

**Manufacturer:** Echodyne
**Last Updated:** March 2026
**Vendor Research:** `../../VendorResearch/Echodyne/products_and_specs.md`

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | 900 | datasheet | Against DJI Mavic Pro / Phantom 4 class target |
| **min_range_m** | 10 | estimated | MESA/FMCW-type, estimated low blind zone |
| **reference_rcs_m2** | 0.01 | estimated | Mavic Pro class, not explicitly stated |
| **azimuth_coverage_deg** | 120 | datasheet | Per panel |
| **elevation_coverage_deg** | 80 | datasheet | |
| **elevation_min_deg** | -5 | estimated | Short-range cUAS AESA. See EstimationModels.md. Slider: -10 to 0. |
| **elevation_max_deg** | 70 | estimated | 80° total FOV. See EstimationModels.md. Slider: +60 to +80. |
| **frequency_band** | K-band | datasheet | |
| **frequency_ghz** | 24.55 | datasheet | US: 24.45-24.65 GHz, International: 24.05-24.25 GHz |
| **mounting_height_m** | 5 | estimated | Tripod/mast typical |
| **requires_los** | true | fixed | Always true for radar |

## Detection Performance

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **scan_type** | AESA (MESA) | datasheet | Metamaterials electronically scanned array |
| **scan_rate_rpm** | N/A | datasheet | Electronic scan, no rotation |
| **track_capacity** | 20 | datasheet | Up to 20 objects of interest simultaneously |
| **update_rate_hz** | 10 | datasheet | 10 Hz target revisit |
| **detection_probability** | | | Not published |
| **false_alarm_rate** | | | Not published |

## Range Table

| Target Type | RCS (m²) | Detection Range |
|-------------|----------|-----------------|
| Pocket UAS (micro drone) | ~0.001 | 200 m |
| DJI Mavic Pro / Phantom 4 | ~0.01 | 900 m |
| DJI Matrice 600 | ~0.05 | 1,400 m |
| Small fixed-wing (Cessna class) | ~1.0 | 2,500 m |
| Vehicles | ~5.0 | 3,500 m |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | 1.25 | datasheet | |
| **dimensions** | 20.3 x 16.3 x 4 cm | datasheet | |
| **power_requirement_w** | 50 | datasheet | Less than 50W operating, <8W hot standby |
| **ip_rating** | IP67 | datasheet | |
| **operating_temp_c** | -40 to +75 | datasheet | |
| **cost_aud** | | | Not published |

## Notes

- ITAR-free — global deployment permitted
- Integrated as cueing radar for EOS Slinger in LAND 156
- Doppler-based classification: outputs probability of UAV (p_uav) in track packet, effective within ~400-500m
- Lightweight deployment kit: backpack form factor, <9 kg total (radar, computer, tripod, batteries)
- FCC ID: 2ANLB-MESASSR00053
- Data protocols: Echodyne API, Asterix, FAS (US), SAPIENT (Europe)
