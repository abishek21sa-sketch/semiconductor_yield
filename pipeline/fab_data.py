"""
Parses the real SMT2020 semiconductor-fab benchmark files (Kopp, Hassoun,
Kalir & Moench, IEEE TSM 2020 -- see data/smt2020_lvhm/ATTRIBUTION.md) into a
station-group-level fab topology.

Modeling choice, stated plainly: the raw benchmark defines ~100 individual
tool sub-families under 12 station groups (STNGRP) and routes with 300-500+
individual process steps. We aggregate to the STNGRP level (Diffusion,
Litho, Dry_Etch, Wet_Etch, ...) because that's the level a capacity/
scheduling decision actually gets made at, and it keeps the simulation and
optimization tractable. Every number at that level (processing times, batch
sizes, reentrancy counts, tool counts, MTBF/MTTR) is taken directly from the
real benchmark files, not invented.
"""
import re
from functools import lru_cache
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data" / "smt2020_lvhm"

# Real STNGRP categories present in tool.txt.1l for this benchmark fab.
STNGRP_PREFIXES = [
    ("WE_", "Wet_Etch"),
    ("Wet_Etch", "Wet_Etch"),
    ("DE_", "Dry_Etch"),
    ("Dry_Etch", "Dry_Etch"),
    ("Diffusion", "Diffusion"),
    ("DefMEt", "Def_Met"),
    ("DefMet", "Def_Met"),
    ("Def_Met", "Def_Met"),
    ("TF_Met", "TF_Met"),
    ("TF_", "TF"),
    ("LithoMet", "Litho_Met"),
    ("Litho_Met", "Litho_Met"),
    ("LithoTrack", "Litho"),
    ("Litho_REG", "Litho"),
    ("Litho", "Litho"),
    ("Implant", "Implant"),
    ("Dielectric", "Dielectric"),
    ("Planar", "Planar"),
    ("Delay", "Delay"),
]


def classify_stngrp(stnfam: str) -> str:
    for prefix, group in STNGRP_PREFIXES:
        if stnfam.startswith(prefix):
            return group
    return "Other"


@lru_cache(maxsize=1)
def load_station_groups() -> pd.DataFrame:
    """Real tool counts per station group + real MTBF/MTTR reliability data."""
    tool = pd.read_csv(DATA / "tool.txt.1l", sep="\t")
    counts = tool.groupby("STNGRP")["STN"].nunique().rename("n_tools").reset_index()

    downcal = pd.read_csv(DATA / "downcal.txt", sep="\t")
    downcal = downcal.rename(columns={"IGNORE": "STNGRP"})[["STNGRP", "MTTF", "MTTR"]]

    stations = counts.merge(downcal, on="STNGRP", how="left")
    # Delay_32 is a transport/queue-time placeholder in the benchmark, not a
    # physical tool -- it has no MTBF/MTTR row and effectively unlimited capacity.
    stations["n_tools"] = stations["n_tools"].fillna(1)
    stations["MTTF"] = stations["MTTF"].fillna(1e9)
    stations["MTTR"] = stations["MTTR"].fillna(0.0)
    stations["availability"] = stations["MTTF"] / (stations["MTTF"] + stations["MTTR"])
    return stations.set_index("STNGRP")


@lru_cache(maxsize=1)
def _route_files():
    return sorted(DATA.glob("route_*.txt"), key=lambda p: int(re.search(r"\d+", p.stem).group()))


def load_route(route_id: int) -> pd.DataFrame:
    """Real ordered process-step sequence for one product, aggregated to
    station-group level. PDIST/PTIME/PTIME2 are the benchmark's own
    stochastic processing-time distribution parameters (uniform(PTIME-PTIME2,
    PTIME+PTIME2) in minutes, per lot/batch/piece per PTPER)."""
    path = DATA / f"route_{route_id}.txt"
    r = pd.read_csv(path, sep="\t")
    r["STNGRP"] = r["STNFAM"].astype(str).apply(classify_stngrp)
    steps = []
    for row in r.itertuples():
        ptime = float(row.PTIME) if pd.notna(row.PTIME) else 0.0
        ptime2 = float(row.PTIME2) if pd.notna(row.PTIME2) else 0.0
        steps.append({
            "step": int(row.STEP),
            "desc": row.DESC,
            "stngrp": row.STNGRP,
            "mean_ptime_min": ptime,
            "spread_ptime_min": ptime2,
            "is_batch": row.PTPER == "per_batch",
            "batch_min": float(row.BATCHMN) if pd.notna(row.BATCHMN) else None,
            "batch_max": float(row.BATCHMX) if pd.notna(row.BATCHMX) else None,
        })
    return pd.DataFrame(steps)


def route_summary(route_id: int) -> dict:
    steps = load_route(route_id)
    total_ptime = steps["mean_ptime_min"].sum()
    by_group = steps.groupby("stngrp").agg(
        visits=("step", "count"), total_min=("mean_ptime_min", "sum"),
    ).sort_values("total_min", ascending=False)
    return {
        "route_id": route_id,
        "n_steps": len(steps),
        "total_process_min": float(total_ptime),
        "top_station_groups": [
            {"stngrp": g, "visits": int(v), "total_min": float(t)}
            for g, v, t in by_group.head(6).itertuples()
        ],
    }


def apply_station_overrides(stations: pd.DataFrame, overrides: dict | None) -> pd.DataFrame:
    """Returns a copy of the station-group table with scenario overrides
    applied (e.g. {"Litho": {"n_tools": 5}} for '2 tools down for PM')."""
    stations = stations.copy()
    if overrides:
        for grp, ov in overrides.items():
            if grp in stations.index:
                for k, v in ov.items():
                    stations.loc[grp, k] = v
    return stations


@lru_cache(maxsize=1)
def load_demand() -> pd.DataFrame:
    """Real per-product weekly demand rate, derived from the benchmark's own
    order.txt release-stream definitions (REPEAT = minutes between standard-
    priority lot releases for that part)."""
    order = pd.read_csv(DATA / "order.txt", sep="\t")
    std = order[order["PRIOR"] == order["PRIOR"].min()].copy()
    std["route_id"] = std["PART"].str.extract(r"(\d+)").astype(int)
    std["weekly_demand_lots"] = (60 * 24 * 7) / std["REPEAT"]
    return std.set_index("route_id")[["PART", "REPEAT", "weekly_demand_lots"]]


def available_products(n=3):
    """List of (route_id, part_name) from the real part.txt product table."""
    part = pd.read_csv(DATA / "part.txt", sep="\t")
    out = []
    for row in part.itertuples():
        m = re.search(r"\d+", row.ROUTEFILE)
        if m:
            out.append({"part": row.PART, "route_id": int(m.group())})
        if len(out) >= n:
            break
    return out
