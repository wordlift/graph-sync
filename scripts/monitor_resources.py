#!/usr/bin/env python3
"""
Estimate optimal worai pool sizes based on system resources and profile configuration.

Memory model varies by ingest_loader:

  playwright (default):
    Total ≈ BASE_OVERHEAD + concurrency × PLAYWRIGHT_MIB
          + pp_pool × POSTPROCESSOR_MIB + shacl_pool × SHACL_MIB
          + mapping_pool × MAPPING_MIB
    Verification: 300 + 6×450 + 3×100 + 3×75 + 2×50 = 3625 MiB (~3.5 GiB ✓)

  simple (HTTP-only, no browser):
    Same formula but concurrency × SIMPLE_MIB instead — much lighter per slot.

Usage:
    uv run scripts/estimate_pools.py
    uv run scripts/estimate_pools.py --profile es
    uv run scripts/estimate_pools.py --memory-gib 16 --cpu 8
    uv run scripts/estimate_pools.py estimate --profile es
    uv run scripts/estimate_pools.py measure --profile es --samples 5
    uv run scripts/estimate_pools.py monitor --watch "worai graph sync"
"""

import argparse
from dataclasses import dataclass
import json
import math
import os
import platform
import re
import statistics
import subprocess
import sys
import textwrap
import time
import tomllib
from pathlib import Path

# Memory estimates per worker (MiB) — calibrated from observed runs
PLAYWRIGHT_MIB = 450  # Playwright browser instance (dominant consumer)
SIMPLE_MIB = 25  # HTTP-only worker (aiohttp + HTML parse, no browser)
POSTPROCESSOR_MIB = 120  # Persistent postprocessor worker (all 4 classes loaded)
SHACL_MIB = 180  # SHACL validator (RDF graph in memory)
MAPPING_MIB = 150  # Mapping worker (DOM + YARRRML)
BASE_OVERHEAD_MIB = 300  # Process + Python runtime + SDK overhead
POOL_CAP = 8

MEMORY_FRACTION = 1.0  # budget = total_ram × this (as configured)
SAFETY_MARGIN = 0.88  # stay at 88% of budget to leave headroom for spikes

# Inline scripts run inside measurement subprocesses.
# Each reports {'rss_mib': float} on stdout after GC.

# Each persistent postprocessor class runs in its OWN subprocess (one process per class
# per pool slot). Measure a single class at a time to get the real per-process cost.
_MEASURE_PP_SCRIPT = textwrap.dedent("""\
    import gc, json, platform, resource, sys, importlib
    spec = sys.argv[1]  # 'module:ClassName' — one class per subprocess
    mod_path, cls_name = spec.rsplit(':', 1)
    mod = importlib.import_module(mod_path)
    instance = getattr(mod, cls_name)()
    gc.collect()
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if platform.system() != 'Darwin':
        rss *= 1024  # Linux reports KB, Darwin reports bytes
    print(json.dumps({'rss_mib': rss / (1024 * 1024)}))
""")

# Loads SHACL shapes via the same code path as the real worker initialiser.
# argv[1]: JSON {exclude_builtin_shapes: [...] | null}
_MEASURE_SHACL_SCRIPT = textwrap.dedent("""\
    import gc, json, platform, resource, sys
    from wordlift_sdk.validation.shacl import PreparedShaclValidator, resolve_shape_specs
    args = json.loads(sys.argv[1])
    shape_specs = resolve_shape_specs(exclude_builtin_shapes=args.get('exclude_builtin_shapes'))
    validator = PreparedShaclValidator.from_shape_specs(shape_specs)
    gc.collect()
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if platform.system() != 'Darwin':
        rss *= 1024
    print(json.dumps({'rss_mib': rss / (1024 * 1024)}))
""")

# morph_kgc is imported lazily inside the worker on first call; import it here
# to simulate the post-first-use (warm) state that matters for sizing.
_MEASURE_MAPPING_SCRIPT = textwrap.dedent("""\
    import gc, json, platform, resource, sys
    import morph_kgc  # noqa: F401 — simulates warm worker state
    gc.collect()
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if platform.system() != 'Darwin':
        rss *= 1024
    print(json.dumps({'rss_mib': rss / (1024 * 1024)}))
""")


def _run_samples(python: str, script: str, arg: str, samples: int) -> dict:
    """Spawn `samples` subprocesses running `script` with `arg` and return RSS stats."""
    results = []
    for _ in range(samples):
        try:
            out = subprocess.check_output(
                [python, "-c", script, arg],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            results.append(json.loads(out.strip())["rss_mib"])
        except Exception:
            continue
    if not results:
        return {"error": "all samples failed"}
    return {
        "mean_mib": statistics.mean(results),
        "min_mib": min(results),
        "max_mib": max(results),
    }


def measure_mib(python: str, script: str, arg: str, samples: int = 3) -> dict:
    return _run_samples(python, script, arg, samples)


def measure_worker_mib(python: str, class_specs: list[str], samples: int = 3) -> dict:
    """Measure per-subprocess RSS for each class individually, return per-process average."""
    per_class = []
    for spec in class_specs:
        result = measure_mib(python, _MEASURE_PP_SCRIPT, spec, samples)
        per_class.append({"class": spec.rsplit(":", 1)[1], **result})
    valid = [r for r in per_class if "error" not in r]
    if not valid:
        return {"error": "all samples failed"}
    return {
        "mean_mib": statistics.mean(r["mean_mib"] for r in valid),
        "min_mib": min(r["min_mib"] for r in valid),
        "max_mib": max(r["max_mib"] for r in valid),
        "per_class": per_class,
    }


def measure_shacl_worker_mib(
    python: str, exclude_builtin_shapes: list[str] | None, samples: int = 3
) -> dict:
    arg = json.dumps({"exclude_builtin_shapes": exclude_builtin_shapes})
    return measure_mib(python, _MEASURE_SHACL_SCRIPT, arg, samples)


def measure_mapping_worker_mib(python: str, samples: int = 3) -> dict:
    return measure_mib(python, _MEASURE_MAPPING_SCRIPT, "{}", samples)


def get_total_ram_mib() -> int:
    if platform.system() == "Darwin":
        out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)
        return int(out.strip()) // (1024 * 1024)
    # Linux
    with open("/proc/meminfo") as f:
        for line in f:
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) // 1024
    raise RuntimeError("Cannot determine total RAM — use --memory-gib")


