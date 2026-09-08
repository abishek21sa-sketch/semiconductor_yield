"""
Stochastic discrete-event digital twin of the real SMT2020 reentrant fab
(see fab_data.py / data/smt2020_lvhm/ATTRIBUTION.md), built with SimPy.

Each station group is a simpy.PreemptiveResource sized to its real tool
count. Each individual tool independently cycles up/down on the benchmark's
real exponential MTBF/MTTR, using a low-priority "self request" that
preempts lot processing -- the standard SimPy machine-breakdown idiom. Lots
follow their route's real per-step sequence and station-group assignment
(from fab_data.load_route). Dispatch rule and release policy are the two
levers a scenario controls; everything else -- topology, times, failure
rates -- comes from the real benchmark.
"""
import random
import statistics
from dataclasses import dataclass, field

import simpy

from . import fab_data

BREAKDOWN_PRIORITY = -1
LOT_PRIORITY = 0


@dataclass
class SimResult:
    completed: int
    started: int
    cycle_times: list = field(default_factory=list)
    max_wip: int = 0
    tool_busy_time: dict = field(default_factory=dict)
    tool_down_time: dict = field(default_factory=dict)

    def summary(self):
        ct = sorted(self.cycle_times)
        n = len(ct)
        def pct(p):
            if not n:
                return None
            idx = min(n - 1, int(p * n))
            return ct[idx]
        return {
            "lots_started": self.started,
            "lots_completed": self.completed,
            "mean_cycle_time_min": statistics.mean(ct) if ct else None,
            "p50_cycle_time_min": pct(0.5),
            "p95_cycle_time_min": pct(0.95),
            "max_wip": self.max_wip,
        }


def _make_breakdown_process(env, resource, n_tools, mttf, mttr, tool_down_time, key, rng):
    def one_tool_lifecycle(tool_idx):
        while True:
            yield env.timeout(rng.expovariate(1.0 / mttf))
            down_start = env.now
            with resource.request(priority=BREAKDOWN_PRIORITY) as req:
                yield req
                dur = rng.expovariate(1.0 / mttr) if mttr > 0 else 0.0
                yield env.timeout(dur)
            tool_down_time[key] = tool_down_time.get(key, 0.0) + (env.now - down_start)

    for i in range(n_tools):
        env.process(one_tool_lifecycle(i))


def _remaining_ptime(steps, from_idx):
    return sum(s["mean_ptime_min"] for s in steps[from_idx:])


