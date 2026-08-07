# HDC FPGA Application Composition and P&R Validation Task

## Purpose

This document summarizes the current project goal and the immediate task for
validating application-level composition on an FPGA target. The goal is not only
to synthesize individual HDC library functions, but to show that a complete HDC
application can be built by composing reusable library functions, selected by
DSE, and validated through whole-design synthesis and place-and-route.

## Project Context

The project is an FPGA-oriented HDC library. HDC applications are expressed as
compositions of reusable library functions such as memory lookup, binding,
bundling, thresholding, and similarity search. Each function can expose
application-level parameters, such as hypervector dimension, datatype, number of
features, and number of prototypes. Architecture choices, such as dimension
parallelism, class parallelism, memory placement, banking, and storage mode, are
treated as implementation candidates for DSE.

The current DSE flow uses per-function characterization results as the input
database. Each function is swept independently across selected knobs, and the
resulting CSV files record latency and resource usage for candidate
implementations. Application-level DSE then composes these per-function
candidates into estimated end-to-end application candidates. These estimates are
used to select a small number of finalists. The finalists must still be validated
by implementing a composed application top and running whole-design HLS
synthesis and P&R.

## Immediate Target Application

The first end-to-end target should be a basic image-classification HDC
application. This is a suitable first application because it exercises the common
HDC inference path:

```text
codebook lookup -> encoding/binding -> bundling -> thresholding -> prototype search
```

In library-function terms, the initial non-pipelined composition can be:

```text
gather -> gather -> bind -> bundle -> threshold -> similarity_search
```

The first `gather` reads the feature or position hypervector. The second
`gather` reads the value or level hypervector. `bind` combines them into an
encoded feature hypervector. `bundle` accumulates encoded feature hypervectors.
`threshold` converts the accumulated vector into a query hypervector.
`similarity_search` compares the query against class prototypes and returns the
predicted label.

## Execution Model for the First Validation

The first validation should use non-pipelined staged execution. This means all
functions can be instantiated in the composed top, but different input samples
are not overlapped across stages. Intermediate hypervectors are materialized in
local on-chip arrays rather than passed through streaming FIFOs.

For the first version, the composed top can use local buffers such as:

```text
feature_hv[D]
value_hv[D]
bound_hv[D]
acc[D]
query_hv[D]
```

This keeps the implementation simple and directly validates whether the library
functions can be connected into a complete application. Later versions can add
streaming/dataflow execution, stage overlap, or more aggressive buffer
placement.

## Expected Environment

On the Vitis server, initialize the tool environment before building:

```bash
source /opt/xilinx/xrt/setup.sh
source /tools/Xilinx/Vitis/2024.2/settings64.sh
```

Then verify that the tools and U280 platform are visible:

```bash
which v++
which vivado
which vitis_hls
which platforminfo
v++ --version
vivado -version
platforminfo -l | grep -i u280
```

If the U280 platform is not automatically visible, set `PLATFORM_REPO_PATHS` or
pass the full `.xpfm` path directly to `v++`.

## Main Tasks

1. Select one image-classification DSE finalist.

   Use the composed DSE result generated from per-function characterization.
   The selected finalist should specify the candidate implementation for each
   stage, including the relevant datatype, dimension parallelism, class
   parallelism, memory placement, and banking choices where applicable.

2. Implement a composed top.

   Add an application-level top function, for example:

   ```text
   image_classification_top()
   ```

   This top should instantiate the existing library functions and connect them
   through local arrays. The top should be parameterized enough to match the
   selected DSE candidate, but it does not need to support the full design space
   in the first version.

3. Add a correctness testbench.

   The testbench should use a small synthetic classification problem or a small
   extracted workload. The expected output should be checked against a simple
   software HDC reference path. The first success criterion is functional
   correctness, not performance.

4. Run HLS C simulation.

   Confirm that the composed application top produces the same label as the
   software reference. This validates the application composition logic.

5. Run whole-top HLS synthesis.

   Synthesize `image_classification_top` as one composed top. Record latency,
   initiation interval if reported, and estimated LUT, FF, DSP, BRAM, and URAM
   usage. This result should be compared against the DSE estimate.

6. Run U280 hardware implementation/P&R.

   Package or link the composed top for the U280 platform using Vitis/Vivado.
   The implementation flow should produce post-implementation resource, timing,
   and power reports. This is the evidence needed to show that the composed
   application design is not only HLS-synthesizable but also implementable on the
   target FPGA.

## Deliverables

The minimum useful deliverables are:

- A composed image-classification top function.
- A C-simulation testbench for the composed top.
- A script or command log for running HLS synthesis.
- A script or command log for U280 hardware implementation/P&R.
- A short result summary containing:
  - selected DSE candidate;
  - HLS latency and resource estimate;
  - post-P&R resource usage;
  - timing result or achieved clock;
  - power estimate, if available;
  - comparison between DSE estimate and whole-design result.

## What This Validates

This task validates three claims needed for the paper:

1. The HDC library functions are composable into a complete application.
2. Per-function characterization can guide application-level DSE by selecting
   candidate implementations for each stage.
3. A DSE-selected composed design can pass whole-design FPGA implementation on
   the U280 target.

## Current Boundaries

The first version does not need to implement streaming/dataflow overlap across
multiple input samples. It also does not need to prove global optimality across
the full design space. The expected result is a working, non-pipelined
application-level composition with enough synthesis and P&R evidence to support
the DSE and composability story.

## Open Items to Confirm

- Exact U280 `.xpfm` path on the Vitis server.
- Whether the current server license supports full hardware implementation/P&R.
- Which image-classification dataset or small workload should be used for the
  first correctness baseline.
- Which DSE finalist should be implemented first.
- Whether power should be reported from post-implementation estimation or from a
  board-level measurement.
