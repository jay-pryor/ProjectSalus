# Department 13 (D13) - Products and Specifications

**Company:** Department 13 International, Australia
**Role in LAND 156:** Key partner under LOE1 providing Australian sensor system (passive RF detection) and electronic warfare / soft-kill counter-UAS capability
**Website:** [department13.com](https://department13.com)

Department 13 specialises in protocol manipulation technology for counter-drone applications. Their MESMER system is unique in the C-UAS market as it does not jam signals but instead manipulates the communication protocols of target drones to take control.

---

## 1. MESMER - Protocol Manipulation Counter-Drone System

MESMER is a patented, low-power, non-jamming, non-line-of-sight, non-kinetic drone mitigation solution using protocol manipulation technology.

### Specifications (Version 1.5)

| Parameter | Value |
|---|---|
| **System Type** | Software-defined counter-drone (detection + mitigation) |
| **Technology** | Protocol manipulation (not jamming) |
| **Weight** | Under 30 kg (outside of transit case) |
| **Transmit Power** | Can operate below 1 Watt; within FCC regulatory constraints |
| **Frequency Bands** | Four frequency bands (v1.5, up from two in earlier versions) |
| **Effective Range** | Up to approximately 5 km (v1.5, extended from ~1 km in earlier versions) |
| **Operator Requirement** | Single operator (can manage single drone or swarm) |

### Detection Capabilities

| Parameter | Detail |
|---|---|
| **Detection Method** | Cognitive techniques for blind signal detection and characterisation |
| **Signal Analysis** | Uses signal features and metadata to identify threats |
| **Threat Determination** | Determines existence, type, and characteristics of drone threats |
| **Classification** | Identifies drone communication protocols in the RF environment |

### Mitigation Capabilities

| Mitigation Option | Description |
|---|---|
| **Stop / Hover** | Forces drone to hold position |
| **Redirect** | Changes drone flight path to desired location |
| **Land** | Takes control and lands drone at detected position |
| **Return to Base** | Issues RTB command (with follow-on GPS telemetry and live video) |
| **Full Control** | Takes total control of target drone flight |
| **Covert Monitor** | Monitors live drone data, route, and camera feed without drone operator awareness |
| **Swarm Defeat** | Captures, defeats, and neutralises multiple drones in a defined area |

### Key Differentiators

- **Non-jamming:** Does not attempt to overpower signals; manipulates protocol weaknesses instead
- **Low interference:** Inherently low-power with minimal impact on existing signals in the environment
- **Non-line-of-sight:** Does not require direct line of sight to the target drone
- **Non-kinetic:** No physical projectiles or directed energy; purely electronic
- **Protocol agnostic:** Exploits weaknesses in all digital radio protocols
- **Software-defined:** Primarily a software solution that scales and adapts to different needs

### Deployment Options

- Standalone system
- Layered on top of existing hardware solutions
- Integrated with existing hardware installations
- Quick deployment for a wide range of CONOPS
- Integrates with C2 systems (including Cortex under LAND 156)

---

## Role in LAND 156

Under the LAND 156 LOE1 program, Department 13 serves as the Australian sensor system provider. The integrated solution includes:

- **Department 13:** Passive RF detection and electronic warfare capability (MESMER)
- **Acacia Systems:** Cortex C2 command and control
- **EOS Defence:** Kinetic and directed energy effectors (Slinger)
- **Echodyne:** MESA radar sensors (EchoGuard)
- **Leidos Australia:** Systems integrator

The LAND 156 capability was demonstrated at the Southern Arrow 25 live-fire event in December 2025, where the integrated system demonstrated detection, tracking, identification, and defeat of small drones.

---

## Partnerships

| Partner | Relationship |
|---|---|
| **Raytheon** | Teamed to bring MESMER counter-drone technologies to market |
| **Korea Counter-Terrorism Solutions (KCTS)** | Exclusive distribution agreement for South Korea |
| **Leidos Australia** | LAND 156 systems integration partner |
| **EPE (Elbit Partner)** | Australian distribution |

---

## Technical Notes

Specific details on exact frequency bands covered (e.g., 2.4 GHz, 5.8 GHz, 900 MHz, 433 MHz), specific protocols supported (e.g., Wi-Fi, proprietary DJI, MAVLink), and detailed power consumption specifications are not publicly disclosed, likely for operational security reasons. The system's effectiveness depends on its library of drone protocols, which is continuously expanded.

---

## Sources

- [DSIAC - Department 13 MESMER Successful Tests](https://dsiac.dtic.mil/articles/department-13-completes-successful-tests-of-mesmer-counter-drone-solution/)
- [EPE - MESMER Defence Brochure (PDF)](https://www.epequip.com/wp-content/uploads/2019/05/Mesmer-Defence-compressed.pdf)
- [EPE - MESMER Counter-Drone Solution Demonstration](https://www.epequip.com/mesmer-counter-drone-solution/)
- [Phoenix Group - MESMER D13 Introduction](http://www.phoenixgrouppanama.com/resources-drone-d13.html)
- [Officer.com - MESMER Counter-Drone System](https://www.officer.com/tactical/swat/robotic-equipment/product/12301297/department-13-d13-mesmer-counter-drone-system)
- [BGP4 - Protocol Manipulation Counter-Drone System](https://www.bgp4.com/2018/05/13/south-korea-acquires-open-source-non-jamming-non-line-of-sight-non-kinetic-counter-drone-system/)
- [Australian Defence Magazine - Raytheon and Department 13](https://www.australiandefence.com.au/defence/unmanned/raytheon-teams-with-department-13-for-mesmer-counter-uas)
- [Department 13 - Technology Takes Flight](https://department13.com/technology-takes-flight-attacking-drones/)
