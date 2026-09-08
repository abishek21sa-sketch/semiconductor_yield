const ABBR = {
  none: "None", Center: "Ctr", Donut: "Dnt", "Edge-Loc": "E-L", "Edge-Ring": "E-R",
  Loc: "Loc", "Near-full": "N-f", Random: "Rnd", Scratch: "Scr",
};

export default function ConfusionMatrix({ classes, matrix }) {
  const rowMax = matrix.map((row) => Math.max(...row, 1));
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ borderCollapse: "collapse", fontSize: 10.5 }}>
        <thead>
          <tr>
            <th style={{ padding: 4 }}></th>
            {classes.map((c) => (
              <th key={c} style={{ padding: 4, color: "var(--text-muted)", fontWeight: 600 }}>
                {ABBR[c] ?? c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.map((row, i) => (
            <tr key={classes[i]}>
              <th style={{ padding: 4, textAlign: "right", color: "var(--text-muted)", fontWeight: 600 }}>
                {ABBR[classes[i]] ?? classes[i]}
              </th>
              {row.map((v, j) => {
                const opacity = v === 0 ? 0 : 0.15 + 0.85 * (v / rowMax[i]);
                return (
                  <td key={j} style={{ padding: 0 }}>
                    <div
                      style={{
                        width: 34, height: 26, display: "flex", alignItems: "center", justifyContent: "center",
                        background: `rgba(57,135,229,${opacity})`,
                        color: opacity > 0.55 ? "#06111f" : "var(--text-secondary)",
                        fontFamily: "ui-monospace, monospace", fontWeight: i === j ? 700 : 400,
                        border: i === j ? "1px solid var(--s1-blue)" : "1px solid transparent",
                      }}
                    >
                      {v > 0 ? v : ""}
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 6 }}>
        Rows = real label, columns = predicted label. Diagonal (outlined) = correct.
      </div>
    </div>
  );
}
