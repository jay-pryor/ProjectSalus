# Estimation Models for Missing Specifications

When a vendor doesn't publish a specification, we need a defensible estimate so the simulator can run with a reasonable default. This document defines estimation models for each missing simulation-critical field, with plausible ranges that can be exposed as sliders in the UI.

Each model provides:
- **Plausible range** — the min/max a slider should allow
- **Default value** — a reasonable middle-ground starting point
- **Estimation logic** — why this range is reasonable

These are NOT guesses. They are bounded estimates derived from physics, published data from similar systems, or industry norms. Every estimated value in the product files should reference the model used here.

---

## Sensors

---

### Radar: `elevation_min_deg` / `elevation_max_deg`

Almost no cUAS radar vendor publishes separate min/max elevation angles. We have total elevation coverage for some (e.g. Spexer 2000 3D: 90°, Obsidian: 90° paired) but not the split.

**Estimation logic:** cUAS radars are typically tilted slightly above horizontal to prioritise airspace over ground clutter. The split depends on mounting and intended use.

| Radar Type | `elevation_min_deg` | `elevation_max_deg` | Total Coverage | Logic |
|------------|--------------------|--------------------|----------------|-------|
| Ground surveillance (Spexer 360, Obsidian) | **-5 to 0** (default: -2) | **+20 to +45** (default: +30) | ~30-45° | Optimised for low-altitude, near-horizon targets. Minimal below-horizon look. |
| Short-range cUAS (EchoGuard, Spexer 500) | **-10 to 0** (default: -5) | **+60 to +80** (default: +70) | ~70-80° | Need to see overhead at close range. Published total FOV confirms this. |
| Medium-range AESA (Spexer 2000 3D) | **-5 to 0** (default: -2) | **+80 to +90** (default: +85) | ~90° | Published: 90° total per panel. Slight below-horizon for terrain following. |
| Long-range air defence (KuRFS, Giraffe) | **-3 to 0** (default: -1) | **+60 to +90** (default: +70) | ~70-90° | Designed for aircraft at altitude. Less need for extreme overhead. |

**Slider range for UI:** elevation_min: -15° to 0°. elevation_max: +20° to +90°.

---

### Radar: `reference_rcs_m2` (SAAB Giraffe family)

The Giraffe radars don't publish detection range against specific RCS values for UAS targets. They publish instrumented range (75-400 km) which is against large aircraft.

**Estimation logic:** Use the radar range equation to back-calculate. Detection range scales with RCS^(1/4):

```
R_target = R_ref × (RCS_target / RCS_ref)^(1/4)
```

For Giraffe 1X (75 km instrumented range, X-band AESA, ~150 kg system):
- If we assume 75 km against a 5 m² aircraft target:
- Against 0.01 m² drone: 75 × (0.01/5)^0.25 = 75 × 0.119 ≈ **8.9 km**
- Against 0.1 m² drone: 75 × (0.1/5)^0.25 = 75 × 0.211 ≈ **15.8 km**

| Radar | Assumed Ref Range | Assumed Ref RCS | Est. Range @ 0.01 m² | Est. Range @ 0.1 m² |
|-------|------------------|----------------|----------------------|---------------------|
| Giraffe 1X | 75 km | 5 m² | ~9 km | ~16 km |
| Giraffe 4A | 200 km | 5 m² | ~24 km | ~42 km |
| Giraffe AMB | 100 km | 5 m² | ~12 km | ~21 km |

**Default `reference_rcs_m2`:** Use 5 m² (typical fighter-sized aircraft) as the reference for the published instrumented range. Then let the simulation engine scale to actual drone RCS.

**Slider range:** 1-10 m² for the reference RCS assumption (affects all derived detection ranges).

**Caveat:** These radars are not optimised for micro-drone detection. Their waveforms and processing are designed for aircraft. Actual cUAS performance may be significantly worse than the radar range equation suggests. Apply a **0.5-0.8x performance factor** to account for this.

