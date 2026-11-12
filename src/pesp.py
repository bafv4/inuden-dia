# 日中パターン（1時間周期）を CP-SAT（OR-Tools）で解く。grid2.py で見つけたパターンを出発点にして改善する。
#
# 使い方（data で。BR は入力パターンの支線の時分差で、grid2.py と同じ環境変数）:
#   BR=375,660,2370,3570 PYTHONPATH=../src python ../src/pesp.py opt cyc2_360_690_150_720.pkl [出力.pkl]
#       … 入力パターンを出発点に解き、既存の判定（ops.all_conf）と評価（grid2 の重み）にかけ直して保存
#   PYTHONPATH=../src python ../src/pesp.py check cyc2_360_690_150_720.pkl
#       … モデルの検算。競合ゼロの列車群をそのままモデルに入れて、成り立つこと・評価が一致することを確かめる
# 環境変数: TIME（探索秒数、既定180） WORKERS（並列数、既定 CPU数-2） HOLD_L（各停の待避の上限、15秒単位、既定40＝10分）
#           NOHOLD（途中駅で待たせず、始発駅の発車を遅らせるだけにする列車。「向き,種別,始発,終着」を ; で区切る。
#                   例 NOHOLD="U,急行,蓮木市,軒屋"。入力パターンもその形になっていること）
#           KEEP（繰り下げ・停車延長を入力パターンのまま動かさない列車。書き方は NOHOLD と同じ）
# 必要なもの: OR-Tools（python -m pip install ortools。9.15 で確認）
#
# 規則は sched.conflicts / ops.link・turn_occ・cross_conf を「1時間ごとに同じ列車が来る」形に書き直したもの。
# そちらの規則や、cyc.gen_pattern / run_all.add_branch の本数・行先を変えたら、ここ（build_model / canonical）も
# 合わせて直し、check で検算すること。解は必ず既存の判定と評価にかけ直すので、ずれがあれば保存前に分かる。
import math, sys, os, time, pickle, json
import sched, ops, cyc, grid2, pat_eval, run_all
import build as BM
from build import T, UP_BASE
from try_up import nominal
from net import HN, K2, TOTAL_CAP, SINGLE_SEC, single_sec_of
from sched import H_DEP, H_ARR, PAD, SPAD
try:
    from ortools.sat.python import cp_model
except ImportError:
    sys.exit("OR-Tools が入っていません。 python -m pip install ortools で入れてください")

U = 15; P = 3600 // U; EPS = 1e-6                    # 変数の単位は15秒、周期は240単位
OC = set(K2) | {x for x, c in TOTAL_CAP.items() if c >= 2} | {"学院前"}     # 順序が入れ替われる駅（2線以上）
XSTA = ("就島", "秋田台", "新狛野", "犬塚")           # ops.cross_conf の対象駅
KIND = ("各停", "急行", "快速")
WIN = (T(9, 30), T(13, 0)); HOR = (T(8, 0), T(14, 30))   # grid2.solve_pattern と同じ判定範囲・並べる範囲
BR_KEYS = grid2.BR_KEYS

# ================================================================ モデル
class L:
    """秒 = 15×(整数変数の一次式) + 定数（秒、小数あり）"""
    __slots__ = ("t", "c")
    def __init__(s, t=None, c=0.0): s.t = t or {}; s.c = c
    def __add__(s, o):
        if isinstance(o, L):
            t = dict(s.t)
            for v, k in o.t.items(): t[v] = t.get(v, 0) + k
            return L(t, s.c + o.c)
        return L(dict(s.t), s.c + o)
    def __sub__(s, o):
        if isinstance(o, L):
            t = dict(s.t)
            for v, k in o.t.items(): t[v] = t.get(v, 0) - k
            return L(t, s.c - o.c)
        return L(dict(s.t), s.c - o)

class Cls:
    """1時間に1本ある列車の型"""
    def __init__(s, dir, kind, o, d, frame, note="", xstop=(), slow=None):
        s.dir, s.kind, s.o, s.d, s.frame, s.note = dir, kind, o, d, frame, note
        s.key = (dir, note or kind, o, d, frame)
        p = sched.Train("p", kind, o, d, 0); p.xstop = set(xstop); p.slow = dict(slow or {}); p.compute()      # xstop：通過駅に運転停車させる駅
        s.route = p.route; s.idx = {x: i for i, x in enumerate(p.route)}
        s.ca = {x: p.arr(x) for x in p.route}; s.cd = {x: p.dep(x) for x in p.route}
        s.stop = {x: p.stopped(x) for x in p.route}
        s.D = None; s.hold = {}; s.shift = None; s.okd = s.oka = frame; s.parent = None; s.fix = None
        s.nolink = False      # True：折返しの対応づけに入れない列車（朝の増発。extras.py の nolink と同じ扱い）
        s.nosame = False      # True：同じ種別の間隔のずれを数えない（枠の順に並ぶと決められない列車）
        s.flex = None         # fix した列車を動かしてよいとき (停車延長を足せる上限, 発車を遅らせられる上限[, 1駅間の徐行の上限[, 待避を作り直すか]])。15秒単位
                              # 4番目が True なら、今の停車延長を減らす・なくす・別の駅へ移すこともできる（発車は元より早めない）
        s.slowv = {}          # 徐行の変数：駅 → その駅へ着く手前の1駅間で余分にかける時間
    def _h(s, x, incl):
        t = {s.D: 1}; i = s.idx[x]
        for h, v in s.hold.items():
            j = s.idx[h]
            if j < i or (incl and j == i): t[v] = t.get(v, 0) + 1
        for h, v in s.slowv.items():
            if s.idx[h] <= i: t[v] = t.get(v, 0) + 1
        return t
    def arr(s, x): return L(s._h(x, False), s.ca[x])
    def dep(s, x): return L(s._h(x, True), s.cd[x])
    def iv(s, x):
        """駅 x の在線（開始, 終了）。sched.conflicts と同じ：停車は 着〜発+PAD、通過は 着-5〜着+PAD"""
        if s.stop[x]: return s.arr(x), s.dep(x) + PAD
        return s.arr(x) - 5, s.arr(x) + PAD
    def through(s, x): return x in s.idx and x != s.o and x != s.d
    def name(s): return f"{s.dir}{s.note or s.kind}{s.o}→{s.d}#{s.frame}"

