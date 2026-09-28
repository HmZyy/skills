---
name: delog-analyze
description: Use when the user asks to analyze, diagnose, explain, or inspect a flight or log that is open in DeLOG (DeLOG, delog, "the loaded log", "this flight"), asks what went wrong, or asks to plot, compute, annotate, or mark signals in a running DeLOG session. Drives DeLOG through its external Python API (delog-client).
---

# DeLOG log analysis

Analyze the log loaded in a running DeLOG window through the external Python API.
Answer the user's question, or diagnose what went wrong, and leave the evidence on
screen: raw traces, derived signals published back into DeLOG, annotations on the
plots, and markers on the timeline. Every script you write is saved so the analysis
can be rerun.

API reference: `docs/external_python_api.md` in the same DeLOG checkout that holds
`python/delog-client` (see Preflight). Read it, or the client source under
`python/delog-client/src/delog_client`, if you need a call this skill does not show.

## 1. Preflight

Run these checks in order. Stop and tell the user at the first one that fails.

1. `uv --version` works.
2. The analysis venv imports the client:

       ~/Documents/delog-analyses/.venv/bin/python -c "import delog_client, numpy"

   If that fails, bootstrap it:

       uv venv --python '>=3.11' ~/Documents/delog-analyses/.venv
       uv pip install --python ~/Documents/delog-analyses/.venv numpy <client>

   `delog-client` is not on PyPI. Use for `<client>`, in order:
   - a DeLOG checkout or worktree that contains the client: the first match of
     `ls -d ~/projects/hmzyy/DeLOG/python/delog-client ~/projects/hmzyy/DeLOG/.worktrees/*/python/delog-client 2>/dev/null`
     (any directory holding `python/delog-client/pyproject.toml` works);
   - the newest release wheel:
     `gh release download --repo HmZyy/DeLOG --pattern 'delog_client-*.whl' --dir ~/Documents/delog-analyses/wheels --clobber`,
     then the downloaded `.whl` path;
   - otherwise ask the user where to get it.
3. List instances:

       ~/Documents/delog-analyses/.venv/bin/python -c "from delog_client import DeLOG; [print(i.id, i.label, i.loaded_file) for i in DeLOG.list_instances()]"

   - Nothing printed: DeLOG is not running or external access is off. Tell the
     user to open **Settings -> External API** in DeLOG and press **Enable**, then stop.
   - Several instances: ask the user which one (show id, label, loaded file) and
     pass `--instance ID` to every script.

## 2. Read the catalog

Print the catalog, plus every row of small topics (64 rows or fewer: modes, events,
errors, text messages, mission items). This is exploration, not analysis; it is the
only code you run that is not saved. Everything else goes in the saved script:

    ~/Documents/delog-analyses/.venv/bin/python - <<'EOF'
    from delog_client import DeLOG
    [inst] = DeLOG.list_instances()
    c = DeLOG.connect(inst.id, name="delog-analyze-catalog", takeover=True)
    with c.snapshot() as s:
        for src in s.sources():
            print(f"# source {src.label} ({src.kind}) offset_ns={src.offset_ns}")
            for t in src.topics:
                r = t.time_range_ns
                span = f"{(r.end_ns - r.start_ns) / 1e9:.1f}s" if r else "-"
                fields = ", ".join(f"{f.name}[{f.unit}]" if f.unit else f.name for f in t.fields)
                print(f"{t.name} rows={t.row_count} span={span}: {fields}")
        origin = min(t.time_range_ns.start_ns for src in s.sources() for t in src.topics if t.time_range_ns)
        for src in s.sources():
            for t in src.topics:
                if 0 < t.row_count <= 64:
                    print(f"## {t.path}")
                    for row in t.read().to_pylist():
                        at = (row.pop("__delog_time_ns") - origin) / 1e9
                        row.pop("__source_time_ns")
                        print(f"  t={at:.2f}s {row}")
    c.close()
    EOF

For several instances replace `[inst] = ...` with the chosen id.

From the topic names identify the firmware:
- PX4 ULog: snake_case topics like `vehicle_status`, `sensor_combined`, `vehicle_attitude`.
- ArduPilot dataflash (`.bin`): upper-case messages like `ATT`, `VIBE`, `BAT`, `MODE`.
- MAVLink telemetry (`.tlog`): upper-case MAVLink names like `HEARTBEAT`, `ATTITUDE`, `SYS_STATUS`.

