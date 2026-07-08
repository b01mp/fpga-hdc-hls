"""
sweep.py -- enumerate the parameter space with the fast estimator, and extract
the Pareto front.

This is the DSE-facing tool: it brute-forces combinations of architecture
parameters, scores each with estimate() in microseconds, and returns the
non-dominated (Pareto-optimal) points -- the shortlist worth actually
synthesizing. It is the *evaluation engine*; a real DSE wraps smarter search and
real-synthesis verification around it.
"""
import itertools
from .estimate import estimate


def sweep(base, grid):
    """Run estimate() over the cartesian product of `grid`.

    base : dict of fixed params (e.g. the app config).
    grid : dict of param_name -> list of values to sweep.
    returns: list of metric dicts (each carries its own 'params').
    """
    keys = list(grid)
    results = []
    for combo in itertools.product(*(grid[k] for k in keys)):
        params = dict(base)
        params.update(dict(zip(keys, combo)))
        results.append(estimate(params))
    return results


def pareto(results, x="latency_us", y_key="LUT"):
    """Non-dominated points minimizing latency `x` and a resource utilization
    `y_key` (one of LUT/FF/DSP/BRAM36/URAM). Infeasible points are dropped."""
    pts = [r for r in results if r["feasible"]]

    def yv(r):
        return r["util_pct"][y_key]

    front = []
    for r in pts:
        dominated = any(
            (o is not r)
            and o[x] <= r[x] and yv(o) <= yv(r)
            and (o[x] < r[x] or yv(o) < yv(r))
            for o in pts
        )
        if not dominated:
            front.append(r)
    front.sort(key=lambda r: r[x])
    return front


def print_table(results, title=None):
    if title:
        print(title)
    hdr = (f"{'DP':>4} {'FP':>4} {'CP':>4} {'mem':>5} "
           f"{'lat(us)':>11} {'thru(/s)':>11} "
           f"{'LUT%':>6} {'DSP%':>6} {'BRAM%':>6} {'URAM%':>6} {'fit':>4}")
    print(hdr)
    print("-" * len(hdr))
    for r in results:
        p, u = r["params"], r["util_pct"]
        print(f"{p['dp']:>4} {p['fp']:>4} {p['cp']:>4} {p['memory_space']:>5} "
              f"{r['latency_us']:>11.1f} {r['throughput_infps']:>11.1f} "
              f"{u['LUT']:>6.1f} {u['DSP']:>6.1f} {u['BRAM36']:>6.1f} {u['URAM']:>6.1f} "
              f"{('Y' if r['feasible'] else 'N'):>4}")
