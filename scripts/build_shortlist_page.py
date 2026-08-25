"""把 data/shortlist.json 渲染成一个可筛选的单页 HTML。"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

TPL_HEAD = """<title>Remote Job Shortlist</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<style>
:root{
  --ground:#F5F7F8; --card:#FFFFFF; --raise:#EDF1F3;
  --ink:#12171B; --muted:#5C6872; --faint:#8A959E;
  --line:#DCE3E7; --accent:#0E6D63; --accent-soft:#DCEFEC;
  --warn:#A8600C; --warn-soft:#F7EBD9; --good:#1D6F3F; --good-soft:#DDEFE4;
  --shadow:0 1px 2px rgba(18,23,27,.06),0 8px 24px -16px rgba(18,23,27,.28);
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --ground:#0E1216; --card:#161B21; --raise:#1E252C;
    --ink:#E7ECF0; --muted:#95A2AD; --faint:#6D7B87;
    --line:#262E36; --accent:#2FCFB8; --accent-soft:#0F2E2B;
    --warn:#E0A24B; --warn-soft:#2E2415; --good:#5BC98A; --good-soft:#13291D;
    --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 28px -18px rgba(0,0,0,.8);
  }
}
:root[data-theme="dark"]{
  --ground:#0E1216; --card:#161B21; --raise:#1E252C;
  --ink:#E7ECF0; --muted:#95A2AD; --faint:#6D7B87;
  --line:#262E36; --accent:#2FCFB8; --accent-soft:#0F2E2B;
  --warn:#E0A24B; --warn-soft:#2E2415; --good:#5BC98A; --good-soft:#13291D;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 28px -18px rgba(0,0,0,.8);
}
*{box-sizing:border-box}
body{
  margin:0; background:var(--ground); color:var(--ink);
  font-family:"IBM Plex Sans",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  font-size:15px; line-height:1.5; -webkit-font-smoothing:antialiased;
}
.wrap{max-width:1180px; margin:0 auto; padding:40px 24px 80px; display:flex; flex-direction:column; gap:28px}
header{display:flex; flex-direction:column; gap:6px}
h1{margin:0; font-size:30px; font-weight:600; letter-spacing:-.02em; text-wrap:balance}
.sub{color:var(--muted); font-size:14px}
.stats{display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px}
.stat{background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px 16px; display:flex; flex-direction:column; gap:4px}
.stat .k{font-size:11px; letter-spacing:.09em; text-transform:uppercase; color:var(--faint); font-weight:600}
.stat .v{font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:24px; font-weight:600; font-variant-numeric:tabular-nums}
.controls{display:flex; flex-wrap:wrap; gap:10px; align-items:center; position:sticky; top:0; z-index:5;
  background:var(--ground); padding:12px 0; border-bottom:1px solid var(--line)}
input[type=search]{
  flex:1 1 240px; min-width:200px; padding:9px 12px; border-radius:8px; border:1px solid var(--line);
  background:var(--card); color:var(--ink); font:inherit;
}
input[type=search]:focus-visible,button:focus-visible{outline:2px solid var(--accent); outline-offset:2px}
button{
  font:inherit; font-size:13px; font-weight:500; padding:8px 13px; border-radius:999px; cursor:pointer;
  border:1px solid var(--line); background:var(--card); color:var(--muted); transition:.14s;
}
button:hover{border-color:var(--accent); color:var(--ink)}
button[aria-pressed="true"]{background:var(--accent-soft); border-color:var(--accent); color:var(--accent); font-weight:600}
.count{font-family:"IBM Plex Mono",monospace; font-size:13px; color:var(--muted); font-variant-numeric:tabular-nums}
.list{display:flex; flex-direction:column; gap:10px}
.job{
  background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px 18px;
  display:grid; grid-template-columns:44px 1fr auto; gap:4px 16px; align-items:start; box-shadow:var(--shadow);
}
.rank{font-family:"IBM Plex Mono",monospace; font-size:13px; color:var(--faint); font-variant-numeric:tabular-nums; padding-top:2px}
.body{display:flex; flex-direction:column; gap:7px; min-width:0}
.title{font-size:16px; font-weight:600; letter-spacing:-.01em; margin:0; overflow-wrap:anywhere}
.meta{display:flex; flex-wrap:wrap; gap:8px 14px; align-items:center; font-size:13px; color:var(--muted)}
.co{font-weight:500; color:var(--ink)}
.sal{font-family:"IBM Plex Mono",monospace; font-size:13px; color:var(--good); font-weight:500}
.chips{display:flex; flex-wrap:wrap; gap:6px}
.chip{font-size:11px; padding:2.5px 8px; border-radius:5px; background:var(--raise); color:var(--muted); font-weight:500;
  letter-spacing:.02em}
