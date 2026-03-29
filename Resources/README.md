# Resources — Research Data Structure

## Directory Layout

```
Resources/
├── Sensors/                    ← One file per sensor product
│   ├── Radar/                  e.g. echodyne_echoguard.md
│   ├── RF/                     e.g. droneshield_rfone_mk2.md
│   ├── EO_IR/                  e.g. dedrone_rf360.md
│   └── Acoustic/               e.g. droneshield_dronesentinel.md
│
├── Effectors/                  ← One file per effector product
│   ├── RF_Jammer/              e.g. droneshield_dronecannon_mk2.md
│   ├── Kinetic/                e.g. eos_slinger.md
│   ├── Directed_Energy/        e.g. eos_apollo.md
│   └── Cyber_Protocol/         e.g. department13_mesmer.md
│
├── Targets/                    ← One file per drone threat profile
│   ├── Commercial_Multirotor/  e.g. dji_mavic_3_pro.md
│   ├── FPV/                    e.g. generic_5inch_fpv.md
│   ├── Fixed_Wing/             e.g. generic_group1_fixedwing.md
│   └── Group3_Plus/            e.g. bayraktar_tb2.md
│
└── VendorResearch/             ← Raw vendor research (reference material)
    ├── DroneShield/
    │   └── products_and_specs.md
    ├── Echodyne/
    │   └── products_and_specs.md
    └── ...
```

## How to Use

### Adding a new product

1. Find the right category folder (e.g. `Sensors/Radar/`)
2. Copy `_TEMPLATE.md` and rename to `manufacturer_product.md` (lowercase, underscores)
3. Fill in the fields using vendor datasheets, the VendorResearch files, or other sources
4. For every value, record the **Source** column: `datasheet`, `estimated`, or `default`
5. Use the **Notes** column for context (e.g. "range quoted for DJI Mavic-class target")

### Source confidence tags

| Tag | Meaning |
|-----|---------|
| `datasheet` | Value taken directly from a published vendor datasheet or spec document |
| `estimated` | Inferred from similar systems, domain knowledge, partial disclosures, or back-calculation |
| `default` | Generic default used when no information is available |

### Naming convention

Files: `manufacturer_product.md` — lowercase, underscores, no spaces.
- `echodyne_echoguard.md`
- `droneshield_rfone_mk2.md`
- `eos_slinger.md`
- `dji_mavic_3_pro.md`
- `generic_5inch_fpv.md`

### Relationship to VendorResearch

VendorResearch files are the raw reference material — everything a vendor publishes, including business context, contracts, C2 software, and products that may not be simulation-relevant. The per-product files in Sensors/Effectors/Targets extract only the simulation-relevant specs into a standardised format.

Each per-product file links back to its VendorResearch source for traceability.

### Relationship to YAML (simulation engine)

These research files are the **source of truth with provenance**. When it's time to build the simulation database, each research file gets converted to a clean YAML file (no source/confidence annotations) for the engine to consume. The research file retains the "why" behind each number.

See `SpecificationRequirements.md` for the full field definitions, estimation rules, and which engine module consumes each field.