def get_cpu_count() -> int:
    return os.cpu_count() or 4


def resolve_ingest_loader(profile_data: dict, base_data: dict) -> str:
    """Return the ingest_loader for a profile, falling back to _base."""
    return (
        profile_data.get("ingest_loader")
        or base_data.get("ingest_loader")
        or "playwright"
    )


def count_active_postprocessors(profile_dir: Path, base_dir: Path) -> int:
    """Count enabled postprocessors for a profile, falling back to _base."""
    for candidate in (
        profile_dir / "postprocessors.toml",
        base_dir / "postprocessors.toml",
    ):
        if candidate.exists():
            with open(candidate, "rb") as f:
                cfg = tomllib.load(f)
            if not cfg.get("enabled", True):
                return 0
            return sum(
                1 for pp in cfg.get("postprocessors", []) if pp.get("enabled", True)
            )
    return 0


@dataclass(frozen=True)
class PoolEstimate:
    concurrency: int
    postprocessor_pool_size: int
    shacl_pool_size: int
    mapping_pool_size: int
    estimated_mib: int
    target_mib: int


def _grow_balanced_pools(
    leftover: float,
    shacl_pool: int,
    mapping_pool: int,
    shacl_cost: float,
    mapping_cost: float,
    pool_cap: int,
) -> tuple[int, int]:
    while leftover >= min(shacl_cost, mapping_cost):
        grew = False
        if (
            mapping_pool <= shacl_pool
            and mapping_pool < pool_cap
            and leftover >= mapping_cost
        ):
            mapping_pool += 1
            leftover -= mapping_cost
            grew = True
        elif shacl_pool < pool_cap and leftover >= shacl_cost:
            shacl_pool += 1
            leftover -= shacl_cost
            grew = True
        elif mapping_pool < pool_cap and leftover >= mapping_cost:
            mapping_pool += 1
            leftover -= mapping_cost
            grew = True
        if not grew:
            break
    return shacl_pool, mapping_pool


def load_worai_profiles(root: Path) -> dict:
    with open(root / "worai.toml", "rb") as f:
        return tomllib.load(f)


def resolve_profile_data(worai: dict, profile: str | None) -> tuple[dict, dict, dict]:
    base_data = worai.get("profiles", {}).get("_base", {})
    profile_data = worai.get("profiles", {}).get(profile, {}) if profile else {}
    merged = {**base_data, **profile_data}
    return base_data, profile_data, merged


def find_postprocessors_toml(profile_dir: Path, base_dir: Path) -> Path | None:
    return next(
        (
            p
            for p in (
                profile_dir / "postprocessors.toml",
                base_dir / "postprocessors.toml",
            )
            if p.exists()
        ),
        None,
    )


def print_suggested_settings(estimate: PoolEstimate, target_mib: int) -> None:
    pct = estimate.estimated_mib / target_mib * 100
    print("Suggested settings    :")
    print(f"  concurrency             = {estimate.concurrency}")
    print(f"  postprocessor_pool_size = {estimate.postprocessor_pool_size}")
    print(f"  shacl_pool_size         = {estimate.shacl_pool_size}")
    print(f"  mapping_pool_size       = {estimate.mapping_pool_size}")
    print(
        f"Estimated peak memory : {estimate.estimated_mib / 1024:.2f} GiB  "
        f"({pct:.0f}% of {target_mib / 1024:.2f} GiB target)\n"
    )