.chip.stack{background:var(--accent-soft); color:var(--accent); font-weight:600}
.chip.geo-ok{background:var(--good-soft); color:var(--good); font-weight:600}
.chip.geo-block{background:var(--warn-soft); color:var(--warn); font-weight:600}
.apply{
  align-self:center; white-space:nowrap; text-decoration:none; font-size:13px; font-weight:600;
  padding:8px 15px; border-radius:8px; background:var(--accent); color:var(--ground); transition:.14s;
}
:root[data-theme="dark"] .apply,:root:not([data-theme="light"]) .apply{color:#08120F}
@media (prefers-color-scheme:light){:root:not([data-theme="dark"]) .apply{color:#FFFFFF}}
.apply:hover{filter:brightness(1.08)}
.apply.off{background:var(--raise); color:var(--faint); pointer-events:none}
.empty{padding:40px; text-align:center; color:var(--muted)}
footer{color:var(--faint); font-size:12.5px; border-top:1px solid var(--line); padding-top:16px; line-height:1.7}
@media (max-width:620px){
  .job{grid-template-columns:1fr; gap:10px}
  .rank{display:none}
  .apply{justify-self:start}
}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
</style>
"""


def esc(s):
    return html.escape(str(s or ""))


def build(rows: list[dict]) -> str:
    n = len(rows)
    n_link = sum(1 for r in rows if r["has_link"])
    n_ww = sum(1 for r in rows if r["location_friendly"])
    n_sal = sum(1 for r in rows if r["salary"] and r["salary"] not in ("未披露", "面议", "Not specified"))

    cards = []
    for i, r in enumerate(rows, 1):
        chips = "".join(f'<span class="chip stack">{esc(s)}</span>' for s in r["stack_hits"])
        if r["location_blocked"]:
            chips += '<span class="chip geo-block">有地域限制</span>'
        elif r["location_friendly"]:
            chips += '<span class="chip geo-ok">worldwide</span>'
        chips += f'<span class="chip">{esc(r["channel"])}</span>'
        sal = (f'<span class="sal">{esc(r["salary"])}</span>'
               if r["salary"] and r["salary"] not in ("未披露", "面议", "Not specified") else "")
        city = f'<span>{esc(r["city"])}</span>' if r["city"] else ""
        apply_el = (f'<a class="apply" href="{esc(r["url"])}" target="_blank" rel="noopener">申请 →</a>'
                    if r["has_link"] else '<span class="apply off">无链接</span>')
        hay = esc(" ".join([r["title"], r["company"], r["city"], " ".join(r["stack_hits"]), r["channel"]]).lower())
        cards.append(f'''<article class="job" data-stack="{esc(",".join(r["stack_hits"]))}"
 data-sal="{1 if sal else 0}" data-ww="{1 if r["location_friendly"] else 0}" data-q="{hay}">
<div class="rank">{i}</div>
<div class="body">
<h2 class="title">{esc(r["title"])}</h2>
<div class="meta"><span class="co">{esc(r["company"])}</span>{sal}{city}</div>
<div class="chips">{chips}</div>
</div>
{apply_el}
</article>''')

    return TPL_HEAD + f'''<div class="wrap">
<header>
<h1>可投岗位短名单</h1>
<p class="sub">从 5,791 条抓取结果里筛出的 {n} 个海外远程岗位 · 按可投递性排序 · Node.js / Python / Java / AI Agent</p>
</header>

<section class="stats">
<div class="stat"><span class="k">岗位</span><span class="v">{n}</span></div>
<div class="stat"><span class="k">有申请链接</span><span class="v">{n_link}</span></div>
<div class="stat"><span class="k">明确 worldwide</span><span class="v">{n_ww}</span></div>
<div class="stat"><span class="k">披露薪资</span><span class="v">{n_sal}</span></div>
</section>

<div class="controls">
<input type="search" id="q" placeholder="搜岗位、公司、技术栈…" aria-label="搜索岗位">
<button data-f="stack" data-v="node" aria-pressed="false">Node.js</button>
<button data-f="stack" data-v="python" aria-pressed="false">Python</button>
<button data-f="stack" data-v="java" aria-pressed="false">Java</button>
<button data-f="stack" data-v="agent" aria-pressed="false">AI Agent</button>
<button data-f="ww" aria-pressed="false">仅 worldwide</button>
<button data-f="sal" aria-pressed="false">有薪资</button>
<span class="count" id="count">{n} 条</span>
</div>

<div class="list" id="list">
{"".join(cards)}
</div>
<p class="empty" id="empty" hidden>没有匹配的岗位，换个筛选条件。</p>

<footer>
排序权重：有申请链接 &gt; 远程 &gt; 技术栈命中数 &gt; 披露薪资 &gt; 无地域硬限制。<br>
「有地域限制」= 描述里出现 work authorization / must be located in / onsite 一类措辞，不代表一定不能投，但要先确认。<br>
数据来源：Telegram 50 个招聘频道 · X 386 个招聘账号 · Hacker News 近 24 期 who-is-hiring · Discord JobsBot 转发。
</footer>
</div>

<script>
const state = {{stack:new Set(), ww:false, sal:false, q:""}};
const cards = [...document.querySelectorAll(".job")];
const countEl = document.getElementById("count");
const emptyEl = document.getElementById("empty");

function apply(){{
  let shown = 0;
  for(const c of cards){{
    const st = c.dataset.stack.split(",").filter(Boolean);
    let ok = true;
    if(state.stack.size && !st.some(s => state.stack.has(s))) ok = false;
    if(ok && state.ww && c.dataset.ww !== "1") ok = false;
    if(ok && state.sal && c.dataset.sal !== "1") ok = false;
    if(ok && state.q && !c.dataset.q.includes(state.q)) ok = false;
    c.hidden = !ok;
    if(ok) shown++;
  }}
  countEl.textContent = shown + " 条";
  emptyEl.hidden = shown > 0;
}}

document.querySelectorAll("button[data-f]").forEach(b => {{
  b.addEventListener("click", () => {{
    const on = b.getAttribute("aria-pressed") === "true";
    b.setAttribute("aria-pressed", String(!on));
    if(b.dataset.f === "stack"){{
      on ? state.stack.delete(b.dataset.v) : state.stack.add(b.dataset.v);
    }} else {{
      state[b.dataset.f] = !on;
    }}
    apply();
  }});
}});
document.getElementById("q").addEventListener("input", e => {{
  state.q = e.target.value.trim().toLowerCase();
  apply();
}});
</script>
'''


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="data/shortlist.json")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    rows = json.loads(Path(args.src).read_text(encoding="utf-8"))
    Path(args.out).write_text(build(rows), encoding="utf-8")
    print(f"-> {args.out} ({len(rows)} 条)")


if __name__ == "__main__":
    main()
