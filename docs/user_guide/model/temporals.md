!!! warning "Under Construction"

    This documentation is still under construction and will receive major 
    additions and changes in the future. Please be considerate with us and the 
    documentation. However, if you already have any tips and remarks or if you 
    miss some super important aspects, we'd love to hear from you.



# Temporal Data

This page explains how Odeon represents and manages time‑varying data. The intent is to give you a solid conceptual model, show how everyday modeling tasks map to `Temporal`, and highlight the memory / reuse mechanisms without forcing you to read source code. We keep a narrative flow while still surfacing the most relevant technical points. If you are migrating from older documentation that mentioned a `Timeseries` class: that name has been fully replaced by `Temporal`.

## 1. Time Frame and Resolution
Each branch corresponds to exactly one calendar year. Hourly resolution is mandatory:

- Normal year: 8760 hours
- Leap year: 8784 hours

All temporals in that branch implicitly share the branch’s time index. This fixed frame eliminates alignment headaches. If a quantity is not time‑dependent, you store it simply as a scalar (annual total) or as a constant per‑hour value (fix) that can later expand to an hourly array once a branch context is known.

## 2. Core Concept: Total + Relative Shape = Series
Every temporal quantity decomposes into two complementary pieces:

$$ Series_t = Total \times Relative_t, \quad \sum_t Relative_t = 1 $$

You may have any subset of these elements initially:

| What you know           | Store                    | What becomes available later             |
| ----------------------- | ------------------------ | ---------------------------------------- |
| Just annual magnitude   | `total`                  | Hourly `series` once shape or fix exists |
| Constant per‑hour value | `fix`                    | Total and series once attached to branch |
| Full hourly data        | `series` or `timeseries` | Total + normalized relative              |
| Shape only (fractions)  | `relative_series`        | Series after setting a total             |

Accessing a missing representation (for example calling `relative_series` when you only set `series`) triggers on‑demand derivation and light caching. This keeps input flexible while avoiding redundant storage and keeps notebooks responsive.

## 3. The `Temporal` Object: Key Attributes
- `total`: Annual sum (Number)
- `series`: Hourly values indexed by a simple `RangeIndex`
- `timeseries`: Hourly values with the calendar `DatetimeIndex` (derived once branch attached or user provided)
- `relative_series`: Hourly fractions (RangeIndex) summing to 1
- `relative_timeseries`: Same fractions, but calendar indexed
- `fix`: Constant per‑hour value (expanded lazily)

Rules of thumb:

| Situation                          | Recommended input         | Why                                      |
| ---------------------------------- | ------------------------- | ---------------------------------------- |
| Have complete hourly profile       | `series` or `timeseries`  | Automatic derivation of total + relative |
| Know only annual sum               | `total`                   | Delay expansion; stay minimal            |
| Constant per‑hour behaviour        | scalar assignment / `fix` | Lowest overhead; expands later           |
| Shape known; magnitude TBD         | `relative_series`         | Plug in scenarios via `total` quickly    |
| Multiple related flows share shape | master + `create_client`  | Memory saving and synchronized updates   |

## 4. Reuse via Master–Client Relationships
Many flows share the same diurnal/seasonal rhythm. Instead of cloning large arrays, one `Temporal` can act as a master holding the shape; clients reference that shape and retain only their own totals. Clients compute their hourly series on demand as `client.total * master.relative_series`. Updating the master’s shape instantly updates all clients, enabling fast scenario iteration.

Creating a client (illustrative pattern):
```python
from odeon.model import Temporal
import pandas as pd, numpy as np

# shape baseline
shape = pd.Series(np.random.rand(8760)); shape /= shape.sum()
heat = Temporal(relative_series=shape, total=12000)
emissions = heat.create_client(total=2500)  # shares shape, different annual magnitude
```

Detaching or moving clients is reversible; no long‑lived coupling is forced. Internally each client simply keeps a reference to the master and its own `total`. It inherits shape automatically; you do not duplicate arrays unless you explicitly break the relationship.

### When NOT to use a client
If two profiles are *almost* but not exactly the same (e.g. one has an efficiency dip in summer) keep them independent; forcing a client relationship would hide genuine structural difference. A good heuristic: if you would feel comfortable plotting one over the other and describing the difference purely with a scale factor, they qualify for master/client.

## 5. Constant Values vs. Derived Series
Setting `fix=5` (or assigning a scalar through an object attribute that expects a temporal) does not immediately materialize an 8760‑length array. Only once you request something that needs that expansion (e.g. the hourly series) or the object joins a branch will Odeon derive the implied constant profile. This lazy expansion reduces memory use in early modeling phases.

