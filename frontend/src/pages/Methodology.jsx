import Header from "../components/Header.jsx";
import Footer from "../components/Footer.jsx";

const ITEMS = [
  {
    num: "01 · DATA",
    title: "Three real datasets, not one written for this app",
    body: (
      <>
        SECOM (UCI #179): 1567 real lots, 590 real anonymized sensors, real pass/fail. WM-811K
        (Wu, Jang &amp; Chen, <em>IEEE TSM</em> 2015): 811,457 real wafer maps, 172,950 human-labeled
        into 9 real classes. SMT2020 (Kopp, Hassoun, Kalir &amp; Mönch, <em>IEEE TSM</em> 2020):
        the published academic benchmark for reentrant wafer-fab simulation — real routes, real
        tool counts, real MTBF/MTTR, published in two real archetype configurations (LVHM and
        HVLM) this app uses both of.
      </>
    ),
  },
  {
    num: "02 · YIELD MODEL",
    title: "Cross-validated, not overfit",
    body: (
      <>
        <code>RandomForestClassifier</code>, class-balanced, 5-fold stratified CV with
        out-of-fold predictions — no leakage. Evaluated on ROC/PR-AUC, not accuracy, because the
        real fail rate is 6.6% and accuracy alone is misleading on imbalanced data.
      </>
    ),
  },
  {
    num: "03 · WAFER DEFECT CNN",
    title: "A real CNN, real class imbalance",
    body: (
      <>
        A PyTorch CNN over all 172,950 human-labeled real WM-811K wafers (9 classes). Each real
        wafer map is resized to a fixed 64×64 with nearest-neighbor interpolation — preserves the
        real discrete die states (no die / pass / fail) instead of inventing fake intermediate
        values a linear resize would. Trained with class-weighted loss against a genuine ~1000:1
        imbalance (147,431 "none" vs 149 "Near-full"); the training split additionally caps
        "none" to 25,000 of its real 117,944 training examples so an epoch isn't almost entirely
        spent on the majority class — every other class keeps every real example, and
        validation/test stay the real, un-rebalanced distribution. Evaluated on macro-F1 and
        per-class precision/recall, not accuracy, same reasoning as the yield model. The raw file
        itself needed a real fix first: it was pickled under Python 2 with a ~2019 pandas version,
        so a small custom <code>pickle.Unpickler</code> subclass (
        <code>pipeline/wafer_data.py</code>) redirects a renamed internal pandas module and
        decodes the raw bytes correctly — a real fix, not a workaround that drops data.
      </>
    ),
  },
  {
    num: "04 · CNN EXPLAINABILITY & BASELINE",
    title: "Prove the complexity earns its keep",
    body: (
      <>
        Two checks against building a CNN just because it's fashionable. First, a hand-engineered-
        feature baseline (<code>pipeline/wafer_baseline.py</code>): 6 classic wafer-map features
        (defect density, radial centroid, radial spread, edge concentration, connected-component
        structure) into a class-weighted RandomForest, trained/evaluated on the exact same real
        split as the CNN — so the macro-F1 gap between them is a genuine apples-to-apples "does the
        spatial modeling earn its complexity" comparison, not two different splits that happen to
        look similar. Second, real Grad-CAM (Selvaraju et al. 2017) computed from the trained
        model's own gradients on each sample-gallery wafer — shows which real pixels actually drove
        each prediction, not just what the prediction was.
      </>
    ),
  },
  {
    num: "05 · QUEUEING THEORY",
    title: "Textbook math, unit-tested against itself",
    body: (
      <>
        Little's Law and Kingman's G/G/m (VUT) approximation — closed-form 1961 results, not fit
        to data. Kingman is unit-tested to match the exact M/M/1 formula at c<sub>a</sub>²=c
        <sub>s</sub>²=1, m=1.
      </>
    ),
  },
  {
    num: "06 · SIMULATION",
    title: "Real breakdown physics, not a toy queue",
    body: (
      <>
        SimPy discrete-event twin: each of the real fab's tools independently cycles up/down on
        the benchmark's real exponential MTBF/MTTR via a preemptive-resource idiom. Lots follow
        their route's real 500+-step reentrant sequence. Monte Carlo replications, not one seed.
      </>
    ),
  },
  {
    num: "07 · OPTIMIZATION",
    title: "Real integer programs, real solver",
    body: (
      <>
        Three Gurobi MILPs at three different scales. The single-week release mix (~10 variables)
        maximizes weighted release subject to real per-station-group capacity, with a
        minimum-fill-rate floor modeling a contractual service commitment — explicit in code, not
        hidden. The multi-period stochastic capacity plan (3,380 variables / 5,990 constraints)
        adds 26 weeks of here-and-now release decisions plus recourse variables for capacity
        shortfall under Monte Carlo scenarios sampled from real MTBF/MTTR. The bottleneck dispatch
        scheduler (tens of thousands of variables) does exact batch formation and time-indexed
        parallel-machine sequencing at the real bottlenecks. All three detect and report
        infeasibility — or a missing license — rather than silently degrading.
      </>
    ),
  },
  {
    num: "08 · WHY NOT FULL-FAB EXACT SCHEDULING",
    title: "A scoped-down MILP, deliberately",
    body: (
      <>
        An exact schedule for every lot at every station across the whole fab is combinatorially
        intractable at real scale — a time-indexed formulation over the benchmark's full route set
        would need on the order of 180,000 variables, well past what any solver resolves in
        practical time. The bottleneck dispatch scheduler instead applies the same exact
        machinery (batch formation + time-indexed sequencing) only at the two real constraining
        resources (Diffusion, Dry_Etch) — a standard Theory-of-Constraints scoping choice, not a
        shortcut taken because the full problem wasn't understood.
      </>
    ),
  },
  {
    num: "09 · CROSS-PIPELINE INTEGRATION",
    title: "Real datasets as planning parameters, not a fake join",
    body: (
      <>
        SECOM and this SMT2020 fab are different real fabs — nothing here claims otherwise. What{" "}
        <code>pipeline/capacity_plan.py</code>'s <code>yield_rate</code> parameter does is use the
        real calibrated SECOM yield rate as a representative real-world planning assumption inside
        the SMT2020 capacity plan (netting raw releases down to real good units), exactly how real
        fabs plan when they don't have this specific line's own yield data yet. Separately,{" "}
        <code>pipeline/quality_risk.py</code> maps the real WM-811K defect-type distribution onto
        the SMT2020 station groups conventionally associated with that defect <em>pattern</em> in
        yield-engineering practice — a stated heuristic mapping, not derived co-occurrence data.
        The result, in this app's own real numbers: the capacity bottleneck (Diffusion) and the
        top quality-risk area (Wet_Etch) are different stations — fixing one wouldn't fix the
        other, a genuinely useful finding neither dataset shows on its own.
      </>
    ),
  },
  {
    num: "10 · ARCHETYPE COMPARISON",
    title: "Same fab, same tools, different demand concentration",
    body: (
      <>
        LVHM and HVLM are real SMT2020 configurations that share the exact same 106-tool real
        inventory and even reuse two of the same real route files verbatim — the real difference
        is how real demand concentrates (LVHM spreads ~390 lots/week across 10 products; HVLM
        concentrates the same ~390 lots/week onto 2). Evaluated at the same total system release
        rate so the comparison isn't an artifact of picking two different paces,{" "}
        <code>pipeline/archetype_comparison.py</code> shows concentrating demand onto fewer
        products makes the same real bottleneck's Kingman queueing wait measurably worse — same
        capacity, same tools, worse congestion, purely from product-mix strategy.
      </>
    ),
  },
  {
    num: "11 · PERSISTENCE & ACCESS",
    title: "A real backend, not just a compute script",
    body: (
      <>
        Every computed result is persisted via SQLAlchemy models and Alembic migrations (SQLite
        locally, Postgres in Docker via <code>DATABASE_URL</code>) — <code>/api/history</code>{" "}
        reads back real rows a prior request wrote, not synthesized data. <code>/api/*</code> is
        open by default for zero-setup local/demo use, and enforces a real <code>X-API-Key</code>{" "}
        check when the <code>API_KEY</code> environment variable is set.
      </>
    ),
  },
  {
    num: "12 · MODELING CHOICES",
    title: "Stated, not hidden",
    body: (
      <>
        ~100 individual tool sub-families aggregated to 12 station groups for tractability.
        SMT2020 is a published benchmark representing realistic fab characteristics, not one
        company's proprietary data — nothing here is validated against a named plant.
      </>
    ),
  },
];

export default function Methodology() {
  return (
    <>
      <Header />
      <section className="methodology">
        <h2>Methodology</h2>
        <div className="card-sub">What's real, what's modeled, and why each technique was chosen</div>
        <div className="method-grid">
          {ITEMS.map((item) => (
            <div className="method-item" key={item.num}>
              <div className="m-num">{item.num}</div>
              <h3>{item.title}</h3>
              <p>{item.body}</p>
            </div>
          ))}
        </div>
      </section>
      <Footer />
    </>
  );
}
