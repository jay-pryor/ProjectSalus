# Anduril Industries -- Products and Specifications for Australian Land 156

**Last Updated:** 2026-03-18

## Table of Contents

1. [Project Land 156 Context](#project-land-156-context)
2. [Anduril Australia Presence and Contracts](#anduril-australia-presence-and-contracts)
3. [Lattice (C2/AI Platform)](#lattice-c2ai-platform)
4. [Sentry Tower (Autonomous Surveillance)](#sentry-tower-autonomous-surveillance)
5. [WISP (Wide-Area Infrared Sensing with Persistence)](#wisp-wide-area-infrared-sensing-with-persistence)
6. [Iris (Passive Airborne Infrared Sensor Family)](#iris-passive-airborne-infrared-sensor-family)
7. [Anvil (Kinetic Interceptor Drone)](#anvil-kinetic-interceptor-drone)
8. [Pulsar (Electronic Warfare / RF Jamming)](#pulsar-electronic-warfare--rf-jamming)
9. [Roadrunner (Autonomous Air Vehicle Interceptor)](#roadrunner-autonomous-air-vehicle-interceptor)
10. [Ghost UAS (Small Unmanned Aircraft System)](#ghost-uas-small-unmanned-aircraft-system)
11. [Altius (Loitering Munition / ISR UAS)](#altius-loitering-munition--isr-uas)
12. [Counter-UAS Fly-Away Kit (Integrated Package)](#counter-uas-fly-away-kit-integrated-package)
13. [Sources](#sources)

---

## Project Land 156 Context

Project Land 156 is the Australian Defence Force (ADF) initiative launched in 2024 to acquire a complete counter-small UAS (C-sUAS) platform. The ADF requirement encompasses:

- Electro-optic sensors, acoustic and thermal sensors, active and passive radars
- Protection of deployed forces (domestically and internationally)
- Securing infrastructure, expeditionary bases, dismounted personnel, and all classes of ADF vehicles
- High-energy lasers, RF jamming, and ammunition-based defeat mechanisms

The Australian government plans to spend approximately AUD 10 billion on drones and counter-drone capabilities over the next decade.

**Standing Offer Panel:** 28 companies were selected for the Land 156 Standing Offer Panel, including Anduril Australia, Cubic Defense, Leidos, L3Harris, RTX, and Saab.

**Systems Integration Partner:** Leidos Australia was selected as the systems integration partner for Land 156, under a contract valued at AUD 45.9 million.

**Initial Contracts:** Under Land 156, Australia has issued contracts for "at least 120" technologies for testing, including high-energy lasers, RF jamming, and ammunition-based counter-UAS systems.

---

## Anduril Australia Presence and Contracts

### RAAF Base Darwin Trial

| Parameter | Detail |
|---|---|
| Contract Value | AUD 30 million (USD 18.5 million) |
| Duration | 3 years (signed September 2024) |
| Customer | Royal Australian Air Force (RAAF) |
| Location | RAAF Base Darwin, Northern Territory |
| Delivery Model | Capability-as-a-service |
| Deployment Speed | 15 weeks from contract signing to operational capability |

**Systems Deployed:**
- Family of Systems approach: active and passive sensors, kinetic and non-kinetic effectors
- Powered by Lattice for 24/7 persistent awareness
- Autonomous detection, classification, and tracking of objects of interest
- Tailored to Darwin's unique tropical environment

**Progress (as of Avalon 2025 Airshow):**
- 4 hardware updates and 16 software upgrades delivered since October 2024
- New tactics and operating procedures developed using the UAS and intrusion detection technology
- Continuous sensor calibration for local climate, topography, flora, and fauna
- David Goodrich (Anduril Australia CEO) confirmed the system is "performing well, delivering on its contractual commitments"

---

## Lattice (C2/AI Platform)

Lattice is Anduril's core AI-powered operating system and the software backbone for all Anduril hardware products. It integrates sensors, autonomous systems, effectors, and operators into a unified command and control architecture.

### Specifications

| Parameter | Detail |
|---|---|
| Type | AI-powered command and control (C2) software platform |
| Architecture | Open architecture, software-defined |
| Processing Latency | Less than 1 second |
| Data Capacity | Hundreds of sensors and systems simultaneously |
| Protocols | REST and gRPC (internally uses Protobuf for low-bandwidth binary data) |
| Integration | Bidirectional; supports third-party sensors and effectors |
| SDK | Lattice SDK for custom applications, data services, and hardware integrations |
| DDIL Support | Yes, via Oracle distributed cloud and Anduril Menace hardware |

### Core Capabilities

- **Sensor Fusion:** Merges data from radar, EO/IR, RF, acoustic, and third-party sources into a single operational picture
- **AI Classification:** Real-time object detection, identification, classification, and tracking
- **Autonomy-Enhanced Fire Control:** Distributed tracking and kill-chain optimization
- **3D Command Center:** Turns thousands of data streams into a real-time 3D C2 environment
- **Open Integration:** Integrates with third-party radars (e.g., Lockheed Martin Q-53), EW systems, and kinetic interceptors

### Key Contracts

- US Army JIATF-401 C2 system (USD 87 million initial task order, up to USD 20 billion over 10 years)
- US Army IBCS-M (Integrated Battle Command System Maneuver) fire control platform
- USSOCOM IDIQ contract (up to USD 1 billion over 10 years)
- Deployed at RAAF Base Darwin as part of Australian trial

---

## Sentry Tower (Autonomous Surveillance)

The Sentry Tower is an autonomous surveillance platform using AI to detect, identify, and track objects of interest. Over 300 units deployed with US Customs and Border Protection since 2020.

### Variants

#### Standard Sentry Tower (AST)

| Parameter | Detail |
|---|---|
| Height | 33 feet (10 m) |
| Power | Solar-powered (autonomous operation) |
| Sensors | Radar, electro-optical (EO), infrared (IR), radio frequency (RF) |
| Software | Lattice AI platform |
| Deployment | Stationary, no external infrastructure required |
| Weight | Not publicly disclosed |

#### Extended Range Sentry Tower (XRST)

| Parameter | Detail |
|---|---|
| Tower Height | 80 feet (24.4 m) expeditionary tower |
| Autonomous Detection Range | 5+ miles (8+ km) |
| Operator-Assisted Detection Range | 7.5 miles (12 km) |
| Line of Sight | Unobstructed required for maximum range |
| Software | Lattice AI with computer vision and machine learning |
| First Deployment | November 2023, Texas (US-Mexico border) |

#### Mobile Sentry

| Parameter | Detail |
|---|---|
| Configuration | Trailer-mounted, wheeled |
| Setup Time | Under 20 minutes by one operator |
| Training Required | No specialized MOS, training, or Anduril support |
| Power | Integrated power generation + UPS battery (infrastructure-independent) |
| Customization | Modular sensor bays, multiple payload/comms options |
| Missions | Force protection, counter-UAS, border security, critical infrastructure |
| Weight | Not publicly disclosed |

#### Maritime Sentry Tower

| Parameter | Detail |
|---|---|
| Height | 5.5 m |
| Sensors | Radar, thermal imaging, electro-optical |
| Known Deployment | 10+ units identified between Hastings and Ramsgate (UK) |

### Sensor Suite (All Variants)

- Radar (active, for detection and tracking)
- Electro-optical (daylight imaging, classification)
- Infrared / thermal (night and low-visibility detection)
- Radio frequency sensors (drone RF link detection)
- AI-powered computer vision for autonomous classification
- Repurposed IR laser illumination for high-resolution distant imaging

---

## WISP (Wide-Area Infrared Sensing with Persistence)

WISP is a passive 360-degree infrared surveillance sensor based on Computational Pixel Imager (CPI) technology, originally developed by Copious Imaging (MIT Lincoln Lab spinoff, acquired by Anduril in 2021).

### Specifications

| Parameter | Detail |
|---|---|
| Detection Method | Passive infrared (no RF emissions) |
| Horizontal FOV | 360 degrees |
| Vertical FOV | 125 degrees |
| Autonomous UAV Detection Range | 3 to 10 miles (5 to 16 km) |
| Commercial Aircraft Detection | ~93 miles (150 km) at 12,000 ft altitude |
| Sensor Dimensions | 15 x 15 x 22 inches (38 x 38 x 56 cm) |
| Processor Dimensions | 19 x 8 x 26 inches (48 x 20 x 66 cm) |
| AI Processing | Real-time AI for automated threat detection and classification |
| Emissions | Zero RF emission (covert operation, undetectable) |

### Mounting Platforms

- Fixed towers (Sentry Tower integration)
- Tactical vehicles
- Boats and ships
- Tripod-mounted on structures

### Key Contracts

- US Air Force Test Center, Edwards AFB: USD 31.1 million sole-source for WISP SkyFence project
- Integrated with Rheinmetall Skymaster C2 for layered counter-sUAS defense
- Part of Anduril counter-UAS fly-away kit (SkyFence configuration)

---

## Iris (Passive Airborne Infrared Sensor Family)

Iris is the next-generation evolution of WISP, designed for airborne platforms including crewed aircraft, AAVs, and uncrewed systems.

### Specifications

| Parameter | Detail |
|---|---|
| Type | Passive airborne imaging and targeting sensor |
| Core Technology | Computational Pixel Imager (CPI) with AI per-pixel processing |
| Emissions | Passive (no detectable radiation) |
| Architecture | Open Mission System (OMS) compliant |
| Design | Low SWaP (Size, Weight, and Power) |
| AI Processing | Edge-based autonomous detection and tracking of hundreds of targets |
| Modularity | Multiple configurations across lens type, wavelength, and pixel format |
| Software | Software-defined with rapid iteration capability |

### Applications

- Infrared Search and Track (IRST)
- Missile warning
- Visualization and targeting
- Counter-UAS (building on WISP heritage)

### Platform Compatibility

- Tactical combat jets (demonstrated in live-flight tests)
- Autonomous Air Vehicles (AAVs)
- Uncrewed platforms
- Adaptable to most aircraft types

**Note:** Detailed specifications (exact detection ranges, resolution, wavelength bands) are restricted to government customers.

---

## Anvil (Kinetic Interceptor Drone)

Anvil is an autonomous kinetic interceptor designed to physically defeat hostile Group 1 and Group 2 UAS (up to 55 lbs / 24 kg, operating at up to 3,500 ft / 1,066 m altitude).

### Specifications

| Parameter | Detail |
|---|---|
| Type | Unmanned combat aerial vehicle (quadcopter) |
| Weight | ~11.6 lbs (5.3 kg) |
| Launch Box Weight | ~253 lbs (115 kg) |
| Maximum Speed | Up to 200 mph (320 km/h) |
| Guidance | Computer vision + Lattice AI |
| Defeat Mechanism | Kinetic (ram-to-kill) |
| Launch System | Ruggedized, self-contained, easily transportable launch box |
| Target Types | Group 1 and Group 2 UAS |

### Variants

| Variant | Defeat Method | Target Set |
|---|---|---|
| **Anvil (Kinetic)** | Ram-to-kill via physical collision | Group 1 and 2 UAS |
| **Anvil-M (Munitions)** | Fire-control module with munitions payload | Higher-end, faster Group 2 UAS |
| **Anvil (Non-Kinetic)** | Non-kinetic, low-collateral effect (likely RF/EW) | Drone threats requiring soft-kill |

### Key Contracts

- USMC counter-drone systems: USD 642 million, 10-year contract (through 2035)
- USSOCOM IDIQ: Part of USD 1 billion, 10-year counter-drone contract
- USNORTHCOM: Included in counter-UAS fly-away kits
- Part of RAAF Darwin trial system

---

## Pulsar (Electronic Warfare / RF Jamming)

Pulsar is Anduril's AI-enabled electromagnetic warfare system for detecting, locating, and disrupting drone command links and other RF threats.

### Specifications

| Parameter | Detail |
|---|---|
| Type | Software-defined electronic warfare platform |
| AI Processing | Machine learning at the tactical edge for real-time threat identification |
| Functions | Electronic Support (ESM), Electronic Attack (EA/jamming), Direction Finding, Geolocation, Communications |
| Architecture | Modular "Lego block" design with four core components |
| Software | Software-defined with rapid reprogramming; shared learning across deployed fleet |
| Lattice Integration | Optional (can operate independently or integrated) |

### Variants

| Variant | Form Factor | Notes |
|---|---|---|
| **Pulsar-V** | Vehicle-mounted | For mobile platforms |
| **Pulsar Alpha** | Airborne | Smaller, lighter with blade antennas |
| **Pulsar (Fixed)** | Fixed-site | Tripod, large power amps, directional antennas |
| **Pulsar-L (Lite)** | Man-portable / expeditionary | Shoebox-sized, under 25 lbs (11.3 kg) |

### Pulsar-L Specific Specs

| Parameter | Detail |
|---|---|
| Weight | Less than 25 lbs (11.3 kg) |
| Size | Approximately shoebox-sized |
| Setup Time | As little as 2 minutes to operational |
| Configurations | Airborne and expeditionary |
| Development Time | Concept to deployment in 8 months |

### Capabilities

- Passive sensing and classification of RF activity
- Direction finding and geolocation to cue optics, radars, or patrols
- Focused electronic attack to break command links or disrupt mission execution
- Counter drone swarms
- Rapid reprogramming: once one node records a novel signal, counter-techniques can be distributed fleet-wide in hours or days

### Key Contracts

- Part of USD 250 million counter-drone package (including 500 Roadrunner rounds)
- USSOCOM IDIQ: Part of USD 1 billion, 10-year contract
- Production target: 100+ LRIP units scaling to thousands annually

**Note:** Exact frequency ranges, effective jamming range, and radiated power levels are not publicly disclosed.

---

## Roadrunner (Autonomous Air Vehicle Interceptor)

Roadrunner is a modular, twin-jet-powered autonomous air vehicle designed for ground-based air defense. Roadrunner-M is the high-explosive interceptor variant.

### Specifications

| Parameter | Detail |
|---|---|
| Type | Twin-jet VTOL autonomous air vehicle |
| Propulsion | Twin jet engines |
| Speed | High subsonic |
| Maneuverability | High-G capability |
| Guidance | Onboard sensors and processing for autonomous target acquisition and intercept |
| Reusability | Yes (if target not engaged, returns to base for refueling and reuse) |
| Launch System | Containerized "Nest" enclosure for rapid deployment |
| Operator Requirement | Single operator can control multiple Roadrunner squadrons |
| Target Range | Group 1 through Group 5 UAS, cruise missiles, and full-sized aircraft |
| Cost per Unit | "Low hundreds of thousands" of dollars (expected to decrease at scale) |

### Roadrunner-M (Munitions Variant)

| Parameter | Detail |
|---|---|
| Warhead Capacity | Up to 33 lbs (comparable to AGM-114 Hellfire) |
| vs. Competitors | 3x warhead payload capacity, 10x one-way effective range, 3x more maneuverable (G-force) |
| Defeat Method | High-explosive intercept or kinetic kill |
| Reusability | Reusable if not consumed in engagement |

### Key Contracts

- Defense Innovation Unit (DIU) Counter NEXT program (US Navy)
- Part of USD 250 million counter-drone package (500 all-up rounds)

**Note:** Exact dimensions, weight, top speed, and range are not publicly disclosed.

---

## Ghost UAS (Small Unmanned Aircraft System)

The Ghost is a modular, autonomous, single-rotor VTOL UAS designed for reconnaissance, ISR, cargo delivery, signals intelligence, and electronic warfare missions.

### Ghost 4 Specifications

| Parameter | Detail |
|---|---|
| Length | 2.72 m |
| Width | 0.42 m |
| Height | 0.43 m |
| Rotor Diameter | 2.27 m |
| Cruise Speed | 52 kt (96 km/h) |
| Maximum Speed | 136.8 km/h (85 mph) |
| Endurance | 100+ minutes |
| Range | ~100 miles (161 km) on a single charge |
| Recharge Time | ~35 minutes (full) |
| Power | Battery-electric |
| AI Processing | 32 trillion operations per second (Lattice platform) |
| Payload Bays | 5 modular bays with data and power links |
| Durability | IP67 saltwater submersible, shock/heat/cold/waterproof |
| Acoustic Signature | Silent above 300 ft |
| Radar Cross Section | Frontal cross section approximately the size of an iPhone |
| Assembly | Under 1 minute by one person |
| Portability | Collapses to fit in a backpack (Group 2 capability in Group 1 form factor) |
| Autonomy | Point-and-click via Lattice web or mobile app; no joysticks or flight training required |

### Ghost 4 Payload Options

- Processors and additional compute
- EO/IR sensors
- Loudspeakers
- Laser designators
- Electronic warfare modules
- 3D scanning modules
- LIDAR

### Ghost-X Specifications

| Parameter | Detail |
|---|---|
| Endurance | 80-90 minutes cruise |
| Operating Range | Up to 15 miles |
| Payload Capacity | Up to 25 lbs (11.3 kg) |
| Weatherization | Rated for harsh and austere environments |
| Deployment | Deploys in minutes from slim rifle case or tactical soft case |
| Launch/Recovery | Confined landing zones capable |

### Key Contracts and Programs

- US Army Company-Level sUAS Directed Requirement (Tranche 1 selection, September 2024)
- DOD Replicator Initiative (Tranche 2 mass production selection)
- Deployed with US Army units

### Swarming and Autonomy

- Multiple Ghosts controlled from a single app by one operator
- Automatic battery-level monitoring with autonomous mission handover between aircraft
- Persistent target coverage through battlefield handover

---

## Altius (Loitering Munition / ISR UAS)

The Altius family consists of tube-launched, multi-mission drones capable of ISR, electronic warfare, communications relay, and strike missions.

### ALTIUS-600 Specifications

| Parameter | Detail |
|---|---|
| Gross Weight | 12.25 kg (27 lbs) |
| Payload Capacity | Up to 3.2 kg (7 lbs) |
| Cruising Speed | 60 km/h (37 mph) |
| Maximum Speed | ~90 km/h (56 mph) |
| Operational Range | Up to 440 km (270 miles) |
| Endurance | Up to 4 hours (ISR configuration) |
| Launch Platforms | C-130, UH-60, ground vehicles, MQ-1C Grey Eagle, XQ-58 Valkyrie |
| Architecture | Open system, compatible with various flight control software |

### ALTIUS-600M (Loitering Munition) Specifications

| Parameter | Detail |
|---|---|
| Weight | 20-27 lbs (9-12 kg) depending on payload |
| Payload | 3-7 lbs (1.4-3.2 kg) |
| Maximum Range | 400 km |
| Payload Options | ISR sensors, SIGINT sensors, RF decoys, comms relays, EW assets, warhead |
| Notable Deployment | Included in USD 2 billion US aid package for Ukraine (April 2023) |

### ALTIUS-700M (Large Loitering Munition) Specifications

| Parameter | Detail |
|---|---|
| Weight | Up to 65 lbs (29.5 kg) |
| Warhead Capacity | Up to 35 lbs (15.9 kg) -- comparable to AGM-114 Hellfire |
| Range | Up to 100 miles (160 km) |
| Endurance | 75 minutes |
| Target Types | Tanks, armored vehicles, vessels, infrastructure |

### Multi-Domain Launch Capability

All Altius variants are designed for expeditionary deployment by air, mobile, ground, or maritime forces.

---

## Counter-UAS Fly-Away Kit (Integrated Package)

Anduril offers a rapidly deployable, integrated counter-UAS kit that bundles multiple products into a single package covering the full kill chain.

### Kit Components

| Component | Function |
|---|---|
| **Mobile Sentry** | Autonomous detection and tracking (radar + EO/IR) |
| **WISP (SkyFence config)** | Wide-area passive IR 360-degree coverage |
| **Pulsar** | RF detection, direction finding, electronic attack (jamming) |
| **Anvil** | Low-collateral kinetic defeat interceptor |
| **Lattice** | C2 software tying all components together |
| **Power/Compute/Networking** | Integrated support infrastructure |

### Operational Characteristics

| Parameter | Detail |
|---|---|
| Kill Chain Coverage | Full: detect, track, identify, and defeat |
| Deployment | Rapidly deployable by military personnel |
| Escalation Model | Non-kinetic first (Pulsar RF disruption), kinetic if necessary (Anvil) |
| Airspace Compliance | Designed for operation within FAA-regulated US airspace |
| Demonstration | Validated at Falcon Peak 25.2, Eglin AFB (USNORTHCOM) |

### Partnership: Rheinmetall-Anduril Layered C-sUAS

Rheinmetall and Anduril are developing a combined layered counter-sUAS air defense system integrating:
- Rheinmetall Skymaster C2 and high-power guns
- Anduril Sentry Tower, WISP sensors, and Anvil interceptors

---

## Sources

### Anduril Product Pages
- [Sentry Tower](https://www.anduril.com/hardware/sentry/)
- [Anvil](https://www.anduril.com/hardware/anvil/)
- [Lattice C2](https://www.anduril.com/lattice/command-and-control)
- [Lattice SDK](https://www.anduril.com/lattice/lattice-sdk)
- [Ghost UAS](https://www.anduril.com/ghost-uas)
- [Altius](https://www.anduril.com/altius)
- [Roadrunner](https://www.anduril.com/roadrunner)
- [Counter-UAS](https://www.anduril.com/counter-uas)
- [Pulsar](https://www.anduril.com/pulsar)
- [Iris](https://www.anduril.com/hardware/iris/)

### Australia / Land 156
- [Australia Forms Counter-sUAS Industry Panel Under Project Land 156 - GovCon Exec](https://www.govconexec.com/2026/01/australia-counter-suas-panel-project-land-156/)
- [Defence outlines C-UAS plans - Australian Defence Magazine](https://www.australiandefence.com.au/news/news/defence-outlines-c-uas-plans)
- [Australia launches hunt for counter-drone systems - EOS](https://eos-aus.com/news/australia-launches-hunt-for-counter-drone-systems/)
- [Leidos Australia selected as systems integration partner for Project Land 156](https://www.unmannedairspace.info/latest-news-and-information/leidos-australia-selected-as-systems-integration-partner-for-project-land-156/)
- [Australia issues first batch of counter-UAS system contracts - Breaking Defense](https://breakingdefense.com/2025/07/threat-detectors-australia-issues-first-batch-of-counter-uas-system-contracts/)
- [Anduril Working with Australian Air Force on Counter-UAS - National Defense Magazine](https://www.nationaldefensemagazine.org/articles/2025/3/28/anduril-working-with-australian-air-force-on-counteruas-project)
- [Anduril signs deal with RAAF on autonomous capabilities - APDR](https://asiapacificdefencereporter.com/anduril-signs-three-year-contract-with-raaf-to-deliver-autonomous-security-capabilities/)
- [Avalon 2025: Anduril delivers UAS detection system to RAAF - Janes](https://www.janes.com/osint-insights/defence-news/defence/avalon-2025-anduril-delivers-uas-detection-system-to-raaf)

### Sentry Tower
- [Anduril Launches XRST](https://www.anduril.com/article/anduril-launches-extended-range-sentry-tower-xrst/)
- [Anduril Adds To Sentry Tower Family - Defense Daily](https://www.defensedaily.com/anduril-adds-to-sentry-tower-family-with-extended-range-version/homeland-security/)
- [Anduril debuts wheeled Mobile Sentry - Defense News](https://www.defensenews.com/industry/2022/10/10/anduril-debuts-wheeled-version-of-sentry-surveillance-tower/)

### Anvil
- [Anduril unveils Anvil-M - C4ISRNet](https://www.c4isrnet.com/unmanned/uas/2023/10/05/anduril-unveils-anvil-m-counter-drone-kit-that-can-defeat-smaller-uas/)
- [Anduril Scores $642M Deal for Marines - The Defense Post](https://thedefensepost.com/2025/03/12/anduril-counter-drone-marines/)

### Lattice
- [Lattice Developer Documentation](https://developer.anduril.com/guides/concepts/overview)
- [Army picks Anduril for IBCS-M - DefenseScoop](https://defensescoop.com/2025/11/11/army-ibcs-maneuver-anduril-lattice-counter-uas/)
- [Lockheed Martin Integrates Q-53 Radar with Lattice - Army Recognition](https://armyrecognition.com/news/army-news/army-news-2024/lockheed-martin-integrates-q-53-radar-with-andurils-lattice-c2-to-counter-drones)
- [Army awards Anduril counter-drone task order - Breaking Defense](https://breakingdefense.com/2026/03/army-awards-anduril-counter-drone-task-order-as-first-in-new-20b-contract-vehicle/)

### WISP and Iris
- [Anduril Seeks Covert Sensing Capability With New Acquisition - Breaking Defense](https://breakingdefense.com/2021/09/anduril-seeks-covert-sensing-capability-new-acquisition/)
- [Anduril Unveils Iris Sensor Family - Defense Advancement](https://www.defenseadvancement.com/news/anduril-unveils-new-family-of-passive-infrared-sensors/)
- [USAF Edwards AFB WISP SkyFence - Military Aerospace](https://www.militaryaerospace.com/computers/article/14303950/artificial-intelligence-ai-sensor-fusion-counter-uav)

### Pulsar
- [Anduril Announces Pulsar Family](https://www.anduril.com/article/anduril-announces-pulsar/)
- [Anduril announces lighter Pulsar-L - Defense News](https://www.defensenews.com/pentagon/2025/04/29/anduril-announces-lighter-smaller-pulsar-jammer/)
- [Anduril Reveals Pulsar at WDS 2026 - Army Recognition](https://www.armyrecognition.com/archives/archives-defense-exhibitions/2026-archives-news-defense-exhibitions/world-defense-show-2026/u-s-anduril-reveals-pulsar-electronic-warfare-system-for-360-anti-drone-defense-at-wds-2026)

### Roadrunner
- [Anduril unveils Roadrunner and Roadrunner-M](https://www.anduril.com/news/anduril-unveils-roadrunner-and-roadrunner-m)
- [Roadrunner-M: CUAS High-Explosive Interceptor - UST](https://www.unmannedsystemstechnology.com/2023/12/roadrunner-m-unveiled-cuas-high-explosive-interceptor/)
- [Roadrunner Reusable Anti-Air Interceptor - The War Zone](https://www.twz.com/roadrunner-reusable-anti-air-interceptor-breaks-cover)

### Ghost UAS
- [Ghost 4 VTOL sUAS - Airforce Technology](https://www.airforce-technology.com/projects/ghost-4-vtol-suas/)
- [Ghost-X Selected for US Army - Anduril](https://www.anduril.com/news/ghost-x-selected-for-u-s-army-s-company-level-suas-directed-requirement)
- [Army Deploys Ghost-X - Army Recognition](https://www.armyrecognition.com/news/army-news/2025/us-army-deploys-anduril-ghost-x-drone-showcasing-increased-use-of-unmanned-aerial-systems-in-combat-operations)

### Altius
- [Anduril Altius - Wikipedia](https://en.wikipedia.org/wiki/Anduril_Altius)
- [ALTIUS-600 Specifications - TheDefenseWatch](https://thedefensewatch.com/product/altius-600-drone/)
- [ALTIUS-700M Kamikaze Drone - Defense Mirror](https://defensemirror.com/news/36372/U_S__Army_Tests_New_ALTIUS_700M_Kamikaze_Drone)

### Counter-UAS Kit
- [Anduril delivers rapid-deploy counter-UAS kits to USNORTHCOM - CUASHub](https://cuashub.com/en/content/anduril-delivers-rapid-deploy-counter-uas-kits-to-usnorthcom/)
- [Anduril Demos Mobile Counter-Drone Kit at Falcon Peak - The Defense Post](https://thedefensepost.com/2025/10/20/anduril-demos-cuas-falcon-peak/)
- [Rheinmetall-Anduril layered counter-sUAS - Military Embedded Systems](https://militaryembedded.com/unmanned/counter-uas/layered-counter-suas-air-defense-systems-to-be-developed-by-rheinmetall-anduril-industries)