def estimate_pools(
    total_mib: int,
    cpu_count: int,
    ingest_loader: str = "playwright",
    num_pp_classes: int = 1,
    *,
    pp_mib: int = POSTPROCESSOR_MIB,
    shacl_mib: int = SHACL_MIB,
    mapping_mib: int = MAPPING_MIB,
) -> dict:
    target_mib = int(total_mib * MEMORY_FRACTION * SAFETY_MARGIN)

    worker_mib = SIMPLE_MIB if ingest_loader == "simple" else PLAYWRIGHT_MIB

    # Playwright is CPU-bound; simple HTTP is I/O-bound so allow 2× cpu_count.
    cpu_cap = cpu_count * 2 if ingest_loader == "simple" else cpu_count

    # Each pool slot spawns num_pp_classes separate subprocesses (one per class).
    pp_cost_per_slot = pp_mib * num_pp_classes

    # Start with minimum shacl/mapping pools; we'll scale them up from leftover budget.
    min_shacl = 1
    min_mapping = 1
    fixed_base = BASE_OVERHEAD_MIB + min_shacl * shacl_mib + min_mapping * mapping_mib

    # Reserve at least 1 pp slot when computing concurrency headroom.
    concurrency = max(
        1,
        min(
            (target_mib - fixed_base - pp_cost_per_slot) // worker_mib,
            cpu_cap,
        ),
    )

    # Scale pp_pool to match concurrency so fetches don't queue for postprocessing.
    remaining_after_conc = target_mib - (fixed_base + concurrency * worker_mib)
    pp_pool = max(1, min(remaining_after_conc // pp_cost_per_slot, concurrency))

    # Use leftover budget to grow shacl_pool and mapping_pool, alternating to keep them balanced.
    shacl_pool = min_shacl
    mapping_pool = min_mapping
    pool_cap = min(pp_pool, POOL_CAP)
    leftover = target_mib - (
        BASE_OVERHEAD_MIB
        + concurrency * worker_mib
        + pp_pool * pp_cost_per_slot
        + shacl_pool * shacl_mib
        + mapping_pool * mapping_mib
    )
    shacl_pool, mapping_pool = _grow_balanced_pools(
        leftover, shacl_pool, mapping_pool, shacl_mib, mapping_mib, pool_cap
    )

    estimated_mib = (
        BASE_OVERHEAD_MIB
        + concurrency * worker_mib
        + pp_pool * num_pp_classes * pp_mib
        + shacl_pool * shacl_mib
        + mapping_pool * mapping_mib
    )

    return PoolEstimate(
        concurrency=int(concurrency),
        postprocessor_pool_size=pp_pool,
        shacl_pool_size=shacl_pool,
        mapping_pool_size=mapping_pool,
        estimated_mib=estimated_mib,
        target_mib=target_mib,
    )


def _build_legacy_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--profile", metavar="NAME", help="Analyze a single profile (default: all)"
    )
    parser.add_argument(
        "--memory-gib", type=float, metavar="GIB", help="Override total RAM in GiB"
    )
    parser.add_argument("--cpu", type=int, metavar="N", help="Override CPU core count")
    parser.add_argument(
        "--measure",
        action="store_true",
        help="Measure actual worker RSS for all pool types (requires --profile)",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=3,
        metavar="N",
        help="Subprocess samples per worker type for --measure (default: 3)",
    )
    parser.add_argument(
        "--update-constants",
        action="store_true",
        help="Persist measured MiB values into this script's constants (use with --measure)",
    )
    parser.add_argument(
        "--monitor",
        type=int,
        metavar="PID",
        dest="pid",
        help="Attach to a running worai process and track peak RSS of its process tree",
    )
    parser.add_argument(
        "--watch",
        metavar="PATTERN",
        help="Wait for a process matching PATTERN to appear, then monitor it (useful in CI before the sync step)",
    )
    parser.add_argument(
        "--watch-timeout",
        type=int,
        default=300,
        metavar="SEC",
        help="Seconds to wait for --watch pattern before giving up (default: 300)",
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        help="Write monitor results as JSON to FILE (in addition to stdout)",
    )
    parser.add_argument(
        "--markdown-output",
        metavar="FILE",
        help="Write a formatted markdown summary to FILE (append to $GITHUB_STEP_SUMMARY)",
    )
    parser.add_argument(
        "--root",
        metavar="DIR",
        help="Project root directory containing worai.toml (default: parent of this script's directory)",
    )
    return parser


def _build_subcommand_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--profile", metavar="NAME", help="Analyze a single profile (default: all)"
    )
    parser.add_argument(
        "--memory-gib", type=float, metavar="GIB", help="Override total RAM in GiB"
    )
    parser.add_argument("--cpu", type=int, metavar="N", help="Override CPU core count")
    subparsers = parser.add_subparsers(dest="mode")

    estimate = subparsers.add_parser(
        "estimate", help="Suggest pool sizes based on system resources"
    )
    estimate.add_argument(
        "--profile", metavar="NAME", help="Analyze a single profile (default: all)"
    )
    estimate.add_argument(
        "--memory-gib", type=float, metavar="GIB", help="Override total RAM in GiB"
    )
    estimate.add_argument(
        "--cpu", type=int, metavar="N", help="Override CPU core count"
    )

    measure = subparsers.add_parser(
        "measure", help="Measure actual worker RSS for all pool types"
    )
    measure.add_argument(
        "--profile", metavar="NAME", required=True, help="Profile to measure"
    )
    measure.add_argument(
        "--memory-gib", type=float, metavar="GIB", help="Override total RAM in GiB"
    )
    measure.add_argument("--cpu", type=int, metavar="N", help="Override CPU core count")
    measure.add_argument(
        "--samples",
        type=int,
        default=3,
        metavar="N",
        help="Subprocess samples per worker type (default: 3)",
    )
    measure.add_argument(
        "--update-constants",
        action="store_true",
        help="Persist measured MiB values into this script's constants",
    )

    monitor = subparsers.add_parser(
        "monitor", help="Attach to a running worai process and track peak RSS"
    )
    monitor.add_argument(
        "--profile", metavar="NAME", help="Profile name for suggested settings"
    )
    monitor.add_argument(
        "--memory-gib", type=float, metavar="GIB", help="Override total RAM in GiB"
    )
    monitor.add_argument("--cpu", type=int, metavar="N", help="Override CPU core count")
    monitor.add_argument(
        "--pid", type=int, metavar="PID", help="Attach to a running worai process"
    )
    monitor.add_argument(
        "--watch",
        metavar="PATTERN",
        help="Wait for a process matching PATTERN to appear, then monitor it",
    )
    monitor.add_argument(
        "--watch-timeout",
        type=int,
        default=300,
        metavar="SEC",
        help="Seconds to wait for --watch pattern (default: 300)",
    )
    monitor.add_argument(
        "--output",
        metavar="FILE",
        help="Write monitor results as JSON to FILE (in addition to stdout)",
    )
    monitor.add_argument(
        "--markdown-output",
        metavar="FILE",
        help="Write a formatted markdown summary to FILE (append to $GITHUB_STEP_SUMMARY)",
    )

    return parser


