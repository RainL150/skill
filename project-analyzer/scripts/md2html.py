#!/usr/bin/env python3
"""project-analyzer HTML 输出:把分析报告 .md 转成自包含单文件 .html。
线框图(无语言 fence)→ <pre class=wireframe>;mermaid → 构建时 mermaid-cli 渲染成内联 SVG。
内联 SVG 方案:HTML 零运行时依赖,离线可看,可打印 PDF。需 npx + mermaid-cli(首次自动装)。"""
import sys, re, html, subprocess, tempfile, os, shutil

_PPTR = None
def _pptr_cfg():
    global _PPTR
    if _PPTR is None:
        fd, p = tempfile.mkstemp(suffix=".json"); os.write(fd, b'{"args":["--no-sandbox"]}'); os.close(fd)
        _PPTR = p
    return _PPTR

def render_mermaid_to_svg(code, idx):
    """用 mermaid-cli 把 mermaid 源渲染成内联 SVG;失败返回 None。"""
    d = tempfile.mkdtemp()
    try:
        mmd = os.path.join(d, "in.mmd"); svg = os.path.join(d, "out.svg")
        open(mmd, "w", encoding="utf-8").write(code)
        r = subprocess.run(
            ["npx", "-y", "@mermaid-js/mermaid-cli@latest",
             "-i", mmd, "-o", svg, "-b", "transparent", "-p", _pptr_cfg()],
            capture_output=True, text=True, timeout=180)
        if r.returncode != 0 or not os.path.exists(svg):
            sys.stderr.write(f"[mermaid #{idx}] render failed: {r.stderr[-300:]}\n"); return None
        s = open(svg, encoding="utf-8").read()
        s = re.sub(r'<\?xml[^>]*\?>\s*', '', s)            # 去 xml 声明
        s = re.sub(r'<!DOCTYPE[^>]*>\s*', '', s)
        s = s.replace("my-svg", f"mmd{idx}")               # 唯一化 id,避免多图 CSS 冲突
        return s
    finally:
        shutil.rmtree(d, ignore_errors=True)

