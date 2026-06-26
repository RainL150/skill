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
  :root{{ --fg:#1a1a1a; --muted:#6b7280; --bg:#ffffff; --panel:#f6f8fa;
         --border:#e5e7eb; --accent:#2563eb; --code:#f3f4f6; }}
  @media (prefers-color-scheme: dark){{
    :root{{ --fg:#e6e6e6; --muted:#9aa0a6; --bg:#0d1117; --panel:#161b22;
           --border:#30363d; --accent:#58a6ff; --code:#161b22; }} }}
  *{{ box-sizing:border-box; }}
  body{{ margin:0; background:var(--bg); color:var(--fg);
        font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
        line-height:1.7; }}
  .wrap{{ max-width:980px; margin:0 auto; padding:48px 24px 96px; }}
  h1{{ font-size:2rem; border-bottom:2px solid var(--border); padding-bottom:.4em; }}
  h2{{ font-size:1.5rem; margin-top:2.2em; border-bottom:1px solid var(--border); padding-bottom:.3em; }}
  h3{{ font-size:1.2rem; margin-top:1.6em; }}
  h4{{ font-size:1.05rem; color:var(--muted); }}
  a{{ color:var(--accent); text-decoration:none; }} a:hover{{ text-decoration:underline; }}
  table{{ border-collapse:collapse; width:100%; margin:1em 0; font-size:.93rem; }}
  th,td{{ border:1px solid var(--border); padding:8px 12px; text-align:left; vertical-align:top; }}
  th{{ background:var(--panel); font-weight:600; }}
  tr:nth-child(even) td{{ background:var(--panel); }}
  code{{ background:var(--code); padding:.15em .4em; border-radius:4px;
        font-family:"SF Mono",Menlo,Consolas,"Liberation Mono",monospace; font-size:.88em; }}
  pre{{ background:var(--panel); border:1px solid var(--border); border-radius:8px;
       padding:16px; overflow:auto; font-size:.85rem; line-height:1.45; }}
  pre code{{ background:none; padding:0; }}
  pre.wireframe{{ font-family:"SF Mono",Menlo,Consolas,monospace; white-space:pre;
                 line-height:1.35; background:var(--bg); }}
  /* 内联 SVG 图:固定白底卡片,暗色模式下也清晰可读 */
  .mermaid-svg{{ background:#fff; border:1px solid var(--border); border-radius:8px;
                padding:16px; margin:1em 0; text-align:center; overflow:auto; }}
  .mermaid-svg svg{{ max-width:100%; height:auto; }}
  blockquote{{ border-left:4px solid var(--accent); margin:1em 0; padding:.4em 1em;
              background:var(--panel); color:var(--muted); border-radius:0 6px 6px 0; }}
  .summary{{ background:var(--panel); border:1px solid var(--border); border-radius:10px;
            padding:18px 22px; font-size:1.05rem; margin:1.2em 0; }}
  .meta{{ color:var(--muted); font-size:.85rem; }}
  hr{{ border:none; border-top:1px solid var(--border); margin:2.4em 0; }}
  .mermaid{{ background:var(--bg); text-align:center; }}
  ul,ol{{ padding-left:1.4em; }}
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
        return h
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