| Field | Plausible Range | Default | Slider |
|-------|----------------|---------|--------|
| `reference_rcs_m2` (assumed) | 1-10 m² | 5 m² | 1-10 m² |
| `cuas_performance_factor` | 0.3-1.0 | 0.6 | 0.3-1.0 |

---

### RF Sensors: `sensitivity_dbm`

No passive RF sensor vendor publishes receiver sensitivity. This is the single most important missing field for the RF propagation model.

**Estimation logic:** Back-calculate from published max detection range using FSPL.

```
sensitivity_dbm = transmit_power_dbm - FSPL(max_range, frequency)
FSPL(d, f) = 20·log₁₀(d) + 20·log₁₀(f) + 20·log₁₀(4π/c)
```

Assumptions for back-calculation:
- Drone transmit power: 20-26 dBm (DJI class, 100-400 mW EIRP)
- Frequency: 2.4 GHz (worst case — highest FSPL of the common bands)
- Published range is in open field (FSPL-only, no terrain)

| Sensor | Published Range | Assumed Tx Power | FSPL at Range | Derived Sensitivity |
|--------|----------------|-----------------|---------------|-------------------|
| DroneShield RfOne Mk2 | 8 km | 23 dBm (mid) | ~126 dB | ~ **-103 dBm** |
| DroneShield RfPatrol Mk2 | 4 km (rural) | 23 dBm | ~120 dB | ~ **-97 dBm** |
| DroneShield DroneSentry-X | 8 km | 23 dBm | ~126 dB | ~ **-103 dBm** |
| Dedrone RF-360 | 5 km (max) | 23 dBm | ~122 dB | ~ **-99 dBm** |
| Dedrone RF-160 | 5 km (max) | 23 dBm | ~122 dB | ~ **-99 dBm** |

**Plausible range:** -90 to -130 dBm.
- -90 dBm = relatively insensitive (short range, noisy environment)
- -130 dBm = extremely sensitive (lab-grade SDR with low-noise amplifier)

**Default:** Use the back-calculated value from the table above per sensor.

**Slider range for UI:** -90 to -130 dBm.

**Important:** These back-calculations assume the vendor's published range is achievable in true free-space conditions with a DJI-class transmitter. Real-world sensitivity could be 5-10 dB better (more sensitive) if the vendor's range claim is conservative, or 5-10 dB worse if the claim assumes a stronger transmitter or ideal antenna alignment.

---

### RF Sensors: `frequency_range_mhz`

Vendors say "ISM bands" or "broad frequency range" without publishing exact coverage.

**Estimation logic:** cUAS RF sensors must cover the frequencies drones actually use.

| Band | Frequency | Used By | Coverage Likelihood |
|------|-----------|---------|-------------------|
| 433 MHz | 433 | EU ISM, some RC transmitters | Likely on full-range sensors |
| 900 MHz | 868-928 | Crossfire, ELRS, some telemetry | Likely on military-oriented sensors |
| 1.2 GHz | 1200-1300 | Analogue video (legacy), some FPV | Possible on wide-band sensors |
| 2.4 GHz | 2400-2483 | DJI, WiFi drones, ELRS | Almost certain — primary drone band |
| 5.8 GHz | 5725-5875 | DJI video, FPV video, WiFi | Almost certain — primary video band |

**Default per sensor type:**

| Sensor Class | Default `frequency_range_mhz` | Logic |
|-------------|------------------------------|-------|
| Full-range cUAS (RfOne, DroneSentry-X) | 70-6000 | Military-grade, SDR-based, covers all ISM + non-standard |
| Mid-range (RF-360) | 433-5875 | "Broad frequency range, dual-radio" |
| Budget (RF-160, RfPatrol) | 2400-5875 | Published as "2.4 GHz and 5.8 GHz primary" |

**Slider range for UI:** Not applicable — this is discrete, not continuous. Let user toggle which bands the sensor covers.

