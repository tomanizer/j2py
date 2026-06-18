"""Static HTML review report generation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from html import escape
from pathlib import Path

from j2py.llm.review import LlmReviewFinding
from j2py.pipeline import TranslationResult
from j2py.state import StateEntry, entry_from_result, load_state


@dataclass(frozen=True)
class ReportInput:
    source_path: Path
    java_source: str
    python_source: str
    confidence: float
    used_llm: bool
    diagnostics: list[str]
    llm_review_ran: bool = False
    llm_review_findings: list[LlmReviewFinding] | None = None
    llm_review_error: str | None = None


def write_translation_report(
    path: Path,
    results: list[TranslationResult],
    *,
    title: str = "j2py translation report",
) -> None:
    inputs = [
        ReportInput(
            source_path=result.source_path,
            java_source=result.source_path.read_text(),
            python_source=result.python_source,
            confidence=result.confidence,
            used_llm=result.used_llm,
            diagnostics=[
                f"line {item.line}: {item.reason}"
                for item in (result.diagnostics.unhandled if result.diagnostics else [])
            ],
            llm_review_ran=result.llm_review_ran,
            llm_review_findings=result.llm_review_findings,
            llm_review_error=result.llm_review_error,
        )
        for result in results
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_translation_report(inputs, title=title))


def render_translation_report(inputs: list[ReportInput], *, title: str) -> str:
    avg_confidence = sum(item.confidence for item in inputs) / len(inputs) if inputs else 0.0
    nav = "\n".join(_nav_item(index, item) for index, item in enumerate(inputs))
    sections = "\n".join(_file_section(index, item) for index, item in enumerate(inputs))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>
{_REPORT_CSS}
</style>
</head>
<body>
<header>
  <h1>{escape(title)}</h1>
  <span class="score">{avg_confidence:.0%} avg confidence</span>
</header>
<main>
  <nav aria-label="Translated files">
    {nav}
  </nav>
  <section class="files">
    {sections}
  </section>
</main>
</body>
</html>
"""


def write_dashboard_for_results(
    path: Path,
    results: list[TranslationResult],
    *,
    source_root: Path,
    output_root: Path,
    title: str = "j2py translation dashboard",
) -> None:
    entries = [
        entry_from_result(result, source_root=source_root, output_root=output_root)
        for result in results
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_dashboard(entries, title=title))


def write_dashboard_from_state(
    output_root: Path,
    dashboard_path: Path,
    *,
    title: str = "j2py translation dashboard",
) -> None:
    entries = list(load_state(output_root).values())
    dashboard_path.parent.mkdir(parents=True, exist_ok=True)
    dashboard_path.write_text(render_dashboard(entries, title=title))


def render_dashboard(entries: list[StateEntry], *, title: str) -> str:
    total = len(entries)
    avg_confidence = sum(item.confidence for item in entries) / total if total else 0.0
    llm_count = sum(1 for item in entries if item.used_llm)
    validation_known = [item for item in entries if item.validation_ok is not None]
    validation_pass = sum(1 for item in validation_known if item.validation_ok)
    todo_files = sum(1 for item in entries if item.todo_count)
    review_files = sum(1 for item in entries if item.llm_review_ran)
    review_findings = sum(item.llm_review_count for item in entries)
    table_rows = "\n".join(_dashboard_table_row(item) for item in entries)
    treemap = "\n".join(_treemap_item(item) for item in entries)
    breakdown = _unhandled_breakdown(entries)
    data_json = json.dumps([_entry_payload(item) for item in entries]).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>
{_DASHBOARD_CSS}
</style>
</head>
<body>
<header>
  <h1>{escape(title)}</h1>
  <span>{total} files</span>
</header>
<main>
  <section class="summary" aria-label="Summary">
    {_metric("Average confidence", f"{avg_confidence:.0%}")}
    {_metric("LLM usage", f"{llm_count}/{total}" if total else "0/0")}
    {
        _metric(
            "Validation pass",
            f"{validation_pass}/{len(validation_known)}" if validation_known else "not run",
        )
    }
    {_metric("Files with TODOs", str(todo_files))}
    {_metric("LLM-reviewed files", str(review_files))}
    {_metric("LLM review findings", str(review_findings))}
  </section>
  <section>
    <div class="section-head">
      <h2>Confidence Heatmap</h2>
      <span>Box size follows source LOC; color follows confidence.</span>
    </div>
    <div class="treemap">{treemap or "<p>No files translated.</p>"}</div>
  </section>
  <section>
    <div class="section-head">
      <h2>Unhandled Breakdown</h2>
      <span>Total unresolved rule diagnostics by file.</span>
    </div>
    <div class="bars">{breakdown or "<p>No unresolved constructs recorded.</p>"}</div>
  </section>
  <section>
    <div class="section-head">
      <h2>Files</h2>
      <span>Click column headers to sort.</span>
    </div>
    <table id="files">
      <thead>
        <tr>
          <th data-type="text">File</th>
          <th data-type="number">Confidence</th>
          <th data-type="text">Rule/LLM</th>
          <th data-type="text">Validation</th>
          <th data-type="number">TODOs</th>
          <th data-type="number">Unhandled</th>
          <th data-type="text">LLM review</th>
        </tr>
      </thead>
      <tbody>
        {table_rows}
      </tbody>
    </table>
  </section>
