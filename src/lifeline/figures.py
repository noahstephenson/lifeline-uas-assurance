from __future__ import annotations

import csv
from pathlib import Path


def generate_timeline_svg(run_id: str) -> Path:
    from lifeline.evidence.exporter import load_run

    run = load_run(run_id)
    run_dir = Path(run["directory"])
    return render_timeline_svg(run_dir, run_id)


def render_timeline_svg(run_dir: Path, run_id: str) -> Path:
    rows = list(csv.DictReader((run_dir / "timeline.csv").open(encoding="utf-8")))
    if not rows:
        output = run_dir / "timeline.svg"
        output.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="180">'
            '<rect width="100%" height="100%" fill="#0b1320"/>'
            '<text x="40" y="75" fill="#ff7185" font-family="Segoe UI,Arial" font-size="24">'
            f"Project Lifeline — {run_id}</text>"
            '<text x="40" y="115" fill="#e8f0fa" font-family="Segoe UI,Arial" font-size="18">'
            "Run ended before timeline telemetry was available.</text></svg>",
            encoding="utf-8",
        )
        return output
    width, height, left, right = 1200, 620, 110, 40
    top, track_h = 75, 105
    max_t = max(float(row["sim_time_s"]) for row in rows) or 1.0

    def x(time_s: float) -> float:
        return left + (width - left - right) * time_s / max_t

    colors = {
        "NOMINAL": "#38d996",
        "WATCH": "#56c7ff",
        "DEGRADED": "#f4c95d",
        "RECOVER": "#f0a64a",
        "TERMINATE": "#ff5d73",
        "UNKNOWN": "#c792ea",
    }
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#0b1320"/>',
        "<style>text{font-family:Segoe UI,Arial,sans-serif;fill:#e8f0fa}.muted{fill:#9eb0c4}.grid{stroke:#27384b;stroke-width:1}</style>",
        f'<text x="{left}" y="36" font-size="24" font-weight="700">Project Lifeline — {run_id}</text>',
        '<text x="110" y="58" font-size="13" class="muted">Requirement-linked mission assurance timeline (simulation)</text>',
    ]
    for tick in range(0, int(max_t) + 1, 5):
        xpos = x(tick)
        parts.append(f'<line x1="{xpos}" y1="{top}" x2="{xpos}" y2="545" class="grid"/>')
        parts.append(f'<text x="{xpos}" y="570" font-size="11" text-anchor="middle" class="muted">{tick}s</text>')
    labels = ["Link", "Navigation", "Energy margin", "Assurance / decision"]
    for index, label in enumerate(labels):
        y = top + index * track_h
        parts.append(f'<text x="18" y="{y + 30}" font-size="13">{label}</text>')
        parts.append(f'<line x1="{left}" y1="{y + 42}" x2="{width - right}" y2="{y + 42}" class="grid"/>')
    points_link = " ".join(f"{x(float(row['sim_time_s']))},{top + (12 if row['link'] == 'True' else 68)}" for row in rows)
    points_nav = " ".join(f"{x(float(row['sim_time_s']))},{top + track_h + 80 - float(row['navigation_confidence']) * 70}" for row in rows)
    points_energy = " ".join(
        f"{x(float(row['sim_time_s']))},{top + 2 * track_h + 75 - max(-5, min(35, float(row['energy_margin_wh']))) / 40 * 65}"
        for row in rows
    )
    parts.extend(
        [
            f'<polyline fill="none" stroke="#56c7ff" stroke-width="3" points="{points_link}"/>',
            f'<polyline fill="none" stroke="#9ee37d" stroke-width="3" points="{points_nav}"/>',
            f'<polyline fill="none" stroke="#f4c95d" stroke-width="3" points="{points_energy}"/>',
        ]
    )
    last_state = None
    for row in rows:
        state = row["assurance_state"]
        if state != last_state:
            xpos = x(float(row["sim_time_s"]))
            y = top + 3 * track_h + 10
            color = colors.get(state, "#9eb0c4")
            parts.append(f'<circle cx="{xpos}" cy="{y}" r="7" fill="{color}"/>')
            parts.append(f'<text x="{xpos + 10}" y="{y + 4}" font-size="11">{state}: {row["decision_code"]}</text>')
            last_state = state
    parts.append("</svg>")
    output = run_dir / "timeline.svg"
    output.write_text("\n".join(parts), encoding="utf-8")
    return output
