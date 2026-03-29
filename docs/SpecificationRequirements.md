# Specification Requirements — Sensors, Effectors, and Targets

What data do we need to collect for each type of system in order to run the simulation? This document defines the required, desired, and optional fields for every category, explains what each field is used for in the engine, and flags where we'll need to estimate or use defaults when vendor datasheets don't publish a value.

**Confidence tagging:** When populating YAML files, every field should carry a confidence tag:
- `source: datasheet` — value taken directly from a published vendor datasheet or specification document
- `source: estimated` — value inferred from similar systems, domain knowledge, or partial disclosures
- `source: default` — generic default value used when no information is available

---

## Part 1 — Sensors (Detection Systems)

Sensors detect the presence of a drone. Each sensor type uses a different physical phenomenon and therefore has a different propagation model in the simulation engine.

---

### 1.1 — Radar

Radar systems emit radio waves and detect returns from objects. They provide range, bearing, and sometimes altitude and velocity. They require line-of-sight to the target — terrain and structures block radar returns.

**Simulation model:** Viewshed (GDAL) clipped to range and arc.

| Field | Type | Required | Used For | Notes |
|-------|------|----------|----------|-------|
| `name` | string | Yes | Identification | Product name, e.g. "Echodyne EchoGuard" |
| `manufacturer` | string | Yes | Reporting | Vendor name |
| `max_range_m` | float | Yes | Range mask on viewshed | Maximum detection range against a reference RCS target. Vendors often state this for a specific RCS (e.g. "5km against 0.01m² target"). Record the range AND the reference RCS. |
| `min_range_m` | float | Yes | Blind zone modelling | Minimum detection range. Radars have a near-field blind zone, typically 10-100m. If not published, estimate based on radar type (FMCW: ~5m, pulsed: ~50-200m). |
| `reference_rcs_m2` | float | Yes | Range scaling per threat | The RCS value that `max_range_m` is quoted against. Needed to scale detection range for different drone types using the radar range equation. |
| `azimuth_coverage_deg` | float | Yes | Azimuth arc mask | Horizontal angular coverage. 360 for rotating/stacked-panel radars, 90-120 for sector panels. |
| `azimuth_resolution_deg` | float | Desired | Track accuracy modelling (post-MVP) | How precisely the radar can determine bearing. Typically 1-5°. |
| `elevation_coverage_deg` | float | Yes | Elevation arc mask | Vertical angular coverage. Often asymmetric (e.g. -5° to +30°). Record as total span and tilt range if available. |
| `elevation_min_deg` | float | Desired | Low-altitude gap modelling | Minimum elevation angle (below horizon). Determines ability to detect low-flying drones in close. |
| `elevation_max_deg` | float | Desired | High-altitude coverage | Maximum look-up angle. |
| `frequency_band` | string | Yes | RF propagation (post-MVP), classification | Operating band: X-band, Ku-band, S-band, etc. Determines wavelength for diffraction and atmospheric attenuation calculations. |
| `frequency_ghz` | float | Desired | RF propagation calculations | Centre operating frequency in GHz. More precise than band alone. |
| `scan_type` | string | Desired | Track latency for kill chain | Mechanical rotating, electronic scan (AESA/PESA), hybrid. Affects how quickly a target is first detected. |
| `scan_rate_rpm` | float | Desired | Track establishment time | For rotating radars: rotations per minute. Determines revisit rate and therefore track latency. |
| `track_capacity` | int | Desired | Saturation modelling | Maximum simultaneous tracks. Relevant for swarm scenarios. |
| `update_rate_hz` | float | Desired | Kill chain track phase | How often the radar updates a track. Affects track quality and kill chain timeline. |
| `detection_probability` | float | Optional | Probabilistic detection (post-MVP) | Pd at max range against reference RCS. Typically 0.8-0.95. |
| `false_alarm_rate` | float | Optional | Operator workload (post-MVP) | Pfa. Affects operator trust and decision time in kill chain. |
| `mounting_height_m` | float | Yes | Viewshed observer height | Typical installation height above ground. Tripod: 3-5m, mast: 6-15m, vehicle: 3-4m, building: varies. |
| `requires_los` | bool | Yes | Propagation model selection | Always `true` for radar. |
| `power_requirement_w` | float | Optional | Logistics/feasibility | Power draw. Relevant for remote/off-grid sites. |
| `weight_kg` | float | Optional | Logistics/feasibility | System weight including pedestal/mount. |
| `cost_aud` | float | Optional | Configuration comparison, budget optimisation | Unit cost. Often not publicly available. |
| `notes` | string | Optional | Reporting | Anything unusual about the system — limitations, operating modes, etc. |

**Common estimation rules for missing radar fields:**
- `min_range_m`: FMCW radars ≈ 5m, pulsed radars ≈ 50-200m, AESA ≈ 10-30m
- `elevation_coverage_deg`: Small cUAS radars typically 30-80° total, hemispheric radars up to 90°+
- `track_capacity`: Small cUAS radars ≈ 50-200, large systems ≈ 500+
- `reference_rcs_m2`: If vendor says "detects small drones at X km" without specifying RCS, assume 0.01m² (typical for DJI Mavic-class)

---

### 1.2 — RF Passive Detection

RF sensors passively listen for radio frequency emissions from drones — the control link (C2), video downlink, telemetry, or WiFi signals. They do not emit anything themselves. They can detect around obstacles to some extent because they're receiving signals that propagate via RF physics.

**Simulation model:** FSPL + single knife-edge diffraction, compared against sensor sensitivity.