</main>
<script id="j2py-dashboard-data" type="application/json">{data_json}</script>
<script>
{_DASHBOARD_SCRIPT}
</script>
</body>
</html>
"""


def _nav_item(index: int, item: ReportInput) -> str:
    return (
        f'<a href="#file-{index}">'
        f"<span>{escape(item.source_path.name)}</span>"
        f"<strong>{item.confidence:.0%}</strong>"
        "</a>"
    )


def _file_section(index: int, item: ReportInput) -> str:
    diagnostics = "<br>".join(escape(diagnostic) for diagnostic in item.diagnostics)
    if not diagnostics:
        diagnostics = "No unresolved rule-layer diagnostics."
    review = _review_findings_html(item)
    return f"""
<article id="file-{index}" class="file">
  <div class="file-head">
    <h2>{escape(str(item.source_path))}</h2>
    <span class="badge">{item.confidence:.0%}</span>
  </div>
  <div class="diagnostics">{diagnostics}</div>
  {review}
  <div class="split">
    <div class="pane">
      <h3>Java</h3>
      {_source_lines(item.java_source, provenance="java", diagnostics=[])}
    </div>
    <div class="pane">
      <h3>Python</h3>
      {
        _source_lines(
            item.python_source,
            provenance="llm" if item.used_llm else "rule",
            diagnostics=item.diagnostics,
        )
    }
    </div>
  </div>
</article>
"""


def _review_findings_html(item: ReportInput) -> str:
    if not item.llm_review_ran:
        return ""
    if item.llm_review_error:
        return (
            '<div class="llm-review error">'
            "<strong>LLM review failed:</strong> "
            f"{escape(item.llm_review_error)}</div>"
        )
    findings = item.llm_review_findings or []
    if not findings:
        return '<div class="llm-review"><strong>LLM review:</strong> no findings.</div>'
    rows = "\n".join(
        "<li>"
        f"<strong>{escape(finding.severity)}</strong> "
        f"{escape(finding.category)}"
        f"{_review_line_refs(finding)}"
        f": {escape(finding.message)}"
        f"{_review_recommendation(finding)}"
        "</li>"
        for finding in findings
    )
    return f'<div class="llm-review"><strong>LLM review findings</strong><ul>{rows}</ul></div>'


def _review_line_refs(finding: LlmReviewFinding) -> str:
    refs: list[str] = []
    if finding.source_line is not None:
        refs.append(f"Java line {finding.source_line}")
    if finding.output_line is not None:
        refs.append(f"Python line {finding.output_line}")
    return f" ({escape(', '.join(refs))})" if refs else ""


def _review_recommendation(finding: LlmReviewFinding) -> str:
    if not finding.recommendation:
        return ""
    return f"<br><span>{escape(finding.recommendation)}</span>"


def _source_lines(source: str, *, provenance: str, diagnostics: list[str]) -> str:
    lines = source.splitlines() or [""]
    rendered = [
        _line_html(number, line, provenance=provenance, diagnostics=diagnostics)
        for number, line in enumerate(lines, start=1)
    ]
    return '<ol class="code-lines">\n' + "\n".join(rendered) + "\n</ol>"


def _line_html(
    number: int,
    line: str,
    *,
    provenance: str,
    diagnostics: list[str],
) -> str:
    is_todo = "TODO(j2py)" in line or "__j2py_todo__" in line
    classes = [provenance]
    if is_todo:
        classes.append("todo")
    detail = ""
    if is_todo:
        line_diagnostics = [item for item in diagnostics if item.startswith(f"line {number}:")]
        reason = "<br>".join(escape(item) for item in line_diagnostics) or "TODO(j2py)"
        detail = f"<details><summary>TODO</summary><p>{reason}</p></details>"
    return (
        f'<li data-line="{number}" data-provenance="{provenance}" '
        f'class="{" ".join(classes)}">'
        f"<code>{escape(line) or ' '}</code>{detail}</li>"
    )


def _metric(label: str, value: str) -> str:
    return f"<article><span>{escape(label)}</span><strong>{escape(value)}</strong></article>"


def _dashboard_table_row(item: StateEntry) -> str:
    validation = (
        "not run" if item.validation_ok is None else "pass" if item.validation_ok else "fail"
    )
    return f"""