def _parse_args() -> argparse.Namespace:
    args_in = sys.argv[1:]
    subcommands = {"estimate", "measure", "monitor"}
    if args_in and args_in[0] in subcommands:
        parser = _build_subcommand_parser()
        return parser.parse_args()
    # Legacy flags-only invocation
    parser = _build_legacy_parser()
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    if getattr(args, "measure", False) and not args.profile:
        raise SystemExit("--measure requires --profile")

    root = Path(args.root).resolve() if getattr(args, "root", None) else Path(__file__).resolve().parent.parent
    profiles_dir = root / "profiles"
    base_dir = profiles_dir / "_base"

    total_mib = int(args.memory_gib * 1024) if args.memory_gib else get_total_ram_mib()
    cpu_count = args.cpu or get_cpu_count()

    if (
        getattr(args, "mode", None) == "monitor"
        and getattr(args, "pid", None) is None
        and not getattr(args, "watch", None)
    ):
        raise SystemExit("monitor requires --pid or --watch")

    if getattr(args, "watch", None):
        pid = _find_pid_by_pattern(args.watch, timeout=args.watch_timeout)
        if pid is None:
            print(
                f"error: pattern '{args.watch}' not found within {args.watch_timeout}s",
                file=sys.stderr,
            )
            sys.exit(1)
        args.pid = pid

    if getattr(args, "pid", None) is not None:
        run_monitor(args, root, total_mib, cpu_count)
        return

    if getattr(args, "measure", False) or getattr(args, "mode", None) == "measure":
        run_measure(args, root, profiles_dir, base_dir, total_mib, cpu_count)
        return
    budget_mib = int(total_mib * MEMORY_FRACTION)

    print(f"System : {cpu_count} CPUs  |  {total_mib / 1024:.1f} GiB RAM")
    print(
        f"Budget : {budget_mib / 1024:.1f} GiB  ({int(MEMORY_FRACTION * 100)}% of total)\n"
    )

    worai = load_worai_profiles(root)

    all_profiles = {
        name: data
        for name, data in worai.get("profiles", {}).items()
        if not name.startswith("_")
    }

    if args.profile:
        if args.profile not in all_profiles:
            print(
                f"error: profile '{args.profile}' not found in worai.toml",
                file=sys.stderr,
            )
            sys.exit(1)
        profiles_to_check = {args.profile: all_profiles[args.profile]}
    else:
        profiles_to_check = all_profiles

    base_data, _, _ = resolve_profile_data(worai, None)

    # Group profiles by (postprocessor count, ingest_loader) — most will share the same _base config
    groups: dict[tuple[int, str], list[str]] = {}
    for name in sorted(profiles_to_check):
        active_pp = count_active_postprocessors(profiles_dir / name, base_dir)
        loader = resolve_ingest_loader(profiles_to_check[name], base_data)
        groups.setdefault((active_pp, loader), []).append(name)

    for (active_pp, loader), names in sorted(groups.items()):
        est = estimate_pools(
            total_mib, cpu_count, loader, num_pp_classes=max(active_pp, 1)
        )

        if len(names) == len(profiles_to_check) and len(names) > 1:
            profile_label = f"all {len(names)} profiles"
        else:
            profile_label = ", ".join(names)

        print(f"Profile(s)            : {profile_label}")
        print(f"Ingest loader         : {loader}")
        print_suggested_settings(est, est.target_mib)


def _calibrated_mib(result: dict, current: int) -> int:
    """Round measured mean up to the next multiple of 10, with at least 10 MiB headroom."""
    if "error" in result:
        return current
    return math.ceil((result["mean_mib"] + 10) / 10) * 10


def update_constants_in_script(pp_mib: int, shacl_mib: int, mapping_mib: int) -> None:
    script = Path(__file__)
    content = script.read_text()
    for name, value in [
        ("POSTPROCESSOR_MIB", pp_mib),
        ("SHACL_MIB", shacl_mib),
        ("MAPPING_MIB", mapping_mib),
    ]:
        content = re.sub(
            rf"^({name}\s*=\s*)\d+", rf"\g<1>{value}", content, flags=re.MULTILINE
        )
    script.write_text(content)
    print(f"  Updated constants in {script.name}")


def run_measure(
    args, root: Path, profiles_dir: Path, base_dir: Path, total_mib: int, cpu_count: int
) -> None:
    worai = load_worai_profiles(root)
    base_data, profile_data, merged = resolve_profile_data(worai, args.profile)

    profile_dir = profiles_dir / args.profile
    pp_toml = find_postprocessors_toml(profile_dir, base_dir)
    if pp_toml is None:
        print(
            f"error: no postprocessors.toml found for profile '{args.profile}'",
            file=sys.stderr,
        )
        sys.exit(1)
    with open(pp_toml, "rb") as f:
        pp_cfg = tomllib.load(f)

    python_bin = pp_cfg.get("python", sys.executable)
    python_path = Path(python_bin)
    if not python_path.is_absolute():
        python_path = root / python_path
    python_bin = str(python_path)

    class_specs = [
        pp["class"]
        for pp in pp_cfg.get("postprocessors", [])
        if pp.get("enabled", True)
    ]
    exclude_shapes = merged.get("shacl_exclude_builtin_shapes")
    loader = resolve_ingest_loader(profile_data, base_data)

    print(
        f"Measuring worker RSS — profile: {args.profile}  ({args.samples} samples each)\n"
    )

    pp_result = measure_worker_mib(python_bin, class_specs, samples=args.samples)
    shacl_result = measure_shacl_worker_mib(
        python_bin, exclude_shapes, samples=args.samples
    )
    mapping_result = measure_mapping_worker_mib(python_bin, samples=args.samples)

    # Print measurement table
    rows = [
        ("Postprocessors", pp_result, "POSTPROCESSOR_MIB", POSTPROCESSOR_MIB),
        ("SHACL", shacl_result, "SHACL_MIB", SHACL_MIB),
        ("Mapping (morph-kgc)", mapping_result, "MAPPING_MIB", MAPPING_MIB),
    ]
    print(f"  {'Worker':<22} {'Measured':>10}  {'Constant':>10}  Status")
    print(f"  {'─' * 62}")
    for label, result, const_name, const_val in rows:
        if "error" in result:
            print(f"  {label:<22} {'ERROR':>10}  {const_name}={const_val}")
            continue
        mean = result["mean_mib"]
        delta = mean - const_val
        if abs(delta) <= 10:
            status = "ok"
        elif delta > 0:
            status = f"low  → update to {_calibrated_mib(result, const_val)}"
        else:
            status = f"high → update to {_calibrated_mib(result, const_val)}"
        print(f"  {label:<22} {mean:>8.0f} MiB  {const_name}={const_val:>4}  {status}")

    # Show per-class breakdown for postprocessors
    for entry in pp_result.get("per_class", []):
        status = f"  [{entry['class']}: {entry.get('mean_mib', 0):.0f} MiB/subprocess]"
        print(f"    {status}")

    # Derive calibrated MiB values (use measurement if available, else keep constant)
    pp_mib = _calibrated_mib(pp_result, POSTPROCESSOR_MIB)
    shacl_mib = _calibrated_mib(shacl_result, SHACL_MIB)
    mapping_mib = _calibrated_mib(mapping_result, MAPPING_MIB)

    num_pp_classes = len(class_specs)
    # Compute plausible pool sizes using measured values
    est = estimate_pools(
        total_mib,
        cpu_count,
        loader,
        num_pp_classes=num_pp_classes,
        pp_mib=pp_mib,
        shacl_mib=shacl_mib,
        mapping_mib=mapping_mib,
    )
    pct = est.estimated_mib / est.target_mib * 100

    print(f"\nSuggested settings (using measured values, {loader} loader):")
    print(f"  concurrency             = {est.concurrency}")
    print(f"  postprocessor_pool_size = {est.postprocessor_pool_size}")
    print(f"  shacl_pool_size         = {est.shacl_pool_size}")
    print(f"  mapping_pool_size       = {est.mapping_pool_size}")
    print(
        f"Estimated peak memory : {est.estimated_mib / 1024:.2f} GiB  ({pct:.0f}% of {est.target_mib / 1024:.2f} GiB target)"
    )

    if args.update_constants:
        print()
        update_constants_in_script(pp_mib, shacl_mib, mapping_mib)
    else:
        any_off = any(
            abs(r["mean_mib"] - c) > 10
            for r, c in [
                (pp_result, POSTPROCESSOR_MIB),
                (shacl_result, SHACL_MIB),
                (mapping_result, MAPPING_MIB),
            ]
            if "error" not in r
        )
        if any_off:
            print(
                "\nRun with --update-constants to persist measured values into this script."
            )