---

### EO/IR: `instantaneous_fov_h_deg` (HENSOLDT TAROSS)

Not published. TAROSS is a target acquisition sighting system with multiple variants.

**Estimation logic:** Similar military sighting systems (EOTS III, FLIR Ultra, etc.) have:
- Wide FOV: 15-30° (search mode)
- Narrow FOV: 1-5° (identify/track mode)

For coverage modelling, use the wide/search FOV.

| Field | Plausible Range | Default | Logic |
|-------|----------------|---------|-------|
| `instantaneous_fov_h_deg` | 5-30° | 20° | Mid-range target acquisition system. Similar to EOTS III wide mode (26°). |

**Slider range for UI:** 2-40°.

---

## Effectors

---

### RF Jammers: `erp_dbm` (Effective Radiated Power)

No jammer vendor publishes ERP. This is operationally sensitive information.

**Estimation logic:** ERP can be back-calculated from published effective range using the jam-to-signal ratio (J/S) required for disruption. However, this requires knowing the drone's receive sensitivity, which is also unpublished. Instead, use industry benchmarks:

| Jammer Class | Plausible ERP Range | Default | Logic |
|-------------|-------------------|---------|-------|
| Handheld (DroneGun, DedroneDefender) | 30-43 dBm (1-20 W) | 36 dBm (4 W) | Battery-powered, regulatory limits, thermal management. FCC Part 15 limit is 1W EIRP but military exemption allows more. |
| Vehicle-mounted (DroneCannon RW) | 40-50 dBm (10-100 W) | 46 dBm (40 W) | Vehicle power supply, larger antennas, directional gain. |
| Fixed-site (DroneCannon Mk2) | 43-53 dBm (20-200 W) | 50 dBm (100 W) | Mains power, large antenna arrays. |
| Military EW (Pulsar, CORVUS) | 47-60 dBm (50-1000 W) | 53 dBm (200 W) | High-power amplifiers, military power budget. |

**Slider range for UI:** 30-60 dBm (1 W to 1 kW).

**Note:** ERP is post-MVP (jam-to-signal ratio modelling). For MVP, effector coverage uses the published `max_range_m` directly. But having bounded ERP estimates ready means the slider is grounded when we get there.

---

### Effectors: `cost_aud`

Almost never published. However, some data points exist from contracts, media reports, and industry estimates.

| System | Known Data Points | Plausible Range (AUD) | Default (AUD) |
|--------|------------------|----------------------|---------------|
| DroneGun MkIII | | 15,000-30,000 | 20,000 |
| DroneGun Mk4 | | 25,000-50,000 | 35,000 |
| DroneGun Tactical | | 50,000-80,000 | 65,000 |
| DroneCannon Mk2 | | 150,000-300,000 | 200,000 |
| DroneSentry-X Mk2 | | 200,000-400,000 | 300,000 |
| DedroneDefender | | 30,000-60,000 | 45,000 |
| EOS Slinger | <$1.55M USD ≈ ~$2.3M AUD (unit cost published) | 2,000,000-3,000,000 | 2,325,000 |
| EOS Apollo | EUR 71.4M contract for multiple units | 5,000,000-15,000,000 | 10,000,000 |
| Raytheon Coyote (per round) | ~$100K USD | 130,000-180,000 | 150,000 |
| Raytheon Stinger (per round) | ~$38K USD | 50,000-70,000 | 60,000 |
| SAAB RBS 70 BOLIDE (per round) | | 150,000-250,000 | 200,000 |
| SAAB Nimbrix (per round) | "Low cost" | 30,000-80,000 | 50,000 |
| Anduril Anvil | | 50,000-150,000 | 100,000 |
| Anduril Roadrunner | "Low hundreds of thousands" USD | 200,000-500,000 | 350,000 |
| L3Harris VAMPIRE (system) | | 500,000-1,000,000 | 750,000 |
| MESMER | | 200,000-500,000 | 350,000 |
| Raytheon HELWS | | 10,000,000-30,000,000 | 20,000,000 |
| Raytheon Phaser | | 5,000,000-20,000,000 | 12,000,000 |
| Dedrone RF-160 | ~$11,500 USD (2024 list price) | 15,000-20,000 | 17,000 |
| Dedrone RF-360 | | 25,000-50,000 | 35,000 |
| DroneShield RfOne Mk2 | | 30,000-60,000 | 45,000 |
| Echodyne EchoGuard | | 50,000-100,000 | 75,000 |
| HENSOLDT Spexer 500 | | 200,000-500,000 | 350,000 |
| HENSOLDT Spexer 2000 3D | | 500,000-1,500,000 | 1,000,000 |
| QinetiQ Obsidian | | 150,000-400,000 | 275,000 |
| Raytheon KuRFS | | 2,000,000-5,000,000 | 3,500,000 |
| SAAB Giraffe 1X | | 2,000,000-5,000,000 | 3,500,000 |
| Anduril WISP | | 100,000-300,000 | 200,000 |