def canonical():
    """日中パターン1時間ぶんの型（cyc.gen_pattern / run_all.add_branch と同じ並び）"""
    C = []
    for k in range(4):
        C.append(Cls("D", "各停", "軒屋", ["秋田台", "高島"][k % 2], k))
        C.append(Cls("D", "急行", "軒屋", ["犬塚", "蓮木市"][k % 2], k))
        C.append(Cls("D", "快速", "軒屋", "奥雲温泉" if k == 0 else "犬塚", k))
    for k in range(4):
        C.append(Cls("U", "各停", ["秋田台", "高島"][k % 2], "軒屋", k))
        C.append(Cls("U", "急行", ["犬塚", "蓮木市"][k % 2], "軒屋", k))
        C.append(Cls("U", "快速", "奥雲温泉" if k == 0 else "犬塚", "軒屋", k))
    for p in list(C):
        if p.kind != "各停": continue
        b = Cls("D", "各停", "学院前", "蓮木市", p.frame, "線内") if p.dir == "D" else Cls("U", "各停", "蓮木市", "学院前", p.frame, "線内")
        b.parent = p; C.append(b)
    C.append(Cls("D", "各停", "新狛野", "奥雲温泉", 2, "奥雲線")); C.append(Cls("U", "各停", "奥雲温泉", "新狛野", 2, "奥雲線"))
    return C

class M:
    """CP-SAT のモデルと、変数番号→変数の表（同じ順で作れば番号が同じになるので、解を別のモデルへ渡せる）"""
    def __init__(s):
        s.m = cp_model.CpModel(); s.vars = {}; s.cum = {}; s.bad = []; s.n = 0
    def iv(s, lo, hi, nm="v"):
        s.n += 1; v = s.m.new_int_var(lo, hi, f"{nm}{s.n}"); s.vars[v.index] = v; return v.index
    def bv(s, nm="b"):
        s.n += 1; v = s.m.new_bool_var(f"{nm}{s.n}"); s.vars[v.index] = v; return v.index
    def e(s, x): return sum(k * s.vars[v] for v, k in x.t.items() if k)
    def lits(s, enf): return [s.vars[i] if i >= 0 else s.vars[-i].negated() for i in enf]     # 負の番号は否定
    def _add(s, x, lo, hi, enf, why):
        """lo <= 15×式 + 定数 <= hi（秒）。式は15秒の倍数なので、定数の端数は切り上げ・切り捨てで厳密に扱える"""
        lo_u = None if lo is None else math.ceil((lo - x.c) / U - EPS)
        hi_u = None if hi is None else math.floor((hi - x.c) / U + EPS)
        if not any(x.t.values()):
            if not ((lo_u is None or lo_u <= 0) and (hi_u is None or 0 <= hi_u)):
                if enf: s.m.add_bool_or([l.negated() for l in s.lits(enf)])
                else: s.bad.append(why)
            return
        ex = s.e(x)
        for c in ([ex >= lo_u] if lo_u is not None else []) + ([ex <= hi_u] if hi_u is not None else []):
            ct = s.m.add(c)
            if enf: ct.only_enforce_if(s.lits(enf))
    def ge(s, x, lo, enf=None, why=""): s._add(x, lo, None, enf, why)
    def rng(s, x, lo, hi, enf=None, why=""): s._add(x, lo, hi, enf, why)
    def eq_units(s, x, rhs_var):
        """15×式+定数 が 15×rhs に等しい（定数は15の倍数のはず）"""
        r = x.c / U
        assert abs(r - round(r)) < 1e-6, x.c
        s.m.add(s.e(x) + int(round(r)) == s.vars[rhs_var])
    def k(s): return s.iv(-8, 8, "k")              # 周期を何回ぶんずらすか
    def per(s, k): return L({k: P})
    def cum_add(s, key, start, end, pres=None): s.cum.setdefault(key, []).append((start, end, pres))
    def cum_build(s):
        """駅の在線数の上限。1時間で折り返すので、同じ区間を1時間後にも置いて数える"""
        for key, ivs in s.cum.items():
            cap = TOTAL_CAP.get(key[0], 2 if key[0] in K2 else 1)
            if len(ivs) <= cap: continue
            I = []
            for start, end, pres in ivs:
                c0 = math.floor(start.c + EPS); c1 = math.ceil(end.c - EPS)      # 通過時刻の端数は安全側に丸める
                st = U * s.e(start) + c0; size = U * s.e(end - start) + (c1 - c0)
                q = s.vars[s.iv(-8, 8, "q")]; sm = s.vars[s.iv(0, 3599, "sm")]
                s.m.add(sm == st - 3600 * q)
                fixed = isinstance(size, int)
                if not fixed:      # 区間の開始・長さ・終了はそれぞれ1変数の式でないといけない
                    sz = s.vars[s.iv(0, 2 * 3600, "sz")]; s.m.add(sz == size)
                for off in (0, 3600):
                    nm = f"i{key[0]}{len(I)}"
                    if fixed:
                        if pres is None: I.append(s.m.new_fixed_size_interval_var(sm + off, size, nm))
                        else: I.append(s.m.new_optional_fixed_size_interval_var(sm + off, size, s.vars[pres], nm))
                    else:
                        en = s.vars[s.iv(0, 5 * 3600, "en")]; s.m.add(en == sm + off + sz)
                        if pres is None: I.append(s.m.new_interval_var(sm + off, sz, en, nm))
                        else: I.append(s.m.new_optional_interval_var(sm + off, sz, en, s.vars[pres], nm))
            s.m.add_cumulative(I, [1] * len(I), cap)

