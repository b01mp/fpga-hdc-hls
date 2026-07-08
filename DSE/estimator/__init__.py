"""
FPGA-HDC analytical cost estimator.

A fast, white-box model that predicts a design's latency, throughput, and
resource usage from its parameters -- WITHOUT running Vitis synthesis. Synthesis
takes minutes per point; this takes microseconds, so the DSE can score thousands
of design points and only synthesize the Pareto-optimal handful.

The estimator and the parameterized HLS library are two views of ONE cost model:
the library *realizes* the hardware (via pragmas), the estimator *predicts* it.
The per-primitive formulas here must stay consistent with the pragmas we add to
the primitive headers.

Modules
-------
  designpoint.py    the INPUT object (app + arch params)        [deferred / empty]
  models/device.py  per-device resource budgets
  models/datatypes.py  per-datatype op cost (Novelty 1 tie-in)
  models/primitives.py per-primitive latency + resource formulas
  compose.py        stitch primitives into an app pipeline
  estimate.py       top-level estimate(params) -> metrics
  sweep.py          sweep the parameter space -> table + Pareto front
  calibrate.py      fit constants against real csynth reports    [deferred / empty]
  cli.py            command line
"""
