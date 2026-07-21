# Python HDC API to HLS Templates

This directory contains a minimal Python front end for the paper's
Python-to-FPGA flow. It is not a general Python compiler and does not translate
arbitrary TorchHD programs. Instead, users write applications with the supported
`python_hdc` API calls, and each call is explicitly registered to one or more
HLS templates in the FPGA library.

The current flow is:

1. User code calls supported HDC functions such as `quantize`, `gather`, `bind`,
   `bundle`, `threshold`, and `similarity_search`.
2. The API records a typed application graph.
3. The lowering pass attaches HLS template candidates from `registry.py`.
4. The resulting JSON can be consumed by composition and DSE code.

Run the image-classification example:

```bash
python -m python_hdc.examples.image_classification --output build/image_classification_dse.json
```

Run the Python tests:

```bash
python -m unittest discover -s tests
```
