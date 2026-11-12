# 朝の上り（軒屋行）の組み方を見比べるページ（page/compare_extras.html）を書き出す。
# 使い方（data で）: PYTHONPATH=../src python ../src/compare_extras.py パターン.pkl 今の位置=extras.pkl 案2=extras_案2_毎時20本.pkl …
#   引数は ラベル=pickle（extras.pkl と同じ形：先頭が列車のリスト）。最後の引数が .html ならそこへ書き出す。
#   指標は「軒屋着がいちばん混む60分」の上り列車で数える。ダイヤグラムは 6:30〜9:15 を案ごとに上下に並べる。
import sys, os, json, pickle
PK = sys.argv[1]; ARGS = sys.argv[2:]; sys.argv = [sys.argv[0], PK]
from morning_run import *
import net
from compare import line_map, rows, MAJ_M, MAJ_H
W = (T(7, 30), T(9, 0))            # 到着の並びを描く範囲
DW = (T(6, 30), T(9, 15))          # ダイヤグラムに描く範囲
CW = (T(7, 0), T(9, 30))           # 競合を数える範囲
def ms(v):
    v = int(round(v)); return (f"{v//60}分{v%60:02d}秒" if v % 60 else f"{v//60}分") if v >= 60 else f"{v}秒"
def slow(t): return sum((getattr(t, "slow", None) or {}).values())          # 徐行で余分にかかる秒
def hold(t): return sum(v for x, v in t.hold.items() if x != t.o) + slow(t)   # 途中の待ち＝停車延長＋徐行
def same_overtakes(tr):
    """同じ種別どうしの追い越しの件数（6:30〜9:30 に走る列車）"""
    n = 0; L = [t for t in tr if t.kind != "回送" and t.arr(t.d) >= T(6, 30) and t.dep(t.o) <= T(9, 30)]
    for i, A in enumerate(L):
        for B in L[i + 1:]:
            if A.kind != B.kind or A.dir != B.dir: continue
            com = [x for x in A.route if x in B.times]
            if len(com) < 2: continue
            a0, b0 = A.dep(com[0]), B.dep(com[0]); a1, b1 = A.arr(com[-1]), B.arr(com[-1])
            if abs(a0 - b0) <= 3600 and (a0 - b0) * (a1 - b1) < 0: n += 1
    return n
def conf_text(c):
    f = lambda t: ("増発" if getattr(t, "extra", False) else "") + f"{t.kind}{t.o}発{fmt(t.dep(t.o))}"
    if c[0] == "seg": return f"続行 {c[4]}→{c[5]}：{f(c[2])} と {f(c[3])} が詰まりすぎ"
    if c[0] == "cross": return f"折返しの交差 {c[4]}：{f(c[2])} と {f(c[3])}"
    if c[0] == "occ": return f"ホームが足りない {c[4]}：" + "・".join(f(t) for t in c[3])
    return f"単線 {c[4][0]}〜{c[4][1]}：{f(c[2])} と {f(c[3])}"
def nokiya(tr):
    """軒屋（4線）のホームの埋まり方。既存の判定と同じ数え方（ops.turn_occ）。7:00〜9:30"""
    links, _ = link_nl(tr)
    for t in tr:
        if getattr(t, "src", None) is not None: links[t] = t.src
    occ = turn_occ(tr, links).get(("軒屋", "*"), [])
    ev = sorted([(a, 1) for a, b, t in occ] + [(b, -1) for a, b, t in occ], key=lambda z: (z[0], z[1]))
    cur = mx = full = three = 0; last = None
    for t, k in ev:
        if last is not None and CW[0] <= last < CW[1]:
            d = min(t, CW[1]) - last
            if cur >= 4: full += d
            if cur >= 3: three += d
        cur += k; last = t
        if CW[0] <= t <= CW[1]: mx = max(mx, cur)
    return {"max": mx, "full": full, "three": three}
def one(label, fn):
    tr = pickle.load(open(fn, "rb"))[0]
    for t in tr: t.compute()
    return summ(label, os.path.basename(fn), tr)
