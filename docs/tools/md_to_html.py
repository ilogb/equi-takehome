"""Render a spec markdown file into a readable HTML artifact page.

usage: spec_to_html.py <spec.md> <out.html> <title>
"""
import re
import sys
from pathlib import Path

import markdown

src, out, title = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
md = markdown.Markdown(extensions=["tables", "fenced_code", "toc", "sane_lists"],
                       extension_configs={"toc": {"toc_depth": "2-2"}})
body = md.convert(src.read_text())
toc = md.toc
# Blockquote callouts and the "Claude's call" marker get their own styling.
body = body.replace("<blockquote>", '<blockquote class="callout">')
body = re.sub(r"\(Claude(?:&rsquo;|'|’)s call(?:[^)]*)\)", lambda m: f'<span class="call">{m.group(0)[1:-1]}</span>', body)
body = re.sub(r"\((Q\d+(?:[,–-] ?Q?\d+)*)(?:;[^)]*)?\)", lambda m: f'<span class="qref">{m.group(0)[1:-1]}</span>', body)
body = body.replace("TBD", '<mark class="tbd">TBD</mark>')

page = f"""<title>{title}</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;1,400&family=IBM+Plex+Mono:wght@400;500&family=Source+Serif+4:opsz,wght@8..60,600&display=swap">
<style>
/* Layout: a sticky contents rail beside one readable column of spec text; rail folds away on phones. */
:root {{
  --bg: #f5f7f9; --paper: #ffffff; --ink: #19222c; --muted: #5d6a77; --line: #dce3ea;
  --accent: #1d5f8a; --accent-soft: #e5eef6; --call: #fff4d6; --call-ink: #6b4f00; --tbd: #fde2df;
  --display: "Source Serif 4", Georgia, serif;
  --body: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, Menlo, Consolas, monospace;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg: #10151b; --paper: #171f28; --ink: #e4eaf0; --muted: #98a6b4; --line: #2a3541;
  --accent: #7db6df; --accent-soft: #1c3244; --call: #33290f; --call-ink: #f0d58a; --tbd: #4a1f1c; color-scheme: dark }} }}
:root[data-theme="dark"] {{
  --bg: #10151b; --paper: #171f28; --ink: #e4eaf0; --muted: #98a6b4; --line: #2a3541;
  --accent: #7db6df; --accent-soft: #1c3244; --call: #33290f; --call-ink: #f0d58a; --tbd: #4a1f1c; color-scheme: dark }}
body {{ background: var(--bg); color: var(--ink); font-family: var(--body); font-size: 16px; line-height: 1.62; }}
.wrap {{ max-width: 1120px; margin: 0 auto; padding-block: 32px 80px; padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px));
  display: grid; grid-template-columns: 230px minmax(0, 1fr); gap: 36px; align-items: start; }}
@media (max-width: 860px) {{ .wrap {{ grid-template-columns: minmax(0, 1fr); }} nav.toc {{ position: static !important; }} }}
nav.toc {{ position: sticky; top: calc(env(safe-area-inset-top, 0px) + 24px); font-size: 14px; }}
nav.toc .label {{ font-family: var(--mono); font-size: 11px; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); margin-bottom: 8px; }}
nav.toc ul {{ list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; }}
nav.toc ul ul {{ display: none; }}
nav.toc a {{ display: block; color: var(--muted); text-decoration: none; padding: 4px 10px; border-left: 2px solid var(--line); }}
nav.toc a:hover {{ color: var(--ink); border-color: var(--accent); }}
nav.toc a:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
article {{ background: var(--paper); border: 1px solid var(--line); border-radius: 10px; padding: clamp(20px, 4vw, 48px); min-width: 0; }}
article > * {{ max-width: 72ch; }}
article h1 {{ font-family: var(--display); font-size: clamp(26px, 3.4vw, 34px); line-height: 1.2; margin: 0 0 18px; text-wrap: balance; }}
article h2 {{ font-family: var(--display); font-size: 23px; margin: 44px 0 10px; padding-top: 14px; border-top: 1px solid var(--line); text-wrap: balance; scroll-margin-top: 20px; }}
article h3 {{ font-size: 16px; font-weight: 600; margin: 26px 0 6px; }}
article p, article li {{ margin: 0 0 10px; }}
article ul, article ol {{ padding-left: 1.3em; }}
article li > ul {{ margin-top: 6px; }}
code {{ font-family: var(--mono); font-size: .86em; background: var(--accent-soft); padding: 1px 5px; border-radius: 4px; }}
pre {{ max-width: 100% !important; overflow-x: auto; background: var(--bg); border: 1px solid var(--line); border-radius: 8px; padding: 14px 16px; font-size: 13px; line-height: 1.45; }}
pre code {{ background: none; padding: 0; }}
blockquote.callout {{ margin: 0 0 18px; padding: 12px 16px; background: var(--accent-soft); border-radius: 8px; border-left: 3px solid var(--accent); }}
blockquote.callout p:last-child {{ margin-bottom: 0; }}
.call {{ background: var(--call); color: var(--call-ink); font-size: .82em; font-weight: 500; padding: 1px 7px; border-radius: 99px; white-space: nowrap; }}
.qref {{ font-family: var(--mono); font-size: .78em; color: var(--accent); border: 1px solid var(--accent); padding: 0 6px; border-radius: 99px; white-space: nowrap; }}
mark.tbd {{ background: var(--tbd); color: var(--ink); padding: 0 4px; border-radius: 3px; font-weight: 600; }}
table {{ border-collapse: collapse; font-size: 14px; display: block; overflow-x: auto; max-width: 100%; }}
th, td {{ border-bottom: 1px solid var(--line); padding: 6px 10px; text-align: left; vertical-align: top; }}
a {{ color: var(--accent); }}
</style>
<div class="wrap">
  <nav class="toc" aria-label="Contents"><div class="label">Contents</div>{toc}</nav>
  <article>{body}</article>
</div>
"""
out.write_text(page)
print("wrote", out)