Only use topic and field names that exist in this catalog. The playbook names are
typical, not guaranteed; firmware versions rename fields. Multi-instance topics
(two IMUs, two GPS) appear with an instance; pass `instance=` to `snapshot.topic`.
If a name matches several sources, pass `source=` (the label printed above).

## 3. Frame the question

- A specific question ("vibration during takeoff", "why did altitude drop at 3 min"):
  map it to concrete topics and fields and a time window. Answer that question; do
  not run the whole playbook.
- A vague question ("what went wrong", "is this flight ok"): run the playbook below
  in order. Stop digging once one primary cause is supported by evidence, then
  report contributing factors you already saw. Do not keep adding plots past the
  limits.

## 4. Write the script

Path: `~/Documents/delog-analyses/<YYYY-MM-DD>/<log_stem>_<question_slug>.py`

- `<YYYY-MM-DD>`: today's date (`date +%F`).
- `<log_stem>`: basename of `instance.loaded_file` without extension; `session` when
  `loaded_file` is `None`.
- `<question_slug>`: a few words summarizing the question.
- Slugify both parts: lowercase, every run of characters outside `[a-z0-9]` becomes
  `_`, strip leading and trailing `_`; cap the slug at 40 characters.
  Example: `2026-07-28 14-45-21.bin`, "why did it crash?" ->
  `2026-07-28_14_45_21_why_did_it_crash.py`.
- If the file exists for the same question, edit it in place and rerun. If it exists
  for a different question with the same slug, add `_2`, `_3`, ...
- Create the date folder with `mkdir -p`.

Start from the skeleton. Replace the `analyze` body with the real analysis; keep the
helpers and `main` as they are. Rules for the script:

- Module docstring: the question, the log file, the date. No code comments.
- `OWNER = "delog-analyze-<question_slug>"` using the slug exactly as it appears in
  the file name, including any `_2`/`_3` suffix, so two questions never share an
  owner (a shared owner makes one script's `remove_owned()` wipe the other's
  results). `TITLE` = the question in a few words.
- `remove_owned()` runs first so a rerun replaces the previous results.
- Window: `open_window(client)` returns the main DeLOG window when it holds exactly
  one plot and that plot is empty; otherwise it opens a new window titled `TITLE`.
  Never put plots in a main window that already shows something.
- Plots: call `next_plot(client, window)` for each plot, in display order. The first
  call reuses the window's empty plot; later calls split the previous plot, which
  keeps every plot the same height. Never call `workspace.add_plot()` directly: it
  splits the whole layout, so each new plot takes half the window and the earlier
  ones shrink to 1/4, 1/8, 1/16. `workspace.equalize()` is not available in safe
  mode. At most 6 plots, one concern per plot.
- Add every trace with `trace(plot, field, mode=...)`, never
  `plot.traces.add` directly: DeLOG can briefly report a just-published field as
  `stale_handle`, and `trace` retries for up to 3 s. It also picks the trace color
  (see Colors).
- Raw evidence: trace snapshot fields directly (`topic.field(name)`), no upload. Add
  them while the snapshot is open.
- Derived signals: compute with numpy, publish with `publish(client, name, t,
  columns, units=..., descriptions=...)` (it decimates and replaces), trace
  `derived.field(name)`. Units map only fields that have a unit.
  Topic names start with `da_` and are lowercase snake_case (`da_vibration_magnitude`),
  so they never collide with a log topic such as `battery_status`.
- Markers (`mark(client, time_ns, label, note=..., color=RED)`) for discrete
  events on the timeline: failsafe, mode change, crash, onset of a problem. Put the
  evidence in `note` (values, thresholds). At most 20; keep the most important.
- Annotations on the plot where the evidence is, always through `annotate`:
  - `annotate(plot, "hline", y, label=...)` for a threshold;
  - `annotate(plot, "rect", (t0, y0), (t1, y1), label=..., fill_opacity=0.15)` over a problem interval;
  - `annotate(plot, "text", time_ns=t, value=y, text=...)` at a peak or exceedance.
  Every `value`/`y` must be finite: wrap with `finite(...)`.
