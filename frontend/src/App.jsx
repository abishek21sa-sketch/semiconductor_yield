import { Routes, Route } from "react-router-dom";
import Workspace from "./pages/Workspace.jsx";
import Methodology from "./pages/Methodology.jsx";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Workspace />} />
      <Route path="/methodology" element={<Methodology />} />
    </Routes>
  );
}