TEMPLATE_HEAD = '''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  /* ── Material-inspired theme (Google 四色点缀) ── */
  :root{{
    --fg:#202124; --muted:#5f6368; --bg:#f1f3f4; --surface:#ffffff; --panel:#f8f9fa;
    --border:#e3e6ea; --accent:#1a73e8; --accent-soft:#e8f0fe; --code:#f1f3f4;
    --g-blue:#4285f4; --g-red:#ea4335; --g-yellow:#fbbc04; --g-green:#34a853;
    --shadow:0 1px 2px rgba(60,64,67,.08), 0 2px 8px rgba(60,64,67,.08);
    --shadow-lg:0 1px 3px rgba(60,64,67,.12), 0 8px 24px rgba(60,64,67,.14);
  }}
  @media (prefers-color-scheme: dark){{
    :root{{
      --fg:#e8eaed; --muted:#9aa0a6; --bg:#0e0f11; --surface:#1c1d20; --panel:#26282c;
      --border:#3c4043; --accent:#8ab4f8; --accent-soft:#1e2a3d; --code:#26282c;
      --shadow:0 1px 2px rgba(0,0,0,.4), 0 2px 8px rgba(0,0,0,.3);
      --shadow-lg:0 1px 3px rgba(0,0,0,.5), 0 8px 24px rgba(0,0,0,.45);
    }} }}
  *{{ box-sizing:border-box; }}
  html{{ scroll-behavior:smooth; }}
  body{{ margin:0; background:var(--bg); color:var(--fg);
        font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;
        line-height:1.75; -webkit-font-smoothing:antialiased; }}
  /* 顶部四色彩条 —— 致敬 Chrome */
  body::before{{ content:""; position:fixed; top:0; left:0; right:0; height:4px; z-index:99;
    background:linear-gradient(90deg,var(--g-blue) 0 25%,var(--g-red) 25% 50%,var(--g-yellow) 50% 75%,var(--g-green) 75% 100%); }}
  .wrap{{ max-width:1040px; margin:0 auto; padding:56px 24px 120px; }}
  /* 内容主卡片 */
  .wrap>h1:first-child{{ margin-top:0; }}
  h1{{ font-size:2.3rem; font-weight:700; letter-spacing:-.02em; line-height:1.25;
      margin:0 0 .2em; }}
  h2{{ font-size:1.5rem; font-weight:650; margin:2.6em 0 .8em; padding-left:14px;
      border-left:4px solid var(--accent); line-height:1.3; }}
  h3{{ font-size:1.2rem; font-weight:600; margin:1.8em 0 .6em; }}
  h4{{ font-size:1.02rem; font-weight:600; color:var(--muted); margin:1.4em 0 .5em; }}
  p{{ margin:.7em 0; }}
  a{{ color:var(--accent); text-decoration:none; }} a:hover{{ text-decoration:underline; }}
  strong{{ font-weight:650; }}
  /* 表格 —— 圆角卡片包裹 */
  .table-wrap{{ margin:1.3em 0; border:1px solid var(--border); border-radius:14px;
    overflow:hidden; box-shadow:var(--shadow); background:var(--surface); }}
  table{{ border-collapse:collapse; width:100%; font-size:.92rem; }}
  th,td{{ padding:11px 16px; text-align:left; vertical-align:top;
    border-bottom:1px solid var(--border); }}
  th{{ background:var(--panel); font-weight:600; color:var(--fg);
    border-bottom:2px solid var(--border); white-space:nowrap; }}
  tbody tr:last-child td{{ border-bottom:none; }}
  tbody tr{{ transition:background .12s; }}
  tbody tr:hover td{{ background:var(--accent-soft); }}
  code{{ background:var(--code); padding:.16em .45em; border-radius:6px;
    font-family:"SF Mono",Menlo,Consolas,"Liberation Mono",monospace; font-size:.86em;
    color:var(--fg); }}
  pre{{ background:var(--surface); border:1px solid var(--border); border-radius:14px;
    padding:18px 20px; overflow:auto; font-size:.85rem; line-height:1.5; box-shadow:var(--shadow); }}
  pre code{{ background:none; padding:0; }}
  /* ASCII 线框图 —— 等宽,严禁换行(保对齐) */
  pre.wireframe{{ font-family:"SF Mono",Menlo,Consolas,monospace; white-space:pre;
    line-height:1.4; background:var(--surface); }}
  /* 内联 SVG 图 —— 固定白底卡片,暗色下也清晰 */
  .mermaid-svg{{ background:#fff; border:1px solid var(--border); border-radius:14px;
    padding:22px; margin:1.3em 0; text-align:center; overflow:auto; box-shadow:var(--shadow); }}
  .mermaid-svg svg{{ max-width:100%; height:auto; }}
  /* 引用块 / 通俗理解 callout */
  blockquote{{ margin:1.1em 0; padding:.7em 1.1em; background:var(--accent-soft);
    border-left:4px solid var(--accent); border-radius:0 12px 12px 0; color:var(--fg); }}
  blockquote p{{ margin:.2em 0; }}
  /* 一句话总结 —— hero 卡片 */
  .summary{{ position:relative; background:var(--surface); border:1px solid var(--border);
    border-radius:18px; padding:24px 28px 24px 30px; font-size:1.08rem; line-height:1.7;
    margin:1.6em 0 2em; box-shadow:var(--shadow-lg); overflow:hidden; }}
  .summary::before{{ content:""; position:absolute; left:0; top:0; bottom:0; width:6px;
    background:linear-gradient(180deg,var(--g-blue),var(--g-green)); }}
  .meta{{ color:var(--muted); font-size:.86rem; margin:.2em 0 1.4em; }}
  hr{{ border:none; border-top:1px solid var(--border); margin:2.6em 0; }}
  ul,ol{{ padding-left:1.5em; }} li{{ margin:.3em 0; }}
  ::selection{{ background:var(--accent-soft); }}
</style>
</head>
<body>
<div class="wrap">
'''

TEMPLATE_TAIL = '''
</div>
</body>
</html>
'''

def inline(t):
    # 提取行内 code 占位,避免内部 ** [] 被二次处理
    spans=[]
    def stash(m):
        spans.append(html.escape(m.group(1)))
        return f"\x00{len(spans)-1}\x00"
    t=re.sub(r'`([^`]+)`', stash, t)
    t=html.escape(t)
    t=re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', t)
    t=re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', t)
    t=re.sub(r'\x00(\d+)\x00', lambda m: f'<code>{spans[int(m.group(1))]}</code>', t)
    return t