- Every time passed to DeLOG (`markers.add`, `add_text(time_ns=...)`, the first
  element of `add_rect`/`add_segment` points) must be a Python `int`: wrap numpy
  values with `ns(...)`. A numpy integer is rejected with `invalid_input`.
- Look topics up with `source=log_source(snapshot, args.source)`: it picks the one
  loaded log when there is exactly one, so derived topics from other runs cannot
  make a name ambiguous.
- Read only the fields you need. For long logs prefer
  `topic.iter_batches(fields=[...], start_ns=..., end_ns=...)`.
- Times in the report are seconds from log start: `(t - origin_ns) / 1e9` with
  `origin_ns = log_origin_ns(snapshot)`.
- Labels, notes, and annotation text: plain ASCII, short, no em dashes, no emoji.
- `analyze` returns the findings lines; the first line is the verdict.
- Colors: within one plot every trace and every annotation has its own color, and
  none matches or resembles a marker color. Other plots may reuse the same colors.
  - Markers draw a line across every plot, so `RED` (failure) and `BLUE` (neutral
    event) are for markers only; `mark` rejects any other color. Markers may share
    those two colors with each other.
  - Traces and annotations get colors from `PLOT_COLORS` through `pick`, which
    `trace` and `annotate` call for you. Pass `color=` only as a preference: `AMBER`
    for a warning threshold or interval, `GREEN` for "checked, fine". A color
    already taken on that plot, or a marker color, falls back to the next free one.
  - Never pass a hex literal or a DeLOG default color: the defaults resemble
    `RED`, `AMBER`, `BLUE` and `GREEN`. Every color is one of the constants in the
    skeleton, chosen so no two look alike (CIE76 distance 35 or more).
  - `PLOT_COLORS` has 7 entries, so a plot holds at most 7 traces and annotations
    together. `pick` stops the script when a plot runs out; split the concern
    across two plots.
  - Two thresholds on one plot (warn and bad) need two colors: pass `AMBER` for
    warn and let the bad one take the next free color; say which is which in the
    labels.

