# Echodyne - Products and Specifications

**Company:** Echodyne Corp., Kirkland, Washington, USA
**Role in LAND 156:** Key partner under LOE1 providing MESA radar sensors for drone detection and tracking
**Website:** [echodyne.com](https://www.echodyne.com)
**ITAR Status:** ITAR-free (global deployment)

Echodyne is the innovator and manufacturer of metamaterials electronically scanned array (MESA) radar technology. MESA uses common materials arranged in a special way to precisely steer radar energy from a dense array without phase shifters, moving parts, or maintenance. This delivers radically reduced size, weight, power, and cost (SWaP-C) compared to traditional ESA radars.

---

## 1. EchoGuard - Compact C-UAS and Surveillance Radar

EchoGuard is a low-SWaP electronically scanned array radar providing high-accuracy detection, tracking, and classification of airspace and ground-based objects.

### Physical Specifications

| Parameter | Value |
|---|---|
| **Dimensions** | 20.3 cm x 16.3 cm x 4 cm |
| **Weight** | 1.25 kg (2.75 lbs) |
| **Power (Operating)** | Less than 50 W |
| **Power (Hot Standby)** | Less than 8 W |
| **Input Voltage (US)** | DC +15 V to +28 V |
| **Input Voltage (International)** | DC +15 V to +24 V |
| **Operating Temperature** | -40 C to +75 C |
| **Weather Protection** | IP67 |
| **Mounting** | VESA 75 and 100 mm standards |

### Radar Performance

| Parameter | Value |
|---|---|
| **Frequency (US)** | 24.45 - 24.65 GHz (K-band, multi-channel) |
| **Frequency (International)** | 24.05 - 24.25 GHz (K-band, multi-channel) |
| **FCC ID** | 2ANLB-MESASSR00053 |
| **Compliance** | CE, RoHS 3, RED (International) |
| **Field of View (Azimuth)** | 120 degrees |
| **Field of View (Elevation)** | 80 degrees |
| **Track Update Rate** | 10 Hz |
| **Simultaneous Tracks** | Up to 20 objects of interest |
| **Beam Steering** | Thousands of pencil-thin beams across FoV in milliseconds |

### Detection Ranges

| Target Type | Detection Range |
|---|---|
| **Pocket UAS (micro drone)** | 200 m |
| **DJI Mavic Pro / Phantom 4** | 900 m |
| **DJI Matrice 600** | 1.4 km |
| **Small Fixed-Wing (Cessna class)** | 2.5 km |
| **Vehicles** | Up to 3.5 km |

### Classification

| Parameter | Detail |
|---|---|
| **Method** | Doppler signature analysis (native in-radar classifier) |
| **Output** | Probability of UAV (p_uav) in track packet |
| **Effective Range** | Within ~400-500 m of radar |
| **Capability** | Distinguishes drones from birds and other airborne objects |

### Data Output and Integration

| Parameter | Value |
|---|---|
| **Interface** | Gigabit Ethernet |
| **R/V Maps** | 40 MB/s |
| **Detections** | 1 MB/s |
| **Measurements** | 1 MB/s |
| **Tracks** | 25 kB/s |
| **Data Protocols** | Echodyne API; Asterix format; FAS (US); SAPIENT (Europe) |

### Portable Deployment

| Parameter | Value |
|---|---|
| **Lightweight Deployment Kit** | Backpack form factor |
| **Kit Weight** | Less than 9 kg (20 lbs) total (radar, computer, tripod, batteries) |

### Key Deployments

- U.S. Army Security Surveillance System (SSS) program - primary sensor for 3D perimeter surveillance
- Selected as radar of choice by dozens of counter-UAS systems providers
- Integrated with EOS Slinger as the cueing radar for LAND 156
- Integrated with Aurelius Systems laser effector platform (demonstrated at DiDEX 2025)

---

## 2. EchoFlight - Airborne Detect-and-Avoid Radar

EchoFlight is an ultra-compact MESA radar designed for airborne platforms, providing detect-and-avoid (DAA) and counter-UAS sensor capability.

### Physical Specifications

| Parameter | Value |
|---|---|
| **Dimensions** | 18.7 cm x 12 cm x 4 cm |
| **Weight** | 817 g (natural convection cooling) |
| **Power (Operating)** | 45 W |
| **Power (Hot Standby)** | Less than 10 W |
| **Input Voltage** | +12 V to +28 V DC |
| **Operating Temperature** | -40 C to +75 C |
| **Weather Protection** | IP67 |

### Detection Ranges

| Target Type | Detection Range |
|---|---|
| **Small Quadcopter** | Up to 750 m |
| **Small Aircraft (Cessna class)** | Up to 2 km |

### Key Features

- High-precision data outputs for integration with drone autopilot systems
- Detection and tracking of both cooperative and non-cooperative aircraft
- Data output options from low bit-rate fully processed tracks to data-rich R/V maps
- Can be combined with ADS-B data sources

### Applications

- Tethered drones for airspace surveillance
- Targeting radar on airborne interceptor platforms (C-UAS interceptor drones)
- Detect-and-avoid systems on UAS (e.g., fitted on AATI AiRanger UAS wings)

---

## 3. MESA Radar Technology Overview

### What is MESA?

Metamaterials Electronically Scanned Array (MESA) is Echodyne's proprietary radar antenna technology. Key attributes:

| Feature | Description |
|---|---|
| **Antenna Design** | Uses metamaterials to steer radar beams without traditional phase shifters |
| **Array Density** | Hundreds of Tx/Rx modules at significantly lower unit cost than traditional ESA |
| **Moving Parts** | None - fully solid-state |
| **Maintenance** | No maintenance required for antenna |
| **SWaP-C** | Radically reduced size, weight, power, and cost vs conventional ESA |

### MESA Radar Family

| Product | Primary Use Case | Weight | Key Differentiator |
|---|---|---|---|
| **EchoGuard** | Ground-based C-UAS and surveillance | 1.25 kg | Largest FoV (120 x 80 deg), longest range |
| **EchoFlight** | Airborne DAA and C-UAS | 817 g | Smallest/lightest, optimised for flight |

### Defence-Specific Features

- Multi-mission capability in modern warfare environments
- Integration with C2 systems via standard protocols (Asterix, FAS, SAPIENT)
- Continuous search while simultaneously tracking multiple targets including swarms
- Up to 10 Hz target revisit rate for precise airspace coordinates
- No ITAR restrictions for global deployment

---

## Sources

- [Echodyne - EchoGuard Product Page](https://www.echodyne.com/radar-solutions-1/echoguard/)
- [Echodyne - Counter-UAS Radar for Defense](https://www.echodyne.com/applications/defense/counter-uas-radar/)
- [Echodyne - EchoGuard Security Datasheet (PDF)](https://www.echodyne.com/media/owckkjvt/echodyne-ts-echoguardsecurity.pdf)
- [EchoFlight Datasheet (PDF)](https://www.echodyne.com/media/ec0jv5tp/ts-echoflight-echodyne.pdf)
- [Defense Advancement - EchoGuard Radar](https://www.defenseadvancement.com/company/echodyne/echoguard-radar/)
- [Defense Advancement - Echodyne Company Profile](https://www.defenseadvancement.com/company/echodyne/)
- [Echodyne - MESA Radar Family Expansion](https://www.echodyne.com/resources/news-events/update-echodyne-develops-family-of-metamaterial-electronically-scanning-array-radars/)
- [Echodyne MESA Defence Brochure (PDF)](https://www.radartutorial.eu/19.kartei/05.perimeter/pubs/brochure-def-echodyne_25ja1.pdf)
- [EverythingRF - EchoFlight](https://www.everythingrf.com/products/radar-systems/echodyne-corp/1069-2160-echoflight)
- [Defense Advancement - Echodyne at DSEI 2025](https://www.defenseadvancement.com/feature/echodyne-highlights-mesa-radar-technology-at-dsei-2025/)
