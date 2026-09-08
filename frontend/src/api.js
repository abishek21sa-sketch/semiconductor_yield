export async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}

export function fmtPct(x) {
  return x == null ? "—" : (x * 100).toFixed(1) + "%";
}
export function fmtNum(x, d = 0) {
  return x == null ? "—" : Number(x).toLocaleString(undefined, { maximumFractionDigits: d });
}
export function fmtMin(x) {
  return x == null || !isFinite(x) ? "∞" : fmtNum(x) + " min";
}
