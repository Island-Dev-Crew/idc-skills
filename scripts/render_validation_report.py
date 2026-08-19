#!/usr/bin/env python3
"""Render docs/report.html deterministically from the 50 validation records."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any, Sequence

from verify_validation_records import ValidationError, _load_object, validate_records


def e(value: object) -> str:
    return html.escape(str(value), quote=True)


def render(payload: dict[str, Any]) -> str:
    records = payload["records"]
    average = sum(float(record["caseAvg"]) for record in records) / len(records)
    cards: list[str] = []
    for record in records:
        cases = "".join(
            f'''<li><div class="case-head"><strong>{e(case['title'])}</strong><span>{e(case['score'])}/10</span></div><p>{e(case['whatHappened'])}</p></li>'''
            for case in record["cases"]
        )
        cards.append(
            f'''<article class="card" data-skill="{e(record['skill'])}" data-search="{e((record['skill'] + ' ' + record['oneLiner']).lower())}">
  <div class="card-top"><div><span class="eyebrow">{e(record['inv'])} invocation</span><h2>{e(record['skill'])}</h2></div><div class="score">{e(record['caseAvg'])}<small>/10</small></div></div>
  <p class="lead">{e(record['oneLiner'])}</p>
  <ol>{cases}</ol>
  <div class="split"><p><b>Standout</b>{e(record['standoutStrength'])}</p><p><b>Residual</b>{e(record['residual'])}</p></div>
  <div class="confidence">confidence {e(record['confidence'])}/10</div>
</article>'''
        )
    embedded = html.escape(json.dumps(records, ensure_ascii=False, separators=(",", ":")))
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Forge 50 validation record · release 2.0.2</title>
<style>
:root{{--bg:#090b10;--panel:#11151d;--line:#293140;--ink:#edf1f6;--muted:#9aa6b5;--gold:#d6ad45;--jade:#4db79e;--rust:#c66b42}}
*{{box-sizing:border-box}} body{{margin:0;background:radial-gradient(circle at 80% -10%,#293044 0,transparent 32%),var(--bg);color:var(--ink);font-family:Inter,ui-sans-serif,system-ui,-apple-system,sans-serif;line-height:1.5}}
header,main,footer{{width:min(1120px,calc(100% - 32px));margin:auto}} header{{padding:72px 0 36px}} .kicker,.eyebrow,.confidence{{font:600 11px/1.4 ui-monospace,SFMono-Regular,monospace;letter-spacing:.12em;text-transform:uppercase;color:var(--jade)}}
h1{{font:500 clamp(42px,8vw,82px)/.96 Georgia,serif;letter-spacing:-.045em;margin:10px 0 18px;max-width:900px}} .deck{{max-width:760px;color:var(--muted);font-size:17px}}
.law{{margin:26px 0;padding:16px 20px;border-left:3px solid var(--gold);background:#d6ad4510}} .stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:30px 0}} .stat{{border:1px solid var(--line);background:#0e1219;padding:18px}} .stat strong{{display:block;font:500 28px Georgia,serif;color:var(--gold)}} .stat span{{color:var(--muted);font-size:12px}}
.tools{{position:sticky;top:0;z-index:3;padding:14px 0;background:#090b10e8;backdrop-filter:blur(16px)}} input{{width:100%;padding:13px 15px;border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:8px;font:inherit}}
.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;padding:20px 0 64px}} .card{{border:1px solid var(--line);background:linear-gradient(145deg,#151a24,#0f131a);padding:22px;border-radius:12px;box-shadow:0 20px 40px #0003}}
.card-top{{display:flex;justify-content:space-between;gap:20px}} h2{{font:500 28px Georgia,serif;margin:5px 0 0}} .score{{font:600 28px ui-monospace,monospace;color:var(--gold)}} .score small{{font-size:12px;color:var(--muted)}} .lead{{color:#c9d0da;min-height:52px}}
ol{{padding-left:20px}} li{{margin:14px 0}} .case-head{{display:flex;justify-content:space-between;gap:12px}} li span{{color:var(--jade);font:600 12px ui-monospace,monospace}} li p{{margin:5px 0;color:var(--muted);font-size:13px}}
.split{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:18px}} .split p{{margin:0;padding:12px;background:#080b10;border:1px solid #202735;color:var(--muted);font-size:12px}} .split b{{display:block;color:var(--rust);text-transform:uppercase;letter-spacing:.09em;font-size:10px;margin-bottom:5px}} .confidence{{margin-top:14px}}
footer{{padding:28px 0 60px;border-top:1px solid var(--line);color:var(--muted);font-size:12px}} .hidden{{display:none}}
@media(max-width:800px){{.stats,.grid{{grid-template-columns:1fr 1fr}}}} @media(max-width:620px){{.stats,.grid,.split{{grid-template-columns:1fr}}header{{padding-top:45px}}}}
</style></head><body>
<header><div class="kicker">IDC Skills · evidence ledger · 2026-08-19</div><h1>Fifty islands. One inspectable record.</h1><p class="deck">Machine-readable semantic validation for every registry seat, rendered from <code>ops/validation/skill-records.json</code>. Scores describe the recorded cases; they do not erase each card's residual boundary.</p><div class="law"><b>No authority without evidence.</b> The full rendered report must be the deterministic byte-for-byte output of the source records, or reacceptance fails.</div><div class="stats"><div class="stat"><strong>50</strong><span>registry-matched records</span></div><div class="stat"><strong>150</strong><span>falsifiable cases</span></div><div class="stat"><strong>{average:.1f}</strong><span>mean case score</span></div><div class="stat"><strong>2.0.2</strong><span>release candidate · signing gate separate</span></div></div></header>
<main><div class="tools"><input id="q" type="search" placeholder="Filter the archipelago…" aria-label="Filter skills"></div><section class="grid">{''.join(cards)}</section></main>
<footer>Generated deterministically from the source records. Structural and semantic evidence are separate claims; read the residual on every island.</footer>
<script id="validation-data" type="application/json">{embedded}</script>
<script>const q=document.querySelector('#q');q.addEventListener('input',()=>{{const v=q.value.toLowerCase().trim();document.querySelectorAll('.card').forEach(c=>c.classList.toggle('hidden',v&&!c.dataset.search.includes(v)))}});</script>
</body></html>'''


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--registry", type=Path, default=root / "skills" / "registry.json")
    parser.add_argument("--records", type=Path, default=root / "ops" / "validation" / "skill-records.json")
    parser.add_argument("--output", type=Path, default=root / "docs" / "report.html")
    args = parser.parse_args(argv)
    registry = _load_object(args.registry, "registry")
    payload = _load_object(args.records, "validation records")
    failures = validate_records(registry, payload)
    if failures:
        raise ValidationError("; ".join(failures))
    args.output.write_text(render(payload), encoding="utf-8", newline="\n")
    print(f"RENDERED — records={len(payload['records'])} path={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