| Field | Type | Required | Used For | Notes |
|-------|------|----------|----------|-------|
| `name` | string | Yes | Identification | |
| `manufacturer` | string | Yes | Reporting | |
| `max_range_m` | float | Yes | Range limit on RF model | Maximum detection range. Highly dependent on drone transmit power and environment. Vendors often quote range in "open field" conditions — this is the FSPL-only case. |
| `min_range_m` | float | Desired | Near-field blind zone | Usually very small for passive sensors (1-10m). If not published, use 0. |
| `sensitivity_dbm` | float | Yes | RF link budget calculation | Receiver sensitivity in dBm. This is the critical field for the RF propagation model — it determines the detection threshold. Lower (more negative) = more sensitive. |
| `frequency_bands` | list[string] | Yes | RF model frequency parameter, threat matching | Which bands the sensor monitors. Common: 433 MHz, 900 MHz, 1.2 GHz, 2.4 GHz, 5.8 GHz. Some sensors cover specific protocols (DJI OcuSync, Lightbridge). |
| `frequency_range_mhz` | object | Desired | Precise RF modelling | Min/max frequency in MHz (e.g. 70-6000 MHz). More precise than named bands. |
| `azimuth_coverage_deg` | float | Yes | Azimuth arc mask | 360 for omnidirectional antennas (most common for RF), 90-120 for directional. |
| `elevation_coverage_deg` | float | Desired | Elevation mask | Often not specified for RF sensors. If omnidirectional, assume ~full hemisphere. |
| `can_identify_protocol` | bool | Desired | Kill chain identify phase | Can the sensor identify the specific drone protocol/model? (e.g. "DJI Mavic 3 detected"). Affects the Identify phase duration in the kill chain. |
| `can_geolocate_drone` | bool | Desired | Track quality for kill chain | Can the sensor determine drone position (not just detect presence)? Some RF sensors provide AOA (angle of arrival) or TDOA geolocation. |
| `can_geolocate_operator` | bool | Desired | Reporting / operational value | Can it locate the drone operator? High operational value but doesn't directly affect coverage simulation. |
| `direction_finding` | bool | Desired | Track phase of kill chain | Does it provide bearing to the signal source? Affects whether it can cue other sensors. |
| `classification_capability` | string | Desired | Kill chain identify phase | Level of classification: "detect only", "protocol ID", "make/model ID". Affects identify time. |
| `requires_los` | bool | Yes | Propagation model selection | Usually `false` — RF propagation modelled via FSPL + diffraction, not viewshed. Set `true` only for directional RF sensors that depend on LOS for geolocation. |
| `mounting_height_m` | float | Yes | Antenna position for RF model | Height above ground affects path geometry and diffraction calculations. |
| `power_requirement_w` | float | Optional | Logistics | |
| `weight_kg` | float | Optional | Logistics | |
| `cost_aud` | float | Optional | Budget modelling | |
| `notes` | string | Optional | Reporting | |

**Key dependency:** The RF model needs both sensor `sensitivity_dbm` AND drone `transmit_power_dbm` (from the target profile). If either is unknown, the RF model falls back to range-circle mode using `max_range_m`.

**Common estimation rules:**
- `sensitivity_dbm`: Typical cUAS RF sensors ≈ -100 to -130 dBm. If vendor says "8km range in open field against DJI", you can back-calculate sensitivity from FSPL at that range and DJI's known transmit power (~20 dBm at 2.4 GHz).
- `frequency_bands`: If vendor says "detects all commercial drones" without specifics, assume [433 MHz, 900 MHz, 2.4 GHz, 5.8 GHz] as minimum.

---

### 1.3 — EO/IR (Electro-Optical / Infrared)

Camera-based sensors that detect drones visually (daylight camera) or thermally (infrared). They require direct line-of-sight. Detection range depends heavily on the target's visual/thermal signature and environmental conditions.

**Simulation model:** Viewshed (GDAL) clipped to range and arc, same as radar.

| Field | Type | Required | Used For | Notes |
|-------|------|----------|----------|-------|
| `name` | string | Yes | Identification | |
| `manufacturer` | string | Yes | Reporting | |
| `max_range_m` | float | Yes | Range mask | Maximum detection range. Highly dependent on target size and environment. Vendors may quote separate ranges for detection/recognition/identification (DRI criteria). Record the detection range. |
| `max_range_recognition_m` | float | Desired | Kill chain identify phase | Range at which the sensor can classify the target as a drone (vs bird, etc.). Shorter than detection range. |
| `max_range_identification_m` | float | Desired | Kill chain identify phase | Range at which the drone type/model can be identified. Shortest of the three. |
| `min_range_m` | float | Desired | Blind zone | Usually very small for cameras. Use 0 if not specified. |
| `sensor_modality` | string | Yes | Day/night capability, environmental degradation | "EO" (daylight only), "IR" (thermal), "EO/IR" (dual-mode), "SWIR". Determines which environmental conditions degrade performance. |
| `azimuth_coverage_deg` | float | Yes | Azimuth arc mask | Fixed cameras: typically 10-60° FOV. PTZ cameras: 360° but only observing one direction at a time (important distinction — see `is_ptz`). Panoramic/staring arrays: 90-360°. |
| `is_ptz` | bool | Yes | Coverage modelling | Pan-Tilt-Zoom camera. If true, 360° azimuth doesn't mean 360° simultaneous coverage — it means the camera can look anywhere but only covers its FOV at any given time. For coverage modelling, use the instantaneous FOV, not the pan range. Unless slewing is modelled (post-MVP). |
| `instantaneous_fov_h_deg` | float | Yes (if PTZ) | Actual coverage arc | Horizontal field of view at any moment. For PTZ cameras this is the real coverage. For fixed cameras this equals `azimuth_coverage_deg`. |
| `instantaneous_fov_v_deg` | float | Desired | Elevation coverage | Vertical field of view. |
| `elevation_coverage_deg` | float | Desired | Elevation mask | Total elevation range the sensor can cover (for fixed: FOV, for PTZ: tilt range). |
| `resolution_megapixels` | float | Optional | DRI range estimation (post-MVP) | Sensor resolution. Higher resolution extends recognition/identification range for a given FOV. |
| `frame_rate_fps` | float | Optional | Track update rate | Affects track quality. Typically 25-60 fps. |
| `has_autotracker` | bool | Desired | Kill chain track phase | Does the system have automatic target tracking? Reduces track time in kill chain. |
| `has_ai_detection` | bool | Desired | Kill chain detect/identify phases | AI-based automatic drone detection? Reduces detect and identify time. |
| `day_night_capability` | string | Yes | Time-of-day modelling | "day only", "night only" (IR), "day and night" (dual mode or IR). |
| `requires_los` | bool | Yes | Propagation model selection | Always `true` for EO/IR. |
| `mounting_height_m` | float | Yes | Viewshed observer height | |
| `power_requirement_w` | float | Optional | Logistics | |
| `weight_kg` | float | Optional | Logistics | |
| `cost_aud` | float | Optional | Budget modelling | |
| `notes` | string | Optional | Reporting | |