def build_model(C, structured=True, hold_max=40, shift_max=59, mingap=120, exp_hold_max=40, no_hold=(), tight_target=None, no_same_overtake=False, slow_max=0, kind_gap=None):
    """C の型を変数にしたモデル。structured=True なら 始発時刻 = 枠の位置 + オフセット + 繰り下げ、支線は本線から派生"""
    m = M(); mm = m.m; info = {"C": C}
    # ---- 変数
    for c in C:
        if c.fix is not None:     # 既存の解に固定して、モデルが成り立つかを確かめるとき
            d0, holds, _ = c.fix
            if c.flex:            # 元の時刻より遅らせる方向にだけ動かせる
                c.D = m.iv(d0, d0 + c.flex[1], "D")
                free = len(c.flex) > 3 and c.flex[3]
                c.hold = {x: m.iv(0 if free else holds.get(x, 0), max(holds.get(x, 0) + c.flex[0], hold_max if free else 0), "h") for x in c.route[1:-1] if c.stop[x] and x in OC}
                for x, v in holds.items():
                    if x not in c.hold: c.hold[x] = m.iv(v, v, "h")
                if len(c.flex) > 2 and c.flex[2]: c.slowv = {x: m.iv(0, c.flex[2], "sl") for x in c.route[1:]}
            else:
                c.D = m.iv(d0, d0, "D"); c.hold = {x: m.iv(v, v, "h") for x, v in holds.items()}
        else:
            c.D = m.iv(-2000, 2000, "D")
            hm = hold_max if c.kind == "各停" else exp_hold_max
            c.hold = {x: m.iv(0, hm, "h") for x in c.route[1:-1] if c.stop[x] and x in OC}     # 停車延長は2線以上の停車駅だけ
            if not c.note and (c.dir, c.kind, c.o, c.d) in no_hold: c.hold = {}               # 途中では待たせない（繰り下げだけ）
            c.shift = m.iv(0, shift_max, "s")
            if slow_max: c.slowv = {x: m.iv(0, slow_max, "sl") for x in c.route[1:]}       # 徐行：1駅間ごとに slow_max まで
    by = {c.key: c for c in C}; V = m.vars
    if structured:
        offD = [m.iv(0, 0, "oD")] + [m.iv(0, 59, "oD") for _ in (1, 2)]       # 下り各停を基準（0）にする
        offU = [m.iv(0, 59, "oU") for _ in range(3)]
        br = {"HASU_D": m.iv(4, 60, "br"), "HASU_U": m.iv(4, 60, "br"), "OKU_D": m.iv(4, 239, "br"), "OKU_U": m.iv(4, 239, "br")}
        info.update(offD=offD, offU=offU, br=br)
        for off in (offD, offU):          # 3種別のオフセットどうしは mingap 以上あける（grid2 の MINGAP と同じ）
            for a in range(3):
                for b in range(a + 1, 3):
                    k = m.k(); m.rng(L({off[b]: 1, off[a]: -1, k: 60}), mingap, 900 - mingap)
        for c in C:
            if c.note: continue
            j = KIND.index(c.kind)
            if c.dir == "D": mm.add(V[c.D] == 60 * c.frame + V[offD[j]] + V[c.shift])
            else:
                base = ((UP_BASE - c.cd["新犬村"]) % 3600) / U
                assert abs(base - round(base)) < 1e-6
                mm.add(V[c.D] == int(round(base)) + 60 * c.frame + V[offU[j]] + V[c.shift])
        for c in C:
            if c.note != "線内": continue
            p = c.parent
            if c.dir == "D": m.eq_units(p.arr("学院前") + L({br["HASU_D"]: 1, c.shift: 1, c.D: -1}), m.iv(0, 0))
            else: m.eq_units(p.arr("学院前") + L({br["HASU_U"]: -1, c.shift: 1, c.D: -1}, -c.ca["学院前"]), m.iv(0, 0))
        # 奥雲線各停の親：快速犬塚行・犬塚発のうち、15分枠の番号を4で割った余りが 2 のもの（run_all.add_branch）。
        # 枠の番号は実際の時刻で決まるので、停車延長で枠をまたぐ場合も含めて「ちょうど1本」を条件にする
        for dr in ("D", "U"):
            b = by[(dr, "奥雲線", "新狛野" if dr == "D" else "奥雲温泉", "奥雲温泉" if dr == "D" else "新狛野", 2)]
            ps = []
            for c in C:
                if c.kind != "快速" or c.note or c.dir != dr or "犬塚" not in (c.o, c.d): continue
                ref = c.dep("軒屋") if dr == "D" else c.dep("新犬村") - UP_BASE
                q = m.iv(-40, 40, "fq"); r = m.iv(0, 59, "fr"); w = m.iv(-10, 10, "fw"); md = m.iv(0, 3, "fm")
                m.eq_units(ref + L({q: -60}), r)                       # 基準時刻 = 900q + r
                mm.add(V[q] == 4 * V[w] + V[md])
                p = m.bv("par"); mm.add(V[md] == 2).only_enforce_if(V[p]); mm.add(V[md] != 2).only_enforce_if(V[p].negated())
                if dr == "D": x = c.dep("新狛野") + L({br["OKU_D"]: 1, b.shift: 1, b.D: -1})
                else: x = c.arr("新狛野") + L({br["OKU_U"]: -1, b.shift: 1, b.D: -1}, -b.ca["新狛野"])
                m.rng(x, 0, 0, enf=[p]); ps.append(V[p])
            mm.add_exactly_one(ps)
    # ---- 単線区間（同じ向き・逆向きを問わず、区間内に同時に入れない）
    sk = {}
    for x, y in SINGLE_SEC:
        tr = []
        for c in C:
            if x in c.idx and y in c.idx:
                ent, ex = (x, y) if c.idx[x] < c.idx[y] else (y, x)
                tr.append((c.dep(ent), c.arr(ex) + SPAD, c))
        for i in range(len(tr)):
            for j in range(i + 1, len(tr)):
                k = m.k(); m.ge(tr[j][0] - tr[i][1] + m.per(k), 0); m.ge(tr[i][0] - tr[j][1] - m.per(k), -3600)
                sk[tr[i][2].key, tr[j][2].key, (x, y)] = k
    # ---- 複線区間の続行。2本の時刻差を周期で折り返した値（k）は、追い抜きのできる駅でしか変わらない
    over = []      # (列車i, 列車j, 駅, 駅の手前のk, 先のk)
    for dr in ("D", "U"):
        cl = [c for c in C if c.dir == dr]
        for a_i in range(len(cl)):
            for b_i in range(a_i + 1, len(cl)):
                ci, cj = cl[a_i], cl[b_i]
                sj = set(zip(cj.route, cj.route[1:])); k = None; prev = False; cur = None
                for a, b in zip(ci.route, ci.route[1:]):
                    sec = single_sec_of(a, b)
                    if (a, b) not in sj or (sec and (ci.key, cj.key, sec) not in sk): prev = False; k = None; cur = None; continue
                    if sec:            # 単線区間：規則は上で入れてある。ここでは順序（追い抜き）だけ追う
                        if sec != cur:
                            k2 = sk[ci.key, cj.key, sec]
                            if k is not None and prev: over.append((ci, cj, a, k, k2))
                            k = k2; cur = sec
                        prev = True; continue
                    cur = None
                    if k is None or a in OC:
                        k2 = m.k()
                        if k is not None and prev: over.append((ci, cj, a, k, k2))
                        k = k2
                    elif (ci.stop[a] or cj.stop[a]) and ci.through(a) and cj.through(a):
                        (si, ei), (sj_, ej) = ci.iv(a), cj.iv(a)       # 1線の駅：在線が重ならない
                        m.ge(sj_ - ei + m.per(k), 0); m.ge(si - ej - m.per(k), -3600)
                    m.rng(cj.dep(a) - ci.dep(a) + m.per(k), H_DEP, 3600 - H_DEP)
                    m.rng(cj.arr(b) - ci.arr(b) + m.per(k), H_ARR, 3600 - H_ARR)
                    prev = True
    if no_same_overtake:      # 同じ種別どうしは追い越さない（時刻差の折り返し k が駅の前後で変わらない）
        for ci, cj, a, k1, k2 in over:
            if ci.kind == cj.kind: mm.add(V[k1] == V[k2])
    # ---- 駅の在線（2線以上の途中駅）
    for c in C:
        for x in c.route[1:-1]:
            if x == "学院前" or x not in OC: continue
            s0, e0 = c.iv(x); m.cum_add((x, "*") if x in TOTAL_CAP else (x, c.dir), s0, e0)
    gak = {(dr, t): [] for dr in ("D", "U") for t in "HM"}       # 学院前：H＝内側（蓮木線）、M＝本線の列車
    for c in C:
        if not c.through("学院前"): continue
        gak[(c.dir, "H" if (c.o in HN[1:] or c.d in HN[1:]) else "M")].append((c, ) + c.iv("学院前"))
    # ---- 折返し（ops.link / turn_occ / cross_conf）
    # ops.link は「先に着いた編成から使う」。毎時同じ形に落ち着いた状態では、着いた順と出る順が入れ替わらず、
    # かつ全編成の折返しをこれ以上詰められない対応づけになる。それを制約として書く。
    for X in sorted(set(c.o for c in C) | set(c.d for c in C)):
        A = [c for c in C if c.d == X and not c.nolink]; Dp = [c for c in C if c.o == X and not c.nolink]
        assert len(A) == len(Dp), f"{X} の1時間の着発本数が合わない"
        for a in C:            # 対応づけに入れない列車：着いた後しばらくホームを使う（ops.turn_occ の「相手のない到着」）
            if a.d != X or not a.nolink: continue
            if X in ("軒屋", "蓮木市", "奥雲温泉"): m.cum_add((X, "*"), a.arr(X), a.arr(X) + 180)
            elif X == "学院前": gak[(a.dir, "H")].append((None, a.arr(X), a.arr(X) + 90))
            else: m.cum_add((X, a.dir), a.arr(X), a.arr(X) + 120)
        if X == "学院前":      # 折返しは引上線。ホームは着後90秒・発前120秒だけ使う
            for a in A: gak[(a.dir, "H")].append((None, a.arr(X), a.arr(X) + 90))
            for d in Dp: gak[(d.dir, "H")].append((None, d.dep(X) - 120, d.dep(X) + PAD))
            continue
        if X == "高島":
            for a in A: m.cum_add((X, a.dir), a.arr(X), a.arr(X) + 120)
            for d in Dp: m.cum_add((X, d.dir), d.dep(X) - 180, d.dep(X) + PAD)
            continue
        n = len(A); mt = ops.minturn(X) // U; LG = ops.LONG // U; x = {}; lay = {}; W = {}
        for a in A:
            W[a] = m.iv(0, P - 1, "W")       # a の折返し時間
            for d in Dp:
                k = m.k(); lay[a, d] = m.iv(0, P - 1, "lay"); m.eq_units(d.dep(X) - a.arr(X) + m.per(k), lay[a, d])
                x[a, d] = m.bv("x"); mm.add(V[W[a]] == V[lay[a, d]]).only_enforce_if(V[x[a, d]])
                if n >= 2: mm.add(V[lay[a, d]] >= mt).only_enforce_if(V[x[a, d]])
        for a in A: mm.add_exactly_one([V[x[a, d]] for d in Dp])
        for d in Dp: mm.add_exactly_one([V[x[a, d]] for a in A])
        if n >= 2:
            zs = []
            for a in A:
                ds = []
                for a2 in A:
                    if a2 is a: continue
                    k = m.k(); dl = m.iv(0, P - 1, "dl"); m.eq_units(a2.arr(X) - a.arr(X) + m.per(k), dl); ds.append(V[dl])
                    b = m.bv("fb")      # a の折返し中に a2 が着く → a2 は a より後に出る
                    mm.add(V[dl] < V[W[a]]).only_enforce_if(V[b]); mm.add(V[dl] >= V[W[a]]).only_enforce_if(V[b].negated())
                    mm.add(V[dl] + V[W[a2]] >= V[W[a]]).only_enforce_if(V[b])
                nx = m.iv(0, P - 1, "nx"); mm.add_min_equality(V[nx], ds)
                z = m.bv("z"); mm.add(V[W[a]] - V[nx] <= mt - 1).only_enforce_if(V[z]); zs.append(V[z])
            mm.add_bool_or(zs)          # 次に着く編成へ1本ずつ繰り上げると、どこかで最短折返しを割る
        star = X in ("軒屋", "蓮木市", "奥雲温泉")
        sh = {}; lg = {}
        for a in A:
            for d in Dp:
                sh[a, d] = m.bv("sh"); lg[a, d] = m.bv("lg")       # 短い折返し（ホームに居続ける）／長い折返し（留置線・車庫へ）
                mm.add(V[sh[a, d]] + V[lg[a, d]] == V[x[a, d]])
                mm.add(V[lay[a, d]] <= LG).only_enforce_if(V[sh[a, d]])
                mm.add(V[lay[a, d]] >= mt).only_enforce_if(V[sh[a, d]])
                if n >= 2: mm.add(V[lay[a, d]] > LG).only_enforce_if(V[lg[a, d]])
                else:                  # 1本しか折り返さない駅では、1時間前に着いた編成でもよい
                    lo = m.bv("lo"); hi = m.bv("hi")
                    mm.add(V[lay[a, d]] < mt).only_enforce_if(V[lo]); mm.add(V[lay[a, d]] > LG).only_enforce_if(V[hi])
                    mm.add_bool_or([V[lg[a, d]].negated(), V[lo], V[hi]])
                m.cum_add((X, "*") if star else (X, a.dir), a.arr(X), a.arr(X) + L({lay[a, d]: 1}, PAD), sh[a, d])
        for a in A:
            la = m.bv("la"); mm.add(V[la] == sum(V[lg[a, d]] for d in Dp))
            m.cum_add((X, "*") if star else (X, a.dir), a.arr(X), a.arr(X) + (180 if star else 120), la)
        for d in Dp:
            ld = m.bv("ld"); mm.add(V[ld] == sum(V[lg[a, d]] for a in A))
            m.cum_add((X, "*") if star else (X, d.dir), d.dep(X) - (480 if star else 240), d.dep(X) + PAD, ld)
            if X in XSTA and d.dir == "U":      # 下り側で折り返して上りへ出る列車と、本線の列車の交差
                sd = m.bv("sd"); mm.add(V[sd] == sum(V[sh[a, d]] for a in A))
                for t in C:
                    if not t.through(X): continue
                    tt = t.arr(X) if t.dir == "D" else t.dep(X)
                    k = m.k(); m.rng(tt - d.dep(X) + m.per(k), 60, 3540, enf=[sd])
    # ---- 学院前の番線。本線の列車は、着いた時に外側が埋まっていれば内側へ（sched.conflicts と同じ決め方）
    for dr in ("D", "U"):
        Hs = gak[(dr, "H")]; Ms = gak[(dr, "M")]
        for i in range(len(Hs)):
            for j in range(i + 1, len(Hs)):
                k = m.k(); m.ge(Hs[j][1] - Hs[i][2] + m.per(k), 0); m.ge(Hs[i][1] - Hs[j][2] - m.per(k), -3600)
        inn = {i: m.bv("in") for i in range(len(Ms))}
        for i in range(len(Ms)):
            for h in Hs:           # 内側を使うなら蓮木線の列車と重ならない
                k = m.k(); m.ge(h[1] - Ms[i][2] + m.per(k), 0, enf=[inn[i]]); m.ge(Ms[i][1] - h[2] - m.per(k), -3600, enf=[inn[i]])
            cov = []
            for j in range(len(Ms)):
                if i == j: continue
                if i < j:          # 同じ側を使うなら重ならない
                    k = m.k()
                    for lits in ([inn[i], inn[j]], [-inn[i], -inn[j]]):
                        m.ge(Ms[j][1] - Ms[i][2] + m.per(k), 0, enf=lits); m.ge(Ms[i][1] - Ms[j][2] - m.per(k), -3600, enf=lits)
                cv = m.bv("cv"); k = m.k(); cov.append(V[cv])      # 内側へ入るのは、着いた時に外側に列車 j がいるときだけ
                mm.add_implication(V[cv], V[inn[j]].negated())
                m.ge(Ms[i][1] - Ms[j][1] + m.per(k), 0, enf=[cv]); m.ge(Ms[j][2] - Ms[i][1] - m.per(k), 0.01, enf=[cv])
            mm.add_bool_or(cov + [V[inn[i]].negated()])
    m.cum_build()
    # ---- 評価（grid2.evaluate と同じ重み。0.5 の重みがあるので2倍した整数で持つ）
    assert abs(2 * grid2.W_XF - round(2 * grid2.W_XF)) < 1e-9
    parts = {}
    wait = []
    for c in C:
        w = 1 if c.kind == "各停" else grid2.W_EXP
        sl = sum(V[v] for v in c.slowv.values())          # 徐行で延びたぶんも待ちと同じ重さで数える
        if c.fix is not None and c.flex: wait.append(w * U * (sum(V[h] for h in c.hold.values()) + V[c.D] - c.fix[0] + c.fix[2] + sl))
        elif c.fix is not None: wait.append(w * U * (sum(c.fix[1].values()) + c.fix[2]))
        else: wait.append(w * U * (V[c.shift] + sum(V[h] for h in c.hold.values()) + sl))
    parts["待ち"] = sum(wait)
    y = {}                 # (列車, 駅) で抜かれる
    for ci, cj, a, k1, k2 in over:
        dk = m.iv(-1, 1, "dk"); mm.add(V[dk] == V[k2] - V[k1])
        b1 = m.bv("ov"); b2 = m.bv("ov"); mm.add(V[dk] == V[b1] - V[b2]); mm.add(V[b1] + V[b2] <= 1)
        for c, b in ((ci, b1), (cj, b2)):      # b1：j が i を抜く
            if (c, a) not in y: y[c, a] = m.bv("y")
            mm.add_implication(V[b], V[y[c, a]])
    parts["待避"] = sum(V[v] for v in y.values())
    ev = {}                # 始発駅の発車・終着駅の到着
    for c in C:
        ev.setdefault((c.o, "発"), []).append((c, c.dep(c.o))); ev.setdefault((c.d, "着"), []).append((c, c.arr(c.d)))
    pens = []; devs = []
    for (st, kd), G in ev.items():
        n = len(G)
        if n < 2: continue
        target = round(0.6 * 3600 / n)       # 詰まり：目安間隔（均等割りの6割）に足りない秒
        if tight_target and (st, kd) in tight_target: target = tight_target[(st, kd)]
        for i in range(n):
            for j in range(i + 1, n):
                k = m.k(); d = m.iv(0, P - 1, "gd"); m.eq_units(G[j][1] - G[i][1] + m.per(k), d)
                p = m.iv(0, target, "pen"); mm.add(V[p] >= target - U * V[d]); mm.add(V[p] >= target - U * (P - V[d])); pens.append(V[p])
                a, b = G[i][0], G[j][0]      # 同じ種別どうしを、終着駅の到着で kind_gap 秒以上あける（どちらかが動かせる列車のとき）
                if kind_gap and kd == "着" and a.kind == b.kind and (st, a.kind) in kind_gap and (a.fix is None or b.fix is None or a.flex or b.flex):
                    gq = kind_gap[(st, a.kind)] // U; mm.add(V[d] >= gq); mm.add(V[d] <= P - gq)
        sub = {}
        for c, t in G:
            if not c.nosame: sub.setdefault((c.kind, c.note), []).append((c.okd if kd == "発" else c.oka, c, t))
        for g in sub.values():
            if len(g) < 2: continue
            # 同じ種別の並び順は枠の順のまま、とみなす。隣どうしの間隔（周期で折り返した値）が理想より詰まるぶん
            g.sort(key=lambda z: z[0]); ideal = 3600 // len(g); dv = m.iv(0, 3600, "dev"); devs.append(V[dv])
            for i in range(len(g)):
                a, b = g[i], g[(i + 1) % len(g)]
                k = m.k(); gp = m.iv(1, P, "gp"); m.eq_units(b[2] - a[2] + m.per(k), gp)
                mm.add(V[dv] >= ideal - U * V[gp])
    parts["詰まり"] = sum(pens); parts["同種別"] = sum(devs)
    xf = []                # 支線の乗り換え待ち（最低60秒）
    for c in C:
        if c.note not in pat_eval.XFER: continue
        st, kinds = pat_eval.XFER[c.note]; rs = []
        if st not in c.idx: st = c.o if c.dir == "D" else c.d      # 旧パターン（奥雲線が犬塚始発）。pat_eval.transfers と同じ
        for x in C:
            if x.note or x.kind not in kinds or x.dir != c.dir or st not in x.idx or not x.stop[st]: continue
            diff = (c.dep(st) - x.arr(st)) if c.o == st else (x.dep(st) - c.arr(st))
            k = m.k(); r = m.iv(0, P - 1, "xr"); m.eq_units(diff - 60 + m.per(k), r); rs.append(V[r])
        w = m.iv(0, P - 1, "xw"); mm.add_min_equality(V[w], rs); xf.append(U * V[w] + 60)
    parts["乗換"] = sum(xf)
    mm.minimize(2 * parts["待ち"] + 2 * grid2.W_OV * parts["待避"] + 2 * grid2.W_TIGHT * parts["詰まり"]
                + 2 * parts["同種別"] + int(round(2 * grid2.W_XF)) * parts["乗換"])
    info["parts"] = parts
    return m, info

