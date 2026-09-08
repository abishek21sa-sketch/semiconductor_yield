import { useCallback, useEffect, useRef, useState } from "react";
import Header from "../components/Header.jsx";
import Footer from "../components/Footer.jsx";
import HeroStats from "../components/HeroStats.jsx";
import PipelineFlow from "../components/PipelineFlow.jsx";
import ScenarioNav from "../components/ScenarioNav.jsx";
import WhatIfPanel from "../components/WhatIfPanel.jsx";
import YieldCard from "../components/YieldCard.jsx";
import SPCCard from "../components/SPCCard.jsx";
import TheoryCard from "../components/TheoryCard.jsx";
import CapacityCard from "../components/CapacityCard.jsx";
import SimCard from "../components/SimCard.jsx";
import OptCard from "../components/OptCard.jsx";
import CapacityPlanCard from "../components/CapacityPlanCard.jsx";
import DispatchCard from "../components/DispatchCard.jsx";
import WaferDefectsCard from "../components/WaferDefectsCard.jsx";
import RecommendationList from "../components/RecommendationList.jsx";
import { fetchJSON } from "../api.js";

export default function Workspace() {
  const [badge, setBadge] = useState("loading pipeline…");
  const [error, setError] = useState(null);

  const [scenarioList, setScenarioList] = useState([]);
  const [topology, setTopology] = useState(null);
  const [yieldData, setYieldData] = useState(null);

  const [activeScenario, setActiveScenario] = useState(null);
  const [scenarioData, setScenarioData] = useState(null);
  const [scenarioLoading, setScenarioLoading] = useState(false);

  const [capacityPlan, setCapacityPlan] = useState(null);
  const [dispatch, setDispatch] = useState(null);
  const [waferDefects, setWaferDefects] = useState(null);

  const scenarioCountRef = useRef(0);

  const loadScenario = useCallback(async (name) => {
    setActiveScenario(name);
    setScenarioLoading(true);
    try {
      const data = await fetchJSON(`/api/scenario/${name}`);
      setScenarioData(data);
    } finally {
      setScenarioLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function init() {
      const list = await fetchJSON("/api/scenarios");
      if (cancelled) return;
      setScenarioList(list);
      scenarioCountRef.current = list.length;

      setBadge("warming pipeline (real data)…");
      // eslint-disable-next-line no-constant-condition
      while (true) {
        const st = await fetchJSON("/api/status");
        if (cancelled) return;
        if (st.yield && Object.keys(st.scenarios).length >= list.length && st.capacity_plan && st.bottleneck_dispatch && st.wafer_defects) break;
        await new Promise((r) => setTimeout(r, 700));
      }
      if (cancelled) return;
      setBadge("● live — real data");

      const [topo, y] = await Promise.all([fetchJSON("/api/topology"), fetchJSON("/api/yield")]);
      if (cancelled) return;
      setTopology(topo);
      setYieldData(y);

      await loadScenario("baseline");
      if (cancelled) return;

      const [plan, disp, wafer] = await Promise.all([
        fetchJSON("/api/capacity_plan"),
        fetchJSON("/api/bottleneck_dispatch"),
        fetchJSON("/api/wafer_defects"),
      ]);
      if (cancelled) return;
      setCapacityPlan(plan);
      setDispatch(disp);
      setWaferDefects(wafer);
    }

    init().catch((e) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [loadScenario]);

  if (error) {
    return (
      <>
        <Header />
        <main id="main">
          <div className="card wide">
            <h2 style={{ color: "var(--critical)" }}>Error</h2>
            <div>{error}. Is the API server running?</div>
          </div>
        </main>
      </>
    );
  }

  return (
    <>
      <Header badge={badge} />

      {yieldData && topology ? (
        <HeroStats y={yieldData} topo={topology} opt={scenarioData?.optimization} wafer={waferDefects} />
      ) : (
        <section className="hero">
          <div className="stat-tile">
            <div className="value">…</div>
            <div className="label">Loading</div>
          </div>
        </section>
      )}

      <PipelineFlow />

      {scenarioList.length > 0 && (
        <ScenarioNav
          scenarios={scenarioList}
          activeKey={activeScenario}
          onSelect={loadScenario}
          description={scenarioData?.description ?? ""}
        />
      )}

      {topology && <WhatIfPanel topology={topology} />}

      <main id="main">
        {yieldData ? (
          <YieldCard y={yieldData} />
        ) : (
          <div className="card wide">
            <h2>Yield Risk — SECOM real fab sensor data</h2>
            <div className="card-sub">UCI ML Repository #179 · 1567 real production lots, real pass/fail outcomes</div>
            <div className="loading">
              <span className="spinner" />
              Running cross-validated model on real sensor data…
            </div>
          </div>
        )}

        {yieldData ? (
          <SPCCard spc={yieldData.spc} />
        ) : (
          <div className="card">
            <h2>SPC Control Chart</h2>
            <div className="card-sub">Top failure-driving sensor, 3-sigma band</div>
            <div className="loading">
              <span className="spinner" />
            </div>
          </div>
        )}

        <TheoryCard />

        {!scenarioLoading && scenarioData ? (
          <CapacityCard cap={scenarioData.capacity} />
        ) : (
          <div className="card">
            <h2>Capacity &amp; Bottleneck (scenario)</h2>
            <div className="card-sub">Real SMT2020 tool counts · Little's Law + Kingman G/G/m queueing</div>
            <div className="loading">
              <span className="spinner" />
              Computing…
            </div>
          </div>
        )}

        {!scenarioLoading && scenarioData ? (
          <SimCard sim={scenarioData.simulation} />
        ) : (
          <div className="card">
            <h2>Stochastic Simulation</h2>
            <div className="card-sub">SimPy discrete-event twin · Monte Carlo over dispatch/release policies</div>
            <div className="loading">
              <span className="spinner" />
              Computing…
            </div>
          </div>
        )}

        {!scenarioLoading && scenarioData ? (
          <OptCard opt={scenarioData.optimization} />
        ) : (
          <div className="card">
            <h2>Release Optimization</h2>
            <div className="card-sub">Gurobi MILP against real order-demand data</div>
            <div className="loading">
              <span className="spinner" />
              Computing…
            </div>
          </div>
        )}

        {capacityPlan ? (
          <CapacityPlanCard plan={capacityPlan} />
        ) : (
          <div className="card wide">
            <h2>Multi-Period Stochastic Capacity Plan</h2>
            <div className="card-sub">
              Two-stage stochastic Gurobi MILP: 10 products × 26 weeks, with recourse over
              Monte-Carlo capacity scenarios sampled from real MTBF/MTTR — large enough to need a
              real license, unlike the single-week plan above
            </div>
            <div className="loading">
              <span className="spinner" />
              Solving a multi-thousand-variable MILP…
            </div>
          </div>
        )}

        {dispatch ? (
          <DispatchCard d={dispatch} />
        ) : (
          <div className="card wide">
            <h2>Bottleneck Dispatch Scheduler</h2>
            <div className="card-sub">
              Exact MILP: real batch formation + parallel-machine sequencing, minimizing weighted
              tardiness against real due dates
            </div>
            <div className="loading">
              <span className="spinner" />
              Solving batch formation + parallel-machine scheduling…
            </div>
          </div>
        )}

        {waferDefects ? (
          <WaferDefectsCard w={waferDefects} />
        ) : (
          <div className="card wide">
            <h2>Wafer Defect Pattern Classification</h2>
            <div className="card-sub">
              Real CNN over the real WM-811K wafer defect-map dataset (172,950 human-labeled real
              wafers, 9 classes)
            </div>
            <div className="loading">
              <span className="spinner" />
              Loading trained model artifacts…
            </div>
          </div>
        )}

        {!scenarioLoading && scenarioData ? (
          <RecommendationList lines={scenarioData.recommendation} />
        ) : (
          <div className="card wide">
            <h2>Explainable Recommendation</h2>
            <div className="card-sub">Each line is tagged with its evidence source</div>
            <ul className="rec-list">
              <li>Loading…</li>
            </ul>
          </div>
        )}
      </main>

      <Footer />
    </>
  );
}