<!-- skeleton -->
```python
"""Question: <the user's question>

Log: <instance.loaded_file>
Date: <YYYY-MM-DD>
"""

from __future__ import annotations

import argparse
import sys
import time

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc

from delog_client import AmbiguousError, Client, DeLOG, DeLOGError, Instance, Plot, StaleHandleError, Trace, Window

OWNER = "delog-analyze-question_slug"
TITLE = "Question title"
RED = "#e5484d"
BLUE = "#3b82f6"
AMBER = "#f5a524"
GREEN = "#30a46c"
CYAN = "#22d3ee"
MAGENTA = "#e879f9"
LIME = "#a3e635"
GRAY = "#d4d4d8"
PURPLE = "#9333ea"
MARKER_COLORS = (RED, BLUE)
PLOT_COLORS = (CYAN, MAGENTA, LIME, GRAY, PURPLE, AMBER, GREEN)
PLOTS: list[Plot] = []
USED_COLORS: dict[str, set[str]] = {}


def select_instance(instance_id: str | None) -> Instance:
    instances = DeLOG.list_instances()
    if instance_id is not None:
        for instance in instances:
            if instance.id == instance_id:
                return instance
        raise SystemExit(f"no running DeLOG instance has id {instance_id!r}")
    if len(instances) != 1:
        listing = ", ".join(f"{i.id} ({i.label}, {i.loaded_file})" for i in instances)
        raise SystemExit(f"pass --instance ID; running instances: {listing or 'none'}")
    return instances[0]


def values(table: pa.Table, name: str) -> np.ndarray:
    column = pc.cast(table.column(name), pa.float64())
    return pc.fill_null(column, float("nan")).to_numpy()


def times(table: pa.Table) -> np.ndarray:
    return table.column("__delog_time_ns").to_numpy().astype(np.int64)


def ns(x) -> int:
    return int(x)


def finite(x: float, fallback: float = 0.0) -> float:
    x = float(x)
    return x if np.isfinite(x) else fallback


def decimate(t: np.ndarray, *series: np.ndarray, limit: int = 1_000_000) -> tuple[np.ndarray, ...]:
    if len(t) <= limit:
        return (t, *series)
    index = np.unique(np.linspace(0, len(t) - 1, limit).astype(np.int64))
    return (t[index], *(s[index] for s in series))


def log_origin_ns(snapshot) -> int:
    starts = [
        topic.time_range_ns.start_ns
        for source in snapshot.sources()
        if source.kind in ("file", "live")
        for topic in source.topics
        if topic.time_range_ns is not None
    ]
    return min(starts) if starts else 0


def log_source(snapshot, requested: str | None) -> str | None:
    if requested is not None:
        return requested
    labels = [source.label for source in snapshot.sources() if source.kind in ("file", "live")]
    return labels[0] if len(labels) == 1 else None


def seconds(time_ns: int, origin_ns: int) -> float:
    return (int(time_ns) - origin_ns) / 1e9


def used_plots(client: Client) -> set[str]:
    state = client.state()
    return {item.plot.handle for item in state.traces + state.annotations}


def open_window(client: Client) -> Window:
    main = next((w for w in client.state().windows if w.owner is None), None)
    if main is not None:
        plots = main.workspace.plots()
        if len(plots) == 1 and plots[0].handle not in used_plots(client):
            return main
    return client.windows.open(TITLE)


def next_plot(client: Client, window: Window) -> Plot:
    if PLOTS:
        plot = PLOTS[-1].split("vertical")
    else:
        used = used_plots(client)
        empty = [p for p in window.workspace.plots() if p.handle not in used]
        plot = empty[0] if empty else window.workspace.add_plot()
    PLOTS.append(plot)
    return plot


def pick(plot: Plot, preferred: str | None = None) -> str:
    used = USED_COLORS.setdefault(plot.handle, set())
    for color in (preferred, *PLOT_COLORS):
        if color in PLOT_COLORS and color not in used:
            used.add(color)
            return color
    raise SystemExit(f"plot {plot.handle} has no free color; move some traces or annotations to another plot")


def trace(plot: Plot, field, color: str | None = None, **style) -> Trace:
    style["color"] = pick(plot, color)
    deadline = time.monotonic() + 3.0
    while True:
        try:
            return plot.traces.add(field, **style)
        except StaleHandleError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.05)


def annotate(plot: Plot, kind: str, *args, color: str | None = None, **style):
    return getattr(plot.annotations, f"add_{kind}")(*args, color=pick(plot, color), **style)


def mark(client: Client, time_ns: int, label: str, note: str | None = None, color: str = BLUE):
    if color not in MARKER_COLORS:
        raise ValueError(f"marker color must be RED or BLUE, got {color!r}")
    return client.markers.add(ns(time_ns), label, note=note, color=color)


def publish(client: Client, name: str, t: np.ndarray, columns: dict[str, np.ndarray], units: dict[str, str], descriptions: dict[str, str]):
    names = list(columns)
    reduced = decimate(t, *(columns[n] for n in names))
    table = pa.table(
        {"__delog_time_ns": pa.array(reduced[0], pa.int64())}
        | {n: pa.array(reduced[i + 1], pa.float64()) for i, n in enumerate(names)}
    )
    return client.publish_topic(name, table, units=units, descriptions=descriptions, replace=True)


def analyze(client: Client, args: argparse.Namespace) -> list[str]:
    client.remove_owned()
    window = open_window(client)
    findings: list[str] = []
    with client.snapshot() as snapshot:
        origin_ns = log_origin_ns(snapshot)
        source = log_source(snapshot, args.source)
        topic = snapshot.topic("TOPIC", source=source)
        table = topic.read(fields=["FIELD"])
        t = times(table)
        y = values(table, "FIELD")
        evidence = next_plot(client, window)
        trace(evidence, topic.field("FIELD"))
    limit = 1.0
    derived = publish(
        client,
        "da_field_excess",
        t,
        {"excess": np.abs(y) - limit},
        units={},
        descriptions={"excess": "abs(FIELD) minus limit"},
    )
    plot = next_plot(client, window)
    trace(plot, derived.field("excess"))
    annotate(plot, "hline", 0.0, label=f"limit {limit}", color=AMBER)
    over = np.flatnonzero(np.abs(y) > limit)
    if len(over):
        first = ns(t[over[0]])
        peak = int(np.nanargmax(np.abs(y)))
        mark(client, first, "FIELD over limit", note=f"abs(FIELD) > {limit}", color=RED)
        annotate(plot, "text", time_ns=ns(t[peak]), value=finite(abs(y[peak]) - limit), text=f"peak {finite(y[peak]):.2f}")
        findings.append(f"FIELD exceeds {limit} from t={seconds(first, origin_ns):.1f}s")
    else:
        findings.append(f"FIELD stays within {limit}")
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=TITLE)
    parser.add_argument("--instance", help="DeLOG instance ID; optional when exactly one runs")
    parser.add_argument("--source", help="source label when a topic name is ambiguous")
    args = parser.parse_args(argv)
    instance = select_instance(args.instance)
    client = DeLOG.connect(instance.id, name=OWNER, takeover=True)
    try:
        findings = analyze(client, args)
    except AmbiguousError as error:
        print(f"ambiguous: {error.message}; candidates: {', '.join(getattr(error, 'candidates', []))}", file=sys.stderr)
        return 1
    except DeLOGError as error:
        print(f"{error.code}: {error.message}", file=sys.stderr)
        return 1
    finally:
        client.close()
    print("FINDINGS")
    for line in findings:
        print(f"- {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

## 5. Run and iterate

    ~/Documents/delog-analyses/.venv/bin/python ~/Documents/delog-analyses/<date>/<file>.py [--instance ID]

- Read the `FINDINGS` block. If the numbers do not support a conclusion, or a
  threshold was wrong, edit the same file and rerun; the rerun replaces what the
  previous run published.
- `not_found`: the field name is wrong for this firmware; look it up in the catalog.
- `ambiguous`: pass `--source` with one of the printed candidates' source labels, or
  set `instance=` in the script.
- `forbidden`: the script touched something it does not own (only change resources
  the script created), or a newer run of the same owner took over this connection.
- `unavailable` with a full queue: slow down; do not wrap markers, annotations,
  plots, or traces in `client.batch()`, which only accepts commands that return
  nothing (playback, equalize) and rejects the rest with `invalid_input`.

## 6. Report

Reply with:

1. **Verdict**: one or two sentences answering the question or naming the primary cause.
2. **Evidence**: bullets with times in seconds from log start and the values that
   support the verdict; name the markers the user can jump to.
3. **In DeLOG**: the window title, what each plot shows, published topics.
4. **Script**: the saved path and the command to rerun it.

Say what you could not determine and why (missing topic, field absent in this log).

## Playbook

Triage order for vague questions. Field names are typical: confirm each in the
catalog. Arrays appear as indexed fields (for example `accelerometer_m_s2[2]`).
Text messages (`MSG`, `STATUSTEXT`) may be string fields; print them from the
script and put the relevant ones in marker notes.

| # | Check | PX4 (ULog) | ArduPilot (.bin) | MAVLink (.tlog) | Derived signal | Heuristic | Mark |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Log end, crash, disarm | `vehicle_status.arming_state`, `sensor_combined.accelerometer_m_s2[0..2]`, `vehicle_land_detected` | `ARM`, `EV`, `ERR`, `IMU.AccX/Y/Z` | `HEARTBEAT.base_mode`, `SCALED_IMU` | accel magnitude | magnitude > 3 g (~30 m/s/s) near the end while armed, or log ends armed and airborne | marker at impact or last sample, red |
| 2 | Mode changes, failsafes | `vehicle_status.nav_state`, `failsafe_flags`, `vehicle_status.failsafe` | `MODE.Mode`, `MODE.Rsn`, `ERR.Subsys/ECode`, `EV.Id`, `MSG` | `HEARTBEAT.custom_mode`, `STATUSTEXT` | none | every mode change; failsafe or ERR entries | marker per change, blue; failsafe red |
| 3 | RC loss | `input_rc.rc_lost`, `input_rc.rssi` | `RCIN.C1..C4`, `ERR` subsys 2 or 5 | `RC_CHANNELS`, `RC_CHANNELS_RAW` | none | rc_lost true, RCIN frozen or dropping to failsafe PWM (< 975) | rect over loss interval |
| 4 | Battery sag, brownout | `battery_status.voltage_v`, `current_a`, `remaining` (0..1), `system_power.voltage5v_v` | `BAT.Volt`, `BAT.Curr`, `BAT.RemPct`, `BAT.Res` (internal resistance, ohm), `POWR.Vcc` | `SYS_STATUS.voltage_battery` (mV), `current_battery` (cA, 10 mA units; -1 = unknown) | sag = resting voltage (first 5 s median) minus voltage; per cell = voltage / cells | per cell < 3.3 V LiPo under load; sag > 15 %; Vcc < 4.5 V or swing > 0.3 V | hline at cell limit; marker at minimum |
| 5 | Vibration, clipping | `vehicle_imu_status.accel_vibration_metric`, `accel_clipping[0..2]`, `sensor_accel` | `VIBE.VibeX/Y/Z`, `VIBE.Clip` (or `Clip0..2`) | `VIBRATION.vibration_x/y/z`, `clipping_0..2` | vibe magnitude; clip count per second | VIBE > 30 m/s/s warn, > 60 bad; any increase in clip count | hline at 30 and 60; rect over high periods |
| 6 | EKF health | `estimator_status.vel_test_ratio`, `pos_test_ratio`, `hgt_test_ratio`, `mag_test_ratio`, `estimator_innovations` | `XKF4.SV/SP/SH/SM` (older `NKF4`), `XKF3` innovations | `EKF_STATUS_REPORT.velocity_variance` etc. | max test ratio | > 0.5 warn, > 1.0 innovation rejected | hline at 1.0; marker at first rejection |
| 7 | GPS | `vehicle_gps_position.satellites_used`, `hdop`, `eph` (horizontal accuracy in m, not HDOP), `fix_type`, `jamming_indicator` | `GPS.NSats`, `GPS.HDop`, `GPS.Status`, `GPA.HAcc` | `GPS_RAW_INT.satellites_visible`, `eph` (HDOP x 100), `fix_type` | none | sats < 6, HDOP > 2 (tlog eph > 200), PX4 eph > 5 m, fix drop below 3D | rect over bad periods |
| 8 | Attitude tracking | `vehicle_attitude_setpoint` vs `vehicle_attitude` (quaternions), `vehicle_rates_setpoint` vs `vehicle_angular_velocity` | `ATT.DesRoll/Roll`, `DesPitch/Pitch`, `DesYaw/Yaw`; `RATE.RDes/R` | `ATTITUDE` only (no setpoint) | error = setpoint minus actual (align by interpolating onto one time base) | roll or pitch error > 10 deg for > 1 s | rect over the interval |
| 9 | Motor saturation, imbalance | `actuator_outputs.output[0..7]`, `actuator_motors.control[..]` | `RCOU.C1..C8`, `CTUN.ThO` | `SERVO_OUTPUT_RAW.servo1_raw..` | max output; spread = max minus min across motors; mean per motor | any motor at max (>= 95 % of range) for > 1 s; one motor mean > 10 % above the others in hover | hline at max; marker at saturation onset |
| 10 | Compass interference | `vehicle_magnetometer.magnetometer_ga[0..2]`, `battery_status.current_a` | `MAG.MagX/Y/Z`, `BAT.Curr` | `SCALED_IMU.xmag..` | field magnitude; correlation with current | magnitude changes > 30 % with throttle or current | text at worst point |
| 11 | Logging gaps, CPU | any high-rate topic timestamps, `cpuload.load` | `IMU` or `ATT` timestamps, `PM.Load`, `PM.NLon` | message timestamps | gap_ms between samples | gap > 5 x median period, or > 100 ms | marker per gap (first 20), text with gap ms |

Align two signals sampled at different rates before subtracting:
`np.interp(t_actual, t_setpoint, setpoint)`. Wrap angle errors into [-180, 180]
before thresholding (`(err + 180) % 360 - 180`): ArduPilot `ATT.Yaw`/`DesYaw` run
0..360 and an unwrapped yaw error jumps by 360 at north. PX4 quaternions are
`q[0..3]` = w, x, y, z. Convert quaternions to Euler with numpy (`roll = atan2(2(wx + yz), 1 - 2(x^2 + y^2))`, `pitch = asin(clip(2(wy - zx), -1, 1))`,
`yaw = atan2(2(wz + xy), 1 - 2(y^2 + z^2))`) and report degrees.