def run_simulation(
    route_ids,
    sim_minutes=60 * 24 * 30,          # 30 simulated days
    release_interval_min=800.0,        # mean minutes between lot releases (push mode)
    dispatch_rule="fifo",              # "fifo" | "spt" | "cr"
    release_mode="push",               # "push" | "conwip"
    conwip_cap=15,
    flow_allowance=3.0,                # due_date = release_time + flow_allowance * raw_process_time
    seed=42,
    warmup_min=60 * 24 * 5,            # exclude first N minutes of completions from stats (ramp-up)
    station_overrides=None,            # e.g. {"Litho": {"n_tools": 5}} for a tool-down scenario
):
    rng = random.Random(seed)
    env = simpy.Environment()
    stations = fab_data.apply_station_overrides(fab_data.load_station_groups(), station_overrides)
    routes = {rid: fab_data.load_route(rid).to_dict("records") for rid in route_ids}

    resources = {}
    tool_down_time = {}
    for stngrp, row in stations.iterrows():
        if stngrp == "Delay":
            continue
        n = max(int(row["n_tools"]), 1)
        res = simpy.PreemptiveResource(env, capacity=n)
        resources[stngrp] = res
        _make_breakdown_process(env, res, n, float(row["MTTF"]), float(row["MTTR"]), tool_down_time, stngrp, rng)

    result = SimResult(completed=0, started=0)
    conwip_slots = simpy.Resource(env, capacity=conwip_cap) if release_mode == "conwip" else None
    wip = {"n": 0}

    def priority_for(rule, step, remaining_after, due_date):
        if rule == "spt":
            return step["mean_ptime_min"]
        if rule == "cr":
            cr = (due_date - env.now) / max(remaining_after, 1e-6)
            return cr
        return env.now  # fifo: earlier arrival = lower "priority number" = served first

    def lot_process(route_id):
        steps = routes[route_id]
        release_time = env.now
        raw_total = sum(s["mean_ptime_min"] for s in steps)
        due_date = release_time + flow_allowance * raw_total
        wip["n"] += 1
        result.max_wip = max(result.max_wip, wip["n"])
        result.started += 1

        for idx, step in enumerate(steps):
            grp = step["stngrp"]
            mean_pt = step["mean_ptime_min"]
            spread = step["spread_ptime_min"]
            if grp == "Delay" or grp not in resources:
                yield env.timeout(max(mean_pt, 0.0))
                continue
            remaining_after = _remaining_ptime(steps, idx)
            prio = priority_for(dispatch_rule, step, remaining_after, due_date)
            res = resources[grp]
            lo, hi = max(mean_pt - spread, 0.01), mean_pt + spread
            remaining = rng.uniform(lo, hi) if hi > lo else mean_pt
            # Retry loop: a tool breakdown (priority BREAKDOWN_PRIORITY) preempts an
            # in-progress lot and raises simpy.Interrupt; resume with the leftover duration.
            while remaining > 1e-9:
                with res.request(priority=prio) as req:
                    yield req
                    start = env.now
                    try:
                        yield env.timeout(remaining)
                        result.tool_busy_time[grp] = result.tool_busy_time.get(grp, 0.0) + (env.now - start)
                        remaining = 0.0
                    except simpy.Interrupt:
                        elapsed = env.now - start
                        result.tool_busy_time[grp] = result.tool_busy_time.get(grp, 0.0) + elapsed
                        remaining -= elapsed

        wip["n"] -= 1
        if env.now >= warmup_min:
            result.completed += 1
            result.cycle_times.append(env.now - release_time)
        if conwip_slots is not None:
            pass  # slot released automatically by `with` block in release_loop

    def push_release_loop():
        while True:
            yield env.timeout(rng.expovariate(1.0 / release_interval_min))
            rid = route_ids[result.started % len(route_ids)]
            env.process(lot_process(rid))

    def lot_with_slot(rid):
        with conwip_slots.request() as slot:
            yield slot
            yield from lot_process(rid)

    def conwip_release_loop():
        i = 0
        while True:
            yield env.timeout(rng.expovariate(1.0 / release_interval_min))
            rid = route_ids[i % len(route_ids)]
            i += 1
            env.process(lot_with_slot(rid))

    if release_mode == "conwip":
        env.process(conwip_release_loop())
    else:
        env.process(push_release_loop())

    env.run(until=sim_minutes)

    util = {}
    for grp in resources:
        busy = result.tool_busy_time.get(grp, 0.0)
        down = tool_down_time.get(grp, 0.0)
        n = int(stations.loc[grp, "n_tools"])
        util[grp] = {
            "utilization": busy / (n * sim_minutes) if sim_minutes else 0.0,
            "down_fraction": down / (n * sim_minutes) if sim_minutes else 0.0,
        }

    out = result.summary()
    out["tool_utilization"] = util
    out["params"] = {
        "route_ids": route_ids, "dispatch_rule": dispatch_rule, "release_mode": release_mode,
        "release_interval_min": release_interval_min, "conwip_cap": conwip_cap, "seed": seed,
    }
    return out


def monte_carlo_policy_comparison(route_ids, release_interval_min, policies, n_replications=5, sim_days=20, station_overrides=None):
    """policies: list of dicts like {"name": "...", "dispatch_rule": "fifo", "release_mode": "push", "conwip_cap": 15}
    Runs each policy across n_replications seeds; returns mean/P95 cycle time and a
    tail-risk (CVaR-style: mean of the worst 20% of replication-level P95s)."""
    out = []
    for pol in policies:
        p95s, means = [], []
        for rep in range(n_replications):
            r = run_simulation(
                route_ids,
                sim_minutes=60 * 24 * sim_days,
                release_interval_min=release_interval_min,
                dispatch_rule=pol.get("dispatch_rule", "fifo"),
                release_mode=pol.get("release_mode", "push"),
                conwip_cap=pol.get("conwip_cap", 15),
                seed=1000 * rep + hash(pol["name"]) % 1000,
                warmup_min=60 * 24 * 3,
                station_overrides=station_overrides,
            )
            if r["p95_cycle_time_min"] is not None:
                p95s.append(r["p95_cycle_time_min"])
                means.append(r["mean_cycle_time_min"])
        p95s_sorted = sorted(p95s)
        tail_n = max(1, int(0.2 * len(p95s_sorted)))
        cvar95 = statistics.mean(p95s_sorted[-tail_n:]) if p95s_sorted else None
        out.append({
            "policy": pol["name"],
            "n_replications": len(p95s),
            "mean_cycle_time_min": statistics.mean(means) if means else None,
            "mean_p95_cycle_time_min": statistics.mean(p95s) if p95s else None,
            "cvar_tail_p95_cycle_time_min": cvar95,
        })
    return out