def summ(label, name, tr):
    """列車リスト tr の集計（比較ページ・編集ページ共通）"""
    cs, _ = all_conf2(tr); ix = {id(t): i for i, t in enumerate(tr)}
    up = sorted([t for t in tr if t.d == "軒屋" and t.kind != "回送"], key=lambda t: t.arr("軒屋"))
    a = [t.arr("軒屋") for t in up if CW[0] <= t.arr("軒屋") <= CW[1]]
    n, s0 = max((sum(1 for x in a if s <= x < s + 3600), -s) for s in a); s0 = -s0        # いちばん混む60分（同数なら早い方）
    H = [t for t in up if s0 <= t.arr("軒屋") < s0 + 3600]
    nxt = min(t.arr("軒屋") for t in up if t.arr("軒屋") >= s0 + 3600)
    arr = [t.arr("軒屋") for t in H] + [nxt]; g = [b - c for c, b in zip(arr, arr[1:])]
    kinds = {}
    for kd in ("各停", "急行", "快速"):
        L = [t for t in H if t.kind == kd]
        kinds[kd] = {"n": len(L), "w": sum(hold(t) for t in L), "max": max([hold(t) for t in L] + [0]), "long": sum(1 for t in L if hold(t) >= 180)}
    kg = {}                # 同じ種別どうしの軒屋着の最短間隔（混む60分に着く列車と、その前後）
    for kd in ("各停", "急行", "快速"):
        ka = [t.arr("軒屋") for t in up if t.kind == kd and s0 - 1200 <= t.arr("軒屋") < s0 + 4800]
        gs = [b - c for c, b in zip(ka, ka[1:]) if s0 <= b and c < s0 + 3600]
        if gs: kg[kd] = min(gs)
    tt = {}
    for t in H: tt.setdefault(f"{t.kind} {t.o}発", []).append(t.arr("軒屋") - t.dep(t.o))
    dia = []        # ダイヤグラム用。(同じ列車かどうかの印, 列車)
    for i, t in enumerate(tr):
        if t.dep(t.o) > DW[1] or t.arr(t.d) < DW[0]: continue
        r = rows(t)
        dia.append((json.dumps([t.kind, t.o, t.d, [[x[0], x[1] and round(x[1], 1), x[2] and round(x[2], 1)] for x in r]], ensure_ascii=False),
                    {"i": i, "kind": t.kind, "o": t.o, "d": t.d, "dir": t.dir, "x": bool(getattr(t, "extra", False)), "note": t.note or "", "line": line_map(t), "rows": r,
                     "ed": bool(getattr(t, "edited", False))}))
    cw = [c for c in cs if CW[0] <= c[1] <= CW[1]]
    return {"label": label, "file": name, "dia": dia, "conf": len(cw), "noki": nokiya(tr),
            "confs": [{"t": c[1], "st": c[4] if isinstance(c[4], str) else c[4][0], "text": conf_text(c), "ids": [ix[id(t)] for t in involved(c) if id(t) in ix]} for c in cw[:40]],
            "same": same_overtakes(tr),
            "arr": [[t.arr("軒屋"), t.kind, bool(getattr(t, "extra", False)), t.o] for t in up if W[0] <= t.arr("軒屋") <= W[1]],
            "peak": [n, fmt(s0)], "gmin": min(g), "gmax": max(g), "short": sum(1 for x in g if x <= 90), "long": sum(1 for x in g if x >= 240),
            "mura": sum(abs(x - 180) for x in g) / 2, "kinds": kinds, "wsum": sum(hold(t) for t in H),
            "tt": {k: sum(v) / len(v) for k, v in tt.items()},
            "list": [{"kind": t.kind, "o": t.o, "x": bool(getattr(t, "extra", False)), "dep": fmt(t.dep(t.o)), "arr": fmt(t.arr("軒屋")), "w": hold(t),
                      "adj": (t.arr("軒屋") - t.before[1]) if getattr(t, "adjusted", None) else None,
                      "wait": "、".join([f"{k} {ms(v)}" for k, v in t.hold.items() if v and k != t.o] + ([f"徐行 {ms(slow(t))}"] if slow(t) else []))} for t in H],
            "slow": sum(slow(t) for t in H), "kgap": kg, "adj": sum(1 for t in tr if getattr(t, "adjusted", None))}