**Estimation rules:**
- `max_range_m` for detection: Small drone at EO ≈ 1-3km (naked eye equivalent), long-range IR ≈ 5-15km, panoramic staring ≈ 2-5km
- `max_range_recognition_m`: Typically 50-70% of detection range
- `max_range_identification_m`: Typically 30-50% of detection range
- `instantaneous_fov_h_deg` for PTZ: Typically 0.5-60° depending on zoom level. Use the widest zoom (largest FOV, shortest range) for search mode, narrowest (smallest FOV, longest range) for track mode. For coverage modelling, use wide/search FOV.

**Important note on PTZ cameras:** A PTZ camera can only cover one direction at a time. In the simulation, a PTZ camera should be modelled as a narrow sector sensor unless it's cued by another sensor (cueing is post-MVP). Don't model a PTZ as 360° coverage — that overstates capability.

---

### 1.4 — Acoustic

Acoustic sensors detect drone propeller noise using microphone arrays. They provide bearing and sometimes range estimation. Very short range compared to other sensor types, but they detect RF-silent drones that passive RF sensors miss.

**Simulation model:** Simple range circle with ambient noise penalty. No terrain occlusion (sound diffracts around obstacles at relevant frequencies).

| Field | Type | Required | Used For | Notes |
|-------|------|----------|----------|-------|
| `name` | string | Yes | Identification | |
| `manufacturer` | string | Yes | Reporting | |
| `max_range_m` | float | Yes | Range circle radius | Maximum detection range in quiet conditions. Typically 300-1000m for cUAS acoustic sensors. Very environment-dependent. |
| `min_range_m` | float | Desired | Blind zone | Usually very small. Use 0 if not specified. |
| `ambient_noise_penalty` | object | Desired | Range reduction model | How much range degrades with ambient noise level. If vendor provides "500m in quiet, 200m in urban", record both data points. The simulation applies a linear or stepped reduction. |
| `quiet_range_m` | float | Desired | Range in ideal conditions | Detection range at < 40 dBA ambient noise. Use as `max_range_m` if only one range is given. |
| `urban_range_m` | float | Desired | Range in noisy conditions | Detection range at ~60 dBA ambient noise. |
| `azimuth_coverage_deg` | float | Yes | Arc mask | Usually 360° (omnidirectional microphone arrays). |
| `can_provide_bearing` | bool | Desired | Cueing capability (post-MVP) | Can the sensor determine the direction of the drone? |
| `bearing_accuracy_deg` | float | Optional | Track quality | Typical bearing accuracy: 5-15°. |
| `frequency_range_hz` | object | Optional | Environmental modelling (post-MVP) | Mic array frequency response. Relevant for wind noise filtering and drone signature matching. |
| `requires_los` | bool | Yes | Propagation model selection | `false` — sound diffracts around most obstacles at drone-relevant frequencies (100-10000 Hz). |
| `mounting_height_m` | float | Yes | Sensor position | Usually ground or low pole mounted (1-5m). |
| `weather_sensitivity` | string | Optional | Environmental degradation (post-MVP) | Wind is the primary degradation factor. If vendor provides max operating wind speed, record it. |
| `max_wind_speed_ms` | float | Optional | Environmental limits | Wind speed at which sensor becomes ineffective. Typically 10-15 m/s. |
| `power_requirement_w` | float | Optional | Logistics | |
| `weight_kg` | float | Optional | Logistics | |
| `cost_aud` | float | Optional | Budget modelling | |
| `notes` | string | Optional | Reporting | |

**Estimation rules:**
- `max_range_m`: Quiet rural ≈ 500-1000m, suburban ≈ 300-500m, urban/industrial ≈ 100-300m
- If vendor quotes a single range without conditions, assume it's the quiet/ideal condition number

---

## Part 2 — Effectors (Countermeasure Systems)

Effectors neutralise a drone after it has been detected, tracked, and identified. Each type uses a different defeat mechanism.

---

### 2.1 — RF Jammer

