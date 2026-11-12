# 【試作】朝専用パターン：上りを毎時20本（15分に 快速1・急行犬塚1・急行蓮木市1・各停2）の周期パターンとして CP-SAT で解く。
# 下りと支線は採用した日中パターンのまま固定。増発にあたる8本（急行犬塚2・急行蓮木市2・各停高島2・各停就島2）は
# extras.py と同じく折返しの対応づけに入れない。日中の並びとつなぐ切り替えの時間帯は作らない（毎時くり返す定常状態だけ）。
# 使い方（data で。OR-Tools が要る）:
#   PYTHONPATH=../src python ../src/peak_proto.py check          … 差し込み案（extras_案2_毎時20本.pkl）をモデルに入れて検算
#   PYTHONPATH=../src python ../src/peak_proto.py solve 900      … 900秒解く → このフォルダに peak_vals.pkl（解）と peak_proto.pkl（列車）
# 環境変数: FIXRAP=1（快速4本は日中パターンの位置のまま固定し、急行・各停だけ組み直す）
#           NOHOLD_EXP=1（急行・快速は途中で待たせない） HINT=前回の peak_vals.pkl（続きから） TGT（軒屋着の目安間隔、既定180秒）
#           OUTV / OUTP（出力ファイル名） WORKERS
# 結果を見比べるには compare_extras.py に peak_proto.pkl を渡す。
import sys, os, pickle, json, itertools, time
PK = "cyc3_375_720_135_300_855_c.pkl"
MODE = sys.argv[1]; SEC = float(sys.argv[2]) if len(sys.argv) > 2 else 240
sys.argv = ["x", PK]
from morning_run import *          # 支線の時分差の設定、nolink を外す対応づけ（link_nl）、all_conf2
import pesp
from pesp import Cls, U, L
from build import UP_BASE
HERE = os.getcwd()
P2 = "extras_案2_毎時20本.pkl"
def fixed_cls(t, i):
    c = Cls(t.dir, t.kind, t.o, t.d, i, t.note if t.note in ("線内", "奥雲線") else "", xstop=[x for x in t.hold if not t.is_stop(x)] + list(t.xstop))
    h0 = t.hold.get(t.o, 0); d0 = (t.dep0 + h0) % 3600
    c.fix = (int(d0 // U), {x: int(v // U) for x, v in t.hold.items() if v and x != t.o}, 0)
    c.okd = t.dep(t.o) % 3600; c.oka = t.arr(t.d) % 3600; c.nolink = bool(getattr(t, "nolink", False)); c.src = t
    return c
def is_upmain(t): return t.dir == "U" and t.note not in ("線内", "奥雲線") and t.kind != "回送"
def load2():
    tr = pickle.load(open(P2, "rb"))[0]
    for t in tr: t.compute()
    up = sorted([t for t in tr if is_upmain(t) and T(7, 46) <= t.arr("軒屋") < T(8, 46)], key=lambda t: t.arr("軒屋"))
    rest = [t for t in tr if not is_upmain(t) and T(7, 30) <= t.dep(t.o) < T(8, 30)]
    return tr, up, rest
FIXRAP = bool(os.environ.get("FIXRAP"))
def peak_classes():
    C = []
    for k in range(4):
        for g, (kind, o, ex) in enumerate((("快速", "奥雲温泉" if k == 0 else "犬塚", False), ("急行", "犬塚", k % 2 == 1), ("急行", "蓮木市", k % 2 == 0),
                                           ("各停", ["秋田台", "高島"][k % 2], False), ("各停", ["高島", "就島"][k % 2], True))):
            if FIXRAP and kind == "快速": continue
            c = Cls("U", kind, o, "軒屋", k); c.g = g; c.nolink = ex; c.nosame = True; C.append(c)
    return C
NH = [("U", "急行", "蓮木市", "軒屋")]
if os.environ.get("NOHOLD_EXP"):      # 急行・快速は途中で待たせない（発車時刻で合わせる）
    NH += [("U", "急行", "犬塚", "軒屋"), ("U", "快速", "犬塚", "軒屋"), ("U", "快速", "奥雲温泉", "軒屋")]
KW = dict(structured=False, no_hold=NH, tight_target={("軒屋", "着"): int(os.environ.get("TGT", "180"))})   # 20本／時なら3分間隔が均等。足りない秒の合計＝間隔のむら
def model(rest, fixvals=None):
    """下り・支線（rest）を固定、上り20本を変数にしたモデル。fixvals があれば上りもその値に固定する"""
    C = [fixed_cls(t, i) for i, t in enumerate(rest)] + peak_classes()
    m, info = pesp.build_model(C, **KW)
    V = m.vars; off = [m.iv(0, 59, "off") for _ in range(5)]; pk = [c for c in C if c.fix is None]
    for c in pk:
        base = ((UP_BASE - c.cd["新犬村"]) % 3600) / U; assert abs(base - round(base)) < 1e-6
        k = m.k()       # 時刻は周期で折り返してよい
        m.m.add(V[c.D] == int(round(base)) + 60 * c.frame + V[off[c.g]] + V[c.shift] + 240 * V[k])
        m.m.add(V[c.D] >= 0); m.m.add(V[c.D] < 240)
    if fixvals:
        for j in range(5): m.m.add(V[off[j]] == fixvals["off"][j])
        for c in pk:
            sh, hd = fixvals[c.key]
            m.m.add(V[c.shift] == sh)
            for x, v in c.hold.items(): m.m.add(V[v] == hd.get(x, 0))
    return m, info, off, pk
def hint_from_plan2(up):
    """案2の上り20本を、枠＋オフセット＋繰り下げの形に当てはめる"""
    pk = peak_classes(); out = {"off": [0] * 5}
    for g in range(5):
        cl = [c for c in pk if c.g == g]
        if not cl: continue
        cand = [t for t in up if t.kind == cl[0].kind and ((t.o == "蓮木市") == (cl[0].o == "蓮木市") if t.kind == "急行" else True)
                and (bool(getattr(t, "extra", False)) == (g == 4) if t.kind == "各停" else True)]
        best = None
        for perm in itertools.permutations(cand, len(cl)):
            if any(t.o != c.o or bool(getattr(t, "extra", False)) != c.nolink for t, c in zip(perm, cl)): continue
            rs = []
            for t, c in zip(perm, cl):
                d0 = (t.dep0 + t.hold.get(t.o, 0)) % 3600; base = (UP_BASE - c.cd["新犬村"]) % 3600
                rs.append(((d0 - base - 900 * c.frame) % 3600) // U)
            for o in set(rs):
                sh = [(r - o) % 240 for r in rs]
                if o <= 59 and max(sh) <= 59 and (best is None or sum(sh) < best[0]): best = (sum(sh), o, sh, perm)
        if best is None: return None
        out["off"][g] = best[1]
        for t, c, s in zip(best[3], cl, best[2]): out[c.key] = (s, {x: int(v // U) for x, v in t.hold.items() if v and x != t.o})
    return out
def copies(pk, vals, hours):
    """解いた上り20本を、指定の各時に置いた列車にする"""
    out = []
    for c in pk:
        D, sh, hd = vals[c.key]
        for h in hours:
            t = Train("", c.kind, c.o, c.d, h * 3600 + D * U); t.hold = {x: v * U for x, v in hd.items() if v}
            t.anchor = t.dep0 - sh * U; t.frozen = True; t.cars = 8 if c.kind != "各停" else 6
            if c.nolink: t.nolink = True; t.extra = True; t.label = c.kind + "（増発）"
            t.compute(); out.append(t)
    return out
if __name__ == "__main__":
    tr2, up2, rest = load2()
    if FIXRAP: rest = rest + [t for t in up2 if t.kind == "快速"]       # 上りの快速も固定側に入れる
    print("案2：上り", len(up2), "本（うち増発", sum(1 for t in up2 if getattr(t, "extra", False)), "）／下り・支線", len(rest), "本", flush=True)
    if MODE == "check":      # 案2をそのまま固定してモデルに入れる → 成り立つはず
        C = [fixed_cls(t, i) for i, t in enumerate(rest + up2)]
        m, info = pesp.build_model(C, structured=False)
        s, st, dt = pesp.solve(m, seconds=60, workers=8)
        print("案2を固定したモデル:", st); sys.exit(0)
    hv = hint_from_plan2(up2); hint = None
    if os.environ.get("HINT"):          # 前回の結果から続ける
        v0, _, off0 = pickle.load(open(os.environ["HINT"], "rb"))
        hv = {"off": off0}; hv.update({k: (sh, hd) for k, (D, sh, hd) in v0.items()})
    if hv is None: print("案2を枠の形に当てはめられなかった（出発点なしで解く）")
    else:
        m1, info1, off1, pk1 = model(rest, hv)
        s1, st1, _ = pesp.solve(m1, seconds=60, workers=8)
        print("案2を出発点として入れた結果:", st1, s1.objective_value / 2 if st1 in ("OPTIMAL", "FEASIBLE") else "", flush=True)
        if st1 in ("OPTIMAL", "FEASIBLE"): hint = {i: s1.value(v) for i, v in m1.vars.items()}
    m, info, off, pk = model(rest)
    s, st, dt = pesp.solve(m, seconds=SEC, workers=int(os.environ.get("WORKERS", "22")), hint=hint)
    print("CP-SAT", st, f"{dt:.0f}s 評価", s.objective_value / 2, "下界", round(s.best_objective_bound / 2), "経過", s.hist[:1] + s.hist[-6:], flush=True)
    if st not in ("OPTIMAL", "FEASIBLE"): sys.exit(1)
    V = m.vars
    print("オフセット（新犬村基準、秒） 快速・急行犬塚・急行蓮木市・各停1・各停2:", [U * s.value(V[o]) for o in off])
    vals = {c.key: (s.value(V[c.D]), s.value(V[c.shift]), {x: s.value(V[h]) for x, h in c.hold.items()}) for c in pk}
    pickle.dump((vals, [c.key + (c.g, c.nolink) for c in pk], [s.value(V[o]) for o in off]), open(os.path.join(HERE, os.environ.get("OUTV", "peak_vals.pkl")), "wb"))
    # ---- 既存の判定で検査：日中パターン（下り・支線）＋ 朝専用の上り
    tr0, S0, down, up = pickle.load(open(PK, "rb"))
    br = dict(zip(pesp.BR_KEYS, map(int, json.load(open(PK.replace(".pkl", ".json"), encoding="utf-8"))["BR"].split(","))))
    day = pesp.build(down, up, br, S0, hor=(T(5, 0), T(11, 30)))
    keep = [t for t in day if not is_upmain(t) or (FIXRAP and t.kind == "快速")]
    for t in keep: t.frozen = True
    new = copies(pk, vals, range(5, 11))
    new = [t for t in new if T(6, 0) <= t.arr("軒屋") <= T(10, 30)]
    tr = keep + new
    for t in tr: t.compute()
    cs, _ = all_conf2(tr)
    win = [c for c in cs if T(7, 0) <= c[1] <= T(9, 30)]
    print("既存の判定：列車", len(tr), "競合（7:00〜9:30）", len(win), "／全体", len(cs))
    for c in win[:8]: print("   ", pesp.describe(c))
    pickle.dump((tr, [], [t for t in new if getattr(t, "extra", False)]), open(os.path.join(HERE, os.environ.get("OUTP", "peak_proto.pkl")), "wb"))