def _read_pss_bytes(pid: int) -> int | None:
    """Read Pss from /proc/PID/smaps_rollup (Linux only). Returns None if unavailable."""
    try:
        with open(f"/proc/{pid}/smaps_rollup") as f:
            for line in f:
                if line.startswith("Pss:"):
                    return int(line.split()[1]) * 1024  # kB → bytes
    except OSError:
        return None
    return None


def _read_cgroup_wss_bytes() -> int | None:
    """Read container Working Set Size from cgroup — the exact metric Kubernetes/Grafana reports.

    WSS = memory.usage_in_bytes − inactive_file_cache
    Tries cgroupv2 (/sys/fs/cgroup/memory.current) then cgroupv1 (/sys/fs/cgroup/memory/).
    Returns None outside a container or on macOS.
    """

    def _parse_stat_field(stat_text: str, field: str) -> int:
        for line in stat_text.splitlines():
            parts = line.split()
            if parts and parts[0] == field:
                return int(parts[1])
        return 0

    # cgroupv2
    try:
        current = int(Path("/sys/fs/cgroup/memory.current").read_text())
        stat = Path("/sys/fs/cgroup/memory.stat").read_text()
        inactive_file = _parse_stat_field(stat, "inactive_file")
        return max(0, current - inactive_file)
    except OSError:
        pass

    # cgroupv1
    try:
        usage = int(Path("/sys/fs/cgroup/memory/memory.usage_in_bytes").read_text())
        stat = Path("/sys/fs/cgroup/memory/memory.stat").read_text()
        # cgroupv1 uses total_inactive_file for hierarchical accounting
        inactive_file = _parse_stat_field(
            stat, "total_inactive_file"
        ) or _parse_stat_field(stat, "inactive_file")
        return max(0, usage - inactive_file)
    except OSError:
        pass

    return None