Emits RF energy to disrupt the drone's control link, video link, or GNSS signal. The drone either enters a failsafe mode (return-to-home, hover, land) or loses control.

**Simulation model:** Range-based coverage circle for omnidirectional jammers, viewshed + range + arc for directional jammers.

| Field | Type | Required | Used For | Notes |
|-------|------|----------|----------|-------|
| `name` | string | Yes | Identification | |
| `manufacturer` | string | Yes | Reporting | |
| `max_range_m` | float | Yes | Engagement zone radius | Maximum effective jamming range. Highly dependent on drone protocol and jammer ERP. |
| `min_range_m` | float | Desired | Minimum engagement range | Usually very small for jammers. |
| `engagement_arc_deg` | float | Yes | Azimuth arc mask | Omnidirectional: 360°. Directional/handheld: typically 30-90°. |
| `elevation_arc_deg` | float | Desired | Elevation mask | Vertical engagement coverage. |
| `frequency_bands_jammed` | list[string] | Yes | Threat matching | Which bands does it jam? 433 MHz, 900 MHz, 2.4 GHz, 5.8 GHz, GNSS (L1/L2). Determines which drone protocols are affected. |
| `jam_gnss` | bool | Yes | Defeat mechanism | Does it jam GPS/GNSS? Important because GNSS jamming forces RTH-via-compass or uncontrolled drift, vs C2 jamming which triggers protocol-specific failsafe. |
| `jam_c2` | bool | Yes | Defeat mechanism | Does it jam the command-and-control link? |
| `jam_video` | bool | Desired | Defeat mechanism | Does it jam the video downlink? FPV drones are blind without video. |
| `erp_dbm` | float | Desired | RF engagement modelling (post-MVP) | Effective Radiated Power. Determines jam-to-signal ratio at range. Higher ERP = longer effective range. |
| `reaction_time_s` | float | Yes | Kill chain engage phase | Time from "engage" command to RF energy on target. Typically 0.5-3s for automated systems, longer for manual. |
| `simultaneous_engagements` | int | Yes | Saturation modelling | How many targets can it jam simultaneously. Omnidirectional: effectively unlimited within range (limited by power budget). Directional: typically 1. |
| `reload_time_s` | float | Yes | Re-engagement timeline | Time to switch to a new target. For jammers this is typically 0-1s (electronic, not mechanical). |
| `defeat_probability` | float | Yes | Kill chain assessment | Probability of successful defeat per engagement. For jammers: depends on drone's failsafe behaviour. Typical estimate: 0.7-0.9 for commercial drones with known protocols. |
| `defeat_mechanism` | string | Yes | Reporting | Description: "C2 link disruption — triggers failsafe (RTH/hover/land)", "GNSS spoofing — redirects to landing zone", etc. |
| `requires_los` | bool | Yes | Propagation model selection | Usually `false` for omnidirectional. `true` for directional jammers (need to point at target). |
| `legal_restrictions` | string | Desired | Reporting | RF jamming is heavily regulated. Note jurisdiction-specific restrictions (e.g. "Defence use only under Australian ACMA exemption"). |
| `mounting_type` | string | Desired | Logistics | "Fixed", "vehicle-mounted", "handheld", "tripod". |
| `mounting_height_m` | float | Yes | Position for LOS check (if directional) | |
| `power_requirement_w` | float | Optional | Logistics | Jammers are typically power-hungry. |
| `weight_kg` | float | Optional | Logistics | |
| `cost_aud` | float | Optional | Budget modelling | |
| `notes` | string | Optional | Reporting | |

**Estimation rules:**
- `reaction_time_s`: Automated systems ≈ 0.5-2s, manual/operator-triggered ≈ 3-10s
- `defeat_probability`: Commercial drones with known protocols ≈ 0.7-0.9, unknown/hardened protocols ≈ 0.3-0.5, autonomous (no C2 link) ≈ 0.0-0.1 (GNSS jamming only recourse)
- `simultaneous_engagements` for omnidirectional: set to 20 (our saturation cap) — effectively unlimited

---

### 2.2 — Kinetic

Physical projectile systems that destroy the drone — cannons, shotguns, net guns, or interceptor drones. Require line-of-sight to the target.

**Simulation model:** Viewshed (LOS) + range + engagement arc.

