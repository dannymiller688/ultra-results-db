"""Queries core.splits/results for a given event and generates a
self-contained HTML chart: cumulative distance vs elapsed time per runner,
with a user-adjustable baseline pace line.

Usage:
    python -m ultra_results.generate_chart <race_name> [out_path]
"""
import json
import sys

from ultra_results.loader import get_conn

HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{title}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<style>
  body {{ font-family: -apple-system, Arial, sans-serif; margin: 2rem; background: #fafafa; }}
  h1 {{ font-size: 1.3rem; }}
  #controls {{ margin-bottom: 1rem; }}
  #controls label {{ font-size: 0.9rem; margin-right: 0.5rem; }}
  #controls input {{ font-size: 0.9rem; padding: 4px 8px; width: 100px; }}
  #chart-container {{ background: white; padding: 1rem; border-radius: 8px; max-width: 1000px; }}
</style>
</head>
<body>
<h1>{title}</h1>
<div id="controls">
  <label for="baseline">Baseline goal distance (miles):</label>
  <input type="number" id="baseline" value="100" step="1">
  <span style="font-size:0.85rem;color:#666;margin-left:1rem;">Dashed line = even pace to hit this distance in {duration_hours} hours</span>
</div>
<div id="chart-container">
  <canvas id="chart" height="120"></canvas>
</div>

<h2 style="font-size:1.1rem;margin-top:2rem;">Miles ahead / behind baseline pace</h2>
<div id="chart-container-2">
  <canvas id="chart2" height="120"></canvas>
</div>

<script>
const runnerData = {runner_data_json};
const durationSeconds = {duration_seconds};
const metersPerMile = 1609.34;

function secondsToHours(s) {{ return s / 3600; }}

function buildDatasets(baselineMiles) {{
  const colors = ['#377ce6','#e6377c','#1d9e75','#f2a623','#7f77dd','#d85a30','#993c1d','#5f5e5a'];
  const datasets = runnerData.map((r, i) => ({{
    label: r.name,
    data: r.points.map(p => ({{ x: secondsToHours(p.t), y: p.d / metersPerMile }})),
    borderColor: colors[i % colors.length],
    backgroundColor: 'transparent',
    borderWidth: 2,
    pointRadius: 0,
    tension: 0,
  }}));

  const baselineMeters = baselineMiles * metersPerMile;
  datasets.push({{
    label: `Even pace to ${{baselineMiles}} mi`,
    data: [{{ x: 0, y: 0 }}, {{ x: secondsToHours(durationSeconds), y: baselineMiles }}],
    borderColor: '#999',
    borderDash: [6, 6],
    borderWidth: 1.5,
    pointRadius: 0,
    tension: 0,
  }});
  return datasets;
}}

function buildDeviationDatasets(baselineMiles) {{
  const colors = ['#377ce6','#e6377c','#1d9e75','#f2a623','#7f77dd','#d85a30','#993c1d','#5f5e5a'];
  const durationHours = secondsToHours(durationSeconds);
  const datasets = runnerData.map((r, i) => ({{
    label: r.name,
    data: r.points.map(p => {{
      const tHours = secondsToHours(p.t);
      const actualMiles = p.d / metersPerMile;
      const baselineMilesAtT = baselineMiles * (tHours / durationHours);
      return {{ x: tHours, y: actualMiles - baselineMilesAtT }};
    }}),
    borderColor: colors[i % colors.length],
    backgroundColor: 'transparent',
    borderWidth: 2,
    pointRadius: 0,
    tension: 0,
  }}));

  datasets.push({{
    label: 'Perfectly even pace',
    data: [{{ x: 0, y: 0 }}, {{ x: durationHours, y: 0 }}],
    borderColor: '#333',
    borderWidth: 1.5,
    pointRadius: 0,
    tension: 0,
  }});
  return datasets;
}}

const ctx = document.getElementById('chart').getContext('2d');
let chart = new Chart(ctx, {{
  type: 'line',
  data: {{ datasets: buildDatasets(parseFloat(document.getElementById('baseline').value)) }},
  options: {{
    parsing: false,
    scales: {{
      x: {{ type: 'linear', title: {{ display: true, text: 'Elapsed time (hours)' }}, min: 0, max: {duration_hours} }},
      y: {{ title: {{ display: true, text: 'Cumulative distance (miles)' }} }}
    }},
    plugins: {{ legend: {{ position: 'right' }} }}
  }}
}});

const ctx2 = document.getElementById('chart2').getContext('2d');
let chart2 = new Chart(ctx2, {{
  type: 'line',
  data: {{ datasets: buildDeviationDatasets(parseFloat(document.getElementById('baseline').value)) }},
  options: {{
    parsing: false,
    scales: {{
      x: {{ type: 'linear', title: {{ display: true, text: 'Elapsed time (hours)' }}, min: 0, max: {duration_hours} }},
      y: {{ title: {{ display: true, text: 'Miles ahead (+) / behind (-) baseline' }} }}
    }},
    plugins: {{ legend: {{ position: 'right' }} }}
  }}
}});

document.getElementById('baseline').addEventListener('input', (e) => {{
  const val = parseFloat(e.target.value) || 0;
  chart.data.datasets = buildDatasets(val);
  chart.update();
  chart2.data.datasets = buildDeviationDatasets(val);
  chart2.update();
}});
</script>
</body>
</html>
"""


def fetch_runner_splits(conn, race_name: str):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT sa.name_raw, sp.elapsed_s, sp.cum_distance_m, e.duration_s
            FROM core.splits sp
            JOIN core.results r ON r.id = sp.result_id
            JOIN core.source_athletes sa ON sa.id = r.source_athlete_id
            JOIN core.events e ON e.id = r.event_id
            JOIN core.races ra ON ra.id = e.race_id
            WHERE ra.name = %s
            ORDER BY sa.name_raw, sp.seq
            """,
            (race_name,),
        )
        rows = cur.fetchall()

    runners = {}
    duration_s = None
    for name, elapsed_s, cum_distance_m, dur in rows:
        duration_s = dur
        runners.setdefault(name, []).append({"t": elapsed_s, "d": float(cum_distance_m)})

    return [{"name": n, "points": pts} for n, pts in runners.items()], duration_s


def main(race_name: str, out_path: str, top_n: int = 8):
    conn = get_conn()
    runner_data, duration_s = fetch_runner_splits(conn, race_name)
    conn.close()

    if not runner_data:
        print(f"No data found for race '{race_name}'")
        return

    runner_data.sort(key=lambda r: r["points"][-1]["d"], reverse=True)
    runner_data = runner_data[:top_n]

    html = HTML_TEMPLATE.format(
        title=f"{race_name} — Cumulative Distance vs Time",
        runner_data_json=json.dumps(runner_data),
        duration_seconds=duration_s,
        duration_hours=round(duration_s / 3600, 2),
    )

    with open(out_path, "w") as f:
        f.write(html)

    print(f"Chart written to {out_path} ({len(runner_data)} runners plotted)")


if __name__ == "__main__":
    race_name = sys.argv[1] if len(sys.argv) > 1 else "Desert Solstice Track Invitational"
    out_path = sys.argv[2] if len(sys.argv) > 2 else "web/chart.html"
    main(race_name, out_path)