class Progress(cp_model.CpSolverSolutionCallback):
    """解が良くなるたびに (経過秒, 評価) を記録する"""
    def __init__(s):
        cp_model.CpSolverSolutionCallback.__init__(s); s.t0 = time.perf_counter(); s.hist = []
    def on_solution_callback(s): s.hist.append((round(time.perf_counter() - s.t0, 1), s.objective_value / 2))
def solve(m, seconds=60, workers=20, log=False, hint=None):
    if hint:
        for v, val in hint.items(): m.m.add_hint(m.vars[v], val)
    s = cp_model.CpSolver()
    s.parameters.max_time_in_seconds = seconds; s.parameters.num_workers = workers; s.parameters.log_search_progress = log
    cb = Progress(); t = time.perf_counter(); st = s.solve(m.m, cb); s.hist = cb.hist
    return s, s.status_name(st), time.perf_counter() - t

# ================================================================ パターンの組み立て・判定・評価（既存のコードを使う）
def build(down, up, br, S, hor=HOR):
    """(オフセット, 支線の時分差, 枠ごとの調整 S) から列車を作る。morning_run.build_base と同じ順序：
    本線に S → 支線を派生 → 支線に S。保存したパターンをこの順で組み立て直せることが、朝のダイヤに使える条件"""
    grid2.set_branch(br); BM.UP_OFF = tuple(up); cyc.UP_OFF = tuple(up); BM.cnt.clear()
    tr = cyc.gen_pattern(hor[0], hor[1], tuple(down))
    def put(t):
        s = S.get(cyc.slot_of(t))
        if s: t.dep0 = t.anchor + s["shift"]; t.hold = dict(s["hold"])
        t.compute()
    for t in tr: put(t)
    b = run_all.add_branch(tr)
    for x in b: x.anchor = x.dep0; put(x)
    return tr + b
