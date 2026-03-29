# Department 13 MESMER

**Manufacturer:** Department 13 International
**Last Updated:** March 2026
**Vendor Research:** `../../VendorResearch/Department13/products_and_specs.md`

---

## Simulation-Critical Fields

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_range_m** | 5000 | datasheet | v1.5: "up to approximately 5 km" (extended from ~1 km in earlier versions) |
| **min_range_m** | 0 | estimated | |
| **engagement_arc_deg** | 360 | estimated | Omnidirectional antenna assumed |
| **mounting_height_m** | 5 | estimated | Mast/pole mounted |
| **requires_los** | false | datasheet | Explicitly "non-line-of-sight" |

## Engagement Parameters

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **supported_protocols** | Unknown — not publicly disclosed | datasheet | "Protocol agnostic — exploits weaknesses in all digital radio protocols." Specific protocols not listed (OPSEC). |
| **defeat_modes** | Stop/Hover, Redirect, Land, Return to Base, Full Control, Covert Monitor, Swarm Defeat | datasheet | |
| **reaction_time_s** | 5 | estimated | Protocol detection + handshake time |
| **simultaneous_engagements** | 5 | estimated | "Single operator can manage single drone or swarm" |
| **reload_time_s** | 2 | estimated | Electronic — switch to new target |
| **defeat_probability** | 0.85 | estimated | Against commercial drones with standard protocols. Unknown/hardened ≈ much lower. |
| **defeat_mechanism** | Protocol exploitation — command injection via protocol manipulation | datasheet | NOT jamming. Manipulates protocol weaknesses. |

## Legal / Regulatory

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **legal_restrictions** | Can operate below 1W transmit power; within FCC regulatory constraints | datasheet | Major advantage over jammers — low power, low interference |

## Physical / Logistics

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **weight_kg** | 30 | datasheet | Under 30 kg (v1.5, outside transit case) |
| **dimensions** | | | Not published |
| **power_requirement_w** | | | Not published |
| **ip_rating** | | | Not published |
| **operating_temp_c** | | | Not published |
| **cost_aud** | | | Not published |

## Notes

- Key differentiator: protocol manipulation, not jamming — minimal RF interference
- Transmit power can operate below 1W — dramatically less than conventional jammers
- v1.5 has four frequency bands (up from two in earlier versions)
- Software-defined — primarily a software solution
- Detection capability: cognitive blind signal detection and characterisation
- Covert monitor mode: monitors drone data, route, and camera feed without operator awareness
- Partnered with Raytheon for market distribution
- Exclusive distribution in South Korea via KCTS
- Part of LAND 156 LOE1 integrated solution (with Acacia Cortex C2, EOS Slinger, Echodyne radar)
- Specific frequency bands and supported protocols not disclosed for OPSEC