def _sample_process_tree(root_pid: int) -> dict[int, dict] | None:
    """Return {pid: {ppid, mem_bytes, mem_metric, cmd}} for all processes in root_pid's tree.

    mem_bytes is PSS (Proportional Set Size) when /proc/PID/smaps_rollup is available (Linux),
    falling back to RSS otherwise (macOS). PSS divides shared pages proportionally across all
    processes sharing them, so summing PSS across a process tree gives the true physical footprint.
    mem_metric is 'PSS' or 'RSS' so callers can label output correctly.
    """
    try:
        out = subprocess.check_output(
            ["ps", "-eo", "pid,ppid,rss,command"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return None

    all_procs: dict[int, dict] = {}
    for line in out.strip().splitlines()[1:]:
        parts = line.split(None, 3)
        if len(parts) < 3:
            continue
        try:
            pid, ppid, rss_kb = int(parts[0]), int(parts[1]), int(parts[2])
        except ValueError:
            continue
        all_procs[pid] = {
            "ppid": ppid,
            "rss_bytes": rss_kb * 1024,
            "cmd": parts[3].strip() if len(parts) > 3 else "",
        }

    if root_pid not in all_procs:
        return None

    children_map: dict[int, list[int]] = {}
    for pid, info in all_procs.items():
        children_map.setdefault(info["ppid"], []).append(pid)
    tree: set[int] = set()
    queue = [root_pid]
    while queue:
        pid = queue.pop()
        tree.add(pid)
        queue.extend(children_map.get(pid, []))

    result = {}
    for pid in tree:
        if pid not in all_procs:
            continue
        info = all_procs[pid]
        pss = _read_pss_bytes(pid)
        if pss is not None:
            result[pid] = {**info, "mem_bytes": pss, "mem_metric": "PSS"}
        else:
            result[pid] = {**info, "mem_bytes": info["rss_bytes"], "mem_metric": "RSS"}
    return result


# Labels for process types, in display order.
_CATEGORIES = ["orchestrator", "pool-worker", "subprocess"]


def _classify(pid: int, root_pid: int, cmd: str) -> str:
    """Classify a process by its role in the worai process tree."""
    if pid == root_pid:
        return "orchestrator"
    # ProcessPoolExecutor workers (SHACL, mapping) spawn via multiprocessing
    if "multiprocessing.spawn" in cmd or "multiprocessing.forkserver" in cmd:
        return "pool-worker"
    # Persistent postprocessor workers (launched via subprocess.Popen with -c script)
    return "subprocess"


def _find_pid_by_pattern(
    pattern: str, timeout: int = 300, interval: float = 2.0
) -> int | None:
    """Poll `ps` every `interval` seconds until a NEW process whose command matches `pattern` appears.

    'New' means not present when this function was first called — this avoids matching the
    monitor script itself or its parent uv/python process, which may also import the same modules.
    Returns the PID of the root new match (parent not also a new match), or None on timeout.
    """

    def _snapshot_pids() -> set[int]:
        try:
            out = subprocess.check_output(
                ["ps", "-eo", "pid"], text=True, stderr=subprocess.DEVNULL
            )
            return {
                int(p)
                for line in out.strip().splitlines()[1:]
                if (p := line.strip()).isdigit()
            }
        except Exception:
            return set()

    existing_pids = _snapshot_pids()
    deadline = time.time() + timeout
    print(f"Waiting up to {timeout}s for a new process matching '{pattern}' …")

    while time.time() < deadline:
        time.sleep(interval)
        try:
            out = subprocess.check_output(
                ["ps", "-eo", "pid,ppid,command"], text=True, stderr=subprocess.DEVNULL
            )
        except subprocess.CalledProcessError:
            continue

        matches: dict[int, int] = {}  # pid -> ppid
        for line in out.strip().splitlines()[1:]:
            parts = line.split(None, 2)
            if len(parts) < 3:
                continue
            try:
                pid, ppid = int(parts[0]), int(parts[1])
            except ValueError:
                continue
            if pid not in existing_pids and pattern in parts[2]:
                matches[pid] = ppid

        # Pick the root match: a new process whose parent is NOT also a new match.
        roots = [pid for pid, ppid in matches.items() if ppid not in matches]
        if roots:
            pid = roots[0]
            print(f"Found PID {pid} — starting monitor.")
            return pid

    return None


def run_monitor(args, root: Path, total_mib: int, cpu_count: int) -> None:
    pid = args.pid
    interval = 0.5
    # timeline: list of (elapsed_s, {category: (pss_bytes, count)}, cgroup_wss_bytes_or_None)
    timeline: list[tuple[float, dict[str, tuple[int, int]], int | None]] = []
    start_t = time.time()

    # Detect whether PSS is available (Linux /proc) or we fall back to RSS (macOS).
    mem_metric = "PSS" if _read_pss_bytes(pid) is not None else "RSS"
    use_cgroup = _read_cgroup_wss_bytes() is not None
    label = f"{mem_metric} + cgroup WSS" if use_cgroup else mem_metric
    print(f"Monitoring PID {pid} — Ctrl+C to stop  [{label}]\n")
    try:
        while True:
            sample = _sample_process_tree(pid)
            if sample is None:
                print(f"\nProcess {pid} exited.")
                break

            elapsed = time.time() - start_t
            buckets: dict[str, tuple[int, int]] = {}
            for p, info in sample.items():
                cat = _classify(p, pid, info["cmd"])
                mem, cnt = buckets.get(cat, (0, 0))
                buckets[cat] = (mem + info["mem_bytes"], cnt + 1)
            cgroup_wss = _read_cgroup_wss_bytes() if use_cgroup else None
            timeline.append((elapsed, buckets, cgroup_wss))

            total_mem = (
                cgroup_wss
                if cgroup_wss is not None
                else sum(m for m, _ in buckets.values())
            )
            total_procs = sum(c for _, c in buckets.values())
            sys.stdout.write(
                f"\r  t={elapsed:.0f}s  procs={total_procs}"
                f"  current={total_mem / (1024**2):.0f} MiB"
                f"  peak={max((cw if cw is not None else sum(m for m, _ in b.values()) for _, b, cw in timeline), default=0) / (1024**2):.0f} MiB  "
            )
            sys.stdout.flush()
            time.sleep(interval)
    except KeyboardInterrupt:
        print()

    if not timeline:
        print("No data collected.")
        return

    # Find the sample with the highest WSS (or PSS if cgroup unavailable)
    def _total(entry):
        _, buckets, cgroup_wss = entry
        return (
            cgroup_wss
            if cgroup_wss is not None
            else sum(m for m, _ in buckets.values())
        )

    peak_idx = max(range(len(timeline)), key=lambda i: _total(timeline[i]))
    peak_elapsed, peak_buckets, peak_cgroup_wss = timeline[peak_idx]
    peak_pss_total = sum(m for m, _ in peak_buckets.values())
    peak_total = peak_cgroup_wss if peak_cgroup_wss is not None else peak_pss_total
    peak_procs = sum(c for _, c in peak_buckets.values())
    overhead = peak_cgroup_wss - peak_pss_total if peak_cgroup_wss is not None else None

    print(f"\nPeak at t={peak_elapsed:.0f}s  ({peak_procs} processes):\n")
    print(f"  {'Category':<20} {mem_metric:>8}   {'Processes':>9}")
    print(f"  {'─' * 42}")
    for cat in _CATEGORIES:
        if cat in peak_buckets:
            mem, cnt = peak_buckets[cat]
            print(f"  {cat:<20} {mem / (1024**2):>6.0f} MiB   {cnt:>5}")
    print(f"  {'─' * 42}")
    print(f"  {f'Total {mem_metric}':<20} {peak_pss_total / (1024**2):>6.0f} MiB")
    if overhead is not None:
        print(
            f"  {'kernel+cache overhead':<20} {overhead / (1024**2):>6.0f} MiB   (kernel mem + active page cache)"
        )
        print(f"  {'─' * 42}")
        print(
            f"  {'cgroup WSS':<20} {peak_cgroup_wss / (1024**2):>6.0f} MiB   {peak_procs:>5}"
        )

    # Per-category independent peaks (may not all occur at the same time)
    print("\nPer-category peak (independent maxima):")
    indep_total = 0
    for cat in _CATEGORIES:
        max_mem = max((t[1].get(cat, (0, 0))[0] for t in timeline), default=0)
        max_cnt = max((t[1].get(cat, (0, 0))[1] for t in timeline), default=0)
        if max_mem:
            indep_total += max_mem
            print(
                f"  {cat:<20} {max_mem / (1024**2):>6.0f} MiB   {max_cnt:>2} processes max"
            )
    print(f"  {'─' * 42}")
    print(f"  {'(sum of maxima)':<20} {indep_total / (1024**2):>6.0f} MiB")

    # Suggest pool sizes from observed active-load costs if profile is known
    if not args.profile:
        print(
            "\nRun with --profile NAME to get pool size suggestions based on observed costs."
        )
        return

    worai = load_worai_profiles(root)
    base_data, profile_data, merged = resolve_profile_data(worai, args.profile)

    shacl_pool = int(merged.get("shacl_pool_size", 2))
    mapping_pool = int(merged.get("mapping_pool_size", 2))
    pp_pool_cfg = int(merged.get("postprocessor_pool_size", 4))
    concurrency = int(merged.get("concurrency", 4))

    # Load num_pp_classes from postprocessors.toml
    profile_dir = root / "profiles" / args.profile
    base_dir = root / "profiles" / "_base"
    pp_toml = find_postprocessors_toml(profile_dir, base_dir)
    num_pp_classes = 1
    if pp_toml:
        with open(pp_toml, "rb") as f:
            pp_cfg_data = tomllib.load(f)
        num_pp_classes = sum(
            1 for pp in pp_cfg_data.get("postprocessors", []) if pp.get("enabled", True)
        )

    orch_mem, _ = peak_buckets.get("orchestrator", (0, 0))
    pool_rss, pool_cnt = peak_buckets.get("pool-worker", (0, 0))
    sub_rss, sub_cnt = peak_buckets.get("subprocess", (0, 0))

    if pool_cnt == 0 or sub_cnt == 0:
        print("\nNot enough process-type data to suggest settings.")
        return

    # Split observed pool_rss between SHACL and mapping workers proportionally
    # using their idle-cost ratio as a proxy (they're indistinguishable at OS level).
    shacl_idle_cost = shacl_pool * SHACL_MIB
    mapping_idle_cost = mapping_pool * MAPPING_MIB
    pool_idle_total = shacl_idle_cost + mapping_idle_cost or 1
    shacl_mib_per = (
        (pool_rss * shacl_idle_cost / pool_idle_total) / shacl_pool / (1024**2)
    )
    mapping_mib_per = (
        (pool_rss * mapping_idle_cost / pool_idle_total) / mapping_pool / (1024**2)
    )

    # Average cost per subprocess across all observed subprocesses (pp workers + any extras).
    # Dividing by sub_cnt (not expected_pp_procs) ensures the total reconstructs correctly
    # and avoids double-counting the extra processes in extra_sub_mib.
    expected_pp_procs = pp_pool_cfg * num_pp_classes
    sub_mib_per = sub_rss / sub_cnt / (1024**2)
    extra_sub_cnt = max(0, sub_cnt - expected_pp_procs)

    target_mib = int(total_mib * MEMORY_FRACTION * SAFETY_MARGIN)
    orch_mib = orch_mem / (1024**2)
    extra_sub_mib = (
        extra_sub_cnt * sub_mib_per
    )  # non-pp subprocesses treated as fixed overhead

    # If cgroup WSS is available, account for kernel+cache overhead in the budget so suggestions
    # are based on the same metric Grafana/Kubernetes uses for OOM decisions.
    overhead_mib = (
        (peak_cgroup_wss - peak_pss_total) / (1024**2)
        if peak_cgroup_wss is not None
        else 0.0
    )

    # Estimate the WSS cost of the current configuration using observed per-process costs.
    # If the current settings already fit within budget, we should not reduce any pool size —
    # only suggest increasing where there is headroom.
    current_estimated_mib = (
        orch_mib
        + overhead_mib
        + extra_sub_mib
        + pp_pool_cfg * num_pp_classes * sub_mib_per
        + shacl_pool * shacl_mib_per
        + mapping_pool * mapping_mib_per
    )
    current_fits = current_estimated_mib <= target_mib

    # Fit pp_pool in remaining budget after orchestrator, overhead, and extras.
    budget_for_pools = target_mib - orch_mib - overhead_mib - extra_sub_mib
    min_shacl, min_mapping = 1, 1

    if current_fits:
        # Current settings fit: compute pp headroom using current shacl/mapping costs
        # so we don't mix pool sizes computed under different assumptions.
        new_shacl_pool = shacl_pool
        new_mapping_pool = mapping_pool
        fixed_pool = shacl_pool * shacl_mib_per + mapping_pool * mapping_mib_per
        computed_pp_pool = max(
            1,
            min(
                int((budget_for_pools - fixed_pool) / (num_pp_classes * sub_mib_per)),
                concurrency,
            ),
        )
        new_pp_pool = max(computed_pp_pool, pp_pool_cfg)
    else:
        # Over budget: recompute everything from minimums.
        new_shacl_pool = min_shacl
        new_mapping_pool = min_mapping
        fixed_pool = min_shacl * shacl_mib_per + min_mapping * mapping_mib_per
        new_pp_pool = max(
            1,
            min(
                int((budget_for_pools - fixed_pool) / (num_pp_classes * sub_mib_per)),
                concurrency,
            ),
        )
    pool_cap = min(new_pp_pool, POOL_CAP)
    leftover = budget_for_pools - (
        new_pp_pool * num_pp_classes * sub_mib_per
        + new_shacl_pool * shacl_mib_per
        + new_mapping_pool * mapping_mib_per
    )
    new_shacl_pool, new_mapping_pool = _grow_balanced_pools(
        leftover,
        new_shacl_pool,
        new_mapping_pool,
        shacl_mib_per,
        mapping_mib_per,
        pool_cap,
    )

    new_total_pss = (
        orch_mib
        + overhead_mib
        + extra_sub_mib
        + new_pp_pool * num_pp_classes * sub_mib_per
        + new_shacl_pool * shacl_mib_per
        + new_mapping_pool * mapping_mib_per
    )
    new_total = new_total_pss
    pct = new_total / target_mib * 100

    print(f"\nObserved active-load costs (peak at t={peak_elapsed:.0f}s):")
    print(
        f"  orchestrator  {orch_mib:>6.0f} MiB  (fixed, includes concurrency={concurrency} async slots)"
    )
    if overhead_mib:
        print(
            f"  kernel+cache  {overhead_mib:>6.0f} MiB  (fixed overhead: kernel mem + active page cache)"
        )
    print(
        f"  pool-worker   {pool_rss / pool_cnt / (1024**2):>6.0f} MiB  each  ({pool_cnt} workers: shacl={shacl_pool} ~{shacl_mib_per:.0f} MiB, mapping={mapping_pool} ~{mapping_mib_per:.0f} MiB)"
    )
    print(
        f"  subprocess    {sub_mib_per:>6.0f} MiB  each  ({sub_cnt} observed = pp_pool={pp_pool_cfg} × {num_pp_classes} classes"
        + (f" + {extra_sub_cnt} other)" if extra_sub_cnt else ")")
    )

    print(
        f"\nSuggested settings (target {target_mib / 1024:.1f} GiB = {total_mib / 1024:.1f} GiB × {SAFETY_MARGIN:.0%}):"
    )
    print(f"  concurrency             = {concurrency}  (unchanged)")
    print(
        f"  postprocessor_pool_size = {new_pp_pool}  ({new_pp_pool} slots × {num_pp_classes} classes = {new_pp_pool * num_pp_classes} subprocesses)"
    )
    print(
        f"  shacl_pool_size         = {new_shacl_pool}"
        + (f"  (was {shacl_pool})" if new_shacl_pool != shacl_pool else "  (unchanged)")
    )
    print(
        f"  mapping_pool_size       = {new_mapping_pool}"
        + (
            f"  (was {mapping_pool})"
            if new_mapping_pool != mapping_pool
            else "  (unchanged)"
        )
    )
    print(
        f"Estimated peak : {new_total / 1024:.2f} GiB  ({pct:.0f}% of {target_mib / 1024:.2f} GiB target)"
    )

    if args.output:
        result = {
            "profile": args.profile,
            "peak_mib": round(peak_total / (1024**2), 1),
            "peak_pss_mib": round(peak_pss_total / (1024**2), 1),
            "peak_cgroup_wss_mib": round(peak_cgroup_wss / (1024**2), 1)
            if peak_cgroup_wss is not None
            else None,
            "overhead_mib": round(overhead_mib, 1),
            "target_mib": target_mib,
            "peak_pct": round(peak_total / (1024**2) / target_mib * 100, 1),
            "breakdown": {
                cat: {"pss_mib": round(mem / (1024**2), 1), "count": cnt}
                for cat, (mem, cnt) in peak_buckets.items()
            },
            "suggested": {
                "concurrency": concurrency,
                "postprocessor_pool_size": new_pp_pool,
                "shacl_pool_size": new_shacl_pool,
                "mapping_pool_size": new_mapping_pool,
            },
            "estimated_mib": round(new_total, 1),
        }
        Path(args.output).write_text(json.dumps(result, indent=2))
        print(f"\nResults written to {args.output}")

    if args.markdown_output:
        try:
            _write_markdown_summary(
                args,
                peak_total,
                peak_pss_total,
                peak_cgroup_wss,
                overhead_mib,
                peak_procs,
                peak_buckets,
                target_mib,
                total_mib,
                concurrency,
                pp_pool_cfg,
                new_pp_pool,
                shacl_pool,
                new_shacl_pool,
                mapping_pool,
                new_mapping_pool,
                new_total,
                pct,
            )
        except Exception as exc:
            print(
                f"\nWarning: failed to write markdown summary: {exc}", file=sys.stderr
            )


def _write_markdown_summary(
    args,
    peak_total,
    peak_pss_total,
    peak_cgroup_wss,
    overhead_mib,
    peak_procs,
    peak_buckets,
    target_mib,
    total_mib,
    concurrency,
    pp_pool_cfg,
    new_pp_pool,
    shacl_pool,
    new_shacl_pool,
    mapping_pool,
    new_mapping_pool,
    new_total,
    pct,
):
    peak_mib = peak_total / (1024**2)
    peak_pss_mib = peak_pss_total / (1024**2)
    over = peak_mib > target_mib
    status = "🔴 **OVER BUDGET**" if over else "🟢 within budget"
    wss_note = " (cgroup WSS)" if peak_cgroup_wss is not None else " (PSS)"
    lines = [
        f"## Memory report — {args.profile}",
        "",
        f"**Peak{wss_note}:** {peak_mib:.0f} MiB &nbsp;·&nbsp; "
        f"**Target:** {target_mib} MiB ({total_mib / 1024:.0f} GiB × {SAFETY_MARGIN:.0%}) &nbsp;·&nbsp; "
        f"**Usage:** {peak_mib / target_mib * 100:.0f}% {status}",
        "",
        "### Breakdown at peak",
        "",
        "| Category | PSS | Processes |",
        "|---|---:|---:|",
    ]
    for cat in _CATEGORIES:
        if cat in peak_buckets:
            mem, cnt = peak_buckets[cat]
            lines.append(f"| {cat} | {mem / (1024**2):.0f} MiB | {cnt} |")
    lines.append(f"| Total PSS | {peak_pss_mib:.0f} MiB | {peak_procs} |")
    if peak_cgroup_wss is not None:
        lines.append(f"| kernel + page cache | {overhead_mib:.0f} MiB | — |")
        lines.append(f"| **cgroup WSS** | **{peak_mib:.0f} MiB** | |")
    lines += [
        "",
        "### Suggested settings",
        "",
        "| Setting | Current | Suggested |",
        "|---|---:|---:|",
        f"| concurrency | {concurrency} | {concurrency} |",
        f"| postprocessor\\_pool\\_size | {pp_pool_cfg} | **{new_pp_pool}** |"
        if new_pp_pool != pp_pool_cfg
        else f"| postprocessor\\_pool\\_size | {pp_pool_cfg} | {new_pp_pool} |",
        f"| shacl\\_pool\\_size | {shacl_pool} | **{new_shacl_pool}** |"
        if new_shacl_pool != shacl_pool
        else f"| shacl\\_pool\\_size | {shacl_pool} | {new_shacl_pool} |",
        f"| mapping\\_pool\\_size | {mapping_pool} | **{new_mapping_pool}** |"
        if new_mapping_pool != mapping_pool
        else f"| mapping\\_pool\\_size | {mapping_pool} | {new_mapping_pool} |",
        "",
        f"Estimated peak with suggested settings: **{new_total:.0f} MiB** ({pct:.0f}% of target)",
        "",
    ]
    with open(args.markdown_output, "a") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nMarkdown summary written to {args.markdown_output}")


if __name__ == "__main__":
    main()
