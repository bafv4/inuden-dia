# 朝の増発8本の差し込み位置を CP-SAT で解く。日中パターンの列車（base.pkl）は動かさず、増発だけを変数にする。
# （REGWAIT / REGSHIFT を指定したときだけ、混む1時間の上りの既存列車を「遅らせる方向に少しだけ」動かせる）
# 使い方（data で。OR-Tools が要る）:
#   PYTHONPATH=../src python ../src/extras_opt.py パターン.pkl 出力.pkl
# 環境変数: TIME（探索秒数、既定120） WORKERS  WT（軒屋着の間隔のむらの重み、既定3。大きいほど間隔を優先、小さいほど待ちを優先）
#           HINT（出発点にする増発入りの pickle。既定 extras.pkl）  NOHOLD（途中で待たせない増発。例 "急行,犬塚;急行,蓮木市"）
#           MAXHOLD（増発1本が1駅で待てる上限、秒。既定600）
#           ORIGIN=0（増発の始発駅で、前後の列車との発車間隔が詰まることを減点しない。既定は grid2 と同じく減点する）
#           EXTRAS（増発の本数。「種別,始発駅:本数」を ; で区切る。既定 "急行,犬塚:2;急行,蓮木市:2;各停,高島:2;各停,就島:2"）
#           KGAP（同じ種別どうしを軒屋着で何秒以上あけるか。例 KGAP="急行:360"。増発の急行が既存の急行にくっついて走るのを避ける）
#           SAMEOV=1（同じ種別どうしの追い越しを許す。既定は許さない＝本人の方針）
#           REGWAIT（既存の上り列車に足してよい停車延長の上限、秒。1駅あたり。既定0＝動かさない）
#           REGSHIFT（既存の上り列車の始発駅の発車を遅らせてよい上限、秒。既定0）
#           REGFREE=1（既存の上り列車の待避パターンも作り直してよい：今の停車延長を減らす・なくす・別の駅へ移す。発車は早めない）
#           SLOW（増発の徐行：1駅間ごとに余分にかけてよい秒の上限。既定0＝徐行なし） REGSLOW（既存の上り列車の徐行の上限。既定0）
# 考え方: 朝のいちばん混む1時間を「毎時くり返す」ものとして pesp.py の周期モデルで解き（日中パターンの34本は固定、
#   増発8本は折返しの対応づけに入れない）、解けた8本を 7:30〜9:00 に着く1時間ぶんとして実際の朝ダイヤに入れ、
#   既存の判定で競合ゼロのものだけ保存する。既存列車を動かした場合は、その1時間に軒屋へ着く列車だけを変える。
# 評価 = 途中の待ち（急行・快速は2倍。既存列車を遅らせたぶんも同じ重さ）＋ WT×軒屋着の間隔のむら（3分に足りない秒の合計）
#        ＋ 待避・始発駅の詰まりなど（grid2 と同じ重み）
import sys, os, pickle, time
PK, OUT = sys.argv[1], sys.argv[2]; sys.argv = [sys.argv[0], PK]
from morning_run import *
import pesp, grid2
from pesp import Cls, U
EX = []          # 増発の一覧（種別, 始発駅）。同じ種類は続けて並べる
for part in os.environ.get("EXTRAS", "急行,犬塚:2;急行,蓮木市:2;各停,高島:2;各停,就島:2").split(";"):
    if part.strip():
        ko, n = part.split(":"); kind, o = ko.split(","); EX += [(kind.strip(), o.strip())] * int(n)
