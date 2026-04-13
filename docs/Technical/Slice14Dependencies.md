# Slice 14 Interface Application — Dependency Map

## Dependency Graph

```
14.1 (Shell) ──────────────────────────────────────────────────────────┐
    │                                                                   │
    ├──► 14.3 (Terrain Loader) ──► 14.5 (Placement Editor) ──► 14.8 ──► 14.9
    │         │                         ▲                      (Sim)    14.10
    │         └──► 14.7 (Corridors      │                               14.12
    │               + Zones) ───────────┤                               14.13
    │                   │               │                                 │
    ├──► 14.4 (Library)─┘               │                                 ▼
    │         │                         │                              14.14
    └──► 14.6 (Budget) ─────────────────┘
                │
                └──► 14.11 (Optimiser)

14.2 (FastAPI) ─────────────────────────────► 14.8, 14.11, 14.13
```

## Build Waves

| Wave | Slices | Blocks on |
|------|--------|-----------|
| 1 | **14.1** Shell + **14.2** FastAPI | Nothing — fully independent of each other |
| 2 | **14.3** Terrain Loader + **14.4** Library Browser + **14.6** Budget Tracker | 14.1 done |
| 3 | **14.5** Placement Editor + **14.7** Corridor + Zone Editors | 14.3 done; 14.5 also needs 14.4 |
| 4 | **14.8** Simulation Runner + **14.11** Optimiser | 14.8 needs 14.2+14.3+14.5; 14.11 needs 14.2+14.6+14.7 — independent of each other |
| 5 | **14.9** Coverage Viewer + Gap Analysis + **14.10** Kill Chain + Saturation + **14.12** Scenario Comparison + **14.13** Report Configurator | All need 14.8; 14.13 also needs 14.2 |
| 6 | **14.14** Persistence + Deployment | All previous |

## Critical Path

Minimum sequential steps if fully parallelised:

```
14.1 → 14.3 → 14.5 → 14.8 → 14.9 → 14.14
```

6 steps. Everything else fits alongside this chain.

## Per-Slice Dependency Detail

| Slice | Depends on | Unlocks |
|-------|-----------|---------|
| 14.1 Shell | — | Everything |
| 14.2 FastAPI | — (pure Python, wraps existing engine) | 14.8, 14.11, 14.13 |
| 14.3 Terrain Loader | 14.1 | 14.5, 14.7, 14.8, 14.9, 14.10, 14.11, 14.12 |
| 14.4 Library Browser | 14.1 (14.2 for live API; can mock) | 14.5 (placement:pending events) |
| 14.5 Placement Editor | 14.1, 14.3, 14.4 | 14.8 |
| 14.6 Budget Tracker | 14.1 | 14.11 (writes constraints) |
| 14.7 Corridor + Zone Editors | 14.1, 14.3 | 14.8 (corridors), 14.11 (zones) |
| 14.8 Simulation Runner | 14.1, 14.2, 14.3, 14.5 | 14.9, 14.10, 14.12, 14.13 |
| 14.9 Coverage Viewer + Gap Analysis | 14.1, 14.8 | 14.14 |
| 14.10 Kill Chain + Saturation | 14.1, 14.8 | 14.14 |
| 14.11 Optimiser | 14.1, 14.2, 14.6, 14.7 | 14.14 |
| 14.12 Scenario Comparison | 14.1, 14.8 | 14.14 |
| 14.13 Report Configurator | 14.1, 14.2, 14.8 | 14.14 |
| 14.14 Persistence + Deployment | All previous | — |

## Parallelism Summary

**Maximum concurrent work: 4 engineers** (Wave 5 — all four analysis/output modules are independent of each other)

**Two independent starting points:** 14.1 (shell JS) and 14.2 (FastAPI Python) share zero code. One person starts on the browser shell while another wraps the Python engine.

**Hidden constraint:** 14.5 needs both 14.3 *and* 14.4 before its `placement:pending` flow works end-to-end. If solo: do 14.3 → 14.4 → 14.5 in sequence. If two people available after Wave 1: 14.3 and 14.4 in parallel.

**Solo developer order:** Follow slice numbers in sequence (14.1 → 14.14). The sequence is already topologically sorted.
