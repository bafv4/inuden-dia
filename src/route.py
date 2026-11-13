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

# 拡大・縮小（2026-11-13 本人の依頼「停車駅図は拡大できるように」）。z は図の全体を画面の幅に合わせた大きさを 1 とする倍率で、
# 元の大きさの KMAX 倍まで。拡大すると図の枠は画面の高さまでになり、枠の中を縦横にスクロールする（マウスはつかんで動かせる）。
# ＋・－・全体のボタンのほか、Ctrl＋ホイール（トラックパッドのピンチ）でもポインタの位置を中心に拡大・縮小する
ZOOM_JS = r"""(function(){
  const W=__W__,H=__H__,KMAX=2.5,STEPS=[1,1.5,2,3,4,6,8,12,16];
  const $=id=>document.getElementById(id),fit=$('fit'),size=$('size'),stage=$('stage'),nav=document.querySelector('nav');
  let z=1,base=1;
  const zmax=()=>Math.max(1,KMAX/base);
  function apply(nz,ax,ay){            // ax・ay は枠の中の、動かさない点（省略すると枠のまん中）
    const old=base*z;
    base=Math.min(1,document.body.clientWidth/W);
    if(ax==null){ax=fit.clientWidth/2;ay=fit.clientHeight/2}
    const cx=(fit.scrollLeft+ax)/old,cy=(fit.scrollTop+ay)/old;
    z=Math.min(zmax(),Math.max(1,nz));
    const k=base*z,zoomed=z>1.001;
    stage.style.transform=`scale(${k})`;size.style.width=W*k+'px';size.style.height=H*k+'px';
    fit.classList.toggle('zoomed',zoomed);
    fit.style.height=(zoomed?Math.min(H*k,Math.max(240,innerHeight-nav.offsetHeight-16)):H*k)+'px';
    fit.scrollLeft=cx*k-ax;fit.scrollTop=cy*k-ay;
    $('zv').textContent=Math.round(z*100)+'%';
    $('zout').disabled=$('zall').disabled=!zoomed;$('zin').disabled=z>=zmax()-0.001;
  }
  $('zin').onclick=()=>apply(STEPS.find(s=>s>z+0.001)||zmax());
  $('zout').onclick=()=>apply([...STEPS].reverse().find(s=>s<z-0.001)||1);
  $('zall').onclick=()=>apply(1);
  // ホイールの1段（約100）で約1.35倍。トラックパッドのピンチは小さい値が続けて来るので少しずつ
  fit.addEventListener('wheel',e=>{if(!e.ctrlKey)return;e.preventDefault();const r=fit.getBoundingClientRect();const d=e.deltaMode===1?e.deltaY*33:e.deltaY;apply(z*Math.exp(-Math.max(-100,Math.min(100,d))*0.003),e.clientX-r.left,e.clientY-r.top)},{passive:false});
  // 拡大中はマウスでつかんで動かす（4px 動くまではクリックのまま）
  let drag=null,moved=false;
  fit.addEventListener('pointerdown',e=>{if(e.pointerType!=='mouse'||e.button!==0||z<=1.001)return;drag={x:e.clientX,y:e.clientY,l:fit.scrollLeft,t:fit.scrollTop};moved=false});
  addEventListener('pointermove',e=>{if(!drag)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;if(!moved&&Math.hypot(dx,dy)<4)return;if(!moved){moved=true;fit.classList.add('drag')}fit.scrollLeft=drag.l-dx;fit.scrollTop=drag.t-dy});
  addEventListener('pointerup',()=>{if(drag){drag=null;fit.classList.remove('drag')}});
  fit.addEventListener('click',e=>{if(moved){e.preventDefault();e.stopPropagation();moved=false}},true);
  addEventListener('resize',()=>apply(z));
  apply(1);
})();"""

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
.fit.zoomed{{overflow:auto;cursor:grab;user-select:none;-webkit-user-select:none;border-top:1px solid #DED2C4;border-bottom:1px solid #DED2C4}}
.fit.drag{{cursor:grabbing}}
.size{{position:relative;overflow:hidden}}
.stage{{width:{W}px;height:{H}px;transform-origin:0 0;position:absolute;left:0;top:0}}
body{{margin:0}}
nav{{display:flex;flex-wrap:wrap;align-items:center;gap:8px;padding:12px 16px 8px}}
.zoom{{margin-left:auto;display:inline-flex;align-items:center;border:1px solid #DED2C4;border-radius:999px;background:#FBF9F4;overflow:hidden;font:13px/1 'Zen Kaku Gothic New',sans-serif;color:#35383B}}      /* 拡大・縮小 */
.zoom button{{font:inherit;color:inherit;background:none;border:0;min-width:34px;height:30px;padding:0 8px;cursor:pointer;display:inline-grid;place-items:center}}
.zoom button:hover:not(:disabled),.zoom button:focus-visible{{background:#EFE8DC}}
.zoom button:disabled{{color:#B9B0A4;cursor:default}}
.zoom output{{min-width:3.6em;text-align:center;font-variant-numeric:tabular-nums}}
.zoom .all{{border-left:1px solid #DED2C4;padding:0 12px}}
.home{{display:inline-flex;align-items:center;gap:6px;padding:5px 12px 5px 9px;border:1px solid #DED2C4;border-radius:999px;background:#FBF9F4;color:#35383B;font:13px/1.2 'Zen Kaku Gothic New',sans-serif;text-decoration:none}}.home:hover,.home:focus-visible{{border-color:#35383B}}      /* 入口（index.html）へ戻る */
</style>
</head>
<body>
<nav><a class="home" href="index.html"><svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true"><path d="M10 3 5 8l5 5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>ホーム</a>
<div class="zoom" role="group" aria-label="拡大・縮小"><button type="button" id="zout" title="縮小" aria-label="縮小"><svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M2 6h8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg></button><output id="zv" aria-live="polite">100%</output><button type="button" id="zin" title="拡大（Ctrl＋ホイールでも）" aria-label="拡大"><svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M2 6h8M6 2v8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg></button><button type="button" id="zall" class="all" title="図の全体を画面の幅に合わせる">全体</button></div></nav>
<div class="fit" id="fit"><div class="size" id="size"><div class="stage" id="stage"></div></div></div>
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
}})();
</script>
<script>
{ZOOM_JS.replace("__W__", str(W)).replace("__H__", str(H))}
</script>
</body>
</html>
"""
open(OUT, "w", encoding="utf-8", newline="\n").write(page)
print("書き出し", os.path.relpath(OUT, ROOT), f"{W}×{H}", title)
