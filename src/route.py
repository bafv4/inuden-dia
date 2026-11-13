# 停車駅のご案内（路線図）を、GitHub Pages でそのまま開ける1枚のページにする
# 使い方（どこからでも）: python src/route.py [入力 .dc.html] [出力 html]
#   入力の既定は page/route_src.dc.html、出力の既定は page/route.html。
#   路線図は別のチャットの Design キャンバス「犬電 停車駅図」（https://claude.ai/artifact/5HqsEBxu9Nk5CrXmEysTmr）で作っている。
#   その project/Main.dc.html を page/route_src.dc.html に写してから、これを実行する（2026-11-13 本人の依頼）。
#   .dc.html はキャンバスの実行環境（support.js）で描く形式なので、ここで使っている部分
#   （<helmet> の中身、{{穴}}、<sc-for>、Component の renderVals）だけを小さな JS で描き直す。
#   それ以外の書き方（<sc-if>・<dc-import> など）が出てきたら止める。そのときはこの変換を足す。
import os, re, sys, json, html

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "page", "route_src.dc.html")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "page", "route.html")

s = open(SRC, encoding="utf-8").read()

def one(pat, what):
    m = re.search(pat, s, re.S)
    if not m: sys.exit(f"{SRC}: {what}が見つからない")
    return m

title = html.unescape(one(r"<title>(.*?)</title>", "<title>").group(1).strip())
xdc = one(r"<x-dc>(.*?)</x-dc>", "<x-dc>").group(1)
helmet = one(r"<helmet>(.*?)</helmet>", "<helmet>").group(1).strip()
body = xdc.replace(one(r"<helmet>.*?</helmet>", "<helmet>").group(0), "").strip()
sm = one(r"<script type=\"text/x-dc\" data-dc-script(?:=\"\")?\s+data-props='(.*?)'>(.*?)</script>", "Component の <script>")
props, code = json.loads(sm.group(1)), sm.group(2).strip()
pv = props.get("$preview", {})
W, H = int(pv.get("width", 0)), int(pv.get("height", 0))
if not (W and H): sys.exit(f"{SRC}: $preview の大きさがない")

used = sorted(set(re.findall(r"<((?:sc|dc|x)-[a-z-]+)", body)) - {"sc-for"})
if used: sys.exit(f"{SRC}: この変換では描けない書き方がある: {', '.join(used)}")
if "</script" in body or "</template" in body or "</script" in code: sys.exit(f"{SRC}: 本文や Component に </script>・</template> がある")

page = f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<!-- src/route.py が page/route_src.dc.html（Design キャンバス「犬電 停車駅図」の Main.dc.html）から書き出した。直すときは元を直して書き出し直す -->
{helmet}
<style>
html,body{{background:#F5F1E9}}
.fit{{width:100%;overflow:hidden}}
.stage{{width:{W}px;height:{H}px;transform-origin:0 0}}
body{{margin:0}}
nav{{padding:12px 16px 0}}
.home{{display:inline-flex;align-items:center;gap:6px;padding:5px 12px 5px 9px;border:1px solid #DED2C4;border-radius:999px;background:#FBF9F4;color:#35383B;font:13px/1.2 'Zen Kaku Gothic New',sans-serif;text-decoration:none}}.home:hover,.home:focus-visible{{border-color:#35383B}}      /* 入口（index.html）へ戻る */
</style>
</head>
<body>
<nav><a class="home" href="index.html"><svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true"><path d="M10 3 5 8l5 5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>ホーム</a></nav>
<div class="fit" id="fit"><div class="stage" id="stage"></div></div>
<template id="dc">{body}</template>
<script>
// キャンバスの DCLogic の代わり（props と renderVals だけ使う）
class DCLogic{{constructor(props){{this.props=props||{{}}}}}}
{code}
(function(){{
  const vals=new Component({{}}).renderVals();
  const get=(path,scope)=>path.trim().split('.').reduce((o,k)=>o==null?undefined:o[k],scope);
  const fill=(str,scope)=>str.replace(/\\{{\\{{([^}}]+)\\}}\\}}/g,(_,p)=>{{const v=get(p,scope);return v==null?'':String(v)}});
  // <sc-for list="{{{{xs}}}}" as="x"> は中身を xs の数だけ繰り返す。ほかの要素は写して、属性と字の {{{{穴}}}} を埋める
  function expand(node,scope){{
    if(node.nodeType===3)return [document.createTextNode(fill(node.nodeValue,scope))];
    if(node.nodeType!==1)return [];
    if(node.localName==='sc-for'){{
      const list=get(node.getAttribute('list').replace(/^\\s*\\{{\\{{|\\}}\\}}\\s*$/g,''),scope)||[],as=node.getAttribute('as'),out=[];
      for(const item of list){{const sc=Object.create(scope);sc[as]=item;node.childNodes.forEach(c=>out.push(...expand(c,sc)))}}
      return out;
    }}
    const el=node.cloneNode(false);
    for(const a of [...el.attributes])if(a.value.includes('{{{{'))el.setAttribute(a.name,fill(a.value,scope));
    node.childNodes.forEach(c=>expand(c,scope).forEach(n=>el.appendChild(n)));
    return [el];
  }}
  const stage=document.getElementById('stage');
  document.getElementById('dc').content.childNodes.forEach(c=>expand(c,vals).forEach(n=>stage.appendChild(n)));
  // 幅に合わせて縮める（大きくはしない）
  const fit=document.getElementById('fit');
  const size=()=>{{const k=Math.min(1,fit.clientWidth/{W});stage.style.transform=`scale(${{k}})`;fit.style.height={H}*k+'px'}};
  addEventListener('resize',size);size();
}})();
</script>
</body>
</html>
"""
open(OUT, "w", encoding="utf-8", newline="\n").write(page)
print("書き出し", os.path.relpath(OUT, ROOT), f"{W}×{H}", title)