def render(md):
    lines=md.split('\n')
    out=[]; i=0; n=len(lines); mmd_idx=[0]
    def flush_table(rows):
        # rows: list of raw "| a | b |" lines, rows[1] is the --- separator
        def cells(r):
            r=r.strip()
            if r.startswith('|'): r=r[1:]
            if r.endswith('|'): r=r[:-1]
            return [c.strip().replace('\\|','|') for c in r.split('|')]
        head=cells(rows[0]); body=[cells(r) for r in rows[2:]]
        h='<table>\n<thead><tr>'+''.join(f'<th>{inline(c)}</th>' for c in head)+'</tr></thead>\n<tbody>'
        for b in body:
            h+='<tr>'+''.join(f'<td>{inline(c)}</td>' for c in b)+'</tr>'
        h+='</tbody></table>'
        return f'<div class="table-wrap">{h}</div>'
    while i<n:
        ln=lines[i]
        # fenced code
        m=re.match(r'^```(\w*)\s*$', ln)
        if m:
            lang=m.group(1); i+=1; buf=[]
            while i<n and not re.match(r'^```\s*$', lines[i]):
                buf.append(lines[i]); i+=1
            i+=1  # skip closing fence
            raw='\n'.join(buf); body=html.escape(raw)
            if lang=='mermaid':
                idx=mmd_idx[0]; mmd_idx[0]+=1
                svg=render_mermaid_to_svg(raw, idx)
                if svg:
                    out.append(f'<div class="mermaid-svg">{svg}</div>')
                else:  # 渲染失败兜底:留可读源码
                    out.append(f'<pre class="mermaid">\n{body}\n</pre>')
            elif lang=='':
                out.append(f'<pre class="wireframe">{body}</pre>')
            else:
                out.append(f'<pre><code class="language-{lang}">{body}</code></pre>')
            continue
        # headings
        m=re.match(r'^(#{1,4})\s+(.*)$', ln)
        if m:
            lvl=len(m.group(1)); txt=inline(m.group(2))
            out.append(f'<h{lvl}>{txt}</h{lvl}>'); i+=1; continue
        # hr
        if re.match(r'^---+\s*$', ln):
            out.append('<hr>'); i+=1; continue
        # table
        if ln.strip().startswith('|') and i+1<n and re.match(r'^\s*\|?[\s:|-]+\|?\s*$', lines[i+1]) and '-' in lines[i+1]:
            rows=[ln, lines[i+1]]; i+=2
            while i<n and lines[i].strip().startswith('|'):
                rows.append(lines[i]); i+=1
            out.append(flush_table(rows)); continue
        # blockquote (可多行)
        if ln.startswith('>'):
            buf=[]
            while i<n and lines[i].startswith('>'):
                buf.append(lines[i][1:].lstrip()); i+=1
            out.append('<blockquote>'+inline(' '.join(buf))+'</blockquote>'); continue
        # lists
        if re.match(r'^\s*[-*]\s+', ln):
            buf=[]
            while i<n and re.match(r'^\s*[-*]\s+', lines[i]):
                buf.append(re.sub(r'^\s*[-*]\s+','',lines[i])); i+=1
            out.append('<ul>'+''.join(f'<li>{inline(x)}</li>' for x in buf)+'</ul>'); continue
        if re.match(r'^\s*\d+\.\s+', ln):
            buf=[]
            while i<n and re.match(r'^\s*\d+\.\s+', lines[i]):
                buf.append(re.sub(r'^\s*\d+\.\s+','',lines[i])); i+=1
            out.append('<ol>'+''.join(f'<li>{inline(x)}</li>' for x in buf)+'</ol>'); continue
        # blank
        if ln.strip()=='':
            i+=1; continue
        # paragraph (聚合到空行/块边界)
        buf=[ln]; i+=1
        while i<n and lines[i].strip()!='' and not re.match(r'^(#{1,4}\s|```|>|\s*[-*]\s|\s*\d+\.\s|\|)', lines[i]) and not re.match(r'^---+\s*$', lines[i]):
            buf.append(lines[i]); i+=1
        para=' '.join(buf)
        if para.startswith('项目分析:') or para.startswith('项目分析：'):
            out.append(f'<div class="summary">{inline(para)}</div>')
        else:
            out.append(f'<p>{inline(para)}</p>')
    return '\n'.join(out)

def main():
    src, dst = sys.argv[1], sys.argv[2]
    md=open(src, encoding='utf-8').read()
    m=re.search(r'^#\s+(.*)$', md, re.M)
    title=m.group(1).strip() if m else 'Analysis Report'
    body_md=md
    # 顶部一级标题已在正文里渲染,无需重复
    htmlout=TEMPLATE_HEAD.format(title=html.escape(title))+render(body_md)+TEMPLATE_TAIL
    open(dst,'w',encoding='utf-8').write(htmlout)
    import os
    print(f"✓ {dst}  ({os.path.getsize(dst)//1024} KB)")

if __name__=='__main__':
    main()