## 6. Swap Modes and Memory Management
Large studies can involve thousands of temporals. Odeon supports three swap modes:

| Mode      | Behaviour                                                     |
| --------- | ------------------------------------------------------------- |
| `loaded`  | Keep series resident in memory                                |
| `lazy`    | Load on first access, then keep until explicitly swapped      |
| `swapped` | Remove from memory; on access load transiently (not retained) |

Switching a temporal’s `swap_mode` may write data to a branch‑scoped HDF5 file (through the project’s file adapter) or reload it. A `TemporalManager` can:
- Apply one mode to all temporals (`set_swap_mode`) 
- Reset policies based on configured type-to-mode mappings
- Adapt modes based on access counters (`swap_or_load_temporals`) to elevate hot series and demote cold ones.

Cleaning disk artifacts is explicit: after loading things back you may call `project.file_adapter.clean()` to shrink HDF storage. Loaded data is *not* automatically purged on purpose—this avoids accidental data loss if you toggle swap modes during interactive work.

### Access counters
Each temporal counts how often its series is accessed. `TemporalManager.swap_or_load_temporals()` uses thresholds to promote frequently accessed series to `loaded`, demote rarely used series to `swapped`, and keep ambiguous ones `lazy`. This adaptive pattern works well in iterative calibration loops: the few “hot” profiles stay resident while the tail of rarely touched data shifts to disk.

### Practical memory pattern
1. Start everything as `lazy` (default or manager‑applied).
2. Run a typical analysis path once.
3. Invoke `swap_or_load_temporals()` with modest thresholds (e.g. 1 / 3).
4. Inspect memory usage. Repeat if working set changes.

This is often superior to hand‑picking swap modes for dozens of classes.

### Cleaning strategy
Call `clean()` only after a period of stability (e.g. before persisting a project archive). During active iterative modeling, leaving stale on‑disk data is harmless and saves re‑write churn.

## 7. Arithmetic and Combination
`Temporal` objects support arithmetic with scalars and with other `Temporal` objects (provided they are aligned to the same branch/year). Internally, operations prefer to keep a relative + total representation where sensible to avoid unnecessary full materialization. Some examples:

```python
from odeon.model import Temporal
import pandas as pd, numpy as np

shape = pd.Series(np.random.rand(8760)); shape /= shape.sum()
load = Temporal(relative_series=shape, total=5000)
pv = Temporal(relative_series=shape, total=1200)  # same shape for illustration

net = load - pv  # subtraction produces a new Temporal
scaled = load * 1.1  # scalar scaling

print(net.total)        # approximate difference of totals
print(round(scaled.total, 2))
```

If shape alignment is impossible (different lengths, different years), operations should be avoided or preceded by explicit transformation. Mixing leap and non‑leap year branches is intentionally not auto‑aligned.

## 8. Error Prevention & Common Pitfalls
| Pitfall                                     | Symptom                           | Underlying cause                            | Resolution                                             |
| ------------------------------------------- | --------------------------------- | ------------------------------------------- | ------------------------------------------------------ |
| Mis‑sized series                            | Length mismatch error             | Provided raw array not matching year length | Reindex or truncate before constructing `Temporal`     |
| Unexpected memory growth                    | Many profiles kept `loaded`       | Never swapping or cleaning                  | Apply manager, use `lazy` or `swap` modes              |
| Surprising series values after shape update | Clients all change simultaneously | Master shape modified                       | Detach clients first if they need independence         |
| Zero or NaN relative fractions              | Division by zero in normalization | All zero input series                       | Provide a valid shape or fall back to constant profile |
| Arithmetic fails                            | Type error                        | Different branches or uninitialized totals  | Ensure same branch; set required totals                |

## 9. Typical Workflow (Expanded)
1. Sketch system structure (objects, expected temporal attributes).
2. Provide minimal placeholders (`total` or `fix`) so downstream code can run early.
3. Introduce measured or synthetic shapes incrementally: start with generic standard loads, refine with real data later.
4. Consolidate recurring shapes into master/client sets to cut memory and keep scenario edits centralized.
5. Run baseline analyses; let access counters accumulate.
6. Apply adaptive swapping to stabilize memory usage.
7. Iterate: adjust totals for scenario scaling, swap shapes in/out to test sensitivity.
8. Clean disk only when freezing or exporting the project.

## 10. Extended Example (Narrative)
Below we build up a small story: a building with electric demand and emissions tied to that demand, plus a retrofit scenario.

