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
  /* ── Editorial / 印刷备忘录风(暖纸底 + 衬线标题 + 低饱和三色)── */
  @import url('https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@500;600;700&family=Noto+Sans+SC:wght@300;400;500&display=swap');
  :root{{
    --ink:#1a1a1a; --ink-mid:#444; --ink-light:#666; --ink-muted:#999;
    --blue:#1a4a7a; --blue-bg:#e8eef5; --blue-dark:#1e3a5f;
    --green:#1a7a4a; --green-bg:#e8f5ee; --green-dark:#14532d;
    --red:#b91c1c; --red-bg:#fef2f2; --red-dark:#7f1d1d;
    --bg:#f9f8f5; --surface:#fffefb; --border:#e2e0da; --rule:#ccc9c1; --code-bg:#eeece6;
    --serif:'Noto Serif SC','Songti SC','STSong',serif;
    --sans:'Noto Sans SC','PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif;
    --mono:'SF Mono',Menlo,Consolas,'Liberation Mono',monospace;
  }}
  *{{ box-sizing:border-box; margin:0; padding:0; }}
  html{{ scroll-behavior:smooth; }}
  body{{ background:var(--bg); color:var(--ink); font-family:var(--sans);
    font-weight:300; font-size:15.5px; line-height:1.9; -webkit-font-smoothing:antialiased; }}
  /* 双栏布局:左侧常驻目录 + 右侧正文 */
  .layout{{ display:grid; grid-template-columns:268px minmax(0,1fr); gap:56px;
    max-width:1200px; margin:0 auto; padding:0 32px; }}
  .content{{ max-width:820px; min-width:0; padding:56px 0 120px; }}
  /* ── 左侧常驻 TOC ── */
  .toc{{ position:sticky; top:0; align-self:start; max-height:100vh; overflow-y:auto;
    padding:56px 10px 56px 0; }}
  .toc-title{{ font-family:var(--serif); font-size:12px; font-weight:600; letter-spacing:.14em;
    text-transform:uppercase; color:var(--ink-muted); margin-bottom:16px; padding-left:14px; }}
  .toc ul{{ list-style:none; padding:0; margin:0; border-left:1px solid var(--border); }}
  .toc a{{ display:block; padding:5px 0 5px 14px; margin-left:-1px;
    border-left:2px solid transparent; color:var(--ink-light); font-size:13px;
    line-height:1.5; text-decoration:none; transition:color .15s,border-color .15s; }}
  .toc a:hover{{ color:var(--ink); border-bottom:none; }}
  .toc a.active{{ color:var(--blue); border-left-color:var(--blue); font-weight:500; }}
  .toc li.lv3 a{{ padding-left:28px; font-size:12px; color:var(--ink-muted); }}
  .toc li.lv3 a.active{{ color:var(--blue); }}
  @media (max-width:920px){{
    .layout{{ grid-template-columns:1fr; padding:0 24px; }}
    .toc{{ display:none; }} .content{{ padding-top:48px; }} }}
  /* 文档头 */
  h1{{ font-family:var(--serif); font-size:27px; font-weight:700; line-height:1.35;
    color:var(--ink); padding-bottom:22px; border-bottom:2px solid var(--ink);
    margin-bottom:14px; letter-spacing:.01em; }}
  /* 章节标题(衬线 + 细规则线) */
  h2{{ font-family:var(--serif); font-size:19px; font-weight:700; color:var(--ink);
    margin:64px 0 28px; padding-bottom:15px; border-bottom:1px solid var(--rule);
    line-height:1.4; }}
  h3{{ font-family:var(--sans); font-size:15px; font-weight:500; color:var(--ink-mid);
    margin:30px 0 12px; padding-left:11px; border-left:3px solid var(--rule);
    letter-spacing:.02em; }}
  h4{{ font-family:var(--sans); font-size:11px; font-weight:500; letter-spacing:.13em;
    text-transform:uppercase; color:var(--ink-muted); margin:22px 0 10px; }}
  p{{ margin:9px 0; }}
  a{{ color:var(--blue); text-decoration:none; border-bottom:1px solid transparent; }}
  a:hover{{ border-bottom-color:var(--blue); }}
  strong{{ font-weight:500; color:var(--ink); }}
  /* 表格 —— 极简底线式,无卡片无投影 */
  .table-wrap{{ margin:18px 0 26px; overflow-x:auto; }}
  table{{ width:100%; border-collapse:collapse; font-size:13.5px; }}
  th{{ text-align:left; font-size:11px; font-weight:500; letter-spacing:.07em;
    text-transform:uppercase; color:var(--ink-muted); white-space:nowrap;
    border-bottom:1px solid var(--rule); padding:9px 14px 9px 0; }}
  td{{ padding:11px 14px 11px 0; border-bottom:1px solid var(--border);
    vertical-align:top; line-height:1.7; color:var(--ink-mid); }}
  tbody tr:last-child td{{ border-bottom:none; }}
  td code,th code{{ font-size:.92em; }}
  code{{ background:var(--code-bg); padding:.1em .4em; border-radius:3px;
    font-family:var(--mono); font-size:.85em; color:var(--ink); }}
  pre{{ background:var(--surface); border:1px solid var(--border); border-radius:6px;
    padding:18px 20px; overflow:auto; font-size:13px; line-height:1.55; margin:16px 0; }}
  pre code{{ background:none; padding:0; }}
  /* ASCII 线框图 —— 等宽,严禁换行(保对齐) */
  pre.wireframe{{ font-family:var(--mono); white-space:pre; line-height:1.4;
    color:var(--ink-mid); }}
  /* 内联 SVG 图 —— 纸白卡片,细边框 + 极轻层次(融合) */
  .mermaid-svg{{ background:#fff; border:1px solid var(--border); border-radius:6px;
    padding:24px; margin:18px 0; text-align:center; overflow:auto;
    box-shadow:0 1px 2px rgba(60,64,67,.04), 0 6px 18px rgba(60,64,67,.05); }}
  .mermaid-svg svg{{ max-width:100%; height:auto; }}
  /* 引用块 / 通俗理解 —— 蓝色左边线 callout */
  blockquote{{ margin:18px 0; padding:16px 22px; background:var(--blue-bg);
    border-left:3px solid var(--blue); border-radius:0 6px 6px 0; }}
  blockquote p{{ margin:6px 0; font-size:14px; line-height:1.8; color:var(--blue-dark); }}
  blockquote p:first-child{{ margin-top:0; }} blockquote p:last-child{{ margin-bottom:0; }}
  /* 一句话总结 —— 绿色判定 callout */
  .summary{{ background:var(--green-bg); border-left:3px solid var(--green);
    border-radius:0 6px 6px 0; padding:20px 24px; margin:18px 0 8px;
    font-size:15px; line-height:1.85; color:var(--green-dark); }}
  .summary strong{{ color:var(--green-dark); font-weight:600; }}
  /* 元信息 / 页脚 */
  .meta{{ color:var(--ink-muted); font-size:11px; letter-spacing:.05em;
    line-height:1.9; margin:0 0 8px; }}
  hr{{ border:none; border-top:1px solid var(--rule); margin:28px 0; }}
  ul,ol{{ padding-left:1.4em; margin:10px 0; }} li{{ margin:5px 0; }}
  ::selection{{ background:#ede9df; }}
</style>
</head>
<body>
'''

TEMPLATE_TAIL = '''
<script>
  // 滚动高亮当前章节(IntersectionObserver,零依赖)
  const links=[...document.querySelectorAll('.toc a')];
  const map=new Map(links.map(a=>[a.getAttribute('href').slice(1),a]));
  const obs=new IntersectionObserver((es)=>{
    es.forEach(e=>{ if(e.isIntersecting){
      links.forEach(l=>l.classList.remove('active'));
      const a=map.get(e.target.id); if(a) a.classList.add('active');
    }});
  },{rootMargin:'0px 0px -78% 0px', threshold:0});
  document.querySelectorAll('h2[id],h3[id]').forEach(h=>obs.observe(h));
</script>
</body>
</html>
'''

def slugify(t):
    t=re.sub(r'<[^>]+>','',t)                       # 去内联标签
    t=re.sub(r'[`*\[\]()]','',t).strip()
    t=re.sub(r'\s+','-',t)
    t=re.sub(r'[^\w一-鿿-]','',t)
    return t.lower() or 'sec'

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
    toc=[]; seen=set()
    def uniq(slug):
        s=slug; k=2
        while s in seen: s=f"{slug}-{k}"; k+=1
        seen.add(s); return s
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
            lvl=len(m.group(1)); raw=m.group(2); txt=inline(raw)
            if lvl in (2,3):                          # h2/h3 进 TOC + 锚点
                sid=uniq(slugify(raw))
                toc.append((lvl, sid, re.sub(r'<[^>]+>','',txt)))
                out.append(f'<h{lvl} id="{sid}">{txt}</h{lvl}>')
            else:
                out.append(f'<h{lvl}>{txt}</h{lvl}>')
            i+=1; continue
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
            joined=' '.join(buf)
            META=('分析框架','分析时间','分析深度','项目路径','自动生成')
            if any(k in joined for k in META):   # 文档元信息/页脚 → 细灰 .meta
                out.append('<p class="meta">'+'<br>'.join(inline(x) for x in buf if x.strip())+'</p>')
            else:                                 # 通俗理解等 → 蓝色 callout
                out.append('<blockquote><p>'+inline(joined)+'</p></blockquote>')
            continue
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
    return '\n'.join(out), toc

def build_toc(toc):
    if not toc: return ''
    items=''.join(
        f'<li class="lv{lvl}"><a href="#{sid}">{html.escape(txt)}</a></li>'
        for lvl,sid,txt in toc)
    return f'<nav class="toc"><div class="toc-title">目录</div><ul>{items}</ul></nav>'

def main():
    src, dst = sys.argv[1], sys.argv[2]
    md=open(src, encoding='utf-8').read()
    m=re.search(r'^#\s+(.*)$', md, re.M)
    title=m.group(1).strip() if m else 'Analysis Report'
    body_html, toc = render(md)         # 一级标题在正文里渲染;h2/h3 进 TOC
    htmlout=(TEMPLATE_HEAD.format(title=html.escape(title))
             + '<div class="layout">' + build_toc(toc)
             + '<main class="content">' + body_html + '</main></div>'
             + TEMPLATE_TAIL)
    open(dst,'w',encoding='utf-8').write(htmlout)
    import os
    print(f"✓ {dst}  ({os.path.getsize(dst)//1024} KB)")

if __name__=='__main__':
    main()
