# Generic 5-Inch FPV Attack Drone

**Manufacturer:** Generic / DIY
**Last Updated:** March 2026

---

## Flight Performance

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **max_speed_ms** | 50 | estimated | 180 km/h. Racing FPV can exceed 200 km/h but attack profiles typically 120-180 km/h. |
| **typical_speed_ms** | 40 | estimated | Attack approach speed ~144 km/h |
| **typical_altitude_m** | 15 | estimated | FPV attacks are very low: 5-30m AGL, using terrain for cover |
| **endurance_min** | 8 | estimated | 6-10 min typical with payload |
| **weight_kg** | 1.0 | estimated | 0.5-1.5 kg including payload |

## Radar Signature

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **rcs_m2** | 0.005 | estimated | Very small airframe, carbon fibre, minimal metal. Extremely difficult radar target. |

## RF Signature

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **rf_protocol** | Analogue video + Crossfire/ELRS | estimated | Video: analogue 5.8 GHz. C2: ExpressLRS 2.4 GHz or Crossfire 900 MHz. |
| **rf_frequency_mhz** | [900, 2400, 5800] | estimated | C2 on 900 or 2400, video on 5800 |
| **transmit_power_dbm** | 30 | estimated | FPV video transmitters commonly 600-2000 mW (28-33 dBm). C2 (ELRS): 25-30 dBm. |
| **autonomous_capable** | false | estimated | Currently mostly manual pilot. Autonomous FPV emerging but not yet common. |
| **gnss_required** | false | estimated | Most FPV flown manually without GPS. Makes GNSS jamming ineffective. |

## Other Signatures

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **visual_signature** | Small | estimated | <250mm class. Extremely hard to see at speed. |
| **acoustic_signature** | Loud | estimated | High-pitch racing props, distinctive sound |
| **acoustic_detection_range_factor** | 1.3 | estimated | Louder than commercial but approaching fast — limited acoustic warning time |

## Threat Assessment

| Field | Value | Source | Notes |
|-------|-------|--------|-------|
| **evasion_capability** | advanced | estimated | Skilled FPV pilots perform aggressive evasive manoeuvres. Small size + high speed + low altitude. |
| **category** | fpv | fixed | |

## Notes

- The primary attack drone threat in modern conflict (Ukraine)
- Extremely low cost: $500-2000 USD complete
- Speed + low altitude + small RCS compresses kill chain to seconds
- No GPS dependency makes GNSS jamming largely ineffective
- Analogue video is harder to jam than digital protocols (no protocol to exploit)
- Key challenge: time from first detection to asset arrival may be <10 seconds at close range
- Diverse builds — no standardised specs. Values here represent a "typical" 5-inch build with payload.
