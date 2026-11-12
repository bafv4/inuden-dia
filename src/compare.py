# 日中パターンを見比べるページ（page/compare.html）を書き出す。
# 使い方（data で）:
#   PYTHONPATH=../src python ../src/compare.py 旧案=cyc_420_330_690_750_c.pkl 新案=cyc2_360_690_150_720.pkl=375,660,2370,3570 CP-SAT案=cyc3_375_720_135_300_855.pkl
#   引数は ラベル=pickle[=支線の時分差]。支線の時分差を省くと、同名の .json（pesp.py が書く）にあればそれを使う。
#   最後の引数が .html ならそこへ書き出す（既定は ../page/compare.html）。
# 評価は grid2.evaluate と同じ重み。各案の詳しいページ（export.py で作る page/pattern_*.html）があればリンクする。
import sys, os, re, json, pickle, glob
import net, ops, grid2, pat_eval
from build import T
from sched import fmt
from net import MN, HN
HERE = os.path.dirname(os.path.abspath(__file__)); PAGE = os.path.join(HERE, "..", "page")
WIN = (T(9, 30), T(13, 0))          # 競合を数える範囲（grid2.solve_pattern と同じ）
DW = (T(10, 0), T(11, 30))          # ダイヤグラムに描く範囲（パターンは毎時同じ）
MAJ_M = {"軒屋", "新犬村", "学院前", "就島", "高島", "秋田台", "新狛野", "犬塚", "奥雲温泉"}
MAJ_H = {"学院前", "佐茂町", "蓮木市"}
def line_map(t):        # export.py と同じ
    on_h = any(x in HN[1:] for x in t.route); m = {}
    for x in t.route:
        if x in HN[1:]: m[x] = "H"
        elif x == "学院前": m[x] = "H" if (on_h and not any(y in MN and y != "学院前" for y in t.route)) else "M"
        else: m[x] = "M"
    return m
def rows(t):            # export.py と同じ形に、徐行（その駅へ着く手前の1駅間で余分にかけた秒）を6番目として足したもの
    out = []; sl = getattr(t, "slow", None) or {}
    for x in t.route:
        ar, dp, stp = t.times[x]
        if x == t.o: out.append([x, None, dp, 1, t.hold.get(x, 0), 0])
        elif x == t.d: out.append([x, ar, None, 1, 0, sl.get(x, 0)])
        else: out.append([x, ar, dp, 1 if stp else 0, t.hold.get(x, 0), sl.get(x, 0)])
    return out
def metrics(tr):        # grid2.evaluate と同じ評価
    m = pat_eval.score(tr)
    m["待避"] = len(set((id(A), w) for A, B, w in pat_eval.overtakes(tr)))
    m["優等の待ち秒"] = sum(sum(t.hold.values()) + (t.dep0 - t.anchor) for t in tr
                      if t.kind != "各停" and pat_eval.W0 <= t.dep(t.o) < pat_eval.W1)
    m["評価"] = (grid2.W_OV * m["待避"] + m["待ち秒"] + (grid2.W_EXP - 1) * m["優等の待ち秒"] + grid2.W_TIGHT * m["詰まり"]
               + m["同種別のずれ"] + grid2.W_XF * m["乗換待ち秒"])
    return m
def kname(t): return t.kind + (f"（{t.note}）" if t.note in ("線内", "奥雲線") else "")
def pattern(label, fn, br):
    tr, S, down, up = pickle.load(open(fn, "rb"))
    for t in tr: t.compute()
    if br is None and os.path.exists(os.path.splitext(fn)[0] + ".json"):
        br = json.load(open(os.path.splitext(fn)[0] + ".json", encoding="utf-8")).get("BR")
    cs, _ = ops.all_conf(tr); conf = sum(1 for c in cs if WIN[0] <= c[1] <= WIN[1])
    m = metrics(tr); m["競合"] = conf
    hour = sorted([t for t in tr if pat_eval.W0 <= t.dep(t.o) < pat_eval.W1], key=lambda t: (t.dir, t.dep(t.o)))
    ev = {}; gap = {}
    for (st, k), L in pat_eval.events(tr).items():
        ev[st + k] = sorted([round(a % 3600), t.kind, t.note or "", t.d if k == "発" else t.o] for a, kd, t in L)
    for st, k, n, mg, same, ts in pat_eval.spacing(tr):
        if mg: gap[st + k] = mg
    waits = []; cnt = {}
    for t in hour:
        g = (t.dir, kname(t), t.o, t.d); cnt[g] = cnt.get(g, 0) + 1
        h0 = t.hold.get(t.o, 0)
        hs = [[x, v] for x, v in t.hold.items() if v and x != t.o]
        sh = t.dep0 - t.anchor + h0
        waits.append({"key": "|".join(g) + f"|{cnt[g]}", "name": f"{'下り' if t.dir == 'D' else '上り'}　{kname(t)}　{t.o}→{t.d}", "nth": cnt[g],
                      "dep": fmt(t.dep(t.o)), "shift": sh, "holds": hs, "sum": sh + sum(v for _, v in hs), "kind": t.kind})
    ov = [[a.kind, f"{a.o}→{a.d} {fmt(a.dep(a.o))}", w, b.kind, f"{b.d}行"] for a, b, w in pat_eval.overtakes(tr)]
    xf = [[kname(t), f"{t.o}→{t.d} {fmt(t.dep(t.o))}", st, w] for t, st, w in pat_eval.transfers(tr)]
    trains = []
    for i, t in enumerate(sorted(tr, key=lambda t: t.dep(t.o))):
        if t.dep(t.o) > DW[1] or t.arr(t.d) < DW[0]: continue
        trains.append({"id": f"t{i}", "kind": t.kind, "o": t.o, "d": t.d, "dir": t.dir, "note": t.note or "", "line": line_map(t), "rows": rows(t)})
    page = None
    for p in glob.glob(os.path.join(PAGE, "pattern_*.html")):
        if f"日中パターン（{os.path.basename(fn)}）" in open(p, encoding="utf-8").read(): page = os.path.basename(p)
    return {"label": label, "file": os.path.basename(fn), "down": list(down), "up": list(up), "br": br, "m": m, "n": len(hour),
            "ev": ev, "gap": gap, "waits": waits, "ov": ov, "xf": xf, "trains": trains, "page": page}
if __name__ == "__main__":
    args = sys.argv[1:]; out = os.path.join(PAGE, "compare.html")
    if args and args[-1].endswith(".html"): out = args.pop()
    pats = []
    for a in args:
        p = a.split("=", 2)
        pats.append(pattern(p[0], p[1], p[2] if len(p) > 2 else None))
    D = {"pats": pats, "t0": DW[0], "t1": DW[1],
         "main": [[s, k, s in MAJ_M] for s, k in net.MAIN], "hasu": [[s, k, s in MAJ_H] for s, k in net.HASU], "single": [list(x) for x in net.SINGLE],
         "w": {"待避": grid2.W_OV, "優等": grid2.W_EXP - 1, "詰まり": grid2.W_TIGHT, "乗換": grid2.W_XF}}
    tmpl = open(os.path.join(PAGE, "compare_tmpl.html"), encoding="utf-8").read()
    open(out, "w", encoding="utf-8").write(tmpl.replace("__DATA__", json.dumps(D, ensure_ascii=False).replace("</", "<\\/")))
    print("書き出し", out, [(p["label"], p["m"]["評価"], "競合", p["m"]["競合"]) for p in pats])