```python
import numpy as np, pandas as pd
from odeon.model import Temporal

hours = 8760
# Base daily pattern: higher daytime consumption
day = (np.sin(np.linspace(0, 2*np.pi, 24, endpoint=False)) + 1.3).clip(min=0.2)
shape = np.tile(day, hours // 24)
relative = pd.Series(shape / shape.sum())

electric_demand = Temporal(relative_series=relative, total=18000)  # kWh/a
emissions = electric_demand.create_client(total=3500)               # kg CO2/a, same shape

# Retrofit: 12% reduction in annual demand (shape unchanged initially)
retrofit_demand = electric_demand.copy()
retrofit_demand.total *= 0.88

print("Base total:", electric_demand.total)
print("Retrofit total:", retrofit_demand.total)
print("Shared first 3 hours base vs retrofit:")
print(electric_demand.series[:3].values, retrofit_demand.series[:3].values)

# Later we discover improved night-time efficiency flattening the shape
flatten_factor = np.linspace(1.0, 0.9, hours)  # small seasonal taper
new_shape_raw = relative.values * flatten_factor
new_shape = pd.Series(new_shape_raw / new_shape_raw.sum())
retrofit_demand.relative_series = new_shape  # magnitude stays; distribution changes
```

This script walks through: starting with a reusable shape, creating a dependent emission profile, scaling to a scenario, then modifying only the distribution for a refinement stage—all with minimal boilerplate.

## 11. Performance Considerations
1. Favor relative + total when exploring scaling scenarios; defers heavy arithmetic on large arrays.
2. Use master/client to keep the proportion of fully materialized arrays small.
3. When running bulk operations (e.g. summing or comparing many temporals), consider pre‑loading frequently accessed ones (manager `set_swap_mode("loaded")`) to avoid repeated disk I/O.
4. After an exploratory notebook session, a single `swap_or_load_temporals()` pass often cuts resident memory dramatically with negligible impact on subsequent responsiveness.

## 12. FAQ Style Clarifications
**Is interpolation supported?** No—resolution is fixed to one hour. Supply already aggregated hourly data or preprocess externally.

**Can I mix leap and non‑leap year series?** Not within the same branch. Create distinct branches; do not pad or clip automatically.

**What happens if I set both `series` and `relative_series`?** The implementation prefers consistency; typically you supply one source of truth and let the other be derived. Supplying contradictory combinations should be avoided.

**Do clients store copies on disk when swapped?** Only the master’s shape is persisted; clients persist minimal metadata and their totals.

**Can I serialize a project and reload temporals later?** Yes, as long as the `FileAdapter` directory (or exported HDF files) moves alongside the saved project state.

## 13. Key Takeaways (Revisited)
The `Temporal` abstraction isolates magnitude from distribution, encourages structural reuse, and offers adaptive memory control. Modeling becomes a process of gradually enriching sparse placeholders into fully shaped, efficiently stored temporal datasets. Keep the loop: define → attach → refine shape → reuse → manage memory → iterate.

If you internalize that loop, the remaining API surface will feel natural when you encounter it.

## 7. Typical Workflow
1. Define objects, set minimal temporal info (maybe just totals or fixes).
2. Attach to a branch → implicit year index; constant and relative forms can expand.
3. Introduce shapes (relative series) or master–client links to reduce duplication.
4. Perform arithmetic, scaling, scenario branching.
5. Tune memory footprint with swap modes; optionally automate with `TemporalManager`.
6. Clean file storage when stable.

## 14. Compact Example (Quick Reference)
```python
import numpy as np, pandas as pd
from odeon.model import Temporal

# Start with total only
demand = Temporal(total=10000)

# Later: add an hourly shape
shape = pd.Series(np.random.rand(8760)); shape /= shape.sum()
demand.relative_series = shape   # series becomes available

# Reuse shape for another quantity
emissions = demand.create_client(total=1900)

print(demand.total, round(demand.series[:3].sum(), 2))
print(emissions.total, emissions.series[:3])
```

## 15. Concise Recap
- One year, hourly resolution—always aligned.
- Separation of magnitude (total) and distribution (relative shape) encourages reuse.
- Master–client pattern prevents redundant arrays.
- Swap modes and a manager exist so you can scale without micromanaging memory.
- Start lean (total or fix) and add detail only when analysis calls for it.

That combination gives both clarity (simple mental model) and efficiency (no silent duplication of large vectors). The extended sections above provide deeper context whenever you need to reason about scaling, reuse, or performance.