| Field | Type | Required | Used For | Notes |
|-------|------|----------|----------|-------|
| `name` | string | Yes | Identification | |
| `manufacturer` | string | Yes | Reporting | |
| `max_range_m` | float | Yes | Engagement zone radius | Maximum effective engagement range. Varies enormously: net gun ≈ 50-100m, autocannon ≈ 1000-2000m, interceptor drone ≈ 1000-3000m. |
| `min_range_m` | float | Yes | Minimum engagement range | Minimum safe engagement distance. Important for systems with explosive projectiles or high-velocity rounds. |
| `engagement_arc_deg` | float | Yes | Azimuth arc mask | Turret-based: typically 360°. Fixed mount: limited arc. |
| `elevation_arc_deg` | float | Yes | Elevation mask | Critical for kinetic — can the weapon elevate enough to engage overhead targets? Typically -10° to +80°. |
| `elevation_min_deg` | float | Desired | Low engagement limit | |
| `elevation_max_deg` | float | Desired | High engagement limit | |
| `projectile_type` | string | Yes | Defeat mechanism, safety | "Net", "Programmable airburst", "HE", "Kinetic energy", "Interceptor drone". Affects collateral damage assessment. |
| `reaction_time_s` | float | Yes | Kill chain engage phase | Time from track to first round/net/interceptor launch. Includes slew time for turrets. |
| `slew_rate_deg_s` | float | Desired | Reaction time refinement | How fast the weapon can traverse to a new bearing. Affects reaction time for off-boresight targets. |
| `simultaneous_engagements` | int | Yes | Saturation modelling | Usually 1 for gun systems. Interceptor drone systems may deploy multiple interceptors. |
| `reload_time_s` | float | Yes | Re-engagement timeline | Time between engagements. Single-shot net: may need manual reload (60s+). Autocannon: burst interval (1-5s). Interceptor drone: new launch (10-30s). |
| `magazine_capacity` | int | Desired | Sustained engagement modelling | Total rounds/interceptors before full resupply. |
| `defeat_probability` | float | Yes | Kill chain assessment | Per-engagement Pk. Net guns at short range ≈ 0.8-0.95. Autocannon ≈ 0.5-0.8 depending on guidance. Interceptor drone ≈ 0.7-0.9. |
| `defeat_mechanism` | string | Yes | Reporting | "Entanglement (net capture)", "Physical destruction (airburst)", "Kinetic intercept (collision)", etc. |
| `collateral_risk` | string | Yes | Safety, site feasibility | "Low" (nets), "Medium" (guided projectiles), "High" (unguided HE). Determines whether the effector can be used in populated areas. |
| `requires_los` | bool | Yes | Propagation model | Always `true` for kinetic. |
| `mounting_type` | string | Desired | Logistics | "Fixed turret", "vehicle-mounted", "tripod", "handheld". |
| `mounting_height_m` | float | Yes | Viewshed observer height | |
| `power_requirement_w` | float | Optional | Logistics | |
| `weight_kg` | float | Optional | Logistics | |
| `cost_aud` | float | Optional | Budget modelling | |
| `cost_per_engagement_aud` | float | Desired | Cost modelling | Cost per round/net/interceptor. Relevant for sustained engagement costing. |
| `notes` | string | Optional | Reporting | |

**Estimation rules:**
- `reaction_time_s`: Automated turret ≈ 2-5s (including slew), manual ≈ 5-15s, interceptor drone launch ≈ 5-15s
- `defeat_probability`: Guided systems ≈ 0.6-0.9, unguided ≈ 0.2-0.5, nets at close range ≈ 0.8-0.95

---

### 2.3 — Directed Energy (Laser / HPM)

High-energy laser (HEL) or high-power microwave (HPM) systems that disable the drone by burning through structure (laser) or frying electronics (HPM). Require line-of-sight (laser) or near-LOS (HPM).

**Simulation model:** Viewshed (LOS) + range + engagement arc for laser. Range circle for HPM.

| Field | Type | Required | Used For | Notes |
|-------|------|----------|----------|-------|
| `name` | string | Yes | Identification | |
| `manufacturer` | string | Yes | Reporting | |
| `de_type` | string | Yes | Model selection | "HEL" (High Energy Laser) or "HPM" (High Power Microwave). Different physics and LOS requirements. |
| `max_range_m` | float | Yes | Engagement zone radius | Maximum effective range. HEL: typically 500-2000m for cUAS. HPM: typically 100-500m. |
| `min_range_m` | float | Desired | Minimum safe range | |
| `engagement_arc_deg` | float | Yes | Azimuth arc mask | HEL turrets: typically 360°. HPM: varies. |
| `elevation_arc_deg` | float | Yes | Elevation mask | |
| `beam_dwell_time_s` | float | Yes (HEL) | Kill chain engage phase | Time the laser must stay on target to achieve defeat. Typically 2-10s depending on power and target material. This IS the engagement time. |
| `reaction_time_s` | float | Yes | Kill chain engage phase | Time from "engage" command to beam on target. Includes slew and acquire. |
| `simultaneous_engagements` | int | Yes | Saturation | Usually 1 (single beam). Some concepts can rapidly switch between targets. |
| `reload_time_s` | float | Yes | Re-engagement | HEL: effectively 0 (beam redirects instantly), but thermal management may require cooldown (5-30s). HPM: capacitor recharge time (5-60s). |
| `magazine_capacity` | string | Desired | Sustained engagement | HEL: "unlimited" (power-limited, not ammo-limited). HPM: may have duty cycle limits. |
| `defeat_probability` | float | Yes | Kill chain assessment | HEL at optimal range: 0.8-0.95 (track quality dependent). HPM: 0.5-0.8 (depends on target electronics hardening). |
| `defeat_mechanism` | string | Yes | Reporting | "Structural burn-through (motor/propeller damage)", "Electronic disruption (HPM)", etc. |
| `weather_sensitivity` | string | Desired | Environmental limitations | HEL performance degrades in rain, fog, dust. Note conditions that reduce effectiveness. |
| `requires_los` | bool | Yes | Propagation model | HEL: always `true`. HPM: `true` for directional, may be less strict for omnidirectional. |
| `mounting_type` | string | Desired | Logistics | |
| `mounting_height_m` | float | Yes | Viewshed observer height | |
| `power_requirement_w` | float | Desired | Logistics | DE systems are very power-hungry (HEL: 10-100+ kW). Important for site feasibility. |
| `weight_kg` | float | Optional | Logistics | |
| `cost_aud` | float | Optional | Budget modelling | |
| `cost_per_engagement_aud` | float | Desired | Cost modelling | HEL: very low (electricity). HPM: very low. Major selling point vs kinetic. |
| `notes` | string | Optional | Reporting | |

