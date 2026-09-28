from __future__ import annotations

import re
import sys
import types
from pathlib import Path

BANNED = {"\u2014": "em dash", "\u2013": "en dash"}
SKELETON = re.compile(r"<!-- skeleton -->\s*```python\n(.*?)```", re.S)


def frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}
    fields = {}
    for line in text[4:end].splitlines():
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip()
    return fields


def check_helpers(module: types.ModuleType) -> list[str]:
    try:
        import numpy as np
        import pyarrow as pa
    except ImportError:
        return ["numpy and pyarrow are needed to exercise the skeleton helpers"]
    problems = []
    table = pa.table({"x": pa.array([1, None, 3], pa.int32())})
    got = module.values(table, "x")
    if got.dtype != np.float64 or not np.isnan(got[1]) or got[2] != 3.0:
        problems.append(f"values() null fill wrong: {got!r}")
    if module.finite(float("nan"), 7.0) != 7.0 or module.finite(float("inf")) != 0.0:
        problems.append("finite() does not replace non-finite values")
    if module.finite(2.5) != 2.5:
        problems.append("finite() changed a finite value")
    t = np.arange(10, dtype=np.int64)
    small_t, small_y = module.decimate(t, t.astype(float), limit=4)
    if len(small_t) > 4 or small_t[0] != 0 or small_t[-1] != 9 or len(small_y) != len(small_t):
        problems.append(f"decimate() wrong: {small_t!r}")
    same_t, _ = module.decimate(t, t.astype(float), limit=100)
    if len(same_t) != 10:
        problems.append("decimate() dropped rows under the limit")
    got_ns = module.ns(np.int64(5))
    if type(got_ns) is not int or got_ns != 5:
        problems.append(f"ns() must return a Python int: {got_ns!r}")
    one = types.SimpleNamespace(sources=lambda: (
        types.SimpleNamespace(label="flight", kind="file"),
        types.SimpleNamespace(label="owner/da_x", kind="derived"),
    ))
    two = types.SimpleNamespace(sources=lambda: (
        types.SimpleNamespace(label="a", kind="file"),
        types.SimpleNamespace(label="b", kind="file"),
    ))
    if module.log_source(one, None) != "flight":
        problems.append("log_source() must pick the only file or live source")
    if module.log_source(two, None) is not None:
        problems.append("log_source() must return None when several logs are loaded")
    if module.log_source(two, "b") != "b":
        problems.append("log_source() must keep an explicit source")
    problems.extend(check_colors(module))
    return problems


def lab(color: str) -> tuple[float, float, float]:
    rgb = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
    fx, fy, fz = (t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116 for t in (x, y, z))
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def check_colors(module: types.ModuleType) -> list[str]:
    problems = []
    markers, plots = module.MARKER_COLORS, module.PLOT_COLORS
    if set(markers) & set(plots):
        problems.append("a marker color is also a plot color")
    palette = [*markers, *plots]
    for i, a in enumerate(palette):
        for b in palette[i + 1:]:
            distance = sum((p - q) ** 2 for p, q in zip(lab(a), lab(b))) ** 0.5
            if distance < 35:
                problems.append(f"colors {a} and {b} look alike (distance {distance:.1f})")
    module.USED_COLORS.clear()
    plot = types.SimpleNamespace(handle="p1")
    other = types.SimpleNamespace(handle="p2")
    picked = [module.pick(plot, module.AMBER), module.pick(plot, module.AMBER), module.pick(plot, module.RED)]
    if picked[0] != module.AMBER or len(set(picked)) != 3 or set(picked) & set(markers):
        problems.append(f"pick() reused a color or gave a marker color: {picked!r}")
    if module.pick(other, module.AMBER) != module.AMBER:
        problems.append("pick() must let another plot reuse a color")
    for _ in range(len(plots) - 3):
        module.pick(plot)
    try:
        module.pick(plot)
        problems.append("pick() must stop when a plot has no free color")
    except SystemExit:
        pass
    module.USED_COLORS.clear()
    try:
        module.mark(None, 0, "x", color=module.AMBER)
        problems.append("mark() must reject a non-marker color")
    except ValueError:
        pass
    return problems


def check(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    problems = []
    meta = frontmatter(text)
    if meta.get("name") != path.parent.name:
        problems.append(f"frontmatter name must be {path.parent.name!r}")
    if len(meta.get("description", "")) < 40:
        problems.append("frontmatter description missing or too short")
    for number, line in enumerate(text.splitlines(), 1):
        for char, label in BANNED.items():
            if char in line:
                problems.append(f"line {number}: {label}")
        if any(ord(c) >= 0x2190 for c in line):
            problems.append(f"line {number}: glyph or symbol character")
    match = SKELETON.search(text)
    if match is None:
        problems.append("no <!-- skeleton --> python block")
        return problems
    source = match.group(1)
    try:
        code = compile(source, "skeleton.py", "exec")
    except SyntaxError as error:
        problems.append(f"skeleton does not compile: {error}")
        return problems
    if any(line.lstrip().startswith("#") for line in source.splitlines()):
        problems.append("skeleton has code comments")
    module = types.ModuleType("skeleton")
    try:
        exec(code, module.__dict__)
    except ImportError as error:
        problems.append(f"skeleton import failed: {error}")
        return problems
    problems.extend(check_helpers(module))
    return problems


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: check_skill.py SKILL.md", file=sys.stderr)
        return 2
    problems = check(Path(argv[1]))
    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
