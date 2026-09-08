# WM-811K Wafer Map Dataset -- Attribution

**Source**: Wu, M.-J., Jang, J.-S. R., & Chen, J.-L. (2015). *Wafer Map Failure Pattern Recognition and Similarity Ranking for Large-Scale Data Sets*. IEEE Transactions on Semiconductor Manufacturing, 28(1), 1-12.

**Distribution**: https://www.kaggle.com/datasets/qingyi/wm811k-wafer-map (file `LSWMD.pkl`, ~2.1GB uncompressed). Not redistributed in this repository -- `data/wm811k/` is gitignored; download it yourself and place `LSWMD.pkl` in this directory.

## What it is

811,457 real wafer maps from 46,293 real production lots at a real semiconductor fab. Each wafer map is a 2D grid (0 = no die at that position, 1 = die passed test, 2 = die failed test) at the wafer's own real resolution -- resolutions vary across lots (346 distinct shapes among the labeled subset alone), reflecting real differences in wafer map granularity across products/tools.

172,950 of the 811,457 wafers were labeled by human reviewers into one of 8 real defect-pattern classes (Center, Donut, Edge-Loc, Edge-Ring, Loc, Near-full, Random, Scratch) or "none" (reviewed and found normal). The remaining 638,507 are real but unlabeled, and unused here since there's nothing to supervise a classifier against.

The dataset also carries a `trianTestLabel` field (its own spelling) marking each labeled wafer Test or Training, as assigned by the original authors -- this repo does not use that split (see `pipeline/wafer_data.py`'s `stratified_split` for why: it isn't class-stratified and skews ~69% Test / 31% Training, not a standard supervised-learning split). This project cuts its own stratified 80/10/10 split instead, stated explicitly rather than silently substituted.

## What this is not

This is real fab data, but it predates and is independent of the SMT2020 benchmark (`data/smt2020_lvhm/`) used elsewhere in this app -- the two datasets are not from the same fab and are not combined or cross-referenced anywhere in this pipeline.