**Estimation rules:**
- `beam_dwell_time_s`: Low-power HEL (5-10kW) ≈ 5-10s, high-power (50kW+) ≈ 1-3s
- `reaction_time_s`: Automated HEL turret ≈ 2-5s including acquire
- `defeat_probability`: HEL on small drone in clear weather ≈ 0.85-0.95, in rain/fog ≈ 0.4-0.7

---

### 2.4 — Cyber / Protocol

Systems that exploit the drone's communication protocol to take control or force a landing. Unlike jamming (brute force disruption), these systems interact with the protocol itself.

**Simulation model:** Range circle (similar to omnidirectional jammer). LOS not required.

| Field | Type | Required | Used For | Notes |
|-------|------|----------|----------|-------|
| `name` | string | Yes | Identification | |
| `manufacturer` | string | Yes | Reporting | |
| `max_range_m` | float | Yes | Engagement zone radius | Maximum effective range. Protocol-dependent — typically shorter than broadband jamming because lower power is needed but protocol interaction requires signal quality. |
| `min_range_m` | float | Desired | Minimum range | |
| `engagement_arc_deg` | float | Yes | Arc mask | Usually 360° (omnidirectional antenna). |
| `supported_protocols` | list[string] | Yes | Threat matching | Which protocols can be exploited: "DJI OcuSync", "DJI Lightbridge", "MAVLink", "WiFi", "analogue video", etc. If the drone uses an unsupported protocol, this effector has 0% effectiveness. |
| `defeat_modes` | list[string] | Yes | Reporting | What can it do: "Force land", "Take control", "Redirect to safe zone", "Kill motors". |
| `reaction_time_s` | float | Yes | Kill chain engage phase | Time from engagement command to protocol handshake. Typically 2-10s for protocol cracking. |
| `simultaneous_engagements` | int | Yes | Saturation | How many drones can it control at once. Typically 1-5, protocol-dependent. |
| `reload_time_s` | float | Yes | Re-engagement | Time to switch to a new target protocol. Typically 1-5s. |
| `defeat_probability` | float | Yes | Kill chain assessment | Highly protocol-dependent. Known protocols (DJI) ≈ 0.8-0.95. Unknown/encrypted ≈ 0.0-0.1. |
| `defeat_mechanism` | string | Yes | Reporting | "Protocol exploitation — command injection to force landing", "GNSS spoofing via protocol", etc. |
| `requires_los` | bool | Yes | Propagation model | Usually `false`. |
| `mounting_height_m` | float | Yes | Position | |
| `legal_restrictions` | string | Desired | Reporting | Protocol exploitation may have additional legal considerations beyond jamming. |
| `power_requirement_w` | float | Optional | Logistics | Typically much lower than jammers. |
| `weight_kg` | float | Optional | Logistics | |
| `cost_aud` | float | Optional | Budget modelling | |
| `notes` | string | Optional | Reporting | |

---

## Part 3 — Targets (Drone Threat Profiles)

Targets define what the cUAS system is defending against. Each threat profile has physical characteristics that determine how detectable and engageable it is.

---

### 3.1 — Multirotor (Commercial / COTS)

The most common cUAS threat. Commercial off-the-shelf quadcopters and hexacopters (DJI, Autel, Skydio, etc.). Low-and-slow flight profile, strong RF signature from standard control protocols.

| Field | Type | Required | Used For | Notes |
|-------|------|----------|----------|-------|
| `name` | string | Yes | Identification | e.g. "DJI Mavic 3 Pro", "DJI Matrice 300 RTK" |
| `manufacturer` | string | Yes | Reporting | |
| `category` | string | Yes | Grouping | "commercial_multirotor" |
| `max_speed_ms` | float | Yes | Time-in-coverage, kill chain timing | Maximum flight speed in m/s. DJI Mavic: ~20 m/s, Matrice: ~23 m/s. |
| `typical_speed_ms` | float | Desired | Realistic corridor timing | Cruise speed during approach. Usually 50-70% of max. |
| `max_altitude_m` | float | Desired | Altitude banding for corridor analysis | Software-limited (400ft/120m for DJI) but can be unlocked. |
| `typical_altitude_m` | float | Yes | Default altitude for corridor analysis | What altitude to model for threat corridors if not specified per-corridor. |
| `rcs_m2` | float | Yes | Radar range scaling | Radar cross-section in m². Determines radar detection range via the radar range equation. DJI Mavic ≈ 0.01 m², Matrice ≈ 0.05-0.1 m². |
| `rcs_band` | string | Desired | Frequency-dependent RCS (post-MVP) | RCS varies with radar frequency. If available, record per-band: "X-band: 0.01, Ku-band: 0.008". |
| `rf_signature` | object | Yes | RF detection model | Control protocol details for RF sensor matching. |
| `rf_protocol` | string | Yes | RF detection, cyber effector matching | "DJI OcuSync 3.0", "DJI Lightbridge", "MAVLink", "WiFi", "Analogue", "Proprietary/unknown". |
| `rf_frequency_mhz` | list[float] | Yes | RF propagation model frequency | Operating frequencies of the C2/video links. DJI: [2400, 5800]. |
| `transmit_power_dbm` | float | Yes | RF link budget — the other half of the equation | Drone's C2 transmitter output power. DJI ≈ 20-26 dBm (100-400 mW). Critical for RF detection range calculation paired with sensor `sensitivity_dbm`. |
| `rf_emission_continuous` | bool | Desired | RF detection reliability | Does the drone emit continuously or intermittently? Continuous (DJI) ≈ easy to detect. Some protocols use frequency hopping or burst transmission. |
| `visual_signature` | string | Desired | EO/IR modelling (post-MVP) | Size and visual characteristics. "Small (< 250mm)", "Medium (250-600mm)", "Large (> 600mm)". Affects EO detection range. |
| `thermal_signature` | string | Desired | IR modelling (post-MVP) | "Low" (small battery drone in cold weather), "Medium" (warm motors, visible on IR), "High" (combustion engine). |
| `acoustic_signature` | string | Desired | Acoustic range modelling | "Quiet" (folding props, slow flight), "Medium" (standard props), "Loud" (racing props, high speed). Affects acoustic detection range. |
| `acoustic_detection_range_factor` | float | Desired | Acoustic range scaling | Multiplier on sensor's base range. Quiet drone ≈ 0.5x, standard ≈ 1.0x, loud ≈ 1.5x. |
| `weight_kg` | float | Desired | Defeat modelling (post-MVP) | Heavier drones are harder to stop with nets, resist wind from downwash effectors. |
| `payload_capacity_kg` | float | Desired | Threat assessment / reporting | What the drone could carry. Relevant for threat context. |
| `endurance_min` | float | Optional | Sustained threat modelling | Flight time. Relevant for loitering threats. |
| `evasion_capability` | string | Yes | Corridor modelling | "none" (straight line approach), "basic" (operator-controlled deviation), "advanced" (autonomous obstacle avoidance). MVP uses "none" — all straight-line. |
| `autonomous_capable` | bool | Yes | RF detection / jammer effectiveness | Can the drone fly a pre-programmed mission without C2 link? If yes, RF sensors may not detect it and jammers are ineffective. GNSS jamming/spoofing becomes the only RF-based option. |
| `gnss_required` | bool | Desired | GNSS jammer effectiveness | Does the drone need GNSS to navigate? If yes, GNSS jamming is effective. If no (visual/inertial nav), even GNSS jamming fails. |
| `notes` | string | Optional | | |