<tr>
  <td>{escape(item.source_path)}</td>
  <td data-value="{item.confidence:.6f}">{item.confidence:.0%}</td>
  <td>{"LLM" if item.used_llm else "Rule only"}</td>
  <td>{validation}</td>
  <td data-value="{item.todo_count}">{item.todo_count}</td>
  <td data-value="{item.unhandled_count}">{item.unhandled_count}</td>
  <td data-value="{item.llm_review_count}">{_dashboard_review_cell(item)}</td>
</tr>"""


def _treemap_item(item: StateEntry) -> str:
    loc = max(item.loc, 1)
    color = _confidence_color(item.confidence)
    return (
        f'<a class="tile" href="#files" style="flex-grow:{loc};background:{color}" '
        f'title="{escape(item.source_path)}">'
        f"<span>{escape(Path(item.source_path).name)}</span>"
        f"<strong>{item.confidence:.0%}</strong>"
        "</a>"
    )


def _confidence_color(confidence: float) -> str:
    red = round(232 - (confidence * 118))
    green = round(79 + (confidence * 118))
    blue = round(79 + (confidence * 41))
    return f"rgb({red}, {green}, {blue})"


def _unhandled_breakdown(entries: list[StateEntry]) -> str:
    selected = sorted(
        [item for item in entries if item.unhandled_count],
        key=lambda item: (-item.unhandled_count, item.source_path),
    )[:12]
    if not selected:
        return ""
    max_count = max(item.unhandled_count for item in selected)
    rows = []
    for item in selected:
        width = round((item.unhandled_count / max_count) * 100)
        rows.append(
            f'<div class="bar"><span>{escape(item.source_path)}</span>'
            f'<strong style="width:{width}%">{item.unhandled_count}</strong></div>'
        )
    return "\n".join(rows)


def _entry_payload(item: StateEntry) -> dict[str, object]:
    return {
        "source_path": item.source_path,
        "output_path": item.output_path,
        "confidence": item.confidence,
        "used_llm": item.used_llm,
        "validation_ok": item.validation_ok,
        "todo_count": item.todo_count,
        "unhandled_count": item.unhandled_count,
        "llm_review_ran": item.llm_review_ran,
        "llm_review_count": item.llm_review_count,
        "llm_review_error": item.llm_review_error,
        "loc": item.loc,
    }


def _dashboard_review_cell(item: StateEntry) -> str:
    if not item.llm_review_ran:
        return "not run"
    if item.llm_review_error:
        return "error"
    return str(item.llm_review_count)


_REPORT_CSS = """
:root {
  color-scheme: light;
  --bg: #f6f7f9;
  --ink: #17202a;
  --muted: #5f6b7a;
  --line: #d8dee8;
  --rule: #e7f6ed;
  --llm: #fff4d8;
  --todo: #ffe1df;
  --panel: #ffffff;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font: 14px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
header {
  align-items: center;
  background: var(--panel);
  border-bottom: 1px solid var(--line);
  display: flex;
  gap: 16px;
  justify-content: space-between;
  padding: 14px 20px;
  position: sticky;
  top: 0;
  z-index: 2;
}
h1, h2, h3 { margin: 0; }
h1 { font-size: 18px; }
h2 { font-size: 15px; overflow-wrap: anywhere; }
h3 { color: var(--muted); font-size: 12px; letter-spacing: .04em; text-transform: uppercase; }
main { display: grid; grid-template-columns: 260px 1fr; min-height: calc(100vh - 56px); }
nav {
  background: var(--panel);
  border-right: 1px solid var(--line);
  padding: 12px;
}
nav a {
  align-items: center;
  border-radius: 6px;
  color: inherit;
  display: flex;
  gap: 8px;
  justify-content: space-between;
  padding: 8px;
  text-decoration: none;
}
nav a:hover { background: var(--bg); }
.files { padding: 16px; }
.file {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  margin: 0 0 16px;
  overflow: hidden;
}
.file-head, .diagnostics {
  align-items: center;
  border-bottom: 1px solid var(--line);
  display: flex;
  justify-content: space-between;
  padding: 10px 12px;
}
.diagnostics { color: var(--muted); display: block; font-size: 12px; }
.llm-review {
  border-bottom: 1px solid var(--line);
  color: var(--ink);
  font-size: 12px;
  padding: 10px 12px;
}
.llm-review.error { color: #a61b1b; }
.llm-review ul { margin: 6px 0 0; padding-left: 18px; }
.llm-review li + li { margin-top: 6px; }
.llm-review span { color: var(--muted); }
.score, .badge {
  background: #edf2f7;
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 3px 8px;
}
.split { display: grid; grid-template-columns: 1fr 1fr; }
.pane { min-width: 0; }
.pane + .pane { border-left: 1px solid var(--line); }
.pane h3 { border-bottom: 1px solid var(--line); padding: 8px 12px; }
.code-lines {
  counter-reset: line;
  font: 12px/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  list-style: none;
  margin: 0;
  overflow: auto;
  padding: 0;
}
.code-lines li {
  display: grid;
  grid-template-columns: 56px minmax(0, 1fr) auto;
  min-height: 22px;
}
.code-lines li::before {
  color: var(--muted);
  content: attr(data-line);
  padding: 2px 10px;
  text-align: right;
}
.code-lines code { padding: 2px 10px; white-space: pre; }
.rule { background: var(--rule); }
.llm { background: var(--llm); }
.java { background: #f8fafc; }
.todo { background: var(--todo); }
details { padding: 2px 8px; }
details p { margin: 6px 0; max-width: 360px; white-space: normal; }
@media (max-width: 860px) {
  main { grid-template-columns: 1fr; }
  nav { border-right: 0; border-bottom: 1px solid var(--line); }
  .split { grid-template-columns: 1fr; }
  .pane + .pane { border-left: 0; border-top: 1px solid var(--line); }
}
"""

_DASHBOARD_CSS = """
:root {
  color-scheme: light;
  --bg: #f7f8fa;
  --ink: #18212f;
  --muted: #687386;
  --line: #d8dee8;
  --panel: #ffffff;
  --accent: #1f7a8c;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font: 14px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
header {
  align-items: center;
  background: var(--panel);
  border-bottom: 1px solid var(--line);
  display: flex;
  justify-content: space-between;
  padding: 16px 22px;
}
h1, h2 { margin: 0; }
h1 { font-size: 20px; }
h2 { font-size: 16px; }
main { display: grid; gap: 18px; padding: 18px; }
section {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  overflow: hidden;
}
.summary {
  background: transparent;
  border: 0;
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(4, minmax(0, 1fr));
}
.summary article {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 14px;
}
.summary span, .section-head span { color: var(--muted); font-size: 12px; }
.summary strong { display: block; font-size: 24px; margin-top: 4px; }
.section-head {
  align-items: center;
  border-bottom: 1px solid var(--line);
  display: flex;
  justify-content: space-between;
  padding: 12px 14px;
}
.treemap {
  align-content: stretch;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-height: 220px;
  padding: 12px;
}
.tile {
  border: 1px solid rgba(0,0,0,.18);
  border-radius: 6px;
  color: #08111f;
  display: flex;
  flex-basis: 120px;
  flex-direction: column;
  justify-content: space-between;
  min-height: 74px;
  min-width: 120px;
  overflow: hidden;
  padding: 8px;
  text-decoration: none;
}
.tile span { overflow-wrap: anywhere; }
.tile strong { align-self: flex-end; }
.bars { display: grid; gap: 8px; padding: 12px; }
.bar {
  align-items: center;
  display: grid;
  gap: 10px;
  grid-template-columns: minmax(120px, 280px) 1fr;
}
.bar span { color: var(--muted); overflow-wrap: anywhere; }
.bar strong {
  background: var(--accent);
  border-radius: 4px;
  color: white;
  min-width: 28px;
  padding: 3px 7px;
}
table {
  border-collapse: collapse;
  width: 100%;
}
th, td {
  border-bottom: 1px solid var(--line);
  padding: 9px 10px;
  text-align: left;
}
th {
  background: #eef2f6;
  cursor: pointer;
  user-select: none;
}
td:first-child { overflow-wrap: anywhere; }
@media (max-width: 780px) {
  .summary { grid-template-columns: 1fr 1fr; }
  .section-head { align-items: flex-start; flex-direction: column; gap: 4px; }
}
"""

_DASHBOARD_SCRIPT = """
document.querySelectorAll("th").forEach((header, index) => {
  header.addEventListener("click", () => {
    const table = header.closest("table");
    const tbody = table.querySelector("tbody");
    const rows = Array.from(tbody.querySelectorAll("tr"));
    const type = header.dataset.type;
    const direction = header.dataset.direction === "asc" ? -1 : 1;
    document.querySelectorAll("th").forEach((item) => item.dataset.direction = "");
    header.dataset.direction = direction === 1 ? "asc" : "desc";
    rows.sort((left, right) => {
      const leftCell = left.children[index];
      const rightCell = right.children[index];
      const leftValue = leftCell.dataset.value || leftCell.textContent.trim();
      const rightValue = rightCell.dataset.value || rightCell.textContent.trim();
      if (type === "number") {
        return (Number(leftValue) - Number(rightValue)) * direction;
      }
      return leftValue.localeCompare(rightValue) * direction;
    });
    rows.forEach((row) => tbody.appendChild(row));
  });
});
"""
