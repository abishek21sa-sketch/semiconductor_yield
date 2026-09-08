/** Live client-side recompute of station utilization against the real SMT2020 topology --
 * same formula as pipeline/capacity.py, evaluated in the browser for instant slider feedback. */
export function computeWhatIf(topology, diffTools, lithoTools, weeklyRate) {
  const stations = topology.stations;
  const overrides = { Diffusion: diffTools, Litho: lithoTools };
  const releasePerMinPerRoute = weeklyRate / topology.route_ids.length / (60 * 24 * 7);
  const results = [];
  for (const [grp, s] of Object.entries(stations)) {
    if (grp.startsWith("Delay")) continue;
    const nTools = overrides[grp] ?? s.n_tools;
    let load = 0;
    for (const rid of topology.route_ids) {
      load += releasePerMinPerRoute * (topology.routes[rid][grp] || 0);
    }
    const capacityPerMin = nTools * s.availability;
    const utilization = capacityPerMin > 0 ? load / capacityPerMin : Infinity;
    results.push({ key: grp, label: grp, utilization, n_tools: nTools });
  }
  return results;
}