---

### 3.2 — FPV (First-Person-View Racing / Attack)

FPV drones are fast, agile, and cheap. They're the primary attack vector in modern conflict (Ukraine). Flown manually via low-latency video link, they close distance rapidly and are difficult to engage.

| Field | Type | Required | Used For | Notes |
|-------|------|----------|----------|-------|
| `name` | string | Yes | Identification | e.g. "Generic 5-inch FPV" |
| `category` | string | Yes | Grouping | "fpv" |
| `max_speed_ms` | float | Yes | Kill chain timing | FPV drones are fast: 30-50 m/s typical, 70+ m/s max. This dramatically compresses the kill chain timeline. |
| `typical_speed_ms` | float | Yes | Corridor timing | Attack approach speed. Often near max speed. |
| `typical_altitude_m` | float | Yes | Corridor analysis | FPV attacks are typically very low altitude (5-30m AGL) to exploit terrain cover. |
| `rcs_m2` | float | Yes | Radar detection | Small airframe: typically 0.005-0.01 m². Very difficult radar target. |
| `rf_protocol` | string | Yes | RF/cyber matching | "Analogue video" (5.8 GHz), "DJI FPV system", "Crossfire/ELRS" (900 MHz), "ExpressLRS" (2.4 GHz). |
| `rf_frequency_mhz` | list[float] | Yes | RF model | C2: [900] or [2400]. Video: [5800]. |
| `transmit_power_dbm` | float | Yes | RF detection range | Often higher than commercial drones for range/penetration: 25-33 dBm (300-2000 mW). |
| `visual_signature` | string | Desired | EO modelling | "Small" — very difficult to visually detect at speed. |
| `acoustic_signature` | string | Desired | Acoustic modelling | "Loud" — high-pitch racing props are distinctive but speed limits acoustic detection utility. |
| `acoustic_detection_range_factor` | float | Desired | Acoustic scaling | Typically 1.2-1.5x (louder than commercial). |
| `weight_kg` | float | Desired | Defeat modelling | Typically 0.5-2kg. Light = hard to net, easy to defeat with laser. |
| `evasion_capability` | string | Yes | Corridor modelling | "basic" to "advanced" — skilled FPV pilots can perform aggressive evasive manoeuvres. |
| `autonomous_capable` | bool | Yes | Jammer effectiveness | Currently `false` for most FPV, but autonomous FPV is emerging. |
| `gnss_required` | bool | Desired | GNSS jammer effectiveness | Most FPV don't use GPS for navigation (manual pilot). GNSS jamming less effective. |
| `notes` | string | Optional | | |

---

### 3.3 — Fixed-Wing

Fixed-wing drones including mapping/survey UAVs, loitering munitions, and ISR platforms. Faster than multirotors in cruise, longer endurance, higher altitude, but less agile.