TMPL = r"""<title>犬電 朝の上りの比較</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Zen+Kaku+Gothic+New:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
/* Layout: 見出し → 指標の表 → 軒屋着の帯（案ごとに上下に並べる。増発は別の段）→ ダイヤグラム（案ごとに上下に並べ、横スクロール連動）→ いちばん混む60分の列車（案を横に並べる） */
:root{--bg:#F5F1E9;--panel:#FBF9F4;--ink:#35383B;--sub:#645044;--muted:#7B6A5E;--line:#DED2C4;--grid:rgba(222,210,196,.16);
  --teal:#236962;--amber:#EAC05B;--brick:#963D39;--k-loc:#35383B;--k-exp:#246BA3;--k-rap:#BE493B;--dia-bg:#FFFDF8;--dia-grid:#ECE4D8;--dia-grid2:#DCCFBF;--dia-st:#E7DED2;--dia-major:#CDBDAA;--tk:#fff;
  --f-ui:"Zen Kaku Gothic New","Hiragino Kaku Gothic ProN","Noto Sans JP","Yu Gothic",sans-serif;--f-num:"IBM Plex Mono",ui-monospace,Menlo,monospace}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#2E3134;--panel:#35383B;--ink:#F5F1E9;--sub:#DED2C4;--muted:#B8A898;--line:#4C5054;--grid:rgba(222,210,196,.04);
  --teal:#5BAEA3;--amber:#EAC05B;--brick:#D26B64;--k-loc:#EDE6DA;--k-exp:#6FA8DA;--k-rap:#E67A6C;--dia-bg:#303336;--dia-grid:#3A3E42;--dia-grid2:#474B50;--dia-st:#3C4044;--dia-major:#5A5E63;--tk:#2E3134;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#2E3134;--panel:#35383B;--ink:#F5F1E9;--sub:#DED2C4;--muted:#B8A898;--line:#4C5054;--grid:rgba(222,210,196,.04);
  --teal:#5BAEA3;--amber:#EAC05B;--brick:#D26B64;--k-loc:#EDE6DA;--k-exp:#6FA8DA;--k-rap:#E67A6C;--dia-bg:#303336;--dia-grid:#3A3E42;--dia-grid2:#474B50;--dia-st:#3C4044;--dia-major:#5A5E63;--tk:#2E3134;color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background-color:var(--bg);color:var(--ink);font-family:var(--f-ui);line-height:1.7;
  background-image:repeating-linear-gradient(45deg,var(--grid) 0 4px,transparent 4px 52px),repeating-linear-gradient(-45deg,var(--grid) 0 4px,transparent 4px 52px)}
.wrap{max-width:1440px;margin:0 auto;padding:36px max(16px,env(safe-area-inset-right,0px)) 72px max(16px,env(safe-area-inset-left,0px));display:flex;flex-direction:column;gap:40px}
header{display:flex;flex-direction:column;gap:10px;max-width:76ch}
.eyebrow{font-size:11.5px;letter-spacing:.16em;color:var(--sub);font-weight:500}
h1{font-size:clamp(26px,4vw,36px);font-weight:700;letter-spacing:.06em;margin:0;line-height:1.3;text-wrap:balance}
h2{font-size:18px;margin:0;letter-spacing:.08em}h3{font-size:14.5px;margin:0}p{margin:0}
.lead{color:var(--sub);font-size:14.5px}
section{display:flex;flex-direction:column;gap:14px;min-width:0}
.sec-h{display:flex;flex-wrap:wrap;align-items:baseline;gap:6px 16px;border-top:1.5px solid var(--ink);padding-top:10px}
.sec-h .meta{font-size:12.5px;color:var(--muted)}
.small{font-size:12.5px;color:var(--muted)}
.scrollx{overflow-x:auto;border:1px solid var(--line);background:var(--panel)}
.narrow{max-width:1100px}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{padding:7px 14px;border-bottom:1px solid var(--line);text-align:right;vertical-align:baseline;white-space:nowrap}
th.l,td.l{text-align:left}
thead th{background:var(--ink);color:var(--bg);font-weight:700}
thead th .f{display:block;font-family:var(--f-num);font-size:10.5px;font-weight:400;opacity:.75}
td{font-family:var(--f-num)}td.l{font-family:var(--f-ui)}
td.l .s{display:block;font-size:11.5px;color:var(--muted);line-height:1.4}
td.best{color:var(--teal);font-weight:500;box-shadow:inset 3px 0 0 var(--teal)}
tr.cap td{background:color-mix(in srgb,var(--line) 45%,transparent);font-family:var(--f-ui);font-size:12px;color:var(--sub);text-align:left;letter-spacing:.06em;padding-block:4px}
table.ex td{text-align:left;font-family:var(--f-ui);white-space:normal;vertical-align:top;padding-block:5px}
table.ex .t{font-family:var(--f-num);white-space:nowrap}
.wait{color:var(--brick)}.none{color:var(--muted)}
.chip{display:inline-block;font-size:11px;font-weight:700;padding:0 6px;border-radius:2px;color:var(--tk);background:var(--c);line-height:1.6}
.chip.x{box-shadow:0 0 0 2px var(--amber)}
.g{display:flex;flex-direction:column;gap:6px;min-width:1180px;padding:12px 14px}
.g+.g{border-top:1px solid var(--line)}
.row{display:grid;grid-template-columns:130px minmax(0,1fr);gap:12px;align-items:center}
.pl{font-size:13px;font-weight:700;line-height:1.35}.pl span{display:block;font-weight:400;font-size:11.5px;color:var(--muted)}
.strip{background:var(--dia-bg);border:1px solid var(--line);padding:0 26px}
.lane{position:relative;height:21px;background-image:linear-gradient(to right,var(--dia-grid2) 1px,transparent 1px);background-size:16.6667% 100%;border-right:1px solid var(--dia-grid2)}
.lane+.lane{border-top:1px dashed var(--dia-grid)}
.lane.x{background-color:color-mix(in srgb,var(--amber) 14%,transparent)}
.tk{position:absolute;top:2px;transform:translateX(-50%);font-family:var(--f-num);font-size:11px;line-height:16px;padding:0 3px;border-radius:2px;color:var(--tk);background:var(--c);white-space:nowrap}
.tk sup{font-size:8px}
.tk.x{box-shadow:0 0 0 2px var(--amber)}
.axis{display:grid;grid-template-columns:130px minmax(0,1fr);gap:12px;font-family:var(--f-num);font-size:11px;color:var(--muted)}
.axis div:last-child{display:flex;justify-content:space-between;padding:0 8px}
.controls{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center}
.seg{display:inline-flex;flex-wrap:wrap;border:1px solid var(--line);border-radius:4px;overflow:hidden;background:var(--panel)}
.seg button{font:inherit;font-size:13px;border:0;background:transparent;color:var(--ink);padding:6px 12px;cursor:pointer}
.seg button+button{border-left:1px solid var(--line)}
.seg button[aria-pressed="true"]{background:var(--ink);color:var(--bg)}
button:focus-visible{outline:2px solid var(--teal);outline-offset:2px}
.hint{font-size:12.5px;color:var(--muted)}
.dblk{display:flex;flex-direction:column;gap:4px}
.dh{display:flex;flex-wrap:wrap;gap:4px 14px;align-items:baseline}
.dh b{font-size:14.5px;letter-spacing:.04em}
.dia{display:grid;grid-template-columns:88px minmax(0,1fr);border:1px solid var(--line);background:var(--dia-bg);border-radius:3px}
.dia .lab{position:relative;border-right:1px solid var(--line);background:var(--panel)}
.dia .lab span{position:absolute;left:0;right:0;transform:translateY(-50%);font-size:11px;text-align:right;padding:0 8px 0 4px;color:var(--sub);line-height:1.1;white-space:nowrap}
.dia .lab span.maj{color:var(--ink);font-weight:700;font-size:12px}
.dia .pane{overflow-x:auto;overflow-y:hidden;position:relative}
.dia canvas{display:block;cursor:pointer}
.pop{position:absolute;z-index:5;background:var(--panel);border:1px solid var(--line);box-shadow:0 6px 20px rgba(0,0,0,.14);border-radius:4px;padding:10px 12px;font-size:12.5px;max-width:300px}
.pop h4{margin:0 0 4px;font-size:13.5px}
.pop .close{position:absolute;right:6px;top:4px;border:0;background:transparent;color:var(--muted);font-size:16px;cursor:pointer}
.pop table{width:auto;font-size:12px}
.pop td{padding:1px 8px 1px 0;border:0;text-align:left}
.pop td:first-child{font-family:var(--f-ui)}
.pop .pass td{color:var(--muted)}
.pop .scroll{max-height:280px;overflow:auto}
.lg{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:12.5px}
.lg span{display:inline-flex;align-items:center;gap:6px}
</style>
<div class="wrap">
<header>
  <div class="eyebrow">犬村電気鉄道　運転計画（案）　平日朝</div>
  <h1>朝の上りの比較</h1>
  <p class="lead">朝のいちばん混む時間帯の上り（軒屋行）を、組み方ごとに並べています。数字は、軒屋着がいちばん混む60分に着く列車で数えています。</p>
  <div class="lg"><span><i class="chip" style="--c:var(--k-rap)">快</i>快速</span><span><i class="chip" style="--c:var(--k-exp)">急</i>急行</span><span><i class="chip" style="--c:var(--k-loc)">各</i>各停</span><span><i class="chip x" style="--c:var(--k-exp)">急</i>増発（折返しに使わず、車庫から出て車庫へ入る列車）</span></div>
</header>
<section>
  <div class="sec-h"><h2>指標</h2><span class="meta">緑の印はその行でいちばん良い案です。</span></div>
  <div class="scrollx narrow"><table id="cmp"></table></div>
</section>
<section>
  <div class="sec-h"><h2>軒屋への到着の並び</h2><span class="meta">7:30〜9:00。数字は分（小さい字は秒）。上の3段が折返しに使う列車、色つきの2段が増発です。</span></div>
  <div class="scrollx" id="strips"></div>
</section>
<section>
  <div class="sec-h"><h2>ダイヤグラム</h2><span class="meta">6:30〜9:15。横軸が時刻、縦軸が軒屋からの距離です。黄色の縁どりが増発。横スクロールは上下の案で連動します。線をクリックすると停車駅と時刻が出ます。</span></div>
  <div class="controls">
    <div class="seg" role="group" aria-label="表示する案" id="patSeg"></div>
    <div class="seg" role="group" aria-label="表示する路線" id="lineSeg">
      <button type="button" data-l="main" aria-pressed="true">本線・奥雲線</button><button type="button" data-l="hasu" aria-pressed="false">蓮木線</button>
    </div>
    <div class="seg" role="group" aria-label="表示する列車" id="dirSeg">
      <button type="button" data-d="U" aria-pressed="true">上りだけ</button><button type="button" data-d="A" aria-pressed="false">上り・下り</button>
    </div>
    <div class="seg" role="group" aria-label="拡大縮小"><button type="button" id="zo">縮小</button><button type="button" id="zi">拡大</button></div>
    <span class="hint" id="zoomlab"></span>
  </div>
  <div id="dias" style="display:flex;flex-direction:column;gap:18px"></div>
</section>
<section>
  <div class="sec-h"><h2>いちばん混む60分の上り列車</h2><span class="meta">軒屋に着く順。途中の待ちは、待避などで通常より長く止まる駅と時間、徐行で延びる時間です（3分以上は赤字）。「日中から変更」は、日中パターンと時刻を変えた既存の列車です。</span></div>
  <div class="scrollx"><table class="ex" id="ex"></table></div>
</section>
</div>
<script type="application/json" id="data">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent),P=D.pats,$=id=>document.getElementById(id);
const KC={"快速":"--k-rap","急行":"--k-exp","各停":"--k-loc"},T0=27000,T1=32400;
const ms=s=>{s=Math.round(s);const m=Math.floor(s/60),r=s%60;return m?(r?`${m}分${String(r).padStart(2,'0')}秒`:`${m}分`):`${r}秒`};
const mm=t=>{t=Math.round(t);const m=Math.floor(t%3600/60),s=t%60;return String(m).padStart(2,'0')+(s?`<sup>${String(s).padStart(2,'0')}</sup>`:'')};
const tts=[];P.forEach(p=>Object.keys(p.tt).forEach(k=>{if(!tts.includes(k))tts.push(k)}));tts.sort();
const ROWS=[
 {l:"いちばん混む60分の本数",s:"目標は20本",get:p=>p.peak[0],f:(v,p)=>`${v}本<span class="small">　${p.peak[1]}〜</span>`,b:1},
 {l:"競合",s:"7:00〜9:30",get:p=>p.conf,f:v=>v+"件",b:-1},
 {l:"同じ種別どうしの追い越し",get:p=>p.same,f:v=>v+"件",b:-1},
 {l:"軒屋のホーム（4線）",s:"同時に使う線の最大／3線以上埋まる時間",get:p=>p.noki.max*100000+p.noki.three,f:(v,p)=>`${p.noki.max}線<span class="small">　${ms(p.noki.three)}</span>`,b:-1},
 {l:"時刻を動かした既存の列車",s:"日中パターンからの変更",get:p=>p.adj,f:v=>v+"本",b:-1},
 {cap:"軒屋着の間隔"},
 {l:"いちばん短い間隔",get:p=>p.gmin,f:ms,b:1},
 {l:"1分30秒間隔の箇所",get:p=>p.short,f:v=>v+"か所",b:-1},
 {l:"いちばん長い空き",get:p=>p.gmax,f:ms,b:-1},
 {l:"4分以上の空き",get:p=>p.long,f:v=>v+"か所",b:-1},
 {l:"間隔のむら",s:"3分間隔からのずれの合計",get:p=>p.mura,f:ms,b:-1},
 {l:"急行どうしの最短間隔",s:"増発と既存がくっついて走っていないか",get:p=>p.kgap["急行"],f:ms,b:1},
 {l:"各停どうしの最短間隔",get:p=>p.kgap["各停"],f:ms,b:1},
 {cap:"途中の待ち（待避・抑止で通常より長く止まる時間）"},
 {l:"合計",s:"停車延長＋徐行",get:p=>p.wsum,f:ms,b:-1},
 {l:"　うち徐行",s:"駅間をゆっくり走って延びる時間",get:p=>p.slow,f:ms},
 {l:"各停",s:"合計／いちばん長い1本",get:p=>p.kinds["各停"].w,f:(v,p)=>`${ms(v)}<span class="small">　最大 ${ms(p.kinds["各停"].max)}</span>`,b:-1},
 {l:"急行",get:p=>p.kinds["急行"].w,f:(v,p)=>`${ms(v)}<span class="small">　最大 ${ms(p.kinds["急行"].max)}</span>`,b:-1},
 {l:"快速",get:p=>p.kinds["快速"].w,f:(v,p)=>`${ms(v)}<span class="small">　最大 ${ms(p.kinds["快速"].max)}</span>`,b:-1},
 {l:"途中で3分以上待つ列車",get:p=>p.kinds["各停"].long+p.kinds["急行"].long+p.kinds["快速"].long,f:v=>v+"本",b:-1},
 {cap:"軒屋までの所要時間（平均）"},
 ...tts.map(k=>({l:k,get:p=>p.tt[k],f:ms,b:-1}))];
$('cmp').innerHTML=`<thead><tr><th class="l"></th>${P.map(p=>`<th>${p.label}<span class="f">${p.file}</span></th>`).join('')}</tr></thead><tbody>`+ROWS.map(r=>{
  if(r.cap)return `<tr class="cap"><td colspan="${P.length+1}">${r.cap}</td></tr>`;
  const vs=P.map(r.get),ok=vs.filter(v=>v!=null),best=r.b&&new Set(ok).size>1?(r.b<0?Math.min(...ok):Math.max(...ok)):null;
  return `<tr><td class="l">${r.l}${r.s?`<span class="s">${r.s}</span>`:''}</td>${vs.map((v,i)=>v==null?'<td>—</td>':`<td class="${v===best?'best':''}">${r.f(v,P[i])}</td>`).join('')}</tr>`}).join('')+'</tbody>';
const LANES=[["快速",0],["急行",0],["各停",0],["急行",1],["各停",1]];
$('strips').innerHTML=P.map(p=>`<div class="g"><div class="row"><div class="pl">${p.label}<span>混む60分 ${p.peak[0]}本・最短 ${ms(p.gmin)}・最長 ${ms(p.gmax)}</span></div><div class="strip">${LANES.map(([k,x])=>`<div class="lane ${x?'x':''}">${p.arr.filter(a=>a[1]===k&&!!a[2]===!!x).map(a=>`<span class="tk ${x?'x':''}" style="left:${(a[0]-T0)/(T1-T0)*100}%;--c:var(${KC[k]})" title="${k}${x?'（増発）':''} ${a[3]}発">${mm(a[0])}</span>`).join('')}</div>`).join('')}</div></div>
  <div class="axis"><div></div><div><span>7:30</span><span>7:45</span><span>8:00</span><span>8:15</span><span>8:30</span><span>8:45</span><span>9:00</span></div></div></div>`).join('');
const n=Math.max(...P.map(p=>p.list.length));
$('ex').innerHTML=`<thead><tr><th class="l">着順</th>${P.map(p=>`<th class="l">${p.label}</th>`).join('')}</tr></thead><tbody>`+Array.from({length:n},(_,i)=>`<tr><td class="t">${i+1}</td>${P.map(p=>{const e=p.list[i];if(!e)return '<td class="none">—</td>';
  return `<td><span class="chip ${e.x?'x':''}" style="--c:var(${KC[e.kind]})">${e.kind}</span> ${e.o}発　<span class="t">${e.dep} → ${e.arr}</span>　${e.w?`<span class="${e.w>=180?'wait':''}">${e.wait}</span>`:'<span class="none">待ちなし</span>'}${e.adj!=null?`<br><span class="small">日中から変更（軒屋着 ${e.adj>0?'+'+ms(e.adj):e.adj<0?'−'+ms(-e.adj):'同じ'}）</span>`:''}</td>`}).join('')}</tr>`).join('')+'</tbody>';
// ---- ダイヤグラム
const css=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const fmtP=t=>{t=Math.round(t);const h=Math.floor(t/3600),m=Math.floor(t%3600/60),s=t%60;return `${h}:${String(m).padStart(2,'0')}`+(s?`'${String(s).padStart(2,'0')}`:'')};
let line="main",dirSel="U",pxMin=8,show=new Set(P.map((_,i)=>i)),sel=null,panes=[],pop=null;
const DT0=D.t0,DT1=D.t1,LINES={main:{st:D.main,h:560},hasu:{st:D.hasu,h:260}};
$('patSeg').innerHTML=P.map((p,i)=>`<button type="button" data-i="${i}" aria-pressed="true">${p.label}</button>`).join('');
function trainPts(t,L){
  const st=LINES[L].st,km={};st.forEach(s=>km[s[0]]=s[1]);
  const pts=[],want=(L==="main")?"M":"H";
  const usesL=Object.entries(t.line).some(([s,v])=>s!=="学院前"&&v===want);
  for(const r of t.rows){
    const onL=t.line[r[0]]===want||(r[0]==="学院前"&&usesL);
    if(!onL){ if(pts.length&&pts[pts.length-1]!==null)pts.push(null); continue;}
    const k=km[r[0]]; if(k===undefined)continue;
    if(r[1]!=null)pts.push([r[1],k]);
    if(r[2]!=null&&r[2]!==r[1])pts.push([r[2],k]);
    else if(r[1]==null&&r[2]!=null)pts.push([r[2],k]);
  }
  return pts;
}
function path(g,sc){g.beginPath();let pen=false;for(const p of sc){if(!p){pen=false;continue;}if(!pen){g.moveTo(p[0],p[1]);pen=true;}else g.lineTo(p[0],p[1]);}}
function draw(p,cv,lab){
  const L=LINES[line],st=L.st,H=L.h,top=26,bot=10,maxKm=st[st.length-1][1];
  const W=Math.round((DT1-DT0)/60*pxMin)+48,dpr=window.devicePixelRatio||1;
  cv.width=W*dpr;cv.height=(H+top+bot)*dpr;cv.style.width=W+'px';cv.style.height=(H+top+bot)+'px';lab.style.height=(H+top+bot)+'px';
  const g=cv.getContext('2d');g.setTransform(dpr,0,0,dpr,0,0);
  g.fillStyle=css('--dia-bg');g.fillRect(0,0,W,H+top+bot);
  const X=t=>24+(t-DT0)/60*pxMin,Y=k=>top+k/maxKm*H;
  const step=pxMin>=10?2:pxMin>=5?5:10;
  for(let t=Math.ceil(DT0/60/step)*step*60;t<=DT1;t+=step*60){
    const m=(t/60)%60,x=X(t);
    g.strokeStyle=m===0?css('--dia-major'):(m%10===0?css('--dia-grid2'):css('--dia-grid'));
    g.lineWidth=m===0?1.4:1;g.beginPath();g.moveTo(x,top);g.lineTo(x,top+H);g.stroke();
    if(m%10===0){g.fillStyle=m===0?css('--ink'):css('--muted');g.font=(m===0?'700 12px ':'11px ')+css('--f-num');g.textAlign='center';g.fillText(m===0?`${t/3600}:00`:String(m).padStart(2,'0'),x,top-9);}
  }
  for(const s of st){g.strokeStyle=s[2]?css('--dia-major'):css('--dia-st');g.lineWidth=s[2]?1:0.7;g.beginPath();g.moveTo(0,Y(s[1]));g.lineTo(W,Y(s[1]));g.stroke();}
  if(line==="main"){for(const [a,b] of D.single){g.fillStyle='rgba(184,154,130,.10)';g.fillRect(0,Y(a),W,Y(b)-Y(a));}}
  const cache=[],order=["各停","急行","快速"];
  const list=D.common.concat(p.trains).filter(t=>dirSel==="A"||t.dir==="U").sort((a,b)=>(a.x?1:0)-(b.x?1:0)||order.indexOf(a.kind)-order.indexOf(b.kind));
  for(const t of list){
    const pts=trainPts(t,line); if(pts.filter(q=>q).length<2)continue;
    const sc=pts.map(q=>q&&[X(q[0]),Y(q[1])]);cache.push({t,sc});
    if(t.x){g.strokeStyle=css('--amber');g.lineWidth=5;path(g,sc);g.stroke();}
    g.strokeStyle=css(KC[t.kind]);g.lineWidth=t.x?2:(t.kind==="各停"?1.1:1.8);path(g,sc);g.stroke();
  }
  if(sel&&sel.p===p){const c=cache.find(c=>c.t===sel.t);if(c){g.strokeStyle=css('--teal');g.lineWidth=3;path(g,c.sc);g.stroke();}}
  const placed=st.filter(s=>s[2]).map(s=>Y(s[1])),names=st.filter(s=>s[2]);
  for(const s of st){if(s[2])continue;const y=Y(s[1]);if(placed.every(q=>Math.abs(q-y)>=12)){placed.push(y);names.push(s);}}
  lab.innerHTML=names.map(s=>`<span class="${s[2]?'maj':''}" style="top:${Y(s[1])}px">${s[0]}</span>`).join('');
  return cache;
}
function segDist(px,py,a,b){const dx=b[0]-a[0],dy=b[1]-a[1],l=dx*dx+dy*dy;let u=l?((px-a[0])*dx+(py-a[1])*dy)/l:0;u=Math.max(0,Math.min(1,u));return Math.hypot(px-(a[0]+u*dx),py-(a[1]+u*dy));}
function closePop(){if(pop){pop.remove();pop=null;}}
function showPop(pane,t,x,y){
  closePop();pop=document.createElement('div');pop.className='pop';
  const rows=t.rows.map(r=>{const stop=r[3];const tm=stop?`${r[1]!=null&&r[0]!==t.o?fmtP(r[1]):''}${r[1]!=null&&r[2]!=null&&r[0]!==t.o?' → ':''}${r[2]!=null?fmtP(r[2]):''}`:'レ';return `<tr class="${stop?'':'pass'}"><td>${r[0]}</td><td>${tm}</td><td>${r[5]?`<span class="wait">徐行+${ms(r[5])}</span> `:''}${r[4]?`<span class="wait">+${ms(r[4])}</span>`:''}</td></tr>`}).join('');
  pop.innerHTML=`<button class="close" type="button" aria-label="閉じる">×</button><h4><span class="chip ${t.x?'x':''}" style="--c:var(${KC[t.kind]})">${t.kind}</span> ${t.d}行${t.x?'（増発）':''}</h4><div class="small">${t.o} ${fmtP(t.rows[0][2])}発${t.note?'・'+t.note:''}</div><div class="scroll"><table>${rows}</table></div>`;
  pane.appendChild(pop);
  const pw=300;let left=x+pane.scrollLeft+12;if(left+pw>pane.scrollLeft+pane.clientWidth)left=x+pane.scrollLeft-pw-12;
  pop.style.left=Math.max(pane.scrollLeft+4,left)+'px';pop.style.top=Math.max(4,Math.min(y-40,pane.clientHeight-330))+'px';
  pop.querySelector('.close').onclick=()=>{sel=null;drawAll();};
}
function drawAll(){
  const keep=panes.length?panes[0].scrollLeft:null;
  closePop();$('dias').innerHTML='';panes=[];
  P.forEach((p,i)=>{
    if(!show.has(i))return;
    const blk=document.createElement('div');blk.className='dblk';
    blk.innerHTML=`<div class="dh"><b>${p.label}</b><span class="hint">混む60分 ${p.peak[0]}本・途中の待ち ${ms(p.wsum)}・軒屋着 最短 ${ms(p.gmin)}／最長 ${ms(p.gmax)}</span></div><div class="dia"><div class="lab"></div><div class="pane"><canvas></canvas></div></div>`;
    $('dias').appendChild(blk);
    const pane=blk.querySelector('.pane'),cv=blk.querySelector('canvas'),cache=draw(p,cv,blk.querySelector('.lab'));
    pane.addEventListener('scroll',()=>{for(const o of panes)if(o!==pane&&Math.abs(o.scrollLeft-pane.scrollLeft)>1)o.scrollLeft=pane.scrollLeft;});
    cv.addEventListener('click',e=>{
      const r=cv.getBoundingClientRect(),x=e.clientX-r.left,y=e.clientY-r.top;let best=null;
      for(const c of cache){for(let k=1;k<c.sc.length;k++){const a=c.sc[k-1],b=c.sc[k];if(!a||!b)continue;const d=segDist(x,y,a,b)-(c.t.x?1.5:0);if(d<7&&(!best||d<best.d))best={d,t:c.t};}}
      if(best){sel={p,t:best.t};const sl=pane.scrollLeft;drawAll();const np=panes[[...show].sort((a,b)=>a-b).indexOf(i)];panes.forEach(o=>o.scrollLeft=sl);showPop(np,best.t,x,y);}
      else if(sel){sel=null;drawAll();}
    });
    panes.push(pane);
  });
  const sl=keep!=null?keep:(7*3600-DT0)/60*pxMin;       // 最初は 7:00 から
  panes.forEach(o=>o.scrollLeft=sl);
  $('zoomlab').textContent=show.size?`1分＝${pxMin}px`:'表示する案を選んでください';
}
$('patSeg').onclick=e=>{const b=e.target.closest('button');if(!b)return;const i=+b.dataset.i;show.has(i)?show.delete(i):show.add(i);b.setAttribute('aria-pressed',show.has(i));sel=null;drawAll();};
document.querySelectorAll('#lineSeg button').forEach(b=>b.onclick=()=>{line=b.dataset.l;document.querySelectorAll('#lineSeg button').forEach(x=>x.setAttribute('aria-pressed',x===b));sel=null;drawAll();});
document.querySelectorAll('#dirSeg button').forEach(b=>b.onclick=()=>{dirSel=b.dataset.d;document.querySelectorAll('#dirSeg button').forEach(x=>x.setAttribute('aria-pressed',x===b));sel=null;drawAll();});
function zoom(f){const pane=panes[0];const c=pane?(pane.scrollLeft+pane.clientWidth/2)/pxMin:0;pxMin=Math.max(3,Math.min(24,Math.round(pxMin*f*2)/2));drawAll();if(pane)panes.forEach(o=>o.scrollLeft=c*pxMin-o.clientWidth/2);}
$('zi').onclick=()=>zoom(1.5);$('zo').onclick=()=>zoom(1/1.5);
drawAll();
window.addEventListener('resize',()=>drawAll());
try{matchMedia('(prefers-color-scheme: dark)').addEventListener('change',()=>drawAll());}catch(e){}
new MutationObserver(()=>drawAll()).observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});
</script>
"""
if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "page", "compare_extras.html")
    if ARGS and ARGS[-1].endswith(".html"): out = ARGS.pop()
    pats = [one(*a.split("=", 1)) for a in ARGS]
    # どの案にも同じ時刻である列車（日中パターンなど）は1回だけ持ち、案ごとには違う列車だけ持つ
    common = set.intersection(*[set(k for k, _ in p["dia"]) for p in pats])
    com = [o for k, o in pats[0]["dia"] if k in common]
    for p in pats: p["trains"] = [o for k, o in p.pop("dia") if k not in common]
    D = {"pats": pats, "common": com, "t0": DW[0], "t1": DW[1], "single": [list(x) for x in net.SINGLE],
         "main": [[s, k, s in MAJ_M] for s, k in net.MAIN], "hasu": [[s, k, s in MAJ_H] for s, k in net.HASU]}
    open(out, "w", encoding="utf-8").write(TMPL.replace("__DATA__", json.dumps(D, ensure_ascii=False).replace("</", "<\\/")))
    print("書き出し", out, "／共通の列車", len(com), "本、案ごとに違う列車", [len(p["trains"]) for p in pats])
    for d in pats: print("  ", d["label"], "混む60分", d["peak"], "最短", d["gmin"], "最長", d["gmax"], "むら", d["mura"], "待ち", d["wsum"], "競合", d["conf"])