WT = float(os.environ.get("WT", "3")); SEC = float(os.environ.get("TIME", "120")); WORKERS = int(os.environ.get("WORKERS", str(max(1, (os.cpu_count() or 4) - 2))))
NH = [("U",) + tuple(x.split(",")) + ("軒屋",) for x in os.environ.get("NOHOLD", "").split(";") if x]
MAXH = int(os.environ.get("MAXHOLD", "600")) // U
NOSAME = os.environ.get("SAMEOV", "0") != "1"
KGAP = {("軒屋", x.split(":")[0].strip()): int(x.split(":")[1]) for x in os.environ.get("KGAP", "").split(";") if x.strip()}
REGW = int(os.environ.get("REGWAIT", "0")) // U; REGS = int(os.environ.get("REGSHIFT", "0")) // U
SLOW = int(os.environ.get("SLOW", "0")) // U; REGSL = int(os.environ.get("REGSLOW", "0")) // U; REGFREE = os.environ.get("REGFREE", "0") == "1"
def is_upmain(t): return t.dir == "U" and t.note not in ("線内", "奥雲線") and t.kind != "回送"
def fixed_cls(t, i):
    c = Cls(t.dir, t.kind, t.o, t.d, i, t.note if t.note in ("線内", "奥雲線") else "", xstop=[x for x in t.hold if not t.is_stop(x)] + list(t.xstop))
    h0 = t.hold.get(t.o, 0); d0 = (t.dep0 + h0) % 3600
    c.fix = (int(d0 // U), {x: int(v // U) for x, v in t.hold.items() if v and x != t.o}, 0)
    c.okd = t.dep(t.o) % 3600; c.oka = t.arr(t.d) % 3600
    return c
def base_trains():
    tr, _ = pickle.load(open("base.pkl", "rb"))
    for t in tr: t.compute()
    return tr
def model(base, fix=None):
    """日中パターン1時間ぶん（7時半〜8時半ごろの列車）を固定、増発8本を変数にしたモデル"""
    up = [t for t in base if is_upmain(t) and T(7, 45) <= t.arr("軒屋") < T(8, 45)]
    rest = [t for t in base if not is_upmain(t) and T(7, 30) <= t.dep(t.o) < T(8, 30)]
    C = [fixed_cls(t, i) for i, t in enumerate(rest + up)]; n0 = len(C); ex = []
    reg = C[len(rest):]
    if REGW or REGS or REGSL or REGFREE:
        for c in reg: c.flex = (REGW, REGS, REGSL, REGFREE)
    for i, (kind, o) in enumerate(EX):
        c = Cls("U", kind, o, "軒屋", EX[:i].count((kind, o))); c.nolink = True; c.nosame = True; ex.append(c)
    grid2.W_TIGHT = WT
    tgt = {("軒屋", "着"): round(3600 / (len(up) + len(EX)) / U) * U}     # 均等に並んだときの間隔（20本なら3分）。足りない秒の合計＝間隔のむら
    if os.environ.get("ORIGIN", "1") == "0": tgt.update({(o, "発"): 0 for _, o in EX})
    m, info = pesp.build_model(C + ex, structured=False, no_hold=NH, tight_target=tgt, hold_max=MAXH, exp_hold_max=MAXH, no_same_overtake=NOSAME, slow_max=SLOW, kind_gap=KGAP)
    V = m.vars
    for c in ex: m.m.add(V[c.D] >= 0); m.m.add(V[c.D] < 240); m.m.add(V[c.shift] == 0)
    for a, b in zip(ex, ex[1:]):                                          # 同じ種類どうしは入れ替えても同じなので順を決める
        if (a.kind, a.o) == (b.kind, b.o): m.m.add(V[a.D] <= V[b.D])
    if fix:
        for c, (D, hd, sl) in zip(ex, fix):
            m.m.add(V[c.D] == D)
            for x, v in c.hold.items(): m.m.add(V[v] == hd.get(x, 0))
            for x, v in c.slowv.items(): m.m.add(V[v] == sl.get(x, 0))
            if any(x not in c.slowv for x in sl): m.m.add_bool_or([])       # 徐行なしの条件に、徐行のある出発点は入らない
    return m, info, ex, reg
def from_trains(xs):
    """増発入りの列車リストから、増発8本の（発車位置, 停車延長, 徐行）を EX の順で取り出す"""
    out = []; pool = sorted([t for t in xs if getattr(t, "extra", False)], key=lambda t: (t.dep0 + t.hold.get(t.o, 0)) % 3600)
    for kind, o in EX:
        t = next(x for x in pool if x.kind == kind and x.o == o); pool.remove(t)
        out.append((int(((t.dep0 + t.hold.get(t.o, 0)) % 3600) // U), {x: int(v // U) for x, v in t.hold.items() if v and x != t.o},
                    {x: int(v // U) for x, v in (getattr(t, "slow", None) or {}).items() if v}))
    return out
def place(base, sol, regsol):
    """解を実際の朝ダイヤに入れる。増発は軒屋着 7:30〜9:00 の連続する1時間に。既存列車の変更はその1時間に着く列車だけに"""
    xs = []
    for (kind, o), (D, hd, sl) in zip(EX, sol):
        t = Train("", kind, o, "軒屋", D * U); t.hold = {x: v * U for x, v in hd.items() if v}; t.slow = {x: v * U for x, v in sl.items() if v}
        t.compute(); xs.append(t)
    # 8本を連続する1時間に収める切り方のうち、軒屋着が 7:30〜9:00 に収まり、真ん中が 8:15 にいちばん近いものを選ぶ
    ph = sorted(t.arr("軒屋") % 3600 for t in xs); best = None
    for start in ph:
        for h in (7, 8):
            first = h * 3600 + start
            arrs = [(p - start) % 3600 + first for p in ph]
            if first < T(7, 30) or max(arrs) > T(9, 0): continue
            key = abs((min(arrs) + max(arrs)) / 2 - T(8, 15))
            if best is None or key < best[0]: best = (key, start, first)
    _, start, first = best
    for t in xs:
        a = (t.arr("軒屋") - start) % 3600 + first                 # この増発の軒屋着
        t.dep0 += a - t.arr("軒屋"); t.anchor = t.dep0
        t.frozen = True; t.nolink = True; t.extra = True; t.label = t.kind + "（増発）"; t.cars = 8 if t.kind == "急行" else 6
        t.compute()
    arrs = [t.arr("軒屋") for t in xs]; w0 = (min(arrs) + max(arrs)) / 2 - 1800      # 増発を真ん中にした1時間
    mods = []
    for c, D, hd, sl in regsol:
        d0, h0, _ = c.fix
        dsh = (D - d0) * U; dh = {x: (v - h0.get(x, 0)) * U for x, v in hd.items() if v != h0.get(x, 0)}; dsl = {x: v * U for x, v in sl.items() if v}
        if dsh or dh or dsl: mods.append(((c.kind, c.o, c.d, d0), (dsh, dh, dsl)))
    changed = []
    for t in base:      # 変更のある枠（種別・区間・毎時の発車位置）の列車のうち、その1時間に軒屋へ着くもの
        if is_upmain(t) and w0 <= t.arr("軒屋") < w0 + 3600 and apply_mod(t, mods): changed.append(t)
    return xs, changed, mods
def slot4(t): return (t.kind, t.o, t.d, int(((t.dep0 + t.hold.get(t.o, 0)) % 3600) // U))
def apply_mod(t, mods):
    """既存列車 t に、その枠の変更（発車の繰り下げ・停車延長の増減・徐行）を当てる。当てたら True"""
    if getattr(t, "adjusted", None): return False
    for key, (dsh, dh, dsl) in mods:
        if slot4(t) != key: continue
        t.before = (t.dep(t.o), t.arr(t.d)); t.dep0 += dsh
        for x, v in dh.items():
            t.hold[x] = t.hold.get(x, 0) + v
            if not t.hold[x]: del t.hold[x]
        t.slow = dict(dsl); t.compute(); t.adjusted = (dsh, dh, dsl)
        return True
    return False
def tkey(tr): return sorted((t.dir, t.kind, t.o, t.d, t.dep0, tuple(sorted(t.hold.items())), tuple(sorted((getattr(t, "slow", None) or {}).items()))) for t in tr if not getattr(t, "extra", False))
if __name__ == "__main__":
    base = base_trains()
    key0 = tkey(base)
    hint = None; hf = os.environ.get("HINT", "extras.pkl")
    if os.path.exists(hf):
        h = pickle.load(open(hf, "rb"))[0]
        for t in h: t.compute()
        try:
            m1, _, _, _ = model(base, from_trains(h)); s1, st1, _ = pesp.solve(m1, seconds=60, workers=8)
            if st1 in ("OPTIMAL", "FEASIBLE"):
                hint = {i: s1.value(v) for i, v in m1.vars.items()}; print(f"出発点 {hf}: 評価 {s1.objective_value/2}", flush=True)
            else: print(f"出発点 {hf} はこの条件では使えない（{st1}）。出発点なしで解く", flush=True)
        except StopIteration: print("出発点に同じ種類の増発がそろっていないので、出発点なしで解く", flush=True)
    m, info, ex, reg = model(base)
    cond = ("同じ種別の追い越しなし" if NOSAME else "同じ種別の追い越しを許す") + (f"・既存の上りは停車延長 +{REGW*U}秒／発車 +{REGS*U}秒／徐行 1駅間 +{REGSL*U}秒まで動かせる" if REGW or REGS or REGSL or REGFREE else "・既存列車は動かさない") + ("・既存の待避も作り直せる" if REGFREE else "") + (f"・増発の徐行 1駅間 +{SLOW*U}秒まで" if SLOW else "") + "".join(f"・{k[1]}どうしは軒屋着で{v}秒以上あける" for k, v in KGAP.items())
    print(f"増発 {len(ex)} 本を {SEC:.0f} 秒で探索（間隔のむらの重み {WT:g}、{cond}）…", flush=True)
    s, st, dt = pesp.solve(m, seconds=SEC, workers=WORKERS, hint=hint)
    if st not in ("OPTIMAL", "FEASIBLE"): sys.exit(f"解が見つからなかった（{st}）")
    print(f"   {st}{'（この条件での最良と証明）' if st == 'OPTIMAL' else ''}  {dt:.0f}秒  評価 {s.objective_value/2}  下界 {s.best_objective_bound/2:.0f}")
    V = m.vars
    sol = [(s.value(V[c.D]), {x: s.value(V[h]) for x, h in c.hold.items() if s.value(V[h])}, {x: s.value(V[h]) for x, h in c.slowv.items() if s.value(V[h])}) for c in ex]
    regsol = [(c, s.value(V[c.D]), {x: s.value(V[h]) for x, h in c.hold.items()}, {x: s.value(V[h]) for x, h in c.slowv.items()}) for c in reg if c.flex]
    xs, changed, mods = place(base, sol, regsol); tr = base + xs
    cs, _ = all_conf2(tr)
    # モデルは「毎時同じ変更」として解いている。実際に変えるのは混む1時間の列車だけなので、変えた列車と変えていない列車の
    # 境目で競合が出ることがある。そのときは、競合に関わる既存列車にも同じ枠の変更を当てて広げる（全部に当てればモデルの解と同じ）
    for _ in range(12):
        if not cs: break
        more = [t for c in cs for t in involved(c) if not getattr(t, "extra", False) and is_upmain(t) and apply_mod(t, mods)]
        if not more: break
        changed += more; cs, _ = all_conf2(tr)
    for t in sorted(xs, key=lambda t: t.arr("軒屋")):
        print(f"   増発 {t.kind} {t.o} {fmt(t.dep(t.o))}発 → 軒屋 {fmt(t.arr('軒屋'))}着  " + ("、".join(f"{k} {v}秒" for k, v in t.hold.items()) or "待ちなし")
              + (f"／徐行 計{sum(t.slow.values())}秒（{len(t.slow)}駅間）" if t.slow else ""))
    for t in sorted(changed, key=lambda t: t.arr("軒屋")):
        dsh, dh, dsl = t.adjusted
        print(f"   既存 {t.kind} {t.o} {fmt(t.before[0])}発 → 軒屋 {fmt(t.before[1])}着 を変更：" + (f"発車 +{dsh}秒 " if dsh else "") + "、".join(f"{k} {v:+d}秒" for k, v in dh.items())
              + (f" 徐行 計{sum(dsl.values())}秒（{len(dsl)}駅間）" if dsl else "") + f" → 軒屋 {fmt(t.arr('軒屋'))}着")
    print(f"既存の判定：列車 {len(tr)}  競合 {len(cs)}  動かした既存列車 {len(changed)} 本  増発の待ち合計 {sum(sum(t.hold.values()) for t in xs)}秒・徐行の合計 {sum(sum(t.slow.values()) for t in xs)}秒")
    for c in cs[:6]: print("     ", pesp.describe(c))
    if cs: sys.exit("競合が残ったので保存しません")
    if tkey(tr) != key0 and not changed: sys.exit("意図しない変更があるので保存しません")
    pickle.dump((tr, [], xs), open(OUT, "wb")); print("保存", OUT)