def check(tr, win=WIN):
    cs, _ = ops.all_conf(tr)
    return [c for c in cs if win[0] <= c[1] <= win[1]]
def metrics(tr):
    """grid2.evaluate と同じ評価"""
    m = pat_eval.score(tr)
    m["待避"] = len(set((id(A), w) for A, B, w in pat_eval.overtakes(tr)))
    m["優等の待ち秒"] = sum(sum(t.hold.values()) + (t.dep0 - t.anchor) for t in tr
                      if t.kind != "各停" and pat_eval.W0 <= t.dep(t.o) < pat_eval.W1)
    m["評価"] = (grid2.W_OV * m["待避"] + m["待ち秒"] + (grid2.W_EXP - 1) * m["優等の待ち秒"] + grid2.W_TIGHT * m["詰まり"]
               + m["同種別のずれ"] + grid2.W_XF * m["乗換待ち秒"])
    return m
def describe(c):
    f = lambda t: f"{t.dir}{t.kind}{t.o}→{t.d} {sched.fmt(t.dep(t.o))}"
    if c[0] in ("seg", "cross"): return f"{c[0]} {sched.hms(c[1])} {f(c[2])} / {f(c[3])} @{c[4]}" + (f"→{c[5]}" if c[5] else "")
    if c[0] == "occ": return f"occ {sched.hms(c[1])} @{c[4]} {[f(t) for t in c[3]]}"
    return f"single {sched.hms(c[1])} {c[4]} {f(c[2])} / {f(c[3])}"