| Field | Type | Required | Used For | Notes |
|-------|------|----------|----------|-------|
| `name` | string | Yes | Identification | e.g. "Skyeton Raybird-3", "ZALA Lancet" |
| `category` | string | Yes | Grouping | "fixed_wing" |
| `max_speed_ms` | float | Yes | Kill chain timing | Typically 20-60 m/s for small UAS, 60-100+ m/s for loitering munitions. |
| `typical_speed_ms` | float | Yes | Corridor timing | Cruise speed. |
| `min_speed_ms` | float | Desired | Loiter modelling (post-MVP) | Stall speed. Fixed-wing can't hover — minimum speed matters for sustained presence scenarios. |
| `typical_altitude_m` | float | Yes | Corridor analysis | Typically higher than multirotors: 100-500m for ISR, can be low for attack runs. |
| `rcs_m2` | float | Yes | Radar detection | Larger than multirotors: 0.05-0.5 m² for Group 1-2, 0.5-2 m² for Group 3. |
| `wingspan_m` | float | Desired | Visual detection range scaling | Larger wingspan = easier to see. 1-3m typical for cUAS-relevant threats. |
| `rf_protocol` | string | Yes | RF/cyber matching | Often MAVLink (open source autopilots), proprietary, or military datalinks. |
| `rf_frequency_mhz` | list[float] | Yes | RF model | Varies widely: [900], [1200], [2400]. Military may use non-standard bands. |
| `transmit_power_dbm` | float | Yes | RF detection range | Varies: 20-33 dBm typical. |
| `visual_signature` | string | Desired | EO modelling | "Medium" to "Large" depending on wingspan. |
| `acoustic_signature` | string | Desired | Acoustic modelling | Prop-driven: "Medium". Electric pusher: "Quiet". Jet: "Loud". |
| `acoustic_detection_range_factor` | float | Desired | Acoustic scaling | Prop ≈ 0.8-1.0x, electric ≈ 0.5-0.7x, jet ≈ 1.5-2.0x. |
| `weight_kg` | float | Desired | Defeat modelling | 2-25kg for Group 1-2, 25-150kg for Group 3. |
| `endurance_min` | float | Desired | Loiter threat modelling | Often 60-180+ minutes. Long endurance enables persistent ISR. |
| `evasion_capability` | string | Yes | Corridor modelling | "none" for pre-programmed strike, "basic" for operator-controlled, "advanced" for autonomous. |
| `autonomous_capable` | bool | Yes | Jammer effectiveness | Loitering munitions and ISR platforms are commonly autonomous (pre-programmed waypoints). Jammers less effective. |
| `gnss_required` | bool | Desired | GNSS jammer effectiveness | Most fixed-wing autopilots are GPS-dependent. GNSS jamming typically effective. |
| `notes` | string | Optional | | |

---

### 3.4 — Group 3+ / Large UAS

Larger military-grade UAS (>25kg, >150kg). Included for completeness and to set the upper bound of what the simulation can assess, even though most cUAS systems focus on Groups 1-2.

| Field | Type | Required | Used For | Notes |
|-------|------|----------|----------|-------|
| `name` | string | Yes | Identification | e.g. "Bayraktar TB2", "MQ-9 Reaper" (reference only) |
| `category` | string | Yes | Grouping | "group3_plus" |
| `max_speed_ms` | float | Yes | Kill chain timing | 50-100+ m/s. |
| `typical_speed_ms` | float | Yes | Corridor timing | |
| `typical_altitude_m` | float | Yes | Corridor analysis | Often 1000-5000m+ AGL. Above the ceiling of most cUAS sensors/effectors. |
| `rcs_m2` | float | Yes | Radar detection | 0.5-10+ m². Easier to detect but harder to engage at altitude. |
| `rf_protocol` | string | Yes | RF modelling | Typically military datalinks (encrypted, frequency-hopping). |
| `rf_frequency_mhz` | list[float] | Yes | RF model | Military bands, often classified. Use known bands where available. |
| `transmit_power_dbm` | float | Yes | RF detection | Higher power: 30-40+ dBm. |
| `acoustic_signature` | string | Desired | Acoustic | Prop/turboprop: "Loud". Jet: "Very loud". |
| `weight_kg` | float | Desired | Context | 25-1500+ kg. |
| `endurance_min` | float | Desired | Sustained threat | Often 600+ minutes (10+ hours). |
| `evasion_capability` | string | Yes | Corridor modelling | "advanced" — military systems have countermeasures and evasive routing. |
| `autonomous_capable` | bool | Yes | Jammer effectiveness | Yes — pre-programmed mission capability is standard. |
| `gnss_required` | bool | Desired | GNSS effectiveness | INS/GPS hybrid. GNSS jamming degrades accuracy but INS provides fallback. |
| `notes` | string | Optional | | Note: most cUAS effectors in the MVP database cannot engage Group 3+ at typical operating altitudes. Include for completeness and to demonstrate coverage limitations in reports. |

---

## Field Summary — Cross-Reference

Fields that appear across multiple categories and are consumed by the same engine module:

| Engine Module | Sensor Fields Used | Effector Fields Used | Target Fields Used |
|---------------|-------------------|---------------------|-------------------|
| **Viewshed** | `mounting_height_m`, `requires_los` | `mounting_height_m`, `requires_los` | — |
| **Range/Arc Clipping** | `max_range_m`, `min_range_m`, `azimuth_coverage_deg`, `elevation_coverage_deg` | `max_range_m`, `min_range_m`, `engagement_arc_deg`, `elevation_arc_deg` | — |
| **RF Propagation** | `sensitivity_dbm`, `frequency_bands` | — | `transmit_power_dbm`, `rf_frequency_mhz` |
| **Acoustic** | `max_range_m`, `ambient_noise_penalty` | — | `acoustic_detection_range_factor` |
| **Radar Range Scaling** | `max_range_m`, `reference_rcs_m2` | — | `rcs_m2` |
| **Kill Chain** | `update_rate_hz`, `can_identify_protocol`, `has_autotracker` | `reaction_time_s`, `defeat_probability` | `max_speed_ms`, `typical_speed_ms` |
| **Saturation** | — | `simultaneous_engagements`, `reload_time_s` | — |
| **Threat Corridor** | — | — | `max_speed_ms`, `typical_altitude_m`, `evasion_capability` |
| **Configuration Comparison** | `cost_aud` | `cost_aud`, `cost_per_engagement_aud` | — |

---

*Living document. Update as the simulation engine evolves and new field requirements emerge.*
