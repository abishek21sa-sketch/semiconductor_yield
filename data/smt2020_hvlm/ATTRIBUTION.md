# SMT2020 HVLM Dataset Attribution

Source: Kopp, D., Hassoun, M., Kalir, A., & Mönch, L. (2020).
"SMT2020 — A Semiconductor Manufacturing Testbed." IEEE Transactions on
Semiconductor Manufacturing.

Official distribution: https://p2schedgen.fernuni-hagen.de/index.php/downloads/simulation

These raw dataset files were obtained via the open research artifact
"PySCFabSim-revised" (github.com/david-dd/PySCFabSim-revised,
datasets/SMT2020_HVLM/, mirroring the same Zenodo-hosted CC-licensed
research data used for `data/smt2020_lvhm/`), which redistributes the
SMT2020 testbed files unmodified for simulation research and reproduction.

This is the HVLM (High-Volume-Low-Mix) archetype from the same published
SMT2020 testbed as `data/smt2020_lvhm/` (LVHM, Low-Volume-High-Mix) --
the benchmark's authors publish four archetype configurations in total
(LVHM, HVLM, LVHM_E, HVLM_E); this app uses the two base configurations.

**Real relationship between the two archetypes, used explicitly in
`pipeline/archetype_comparison.py`**: HVLM shares the exact same real tool
inventory (`tool.txt.1l`) and real reliability data (`downcal.txt`) as
LVHM -- 106 tools total, identical per-station-group counts and MTBF/MTTR.
It also reuses two of LVHM's own route files verbatim (`route_3.txt` and
`route_4.txt` are byte-identical between the two archetype folders). The
real difference is `order.txt`: LVHM's real demand spreads ~390 lots/week
across all 10 products; HVLM's real demand concentrates the same ~390
lots/week onto just these 2 products. This is genuinely the same
benchmark fab under a different real product-mix/demand-concentration
scenario, not two unrelated fabs -- which is what makes a same-tools,
different-demand-pattern comparison honest rather than an apples-to-oranges
stretch.

As with LVHM: this is a published academic benchmark representing
realistic reentrant semiconductor fab characteristics, not proprietary
data from any specific real company's fab.