**Slider range for UI:** Logarithmic scale, $10,000 to $30,000,000 AUD.

**Caveat:** These are rough order-of-magnitude estimates. Actual prices depend on quantities, contracts, integration, and support packages. The simulation should clearly mark cost-based comparisons as indicative only.

---

## Targets

---

### Drone: `rcs_m2` — Academic Reference Data

RCS values for common drones have been measured in published academic studies:

| Drone | Measured RCS (m²) | Band | Source |
|-------|-------------------|------|--------|
| DJI Phantom 4 | 0.01-0.02 | X-band | Multiple academic papers |
| DJI Mavic Pro | 0.005-0.015 | X-band | Estimated from Phantom 4 scaling |
| DJI Mavic 3 | 0.008-0.015 | X-band | Estimated — similar airframe to Mavic Pro |
| DJI Matrice 600 | 0.03-0.1 | X-band | Echodyne range table implies ~0.05 |
| DJI Matrice 300 | 0.03-0.08 | X-band | Slightly smaller than M600 |
| Generic 5" FPV | 0.003-0.01 | X-band | Carbon fibre, minimal metal |
| Small fixed-wing (1-2m) | 0.05-0.2 | X-band | Composite construction |
| Group 3 fixed-wing | 0.5-2.0 | X-band | Larger, metal components |

**Note:** RCS varies significantly with aspect angle (front/side/top), radar frequency, and specific airframe construction. These are median values for "most likely" engagement geometry (approaching, slight angle off nose).

**Slider range for UI:** 0.001-5.0 m² (logarithmic scale).

---

### Drone: `transmit_power_dbm`

Published for DJI (FCC filings) but estimated for others.

| Protocol/Platform | Plausible Range | Default | Source |
|-------------------|----------------|---------|--------|
| DJI OcuSync (all versions) | 20-26 dBm | 23 dBm | FCC filings for DJI controllers |
| DJI Lightbridge | 18-24 dBm | 21 dBm | Older protocol, lower power |
| WiFi drones (cheap consumer) | 15-20 dBm | 18 dBm | Standard WiFi EIRP limits |
| ExpressLRS 2.4 GHz | 20-30 dBm | 25 dBm | User-configurable in firmware |
| Crossfire 900 MHz | 25-33 dBm | 30 dBm | Long-range protocol, higher power |
| Analogue FPV video 5.8 GHz | 25-33 dBm | 30 dBm | 200-2000 mW typical |
| MAVLink telemetry 900 MHz | 20-30 dBm | 27 dBm | SiK radios, RFD900 |
| Military datalink | 30-43 dBm | 37 dBm | Higher power, directional antennas |

**Slider range for UI:** 10-43 dBm (10 mW to 20 W).

---

*This document should be referenced whenever an `estimated` value is entered in a product file. The product file's Notes column should cite which estimation model was used.*
