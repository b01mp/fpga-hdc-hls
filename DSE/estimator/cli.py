"""
cli.py -- command line for the estimator.

Run from the DSE/ directory:
    python -m estimator.cli estimate
    python -m estimator.cli estimate --set dp=64 --set family=fixed --set elem_bits=8
    python -m estimator.cli sweep

Or run the file directly:
    python estimator/cli.py estimate
"""
import sys
import os
import argparse

# Allow running as a plain script (python estimator/cli.py) as well as -m.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from estimator.estimate import estimate, default_params      # noqa: E402
from estimator.sweep import sweep, pareto, print_table        # noqa: E402


def _coerce(value):
    """Turn a CLI string into int/float where possible, else leave as string."""
    for cast in (int, float):
        try:
            return cast(value)
        except ValueError:
            pass
    return value


def _print_metrics(m):
    p = m["params"]
    print("design point")
    print(f"  app : hv_dim={p['hv_dim']} features={p['num_features']} "
          f"classes={p['num_prototypes']} levels={p['num_levels']} "
          f"family={p['family']} elem_bits={p['elem_bits']}")
    print(f"  arch: dp={p['dp']} fp={p['fp']} cp={p['cp']} "
          f"pipeline={p['pipeline_mode']} mem={p['memory_space']} "
          f"bank={p['banking_factor']} part={p['target_fpga']} clk={p['clock_ns']}ns")
    print()
    print(f"  latency   : {m['latency_cycles']:,} cycles = {m['latency_us']:.2f} us")
    print(f"  throughput: {m['throughput_infps']:,.1f} inferences/s")
    print(f"  feasible  : {'YES' if m['feasible'] else 'NO (exceeds device)'}")
    print()
    r, u = m["resources"], m["util_pct"]
    print("  resources         used         util%")
    for key in ("LUT", "FF", "DSP", "BRAM36", "URAM"):
        uk = u[key if key != "BRAM36" else "BRAM36"]
        print(f"    {key:<7} {r[key]:>12,.0f}   {uk:>7.1f}%")
    print()
    print("  stage latencies (cycles):")
    for name, cyc in m["stages"]:
        print(f"    {name:<12} {cyc:>12,}")


def cmd_estimate(args):
    params = default_params()
    for kv in (args.set or []):
        if "=" not in kv:
            raise SystemExit(f"--set expects key=value, got '{kv}'")
        k, v = kv.split("=", 1)
        params[k] = _coerce(v)
    _print_metrics(estimate(params))


def cmd_sweep(args):
    base = default_params()
    # A small illustrative grid; the real DSE would drive its own.
    grid = {
        "dp": [1, 2, 4, 8, 10, 20, 50, 100],
        "cp": [1, 2, 13, 26],
    }
    results = sweep(base, grid)
    print_table(results, title=f"FULL SWEEP ({len(results)} points)")
    front = pareto(results, y_key="LUT")
    print()
    print_table(front, title=f"PARETO FRONT (latency vs LUT%, {len(front)} points)")


def main():
    ap = argparse.ArgumentParser(description="FPGA-HDC analytical cost estimator")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pe = sub.add_parser("estimate", help="estimate one design point")
    pe.add_argument("--set", action="append", metavar="key=value",
                    help="override a parameter (repeatable), e.g. --set dp=64")
    pe.set_defaults(func=cmd_estimate)

    psw = sub.add_parser("sweep", help="sweep a parameter grid and show the Pareto front")
    psw.set_defaults(func=cmd_sweep)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
