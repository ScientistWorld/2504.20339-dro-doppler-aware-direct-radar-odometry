#!/bin/bash
# Run DRO variants on the local synthetic radar benchmark.

set -e

cd /home/user

[ -e data/synthetic_dro.npz ] || bash scripts/download.sh
mkdir -p checkpoints/dro_synthetic
python method/dro_synthetic.py --mode dro_gd --data data/synthetic_dro.npz --output-dir checkpoints/dro_synthetic
python method/dro_synthetic.py --mode dro_g --data data/synthetic_dro.npz --output-dir checkpoints/dro_synthetic
python method/dro_synthetic.py --mode dro_d --data data/synthetic_dro.npz --output-dir checkpoints/dro_synthetic
