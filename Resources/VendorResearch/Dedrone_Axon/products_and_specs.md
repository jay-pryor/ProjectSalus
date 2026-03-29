# Dedrone by Axon -- Counter-UAS Product Line and Specifications

> **Last Updated:** March 2026
>
> Dedrone was acquired by Axon in October 2024. The combined entity operates as "Dedrone by Axon" and is recognized as a global leader in airspace awareness and counter-UAS solutions, deployed across 900+ sites in 33+ countries with over 800 million drone detections worldwide.

---

## Table of Contents

1. [DedroneTracker.AI (C2 Software Platform)](#1-dedronetrackerai--c2-software-platform)
2. [DedroneCity (Network-Scale Management)](#2-dedronecity--network-scale-management)
3. [DedroneSensor RF-360](#3-dedronesensor-rf-360)
4. [DedroneSensor RF-160](#4-dedronesensor-rf-160)
5. [DedroneDefender (Handheld Effector)](#5-dedronedefender--handheld-effector)
6. [DedroneDefender 2 (AI-Powered Effector)](#6-dedronedefender-2--ai-powered-effector)
7. [DroneDefender (Military Effector -- Legacy Battelle)](#7-dronedefender--military-effector--legacy-battelle)
8. [DedronePortable](#8-dedroneportable)
9. [DedroneTactical](#9-dedronetactical)
10. [DedroneRapidResponse](#10-dedronerapidresponse)
11. [DedroneOnTheMove (OTM)](#11-dedroneonthemove-otm)
12. [DedroneBeyond (BVLOS / DFR)](#12-dedronebeyond--bvlos--dfr)
13. [Radar Integration Capabilities](#13-radar-integration-capabilities)
14. [Australia Land 156 Programme](#14-australia-land-156-programme)
15. [Sources](#15-sources)

---

## 1. DedroneTracker.AI -- C2 Software Platform

DedroneTracker.AI is Dedrone's flagship AI-driven command and control (C2) platform. It serves as the central software layer across all Dedrone hardware products, providing the complete counter-UAS kill chain: detect, track, identify, and mitigate (DTI-M).

### Key Capabilities

| Feature | Detail |
|---|---|
| **Sensor Fusion** | Integrates RF, radar, EO/IR (PTZ cameras), and acoustic sensor inputs into a single unified airspace picture |
| **Detection Accuracy** | 99.7% accuracy (based on millions of labeled drone and non-drone images) |
| **Image Recognition** | AI-driven autonomous detection engine; ~95% accuracy at defense and civilian C-sUAS test events |
| **Drone Library (DedroneDNA)** | Identifies 300+ drone types from 150+ manufacturers, including military types (e.g., Orlan-10, Zala), commercial (DJI), FPV, and homemade drones |
| **Pilot Localization** | Pinpoints both drone and operator positions on integrated map |
| **Threat Prioritization** | AI engine provides risk-prioritized target queue through autonomous background interrogation |
| **Multi-Target Tracking** | Simultaneously tracks multiple friendly and hostile drones |
| **Remote ID** | Fully integrated with US, EU, and Japanese Remote ID standards |
| **Mitigation Control** | Operates jamming, cyber take-over, or kinetic effectors directly from the interface |
| **Forensic Capture** | Records drone model, manufacturer, video verification, time, and duration of activity |
| **NATO Compatible** | Yes |

### Deployment Options

- **On-premise / Air-gapped**: For classified or isolated networks
- **Cloud-hosted**: Browser-based interface for distributed operations
- **Hybrid**: Mixed deployment models supported

### Integrations

- Pre-configured US government C-sUAS integrations
- 30+ proven third-party integrations (radars, cameras, effectors, UTM systems, alerting platforms)
- Open API architecture for custom integrations
- Compatible with Genetec, Axis Communications, and other VMS/PSIM platforms
- SAPIENT interoperability (demonstrated in Project VANAHEIM)

---

## 2. DedroneCity -- Network-Scale Management

DedroneCity is the network management layer that scales DedroneTracker.AI from individual site deployments to citywide or nationwide counter-drone networks.

### Key Capabilities

| Feature | Detail |
|---|---|
| **Scale** | Supports hundreds of networked sensors across multiple sites |
| **Coordination** | Enables real-time coordination across agencies, infrastructure sites, and borders |
| **Example Deployment** | 65+ active sites across every Australian state and territory |
| **Ukraine Deployment** | 250-300 networked sensors on frontlines providing centralized visibility |
| **Single Pane of Glass** | Unified view across all connected sites |

---

## 3. DedroneSensor RF-360

The RF-360 is Dedrone's primary passive RF sensor for detection, classification, direction-finding, and geolocation of drones and their remote controls.

### Technical Specifications

| Parameter | Specification |
|---|---|
| **Type** | Passive RF sensor with direction finding |
| **Detection Range (Typical)** | 2.0 km (1.25 mi) |
| **Detection Range (Maximum)** | 5.0 km (3.1 mi) for specific drones under ideal conditions |
| **Direction Finding Accuracy** | +/- 5 degrees (mean error) |
| **Geolocation** | Requires 2+ RF-360 units for triangulation; locates both drone and pilot |
| **Frequency Coverage** | Broad frequency range; dual-radio design; detects RF, WiFi, and non-WiFi drone protocols |
| **Drone Library** | 600+ drone models from 150+ manufacturers |
| **Dimensions (L x W x H)** | 300 mm x 300 mm x 405 mm (12" x 12" x 15.96") |
| **Weight** | 7.0 kg (15.5 lb) |
| **Ingress Protection** | IP65 |
| **Operating Temperature** | -20 C to +55 C (-4 F to +131 F) |
| **Power Supply** | AC 100-240V 50/60 Hz or PoE IEEE 802.3bt (60 W) |
| **Max Current Draw** | 1 A |
| **Connectivity** | Single Ethernet connection (PoE+); integrated LTE and GPS for cloud-readiness |
| **Installation** | Fast deployment; no specialized IT knowledge required |
| **Urban Optimization** | Filters RF noise from cell towers, microwave antennas, radar systems |

### Variants

- **RF-360T**: Tactical/ruggedized variant for military deployments

---

## 4. DedroneSensor RF-160

The RF-160 is Dedrone's entry-level RF sensor designed for rapid deployment with cloud connectivity. It is an upgraded version of the legacy RF-100.

### Technical Specifications

| Parameter | Specification |
|---|---|
| **Type** | Passive RF sensor (detection and classification; no direction finding) |
| **Detection Range (Average)** | 1.6 km |
| **Detection Range (Maximum)** | Up to 5 km for certain drones |
| **Frequency Bands** | 2.4 GHz and 5.8 GHz primary; advanced antenna config for out-of-band detection |
| **Drone Library** | ~300 drone types |
| **Connectivity** | Integrated LTE for automatic cloud connection; no on-premise server required |
| **Installation** | Minutes; requires only power supply and mounting pole |
| **Urban Optimization** | Designed for high-RF-interference environments |
| **List Price (2024 ref.)** | ~$11,500 USD (DD-HW-3-1600-0000) |
| **Weight** | Not publicly disclosed |
| **Dimensions** | Not publicly disclosed (cylindrical form factor with blue band) |
| **Power** | Not publicly disclosed |

---

## 5. DedroneDefender -- Handheld Effector

The DedroneDefender is a lightweight, handheld precision jammer designed for law enforcement and civilian security use.

### Technical Specifications

| Parameter | Specification |
|---|---|
| **Type** | Handheld narrowband RF jammer |
| **Weight** | 3.4 kg (7.5 lb) |
| **Dimensions** | 560 mm x 127 mm x 254 mm (22" x 5" x 10") |
| **Jamming Type** | Narrowband / "comb" jamming -- minimizes disruption to surrounding devices |
| **Cold Start Time** | < 0.1 seconds |
| **Continuous Operation** | ~1 hour |
| **Military Standard** | MIL-STD-810H |
| **Targeting** | Phone-based app for targeting assistance |
| **Mounting Option** | Can be mounted on pan-tilt-positioner for automated Pan-Tilt-Jammer (PTJ) operation directed by DedroneTracker.AI |
| **Bands Disrupted** | RF control frequencies + GPS, GLONASS, BeiDou, Galileo, SBAS, QZSS geo-location bands |
| **Anti-Swarm** | Capable of disrupting drone swarms |

---

## 6. DedroneDefender 2 -- AI-Powered Effector

The DedroneDefender 2 is the latest-generation smart jammer with AI-powered targeting integrated with DedroneTracker.AI.

### Technical Specifications

| Parameter | Specification |
|---|---|
| **Type** | AI-powered smart jammer (handheld or mounted) |
| **Effective Range** | 300+ meters (can engage targets beyond line of sight) |
| **Targeting Cone** | 20 degrees |
| **AI Integration** | Automatically targets drone protocols identified by DedroneTracker.AI |
| **Jamming Capabilities** | Broadband + narrowband; GNSS jamming; multi-drone simultaneous neutralization |
| **Frequency Coverage** | Additional RF disruption frequency ranges vs. original; added GPS L-bands |
| **Power Output** | Increased vs. original DedroneDefender (exact figures not publicly disclosed) |
| **Antenna** | High-gain multi-band custom antenna |
| **Real-Time Guidance** | Integrated targeting guidance from DedroneTracker.AI |
| **Deployment Modes** | Handheld, vehicle-mounted (DedroneOTM), fixed-site PTJ |
| **Weight** | Not publicly disclosed (expected similar or slightly heavier than original 3.4 kg) |
| **Military Standard** | Expected MIL-STD-810H (consistent with product family) |

---

## 7. DroneDefender -- Military Effector (Legacy Battelle)

The original DroneDefender was developed by Battelle and acquired by Dedrone in 2019. It is designed for military use.

### Technical Specifications

| Parameter | Specification |
|---|---|
| **Type** | Point-and-shoot RF disruption device (rifle-style form factor) |
| **Demonstrated Range** | 400 meters |
| **Method** | Radio control frequency disruption; non-kinetic |
| **Training Required** | Minimal -- easy to use, point-and-shoot |
| **Units Sold** | 700+ jammers to allied military forces worldwide |
| **Threat Types** | Quadcopters, hexacopters, and similar sUAS |
| **Weight** | Lightweight (exact figure not publicly disclosed for military variant) |

---

## 8. DedronePortable

DedronePortable is a self-contained, all-in-one counter-UAS kit for rapid deployable drone detection, tracking, and identification.

### Technical Specifications

| Parameter | Specification |
|---|---|
| **Type** | Portable DTI (Detect, Track, Identify) kit |
| **Setup Time** | < 15-20 minutes |
| **Battery Life** | ~7.5 hours |
| **Drone Library** | 200+ drone signatures |
| **Software** | DedroneTracker.AI pre-loaded on ruggedized laptop |
| **Kit Contents** | RF sensors, power supply, cables, laptop, DedroneDNA database, accessories |
| **Networking** | Standalone or networked with multiple DedronePortable units for defensive perimeter |
| **Defeat Integration** | Pairs with DroneDefender for RF band denial + GNSS disruption |
| **GNSS Bands Disrupted** | GPS, GLONASS, BeiDou, Galileo, SBAS, QZSS |
| **RF Environment** | Optimized for urban and RF-noisy environments |
| **Ruggedization** | Robust design for challenging field conditions |
| **Weight/Dimensions** | Not publicly disclosed (contained in transit cases) |

### Land 156 Relevance

DedronePortable is one of the products selected for evaluation under Australia's Land 156 Phase 1 programme.

---

## 9. DedroneTactical

DedroneTactical is Dedrone's expeditionary-grade modular C-sUAS response kit, designed for military and government rapid deployment.

### System Configuration

| Component | Description |
|---|---|
| **Base Kit** | Single tactical mast with ruggedized RF sensors + BlueHalo Titan EW defeat system |
| **Extended Kit** | Second mast with radar + PTZ camera for non-RF drone detection and visual confirmation |
| **C2 System** | Ruggedized laptop running DedroneTracker.AI |
| **Setup** | Toolless setup and tear-down in 15 minutes |
| **Architecture** | Two masted kits + ruggedized laptop + peripherals |

### Key Specifications

| Parameter | Specification |
|---|---|
| **Detection Sensors** | RF sensors, radar, PTZ cameras (modular) |
| **EW Defeat** | BlueHalo Titan -- EW defeat of RF-based sUAS across all protocols |
| **AI Accuracy** | ~95% (DedroneTracker.AI image recognition and autonomous detection) |
| **Networking** | Can incorporate additional remote DedroneSensors via wireless network links |
| **Sales** | 100+ kits sold to US and global governments |
| **Kill Chain** | End-to-end C-sUAS: detect, track, identify, mitigate |
| **Weight** | Not publicly disclosed |

---

## 10. DedroneRapidResponse

DedroneRapidResponse is a mobile, self-contained counter-UAS solution mounted on a solar-powered trailer for outdoor airspace protection.

### Technical Specifications

| Parameter | Specification |
|---|---|
| **Type** | Mobile trailer-mounted C-UAS system |
| **Detection Range** | 5 km radius |
| **Power** | Solar-powered (self-sustaining) |
| **Detection Method** | Multi-layered: RF sensors + dual cameras |
| **AI/ML** | AI/ML-powered; detects drones as soon as powered on |
| **Multi-Target** | Two cameras track multiple drones simultaneously |
| **Deployment** | Can be placed anywhere; no fixed infrastructure required |
| **Primary Users** | Law enforcement agencies globally |
| **Software** | DedroneTracker.AI |
| **Australian Variant** | Developed in collaboration with Mobile Camera Security (MCS) for Australian, NZ, and Indo-Pacific markets |
| **Weight/Dimensions** | Not publicly disclosed (trailer-mounted) |

---

## 11. DedroneOnTheMove (OTM)

DedroneOnTheMove is a vehicle-mounted mobile C-UAS system providing the full DTI-M kill chain while in motion.

### Technical Specifications

| Parameter | Specification |
|---|---|
| **Type** | Vehicle-mounted mobile C-UAS system |
| **Threat Coverage** | Group 1, 2, and 3 UAS |
| **Targeting Accuracy** | 2.5 degrees (kinetic kill viability) |
| **Detection Accuracy** | 95% (DedroneTracker.AI) |
| **Drone Library** | 200+ drone types from 70+ manufacturers |
| **Defeat System** | DedroneDefender smart jammer (integrated) |
| **Military Standards** | MIL-STD-810H (weather and vibration), MIL-STD-1275 (vehicle power) |
| **C2 Platform** | DedroneTracker.AI on ruggedized on-vehicle tablet |
| **Mounting** | Roof-mount RF sensors; optional telescopic mast |
| **Interoperability** | SAPIENT-compatible; open-architecture |
| **VANAHEIM Performance** | Only vehicle-mounted RF system to detect all known drone threats in Project VANAHEIM |

### Integrated Vehicle Platforms

| Vehicle | Manufacturer | Notes |
|---|---|---|
| **Bushmaster PMV** | Thales Australia | Successfully tested near Thales Bendigo facility in simulated battlefield conditions |
| **HMT Family** | Supacat | Available as standard modular feature across all HMT variants |
| **MRZR** | Polaris | Displayed at DSEI 2025 |

### Adoption

- Deployed by six G7 nations
- Active in Projects VANAHEIM and FLYTRAP (US/UK defence stakeholders)

---

## 12. DedroneBeyond -- BVLOS / DFR

DedroneBeyond is a ground-based detect-and-avoid (DAA) system enabling Beyond Visual Line of Sight (BVLOS) drone operations for Drone as First Responder (DFR) programs.

### Key Capabilities

| Feature | Detail |
|---|---|
| **Purpose** | Enable safe BVLOS operations for law enforcement DFR programs |
| **Altitude Range** | 0-400 ft AGL |
| **Sensor Fusion** | Radar, RF detection (including RF900 for Remote ID), cameras, ADS-B |
| **Aircraft Detection** | Cooperative and non-cooperative crewed aircraft; birds; drones |
| **False Positive Rate** | Virtually eliminated through AI sensor fusion |
| **Integration** | Skydio DFR Command, DroneSense/Axon Air |
| **Validation** | First ground-based DAA system to complete independent third-party validation under ASTM F3442M-23 (by Virginia Tech MAAP, FAA-designated test site) |
| **Regulatory** | Aligned with FAA COW (Certificate of Waiver) process for BVLOS |
| **Deployment Scale** | 145+ public safety agencies; covers 50%+ of US population |
| **C2 Platform** | DedroneTracker.AI |

---

## 13. Radar Integration Capabilities

Dedrone's open API architecture supports integration with multiple radar systems. The platform is explicitly hardware-agnostic.

### Confirmed Radar Partners

| Radar Partner | Product | Integration Notes |
|---|---|---|
| **Echodyne** | MESA (Metamaterials ESA) | Long-standing partnership; forms basis of "DedroneTower" solution; ultra-low SWaP radar; detects autonomous drones and swarms |
| **Saab Australia** | Various | Integrated for Australian defence (Land 156 context) |
| **Silentium Defence** | Various | Integrated for Australian defence (passive radar capability) |

### Additional Sensor Partners

| Partner | Sensor Type | Notes |
|---|---|---|
| **Axis Communications** | PTZ Cameras | AI/ML-driven visual detection and tracking |
| **Squarehead Technology** | Discovair Acoustic Sensor | Acoustic detection layer |
| **BlueHalo** | Titan EW System | Electronic warfare defeat (integrated in DedroneTactical) |
| **TYTAN** | Kinetic Interceptor | Group 3 UAS defeat; kinetic DTI-M capability for NATO |
| **EOS** | Directed Energy / Effectors | Further integrations planned (Australian context) |

### Integration Architecture

- Open API for custom sensor integration
- SAPIENT interoperability standard supported
- Pre-configured US government C-sUAS integrations
- UTM system integration capability
- 30+ proven third-party integrations

---

## 14. Australia Land 156 Programme

### Programme Overview

| Detail | Information |
|---|---|
| **Programme Name** | LAND 156 Counter-Uncrewed Aircraft Systems (C-UAS) |
| **Investment** | AUD $1.3 billion over 10 years |
| **Threat Scope** | Group 1 and Group 2 drones (up to 55 kg) |
| **Focus** | Equip dismounted troops with advanced, portable counter-drone capabilities |
| **Initial Contracts** | $16.9 million to 11 vendors (rolling wave) |
| **Target** | 120+ threat detectors and drone-defeating technologies into ADF service |

### Dedrone's Role in Land 156

| Aspect | Detail |
|---|---|
| **Selection** | Confirmed for Phase 1 evaluation |
| **Products Under Evaluation** | DedronePortable, DedroneDefender |
| **Australian Network** | 65+ active sites across every state and territory |
| **Site Types** | State capitals, stadiums, sensitive government sites |
| **Capability** | Real-time detection, tracking, and coordinated response against multi-threat drone incursions |

### Land 156 Partnerships and Integration

| Partner | Platform/Product | Integration |
|---|---|---|
| **Thales Australia** | Bushmaster PMV | DedroneOTM integrated for on-the-move C-UAS |
| **Supacat** | HMT family | DedroneOTM as standard modular feature |
| **Saab Australia** | Radar systems | Sensor integration for layered detection |
| **Silentium Defence** | Passive radar | Sensor integration for layered detection |
| **EOS** | Effectors | Further integrations planned |
| **MCS (Mobile Camera Security)** | DedroneRapidResponse trailer | Locally produced for Australian/Indo-Pacific markets |

### AUKUS Alignment

Dedrone's involvement in Land 156 supports AUKUS objectives for deeper integration of security and defence technology supply chains between Australia, the UK, and the US. The DedroneOTM solution has been deployed in collaboration with US and UK defence stakeholders through Projects VANAHEIM and FLYTRAP.

---

## 15. Sources

- [Dedrone Official Website -- Products](https://www.dedrone.com/)
- [DedroneTracker.AI Product Page](https://www.dedrone.com/products/drone-detection-software)
- [DedroneDefender 2 Product Page](https://www.dedrone.com/solutions/dedrone-defender-2)
- [DedroneOnTheMove Product Page](https://www.dedrone.com/solutions/dedrone-on-the-move)
- [DedroneBeyond Product Page](https://www.dedrone.com/blog/dedrone-beyond-and-the-future-of-bvlos-why-tested-technology-matters-in-the-new-faa-cow-era)
- [RF-360 Datasheet (PDF)](https://l.dedrone.com/hubfs/Downloads%20-%20PDFs/DS_RF360-360T_en_web.pdf)
- [RF-360 Product Page](https://www.dedrone.com/sensors/rf-360)
- [Dedrone RF-160 Introduction](https://www.dedrone.com/blog/introducing-the-dedrone-rf-160-for-drone-alerting-and-identification)
- [Dedrone RF-160 Press Release](https://www.prnewswire.com/news-releases/dedrone-introduces-radio-frequency-sensor-rf-160-for-suas-detection-and-threat-mitigation-300986137.html)
- [Dedrone RF Sensors Overview (NWS)](https://nwsnext.com/tech/dedrone-rf-sensors/)
- [DedronePortable Datasheet (PDF)](https://sandstormdefence.com/wp-content/uploads/2024/04/Dedrone-DedronePortable-DataSheet-en.pdf)
- [DedronePortable Product Page](https://www.dedrone.com/solutions/dedrone-portable)
- [DedroneTactical Launch Press Release](https://www.dedrone.com/press/dedrone-defense-launches-dedronetactical-to-meet-rising-demand-for-agile-expeditionary-multi-sensor-counter-suas-solutions)
- [Dedrone x Echodyne Integration](https://www.dedrone.com/technology-partners/echodyne-2)
- [Redefining Air Defense: Dedrone Expands Capabilities (NATO/TYTAN)](https://www.axon.com/newsroom/announcements/redefining-air-defense-dedrone-by-axon)
- [Dedrone: Delivering on LAND 156 with Australia's First National Counter-Drone Network](https://www.dedrone.com/blog/dedrone-by-axon-delivering-on-land-156-with-australias-first-national-counter-drone-network)
- [Axon Newsroom: Dedrone Australia Counter-Drone Network](https://www.axon.com/newsroom/announcements/dedrone-aus-first-counter-drone-network)
- [Dedrone Selected for Land 156 Programme (SEN.news)](https://sen.news/dedrone-selected-for-land-156-programme/)
- [Australia Bushmaster C-UAS Testing (Army Recognition)](https://www.armyrecognition.com/news/army-news/2025/australia-tests-bushmaster-protected-mobility-vehicles-with-ai-powered-counter-drone-systems-following-lessons-from-ukraine)
- [Dedrone by Axon and MCS Partnership (APDR)](https://asiapacificdefencereporter.com/dedrone-by-axon-teams-with-mcs-on-counter-drone-work/)
- [Dedrone Project VANAHEIM (Axon)](https://www.axon.com/newsroom/announcements/dedrone-project-vanaheim)
- [Dedrone x Thales Bushmaster Integration (Inside Unmanned Systems)](https://insideunmannedsystems.com/dedrone-and-thales-australia-partner-to-deliver-ai-enabled-c-uas-on-the-move-capabilities/)
- [DedroneDefender Datasheet (PDF)](https://sandstormdefence.com/wp-content/uploads/2024/03/Dedrone-DedroneDefender-data-sheet_letter_en.pdf)
- [DroneDefender Legacy (Battelle)](https://www.battelle.org/insights/case-studies/case-study-details/dronedefender-technology)
- [Frost & Sullivan 2025 Recognition](https://www.dedrone.com/blog/dedrone-by-axon-named-growth-and-innovation-leader-in-frost-sullivans-2025-frost-radar-uas-communication-disruptors)
- [Dedrone 10th Annual Airspace Security Report 2026](https://soldiersystems.net/2025/12/29/dedrone-by-axons-10th-annual-airspace-security-report-2026/)
- [DedroneBeyond x Skydio Integration](https://www.skydio.com/integrations-catalog/dedrone)

---

> **Note:** Some detailed specifications (exact weights, dimensions, power figures) for newer products such as DedroneDefender 2, DedroneTactical, DedroneRapidResponse, and DedronePortable are not publicly disclosed. Dedrone gates full datasheets behind their sales process. Contact sales@dedrone.com or visit dedrone.com for complete technical documentation.
