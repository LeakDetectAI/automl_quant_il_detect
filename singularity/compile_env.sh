#!/bin/bash
rm -rf sandbox
rm -rf pycilt.sif
singularity build --sandbox ./sandbox ./pycilt.def
singularity build ./pycilt.sif ./sandbox/
rm -rf sandbox