def report(label, tr):
    cs = check(tr); mt = metrics(tr)
    n = sum(1 for t in tr if pat_eval.W0 <= t.dep(t.o) < pat_eval.W1)
    print(f"{label}: 競合 {len(cs)}  1時間の本数 {n}  評価 {mt['評価']}  " + " ".join(f"{k} {v:g}" for k, v in mt.items() if k not in ("評価", "待避回数")), flush=True)
    for c in cs[:6]: print("     ", describe(c))
    return cs, mt
def repair(tr):
    """残った競合を既存の手順（grid2.cyc_solve3 → prune）で解く"""
    left, S = grid2.cyc_solve3(tr, WIN, log=[])
    if left: return None
    S = grid2.prune(tr, S, WIN)
    for t in tr: t.compute()
    return S
def canon(down, up, br, S, rounds=6):
    """S から組み立て直しても競合が出ない形になるまで、組み立て→修復を繰り返す。戻り値 (列車, S, 修復した回数)"""
    for r in range(rounds):
        tr = build(down, up, br, S)
        if not check(tr): return tr, S, r
        S = repair(tr)
        if S is None: break
    return None, None, r

# ---- 列車 ⇔ 型
def cls_key_main(t, down, up):
    j = KIND.index(t.kind)
    if t.dir == "D": f = int((t.anchor - down[j]) // 900) % 4
    else: f = int((t.anchor + nominal(t.kind, t.o, t.d, "新犬村") - up[j] - UP_BASE) // 900) % 4
    return (t.dir, t.kind, t.o, t.d, f)
def branch_key(x, mains):
    if x.note != "線内": return (x.dir, "奥雲線", x.o, x.d, 2)
    arr0 = x.anchor + nominal("各停", x.o, x.d, "学院前")       # 繰り下げ・停車延長なしでの学院前の時刻
    ps = [p for p in mains if p.kind == "各停" and p.dir == x.dir and "学院前" in p.route[1:-1] and
          abs((p.arr("学院前") + run_all.HASU_D - x.anchor) if x.dir == "D" else (p.arr("学院前") - run_all.HASU_U - arr0)) < 1]
    return (x.dir, "線内", x.o, x.d, ps[0].cls[4])
def adj_from(tr, down, up):
    """build() で作った列車群から、型ごとの調整 {型: (繰り下げ秒, {駅: 停車延長秒})} を取り出す"""
    mains = [t for t in tr if t.note not in ("線内", "奥雲線")]
    for t in mains: t.cls = cls_key_main(t, down, up)
    out = {}
    for t in tr:
        key = t.cls if t.note not in ("線内", "奥雲線") else branch_key(t, mains)
        h = dict(t.hold); sh = t.dep0 - t.anchor + h.pop(t.o, 0)      # 始発駅の停車延長は発車の繰り下げと同じ
        new = (sh, {x: v for x, v in h.items() if v})
        assert out.get(key, new) == new, (key, out.get(key), new)
        out[key] = new
    return out
def build_adj(down, up, br, adj, hor=HOR):
    """型ごとの調整から列車と S（枠→調整）を作る。build() と同じ順序"""
    grid2.set_branch(br); BM.UP_OFF = tuple(up); cyc.UP_OFF = tuple(up); BM.cnt.clear()
    tr = cyc.gen_pattern(hor[0], hor[1], tuple(down)); S = {}
    def put(t, key):
        a = adj.get(key, (0, {})); S[cyc.slot_of(t)] = {"shift": a[0], "hold": {x: v for x, v in a[1].items() if v}}
        t.dep0 = t.anchor + a[0]; t.hold = dict(S[cyc.slot_of(t)]["hold"]); t.cls = key; t.compute()
    for t in tr: put(t, cls_key_main(t, down, up))
    b = run_all.add_branch(tr)
    for x in b: x.anchor = x.dep0; x.compute(); put(x, branch_key(x, tr))
    return tr + b, S
def hint_from(m, info, down, up, br, adj):
    h = {}
    for j in range(3): h[info["offD"][j]] = int(down[j] // U); h[info["offU"][j]] = int(up[j] // U)
    for k, i in info["br"].items(): h[i] = int(br[k] // U)
    for c in info["C"]:
        sh, hd = adj.get(c.key, (0, {}))
        h[c.shift] = int(sh // U)
        for x, v in c.hold.items(): h[v] = int(hd.get(x, 0) // U)
    return h
def full_hint(down, up, br, adj, **kw):
    """既知の解に固定したモデルを解いて全変数の値を得る。本番のモデルと同じ順で変数を作るので、番号がそのまま使える。
    解が変数の範囲に収まらない（置けない駅の停車延長など）ときは None"""
    C = canonical(); m, info = build_model(C, structured=True, **kw)
    for c in C:
        sh, hd = adj.get(c.key, (0, {}))
        if sh // U > 59 or any(v and x not in c.hold for x, v in hd.items()): return None, None
    for v, val in hint_from(m, info, down, up, br, adj).items(): m.m.add(m.vars[v] == val)
    s, st, dt = solve(m, seconds=60, workers=8)
    if st not in ("OPTIMAL", "FEASIBLE"): return None, None
    return {i: s.value(v) for i, v in m.vars.items()}, s.objective_value / 2
def extract(s, m, info):
    V = m.vars; val = lambda i: s.value(V[i])
    down = tuple(U * val(i) for i in info["offD"]); up = tuple(U * val(i) for i in info["offU"])
    br = {k: U * val(i) for k, i in info["br"].items()}
    adj = {c.key: (U * val(c.shift), {x: U * val(h) for x, h in c.hold.items() if val(h)}) for c in info["C"]}
    return down, up, br, adj

# ---- 検算用：列車群をそのまま型にして固定する
def classes_from(tr):
    C = []
    for t in tr:
        if not (pat_eval.W0 <= t.dep(t.o) < pat_eval.W1): continue
        c = Cls(t.dir, t.kind, t.o, t.d, len(C), t.note if t.note in ("線内", "奥雲線") else "",
                xstop=[x for x in t.hold if not t.is_stop(x)] + list(t.xstop), slow=getattr(t, "slow", None))
        h0 = t.hold.get(t.o, 0)          # 始発駅の停車延長は発車の繰り下げと同じ
        d0 = (t.dep0 + h0) % 3600; assert d0 % U == 0 and all(v % U == 0 for v in t.hold.values())
        c.fix = (int(d0 // U), {x: int(v // U) for x, v in t.hold.items() if v and x != t.o}, int((t.dep0 - t.anchor + h0) // U))
        c.okd = t.dep(t.o) % 3600; c.oka = t.arr(t.d) % 3600; C.append(c)
    return C
def model_check(tr, seconds=30):
    """列車群（10時台に始発駅を出る列車）を固定してモデルに入れる。戻り値 (状態, モデルの評価の内訳)"""
    C = classes_from(tr)
    for X in set(c.o for c in C) | set(c.d for c in C):       # 1時間の着発本数が合わない＝毎時同じ形になっていない
        if sum(c.o == X for c in C) != sum(c.d == X for c in C): return "UNBALANCED", None
    m, info = build_model(C, structured=False)
    s, st, dt = solve(m, seconds=seconds, workers=4)
    if st not in ("OPTIMAL", "FEASIBLE"): return st, None
    parts = {k: (s.value(v) if not isinstance(v, int) else v) for k, v in info["parts"].items()}
    parts["評価"] = s.objective_value / 2
    return st, parts

if __name__ == "__main__":
    mode, fn = sys.argv[1], sys.argv[2]
    tr0, S0, down0, up0 = pickle.load(open(fn, "rb"))
    for t in tr0: t.compute()
    if mode == "check":
        cs, mt = report("保存されている列車", tr0)
        st, parts = model_check(tr0)
        print("モデル:", {"OPTIMAL": "成立", "FEASIBLE": "成立", "INFEASIBLE": "不成立", "UNBALANCED": "1時間の着発本数が合わない"}.get(st, st))
        if parts:
            print("   モデルの評価", parts)
            print("   既存の評価  ", {"待ち": mt["待ち秒"] + (grid2.W_EXP - 1) * mt["優等の待ち秒"], "待避": mt["待避"], "詰まり": mt["詰まり"],
                                 "同種別": mt["同種別のずれ"], "乗換": mt["乗換待ち秒"], "評価": mt["評価"]})
        sys.exit(0)
    if mode != "opt": sys.exit("使い方: pesp.py opt 入力.pkl [出力.pkl] / pesp.py check 入力.pkl")
    if not os.environ.get("BR"): sys.exit("入力パターンの支線の時分差を BR=HASU_D,HASU_U,OKU_D,OKU_U で指定してください")
    br0 = {k: getattr(run_all, k) for k in BR_KEYS}
    seconds = float(os.environ.get("TIME", "180")); workers = int(os.environ.get("WORKERS", str(max(1, (os.cpu_count() or 4) - 2))))
    nohold = [tuple(x.split(",")) for x in os.environ.get("NOHOLD", "").split(";") if x]
    kw = dict(hold_max=int(os.environ.get("HOLD_L", "40")), no_hold=nohold)
    report("入力（保存されている列車）", tr0)
    trc, Sc, r = canon(down0, up0, br0, S0)
    hint = None; start = None
    if trc is None: print("入力を組み立て直せる形にできなかったので、出発点なしで解きます")
    else:
        _, mt0 = report(f"入力（S から組み立て直せる形。修復 {r} 回）", trc); start = mt0["評価"]
        hint, hv = full_hint(down0, up0, br0, adj_from(trc, down0, up0), **kw)
        print("   出発点としてモデルに入れた評価:", hv if hint else "入らなかった（出発点なしで解きます）", flush=True)
    m, info = build_model(canonical(), structured=True, **kw)
    keep = [tuple(x.split(",")) for x in os.environ.get("KEEP", "").split(";") if x]
    if keep and trc is not None:       # 指定の列車は入力のままに固定する
        a0 = adj_from(trc, down0, up0)
        for c in info["C"]:
            if c.note or (c.dir, c.kind, c.o, c.d) not in keep: continue
            sh, hd = a0.get(c.key, (0, {}))
            m.m.add(m.vars[c.shift] == int(sh // U))
            for x, v in c.hold.items(): m.m.add(m.vars[v] == int(hd.get(x, 0) // U))
    print(f"CP-SAT で {seconds:.0f} 秒、{workers} 並列で探索（変数 {len(m.vars)}）…", flush=True)
    s, st, dt = solve(m, seconds=seconds, workers=workers, log=bool(os.environ.get("LOG")), hint=hint)
    if st not in ("OPTIMAL", "FEASIBLE"): sys.exit(f"解が見つからなかった（{st}）")
    h = s.hist; print("   経過 (秒, 評価):", [h[i] for i in sorted(set([0, len(h) - 1] + list(range(0, len(h), max(1, len(h) // 10)))))] if h else [])
    print(f"   {st}  モデルの評価 {s.objective_value/2}  下界 {s.best_objective_bound/2:.0f}" + ("（最適と証明）" if st == "OPTIMAL" else ""))
    down, up, br, adj = extract(s, m, info)
    tr, S = build_adj(down, up, br, adj)
    cs, mt = report("CP-SAT の解（既存の判定・評価）", tr)
    tr, S, r = canon(down, up, br, S)        # 既存の判定で競合が残れば既存の手順で修復し、組み立て直せる形にする
    if tr is None: sys.exit("既存の判定での競合を修復できなかった。保存しません")
    if r: cs, mt = report(f"修復後（{r} 回）", tr)
    bad = [t for t in tr if (t.dir, t.kind, t.o, t.d) in nohold and any(v for x, v in t.hold.items() if x != t.o)]
    if bad: sys.exit(f"NOHOLD の列車に途中の停車延長が残った（{bad[0].kind}{bad[0].o}→{bad[0].d} {bad[0].hold}）。保存しません")
    if start is not None and mt["評価"] >= start: sys.exit(f"入力（{start}）より良くならなかった。保存しません")
    out = sys.argv[3] if len(sys.argv) > 3 else f"cyc3_{down[1]}_{down[2]}_{up[0]}_{up[1]}_{up[2]}.pkl"
    pickle.dump((tr, S, tuple(down), tuple(up)), open(out, "wb"))
    brs = ",".join(str(br[k]) for k in BR_KEYS)
    json.dump({"入力": fn, "入力の評価": start, "下り": down, "上り": up, "BR": brs, "評価": mt, "探索秒": seconds, "NOHOLD": os.environ.get("NOHOLD", ""), "KEEP": os.environ.get("KEEP", "")},
              open(os.path.splitext(out)[0] + ".json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"保存 {out}  下り {down} 上り {up}  BR={brs}  評価 {start} → {mt['評価']}")
