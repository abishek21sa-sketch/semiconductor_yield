import { NavLink } from "react-router-dom";

export default function Header({ badge }) {
  return (
    <header>
      <div>
        <h1>Fab Yield &amp; Capacity Decision Intelligence</h1>
        <div className="sub">
          Real SECOM fab sensor data + the published SMT2020 semiconductor-fab benchmark
          (IEEE Trans. Semiconductor Manufacturing, 2020) — not a demo dataset written for this app.
        </div>
      </div>
      <div className="header-right">
        <nav className="top-nav">
          <NavLink to="/" end className={({ isActive }) => (isActive ? "active" : "")}>
            Workspace
          </NavLink>
          <NavLink to="/methodology" className={({ isActive }) => (isActive ? "active" : "")}>
            Methodology
          </NavLink>
        </nav>
        {badge && <div className="badge">{badge}</div>}
      </div>
    </header>
  );
}
