# 車両運用（2026-11-11 本人と決めた方針：車両の単位は4両編成と2両編成の2種類。運用表と日またぎの順序を作る。
#           検査のため、どの編成も3日に一度は車庫（狛野車庫＝新狛野、就島車庫）に入るように組む）
#   finalize.py が作った day_final.pkl（列車・折返しの鎖・両数）を読み、編成を1本ずつ区別して動きを追う。ダイヤは書き換えない。
#   ・基本の運用：鎖（折返しでつながった列車の並び）1本が、基本の編成1本の1日の行路。
#     8両＝4＋4（4両編成が足りない駅では 4＋2＋2）、6両＝4＋2、奥雲線内の各停＝2（ラッシュは2＋2）
#   ・付属の編成：増結で付き、切り離しで外れる。外れたら、その駅の留置線・車庫で待つか、車両だけの回送で運ばれる
#     同じ長さの2本をつないだ編成（4＋4、2＋2）を切り離すときは、先に付いていた方を外す（残った方がそのあとの基本の編成になる）。
#     こうしないと、奥雲温泉で夜を越す4両が毎日同じ編成になり、車庫に入れない
#   ・夜：その駅に着いた編成・置いてある編成を、翌朝その駅から出る運用に割り当てる。
#     同じ日課を何日も続けて回し、毎日同じ形に落ち着いたところを「定常の形」とする。そこでは、朝の役（どの運用の基本・付属か、
#     どの駅の留置か）ごとに、夜にどの駅にいるかが決まるので、翌朝どの役に入るかの対応（日またぎの順序）を、車庫に入る間隔が
#     短くなるように選ぶ
#   使い方（data で）: PYTHONPATH=../src python ../src/unyo.py パターン.pkl [day_final.pkl] [../page/unyo.html]
#   環境変数: DEPOT_STAY=7200（昼に車庫へ入ったと数える、車庫にいる時間の下限・秒） SEED=1（順序を選ぶ探索の乱数）
import sys, os, pickle, json, random
from collections import Counter, defaultdict
PKF = sys.argv[1]; SRC = sys.argv[2] if len(sys.argv) > 2 else "day_final.pkl"; OUT = sys.argv[3] if len(sys.argv) > 3 else "../page/unyo.html"
sys.argv = [sys.argv[0], PKF]
from morning_run import *
import net, trainno
tr, chains, _start = pickle.load(open(SRC, "rb"))
for t in tr:
    if getattr(t, "slow", None) is None: t.slow = {}
    t.compute()
trainno.assign(tr)
CO = lambda t: getattr(t, "cars_o", t.cars); CD = lambda t: getattr(t, "cars_d", t.cars)
DEPOT = ("新狛野", "就島"); DEPOT_NAME = {"新狛野": "狛野車庫", "就島": "就島車庫"}
DEPOT_STAY = int(os.environ.get("DEPOT_STAY", "7200"))
SWAP = os.environ.get("SWAP", "1") != "0"       # 4＋4・2＋2 を切り離すとき、先に付いていた方（車庫を出てから長い方）を外す。0 にすると後から付けた方を外す
def km(t):
    tot = 0
    for a, b in zip(t.route, t.route[1:]):
        if ("M", a) in net.KM and ("M", b) in net.KM: tot += abs(net.KM[("M", a)] - net.KM[("M", b)])
        else: tot += abs(net.KM[("H", a)] - net.KM[("H", b)])
    return tot
# ---- 基本の運用と運用番号（車両だけの回送の鎖は除く）
base = [c for c in chains if not all(getattr(t, "unyo", None) == 0 for t in c)]
def is_oku(c): return any(t.note == "奥雲線" for t in c)
def cat(c):
    if is_oku(c): return "奥雲線内"
    if c[-1].kind == "回送" and c[-1].note == "増発車の入庫": return "増発"
    if sum(1 for t in c if t.kind != "回送") <= 2: return "増発"
    if sum(1 for t in c if t.note == "線内") > len(c) / 2: return "蓮木線内"
    return "本線"
ORDER = {"本線": 0, "蓮木線内": 1, "奥雲線内": 2, "増発": 3}; FIRST = {"本線": 1, "蓮木線内": 41, "奥雲線内": 51, "増発": 61}
base.sort(key=lambda c: (ORDER[cat(c)], c[0].dep(c[0].o)))
num = {}; cnt = Counter()
for c in base:
    k = cat(c); num[id(c)] = FIRST[k] + cnt[k]; cnt[k] += 1
def uno(c): return f"{num[id(c)]:02d}"
BYNO = {uno(c): c for c in base}
# ---- 1日の出来事（切り離し・増結・入庫・車両だけの回送）
EV = []                                              # (時刻, 順, 種類, 駅, 両数, 鎖, 列車)
for c in base:
    for t in c:
        if getattr(t, "split", None) and CO(t) != CD(t):
            X = t.split
            if CD(t) < CO(t): EV.append((t.dep(X), 0, "cut", X, CO(t) - CD(t), c, t))
            else: EV.append((t.arr(X), 2, "join", X, CD(t) - CO(t), c, t))
    for a, b in zip(c, c[1:]):
        if CO(b) < CD(a): EV.append((a.arr(a.d), 0, "cut", a.d, CD(a) - CO(b), c, a))
        elif CO(b) > CD(a): EV.append((b.dep(b.o), 2, "join", b.o, CO(b) - CD(a), c, b))
    if c[-1].kind == "回送" and c[-1].note == "増発車の入庫": EV.append((c[-1].arr(c[-1].d), 0, "in", c[-1].d, CD(c[-1]), c, c[-1]))
hauls = [t for t in tr if t.kind == "回送" and getattr(t, "unyo", None) == 0]
for t in hauls:
    EV.append((t.dep(t.o), 2, "hdep", t.o, t.cars, None, t)); EV.append((t.arr(t.d), 1, "harr", t.d, t.cars, None, t))
EV.sort(key=lambda e: (e[0], e[1]))
class Unit:
    n = 0
    def __init__(s, size): Unit.n += 1; s.id = Unit.n; s.size = size; s.log = []
def pick(lst, n, base_first=True):
    """置いてある編成（古い順）から n 両ぶん選ぶ。4両は4両編成を先に、なければ2両編成2本。選べなければ None"""
    f4 = [u for u in lst if u.size == 4]; f2 = [u for u in lst if u.size == 2]; got = []
    need4, need2 = {8: (2, 0), 6: (1, 1), 4: (1, 0), 2: (0, 1)}[n]
    while need4 > 0:
        if f4: got.append(f4.pop(0)); need4 -= 1
        elif len(f2) >= 2 + need2: got += [f2.pop(0), f2.pop(0)]; need4 -= 1
        else: return None
    while need2 > 0:
        if f2: got.append(f2.pop(0)); need2 -= 1
        else: return None
    return got
def day(comp, pool, dayno):
    """1日ぶん動かす。comp：運用番号 → 付いている編成（先頭が基本）。pool：駅 → 置いてある編成。足りないところは新しい編成を足す"""
    new = []; riding = {}
    for no, us in comp.items():
        for i, u in enumerate(us): u.log.append((dayno, 0, "朝", BYNO[no][0].o, ("基本" if i == 0 else "付属") + no))
    for X, L in pool.items():
        for u in L: u.log.append((dayno, 0, "朝", X, "留置"))
    def take(X, n, tm, why):
        got = pick(pool[X], n)
        if got is None:
            got = [Unit(sz) for sz in ({8: [4, 4], 6: [4, 2], 4: [4], 2: [2]}[n])]; new.append((X, n, tm, why))
            for u in got: u.log.append((dayno, 0, "朝", X, "留置"))
        else:
            for u in got: pool[X].remove(u)
        return got
    for tm, _, kind, X, n, c, t in EV:
        if kind == "cut":
            us = []; need = n; no = uno(c)
            if SWAP and len(comp[no]) == 2 and comp[no][0].size == comp[no][1].size == n:
                u = comp[no].pop(0); us.append(u); need -= u.size      # 同じ長さの2本をつないだ編成（4＋4、2＋2）は、先に付いていた方を外す。残った方が基本の編成になる
            while need > 0:
                u = comp[no].pop(); us.append(u); need -= u.size
            assert need == 0 and comp[no], ("切り離しの両数が編成の単位に合わない", no, fmt(tm), n)
            for u in us: pool[X].append(u); u.log.append((dayno, tm, "切り離し", X, no))
        elif kind == "join":
            for u in take(X, n, tm, f"運用{uno(c)}への増結"): comp[uno(c)].append(u); u.log.append((dayno, tm, "増結", X, uno(c)))
        elif kind == "in":
            for u in comp[uno(c)]: pool[X].append(u); u.log.append((dayno, tm, "入庫", X, uno(c)))
            comp[uno(c)] = []
        elif kind == "hdep":
            us = take(X, n, tm, "車両だけの回送"); riding[id(t)] = us
            for u in us: u.log.append((dayno, tm, "回送発", X, t.d))
        elif kind == "harr":
            for u in riding.pop(id(t)): pool[X].append(u); u.log.append((dayno, tm, "回送着", X, t.o))
    for no, us in comp.items():
        c = BYNO[no]
        for u in us: u.log.append((dayno, c[-1].arr(c[-1].d), "夜", c[-1].d, no))
    for X, L in pool.items():
        for u in L: u.log.append((dayno, T(27, 0), "夜", X, "留置"))
    return new
def night(comp, pool, order=None):
    """夜：駅ごとに、いる編成（着いた順・置かれた順）を、翌朝その駅から出る運用（発車順）に割り当てる。基本 → 2両の付属 → 4両ぶんの付属の順。
       戻り値：(翌朝の comp, 翌朝の pool, 足りなくて足した編成)"""
    at = defaultdict(list)
    for no, us in comp.items():
        for u in us: at[BYNO[no][-1].d].append(u)
    for X, L in pool.items(): at[X] += L
    for X in at: at[X].sort(key=lambda u: (u.log[-1][1], u.id))
    ncomp = {}; npool = defaultdict(list); new = []
    for X in sorted(set(at) | {c[0].o for c in base}):      # 並べ替えておく（集合の順のままだと、実行のたびに編成の番号と探索の結果が変わる）
        A = at[X]; S = sorted([c for c in base if c[0].o == X], key=lambda c: c[0].dep(X))
        def get(sz, why):
            for u in A:
                if u.size == sz: A.remove(u); return u
            u = Unit(sz); new.append((X, sz, why)); return u
        for c in S: ncomp[uno(c)] = [get(2 if is_oku(c) else 4, "基本" + uno(c))]
        for c in S:
            r = CO(c[0]) - ncomp[uno(c)][0].size
            if r == 2: ncomp[uno(c)].append(get(2, "付属" + uno(c)))
        for c in S:
            r = CO(c[0]) - sum(u.size for u in ncomp[uno(c)])
            while r >= 4:
                if any(u.size == 4 for u in A) or sum(1 for u in A if u.size == 2) < 2: ncomp[uno(c)].append(get(4, "付属" + uno(c)))
                else: ncomp[uno(c)] += [get(2, ""), get(2, "")]
                r -= 4
            assert r == 0, (uno(c), r)
        npool[X] = list(A)
    return ncomp, npool, new
# ---- 同じ日課を続けて回し、落ち着いた形を求める
comp = {}; pool = defaultdict(list)
for c in base: comp[uno(c)] = [Unit(sz) for sz in ([2, 2][:CO(c[0]) // 2] if is_oku(c) else {8: [4, 4], 6: [4, 2], 4: [4]}[CO(c[0])])]
hist = []; sig_prev = None; steady = None
for d in range(1, 41):
    sig = (tuple(sorted((no, tuple(u.size for u in us)) for no, us in comp.items())), tuple(sorted((X, tuple(sorted(u.size for u in L))) for X, L in pool.items() if L)))
    morning = {no: list(us) for no, us in comp.items()}; mpool = {X: list(L) for X, L in pool.items()}
    new_d = day(comp, pool, d)
    comp, pool, new_n = night(comp, pool)
    hist.append((d, len(new_d), len(new_n), Unit.n))
    if sig == sig_prev and not new_d and not new_n and steady is None: steady = d
    sig_prev = sig
    if steady and d >= steady + 1: break
units = {}
def all_units():
    for us in comp.values():
        for u in us: units[u.id] = u
    for L in pool.values():
        for u in L: units[u.id] = u
all_units()
# ---- 定常の1日（最後に回した日）を、朝の役ごとに整理する
D = hist[-1][0]
roles = {}                                           # 役の名前 → {size, start, end, log, visit}
def role_name(u):
    e = [x for x in u.log if x[0] == D][0]
    return e[4] if e[4] != "留置" else None, e[3]
stock = Counter()
for u in units.values():
    lg = [x for x in u.log if x[0] == D]
    nm, st = role_name(u)
    if nm is None: stock[(st, u.size)] += 1; nm = f"留置 {st} {u.size}両-{stock[(st, u.size)]}"
    elif nm.startswith("付属"):
        k = 1
        while f"{nm}-{k}" in roles: k += 1
        nm = f"{nm}-{k}"
    # 昼に車庫にいた時間
    stay = 0; in_since = None
    for (_, tm, kind, X, info) in lg:
        if kind in ("切り離し", "回送着", "入庫") and X in DEPOT: in_since = tm
        elif kind == "朝" and info == "留置" and X in DEPOT: in_since = T(4, 0)
        elif kind in ("増結", "回送発") and in_since is not None: stay = max(stay, tm - in_since); in_since = None
    end = lg[-1][3]
    night_depot = end in DEPOT
    roles[nm] = dict(size=u.size, start=lg[0][3], end=end, endt=lg[-1][1], log=lg, day_depot=stay >= DEPOT_STAY, night_depot=night_depot,
                     visit=(stay >= DEPOT_STAY) or night_depot, unit=u.id, endrole=lg[-1][4])
# 翌朝の役（いまの割り当て＝着いた順）
nxt_fifo = {}
for no, us in comp.items():
    for i, u in enumerate(us):
        nm = ("基本" if i == 0 else "付属") + no
        if i > 0:
            k = 1
            while f"{nm}-{k}" in nxt_fifo.values(): k += 1
            nm = f"{nm}-{k}"
        nxt_fifo[u.id] = nm
st2 = Counter()
for X, L in pool.items():
    for u in L: st2[(X, u.size)] += 1; nxt_fifo[u.id] = f"留置 {X} {u.size}両-{st2[(X, u.size)]}"
pi = {nm: nxt_fifo[r["unit"]] for nm, r in roles.items()}
assert set(pi.values()) == set(roles), ("定常の形になっていない", sorted(set(roles) - set(pi.values()))[:5], sorted(set(pi.values()) - set(roles))[:5])
# ---- 日またぎの順序を選ぶ：同じ駅・同じ両数の編成どうしは翌朝の役を入れ替えられる。車庫に入らない日が続く長さを短く、巡回の数を少なく
def cycles(p):
    seen = set(); out = []
    for r in sorted(p):
        if r in seen: continue
        cyc = []; x = r
        while x not in seen: seen.add(x); cyc.append(x); x = p[x]
        out.append(cyc)
    return out
def runs_of(cyc):
    """巡回の中で、車庫に入らない日が続く長さの一覧（1回も入らない巡回は 10000）"""
    v = [roles[r]["visit"] for r in cyc]; n = len(v)
    if not any(v): return [10 ** 4]
    i0 = v.index(True); run = 0; out = []
    for k in range(1, n + 1):
        if v[(i0 + k) % n]:
            if run: out.append(run)
            run = 0
        else: run += 1
    return out
def maxrun(cyc): return max(runs_of(cyc) or [0])
LIM = int(os.environ.get("DEPOT_GAP", "2"))          # 車庫に入らない日が続いてよい日数（2 ＝ 3日に一度は車庫に入る）
def score(p):
    cs = cycles(p); rs = [r for c in cs for r in runs_of(c)]
    return (sum(max(0, r - LIM) for r in rs), len(cs), max(rs or [0]))
grp = defaultdict(list)
for nm, r in roles.items(): grp[(r["end"], r["size"])].append(nm)
pairs = [(a, b) for L in grp.values() for i, a in enumerate(L) for b in L[i + 1:]]
s0 = score(pi); best = (s0, dict(pi)); ITER = int(os.environ.get("ITER", "120000"))
import math
for seed in range(int(os.environ.get("SEEDS", "4"))):
    rnd = random.Random(seed + int(os.environ.get("SEED", "1"))); cur = dict(pi); c = score(cur)
    for it in range(ITER):
        if not pairs: break
        a, b = rnd.choice(pairs); cur[a], cur[b] = cur[b], cur[a]; s_ = score(cur)
        temp = max(0.01, 1.0 - it / ITER)
        if s_ <= c or rnd.random() < math.exp(-((s_[0] - c[0]) + 0.2 * (s_[1] - c[1])) / temp): c = s_
        else: cur[a], cur[b] = cur[b], cur[a]
        if c < best[0]: best = (c, dict(cur))
    if best[0][:2] == (0, len({r["size"] for r in roles.values()})): break
bs, pi = best
CYC = sorted(cycles(pi), key=lambda c: -len(c))
if __name__ == "__main__":
    n4 = sum(1 for u in units.values() if u.size == 4); n2 = sum(1 for u in units.values() if u.size == 2)
    print(f"対象 {SRC}：基本の運用 {len(base)} 本（" + "、".join(f"{k} {v}" for k, v in cnt.items()) + "）")
    print("続けて回した結果（日, その日に足した編成, 夜に足した編成, 編成の総数）：", hist[:6], "…", hist[-1], "落ち着いた日", steady)
    print(f"編成 {len(units)} 本（4両 {n4} 本・2両 {n2} 本、計 {n4 * 4 + n2 * 2} 両）。朝の役 {len(roles)}（基本 {sum(1 for r in roles if r.startswith('基本'))}・付属 {sum(1 for r in roles if r.startswith('付属'))}・留置 {sum(1 for r in roles if r.startswith('留置'))}）")
    print("8両を4＋2＋2で組む運用：", [no for no, us in sorted(comp.items()) if [u.size for u in us] == [4, 2, 2]])
    print("朝に置いてある編成（留置）：", dict(Counter((r["start"], f"{r['size']}両") for nm, r in roles.items() if nm.startswith("留置"))))
    print("夜を越す場所（編成の数。4両・2両）：", {X: (sum(1 for r in roles.values() if r["end"] == X and r["size"] == 4), sum(1 for r in roles.values() if r["end"] == X and r["size"] == 2)) for X in sorted({r["end"] for r in roles.values()})})
    print("車庫に入る役：昼に入る", sum(1 for r in roles.values() if r["day_depot"]), "・夜を車庫で越す", sum(1 for r in roles.values() if r["night_depot"]), "・どちらか", sum(1 for r in roles.values() if r["visit"]), "／", len(roles))
    print("日またぎの順序：着いた順のままだと（目標を超える日数の合計, 巡回の数, 車庫に入らない日が続く最大）", s0, "→ 選び直して", bs)
    for c in CYC: print(f"   巡回 {len(c)}日：4両 {sum(1 for r in c if roles[r]['size'] == 4)}・2両 {sum(1 for r in c if roles[r]['size'] == 2)}、車庫に入らない日が続く最大 {maxrun(c)}日")
    # ---------------- 運用表のページ（page/unyo.html）
    import html as _h
    def place(X): return DEPOT_NAME.get(X, X)
    def label(nm):
        if nm.startswith("基本"): return f"運用{nm[2:]}（基本）"
        if nm.startswith("付属"):
            no, k = nm[2:].split("-")
            return f"運用{no}の付属" + (f"（{k}本目）" if f"付属{no}-2" in roles else "")
        p = nm.split(); return f"{place(p[1])}で待機（{p[2]}）"
    def hhmm(tm):
        tm = int(round(tm)); return f"{tm // 3600}:{tm % 3600 // 60:02d}'{tm % 60:02d}"      # ダイヤのページと同じ書き方（秒は00でも書く）
    def story(nm):
        r = roles[nm]; out = []
        for (_, tm, kind, X, info) in r["log"]:
            if kind == "朝": out.append(f"朝 {place(X)}で待機" if info == "留置" else f"朝 {X}（運用{info[2:]}の{info[:2]}）")
            elif kind == "増結": out.append(f"{hhmm(tm)} {X}で運用{info}に増結")
            elif kind == "切り離し": out.append(f"{hhmm(tm)} {X}で運用{info}から切り離し")
            elif kind == "回送発": out.append(f"{hhmm(tm)} 回送 {X}→{info}")
            elif kind == "入庫": out.append(f"{hhmm(tm)} {place(X)}に入庫")
            elif kind == "夜": out.append(f"夜 {place(X)}" if info == "留置" else f"夜 {X}（運用{info}で {hhmm(tm)}着）")
        return " → ".join(out)
    def depot_txt(r): return "・".join(x for x in ("昼" if r["day_depot"] else "", "夜" if r["night_depot"] else "") if x) or "—"
    KC = {"快速": "rap", "急行": "exp", "各停": "loc", "回送": "dh"}
    def seq_cars(c):
        seq = []
        for t in c:
            for x in (CO(t), CD(t)):
                if not seq or seq[-1] != x: seq.append(x)
        return "→".join(map(str, seq))
    import tracks                                    # 番線・引上線の割り当て（tracks.py）。行路の発駅・着駅に番線を、折返しのあいだに外へ出るところは注記に出す
    _st = getattr(tr[0], "stored", None)
    if _st is not None: ops_ = __import__("ops"); ops_.STORED.clear(); ops_.STORED.update(_st)
    TRK = tracks.assign(tr)
    def trk(t, x): p = TRK.trk[t].get(x); return f" <span class='tk'>{p}</span>" if p else ""
    rows_u = []
    for c in base:
        no = uno(c); tl = []
        for t in c:
            cars = str(CO(t)) if CO(t) == CD(t) else f"{CO(t)}→{CD(t)}"
            memo = "・".join(x for x in (t.note or "", "増発" if getattr(t, "extra", False) else "", f"{t.split}で分割・併合" if getattr(t, "split", None) and CO(t) != CD(t) else "") if x)
            if t in TRK.side_after: memo = "・".join(x for x in (memo, f"到着後 {TRK.side_after[t][1]}へ") if x)
            tl.append(f"<tr><td class='n'>{t.no}</td><td><span class='chip {KC[t.kind]}'>{t.kind}</span></td><td class='n'>{hhmm(t.dep(t.o))}</td><td>{t.o}{trk(t, t.o)}</td><td class='n'>{hhmm(t.arr(t.d))}</td><td>{t.d}{trk(t, t.d)}</td><td class='n'>{cars}</td><td class='s'>{_h.escape(memo)}</td></tr>")
        nk = sum(1 for t in c if t.kind == "回送")
        rows_u.append(f"<details class='u'><summary><span class='no'>{no}</span><span class='cat'>{cat(c)}</span><span class='od'>{c[0].o} {hhmm(c[0].dep(c[0].o))} → {c[-1].d} {hhmm(c[-1].arr(c[-1].d))}</span><span class='m'>{len(c) - nk}本" + (f"＋回送{nk}" if nk else "") + f"</span><span class='m'>{sum(km(t) for t in c):.0f}km</span><span class='m'>{seq_cars(c)}両</span></summary><div class='scrollx'><table class='t'><thead><tr><th>列車番号</th><th>種別</th><th>発</th><th></th><th>着</th><th></th><th>両数</th><th></th></tr></thead><tbody>{''.join(tl)}</tbody></table></div></details>")
    def role_key(nm): return (0 if nm.startswith("基本") else 1 if nm.startswith("付属") else 2, nm)
    rows_r = "".join(f"<tr><td>{label(nm)}</td><td class='n'>{roles[nm]['size']}両</td><td class='s'>{_h.escape(story(nm))}</td><td>{depot_txt(roles[nm])}</td><td>{label(pi[nm])}</td></tr>"
                     for nm in sorted(roles, key=role_key) if not nm.startswith("基本") or len(roles[nm]["log"]) > 2)
    cyc_html = ""
    for cyc in CYC:
        st = next((i for i in range(len(cyc)) if roles[cyc[i - 1]]["night_depot"]), 0); cyc = cyc[st:] + cyc[:st]      # 車庫で夜を越した翌朝を1日目にする
        body = ""; run = 0
        for d, nm in enumerate(cyc, 1):
            r = roles[nm]; run = 0 if r["visit"] else run + 1
            body += f"<tr class='{'v' if r['visit'] else ''}{' warn' if run > LIM else ''}'><td class='n'>{d}</td><td>{label(nm)}</td><td>{place(r['start']) if nm.startswith('留置') else r['start']} → {place(r['end']) if r['night_depot'] else r['end']}</td><td>{depot_txt(r)}</td><td class='n'>{run if run else ''}</td></tr>"
        sz = roles[cyc[0]]["size"]
        cyc_html += f"<details class='u' open><summary><span class='no'>{sz}両</span><span class='od'>{len(cyc)}日で一巡（{len(cyc)}本の編成が、1日ずつずれて同じ順序を回る）</span><span class='m'>車庫に入らない日は最大{maxrun(cyc)}日</span></summary><div class='scrollx'><table class='t'><thead><tr><th>日</th><th>その日の役</th><th>朝 → 夜</th><th>車庫に入る</th><th>入らない日数</th></tr></thead><tbody>{body}</tbody></table></div></details>"
    nightpos = defaultdict(lambda: [0, 0])
    for r in roles.values(): nightpos[r["end"]][0 if r["size"] == 4 else 1] += 1
    # 予備の編成（2026-11-11 本人が「74本で反映」＝4両3本・2両2本と決めた）。置き場所：駅 → (4両の本数, 2両の本数)。環境変数 SPARE="新狛野:2:1,就島:1:1"（"" で予備なし）
    SPARE = {}
    for x in filter(None, os.environ.get("SPARE", "新狛野:2:1,就島:1:1").split(",")):
        X_, a_, b_ = x.split(":"); SPARE[X_] = (int(a_), int(b_))
    s4 = sum(v[0] for v in SPARE.values()); s2 = sum(v[1] for v in SPARE.values())
    for X_, (a_, b_) in SPARE.items(): nightpos[X_][0] += a_; nightpos[X_][1] += b_
    def spare_txt(X): return "・".join(x for x in (f"4両{SPARE[X][0]}本" if SPARE[X][0] else "", f"2両{SPARE[X][1]}本" if SPARE[X][1] else "") if x) if X in SPARE else "—"
    print(f"予備 4両 {s4}本・2両 {s2}本（{s4 * 4 + s2 * 2}両）を足して、編成 {len(units) + s4 + s2}本（4両 {n4 + s4}本・2両 {n2 + s2}本）・{(n4 + s4) * 4 + (n2 + s2) * 2}両")
    import morning, ops
    def lines_need(X, n4_, n2_):
        """夜に要る線の数：1線に8両まで（奥雲温泉は4両まで）、編成を縦に並べて詰める"""
        if X == "奥雲温泉": return n4_ + -(-n2_ // 2)
        full = n4_ // 2; rest4 = n4_ % 2; n2r = n2_
        if rest4: full += 1; n2r = max(0, n2r - 2)             # 4両1本の線には、2両を2本まで足せる
        return full + -(-n2r // 4)
    NL = {X: (lines_need(X, v[0], v[1]), morning.CAP_STABLE.get(X)) for X, v in nightpos.items()}
    night_over = [X for X, (a, b) in NL.items() if b is not None and a > b]
    rows_n = "".join(f"<tr class='{'warn' if X in night_over else ''}'><td>{X}{'（' + DEPOT_NAME[X] + 'を含む）' if X in DEPOT else ''}</td><td class='n'>{v[0]}</td><td class='n'>{v[1]}</td><td class='n'>{v[0] * 4 + v[1] * 2}</td><td>{spare_txt(X)}</td><td class='n'>{NL[X][0]}</td><td class='n'>{NL[X][1] if NL[X][1] is not None else '—'}</td></tr>" for X, v in sorted(nightpos.items(), key=lambda z: -(z[1][0] * 4 + z[1][1] * 2)))
    print("夜に要る線の数／置ける数：", {X: NL[X] for X in sorted(NL, key=lambda X: -NL[X][0])}, "超える駅", night_over)
    allruns = [x for c in CYC for x in runs_of(c)]; over = [x for x in allruns if x > LIM]
    mix = [no for no, us in sorted(comp.items()) if [u.size for u in us] == [4, 2, 2]]
    facts = [("編成の数", f"{len(units) + s4 + s2}本・{(n4 + s4) * 4 + (n2 + s2) * 2}両", f"4両編成 {n4 + s4}本、2両編成 {n2 + s2}本。" + (f"ダイヤを回すのに要る {len(units)}本（{n4 * 4 + n2 * 2}両）と、予備 {s4 + s2}本（4両 {s4}本・2両 {s2}本、{s4 * 4 + s2 * 2}両）" if s4 + s2 else "検査や故障に備える予備は含みません")),
             ("基本の運用", f"{len(base)}本", "、".join(f"{k} {v}本" for k, v in cnt.items())),
             ("日またぎの順序", "、".join(f"{roles[c[0]]['size']}両は{len(c)}日" for c in CYC) + "で一巡", "同じ長さの編成は、全部が同じ順序を1日ずつずれて回ります"),
             ("車庫に入る間隔", f"入らない日は最大{max(allruns)}日", f"目標は{LIM}日まで（{LIM + 1}日に一度は車庫）。" + (f"超えるところが{len(over)}か所あります" if over else "全部の編成が目標に収まっています"))]
    notes = ["車両の単位は4両編成と2両編成の2種類です。8両は4＋4、6両は4＋2、奥雲線内の各停は2両（ラッシュは2＋2）で組みます。" + (f"朝、4両編成が足りない駅から出る運用{'・'.join(mix)}は、8両を4＋2＋2で組みます。" if mix else ""),
             "同じ長さの2本をつないだ編成（4＋4、2＋2）を切り離すときは、先に付いていた方を外します。残った方がそのあとの基本の編成になります。こうすると、同じ編成が同じ運用に居つかず、車庫へ入る順番が回ってきます。",
             f"車庫に入った日と数えるのは、夜を狛野車庫（新狛野）・就島車庫で越す日と、昼に車庫で{DEPOT_STAY // 3600}時間以上待つ日です。新狛野・就島で夜を越す編成は、駅の線ではなく車庫に入るものとして数えています。日常の検査は狛野車庫（検査線2線）と就島車庫（検査線1線）で、3か月ごとの検査と4年ごとの検査（工場2線）は狛野車庫で行う前提です。",
             "日またぎの順序は、同じ駅で夜を越す同じ長さの編成どうしで、翌朝の役を入れ替えて決めています。ダイヤ（列車の時刻、折返しの相手、回送）は変えていません。",
             f"ダイヤを回すのに要る編成の数（{len(units)}本）は、同じ日課を毎日続けて回したときに足りる数です。増結・切り離しの作業の手順、夜のうちに編成を組み替える作業の時刻は入っていません。"]
    if s4 + s2: notes.insert(1, f"予備は4両編成 {s4}本・2両編成 {s2}本です。工場に入る検査（4年に一度と置いています）で4両・2両が1本ずつ抜け、さらに故障や臨時の修繕で4両2本・2両1本が抜けても回せる数です。3か月ごとの検査は、日またぎの順序の中にある「車庫で待機する役」の日に済ませる想定で、予備には数えていません。予備は" + "、".join(f"{place(X)}に{spare_txt(X)}" for X in SPARE) + "を置きます。日またぎの順序には入れていません（工場から戻った編成が、入れ替わりで予備になります）。検査の周期と入場の日数は仮の置き方です。")
    kd = sorted([t for t in tr if t.note in ("検査のための入庫", "検査のための出庫")], key=lambda t: -t.dep(t.o))
    if kd: notes.append("蓮木線内を往復して学院前へ戻る編成は、そのままでは車庫に入る機会がないので、検査のための回送を足しています（" + "、".join(f"{t.o} {hhmm(t.dep(t.o))}発 → {t.d} {hhmm(t.arr(t.d))}着" for t in kd) + "）。夜に就島車庫へ入れ、代わりに朝いちばんに学院前を出る編成を就島車庫から出します。")
    full = [X for X, (a, b) in NL.items() if b is not None and a == b]
    notes.append("夜の置き場所は、" + ("置ける数を超える駅があります（" + "・".join(night_over) + "）。" if night_over else "どの駅も置ける数に収まります。") + "ただし、切り離して置いてある編成を、着いた列車と同じ線に縦に並べて1線8両まで詰める前提です" + (f"（{'・'.join(full)}は空きがありません）" if full else "") + "。")
    if over: notes.append(f"車庫に入らない日が目標（{LIM}日）より長く続くところが{len(over)}か所残ります（下の順序の表で色をつけた行）。就島車庫を出たあと、車庫のない駅で夜を越す運用が続くためで、順序の入れ替えだけでは直りません。直すには、夜に車庫へ入る回送を足すなど、ダイヤ側の手当てが要ります。")
    css = """:root{--bg:#F5F1E9;--panel:#FBF9F4;--ink:#35383B;--sub:#645044;--muted:#7B6A5E;--line:#DED2C4;--teal:#236962;--brick:#963D39;--k-loc:#35383B;--k-exp:#246BA3;--k-rap:#BE493B;--k-dh:#9A8B7E;--k-fg:#FFFFFF;--f-ui:"Zen Kaku Gothic New","Hiragino Kaku Gothic ProN","Noto Sans JP","Yu Gothic",sans-serif;--f-num:"IBM Plex Mono",ui-monospace,"SFMono-Regular",Menlo,monospace}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#2E3134;--panel:#35383B;--ink:#F5F1E9;--sub:#DED2C4;--muted:#B8A898;--line:#4C5054;--teal:#5BAEA3;--brick:#D26B64;--k-loc:#EDE6DA;--k-exp:#6FA8DA;--k-rap:#E67A6C;--k-dh:#A99D92;--k-fg:#23262A;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#2E3134;--panel:#35383B;--ink:#F5F1E9;--sub:#DED2C4;--muted:#B8A898;--line:#4C5054;--teal:#5BAEA3;--brick:#D26B64;--k-loc:#EDE6DA;--k-exp:#6FA8DA;--k-rap:#E67A6C;--k-dh:#A99D92;--k-fg:#23262A;color-scheme:dark}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--f-ui);font-size:14px;line-height:1.7}
main{max-width:1080px;margin:0 auto;padding-block:28px 60px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));display:flex;flex-direction:column;gap:30px}
h1{font-size:24px;margin:0;text-wrap:balance}h2{font-size:17px;margin:0}
a{color:var(--teal)}.lead{color:var(--sub);margin:6px 0 0;max-width:65ch}
.sec-h{display:flex;flex-direction:column;gap:2px;border-top:1.5px solid var(--ink);padding-top:10px;margin-bottom:10px}.sec-h .meta{font-size:12.5px;color:var(--muted);max-width:80ch}
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,230px),1fr));gap:1px;background:var(--line);border:1px solid var(--line);margin:0}
.fact{background:var(--panel);padding:12px 14px}.fact dt{font-size:12px;color:var(--muted)}.fact dd{margin:2px 0 0;font-size:17px;font-weight:700}.fact .s{display:block;font-size:12px;color:var(--muted);margin-top:2px}
.scrollx{overflow-x:auto;border:1px solid var(--line);background:var(--panel)}
table.t{border-collapse:collapse;width:100%;font-size:13px}table.t th,table.t td{padding:5px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top;white-space:nowrap}
table.t tbody tr:last-child td{border-bottom:0}
table.t th{font-weight:500;color:var(--muted);font-size:12px}table.t td.n{font-family:var(--f-num)}table.t td.s{white-space:normal;color:var(--sub);min-width:280px}
.tk{font-size:11.5px;color:var(--muted)}
table.t tr.v td:nth-child(4){color:var(--teal);font-weight:700}table.t tr.warn td{background:color-mix(in srgb,var(--brick) 16%,transparent)}
.chip{display:inline-block;font-size:11px;font-weight:700;padding:0 6px;border-radius:2px;color:var(--k-fg);line-height:1.6}.chip.loc{background:var(--k-loc)}.chip.exp{background:var(--k-exp)}.chip.rap{background:var(--k-rap)}.chip.dh{background:var(--k-dh)}
details.u{border:1px solid var(--line);background:var(--panel);border-radius:3px}details.u+details.u{margin-top:4px}
details.u summary{display:flex;flex-wrap:wrap;gap:4px 16px;align-items:baseline;padding:7px 12px;cursor:pointer}
details.u summary .no{font-family:var(--f-num);font-weight:700;font-size:15px;min-width:34px}details.u summary .cat{font-size:12px;color:var(--muted);min-width:64px}
details.u summary .od{flex:1;min-width:230px}details.u summary .m{font-family:var(--f-num);font-size:12.5px;color:var(--sub)}
details.u .scrollx{border:0;border-top:1px solid var(--line)}
ul.notes{margin:0;padding-left:20px;max-width:75ch}ul.notes li{margin:4px 0}"""
    page = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>犬電 車両運用表</title><style>{css}</style></head><body><main>
<header><h1>犬村電気鉄道 車両運用表</h1><p class="lead">終日のダイヤ（営業列車 {sum(1 for t in tr if t.kind != '回送')}本と回送 {sum(1 for t in tr if t.kind == '回送')}本）を、4両編成と2両編成でどう回すかをまとめた表です。編成を1本ずつ区別して、1日の動きと、翌日どの役に入るかを決めています。列車番号は<a href="dia_all.html">終日ダイヤのページ</a>と同じです。</p></header>
<section><dl class="facts">{''.join(f'<div class="fact"><dt>{a}</dt><dd>{b}<span class="s">{c}</span></dd></div>' for a, b, c in facts)}</dl></section>
<section><div class="sec-h"><h2>基本の運用</h2><span class="meta">折返しでつながった列車の並びが、基本の編成1本の1日の行路です。行を開くと、列車番号つきの行路が出ます。駅名の横は発着の番線です。両数は、付属の編成を付けたり外したりして変わります。</span></div>{''.join(rows_u)}</section>
<section><div class="sec-h"><h2>付属の編成・待機する編成の動き</h2><span class="meta">朝の時点の役ごとの1日の動きと、翌朝に入る役です。基本の編成のうち、途中で切り離されて入れ替わるものもここに載せています。</span></div>
<div class="scrollx"><table class="t"><thead><tr><th>朝の役</th><th>長さ</th><th>1日の動き</th><th>車庫に入る</th><th>翌朝の役</th></tr></thead><tbody>{rows_r}</tbody></table></div></section>
<section><div class="sec-h"><h2>日またぎの順序</h2><span class="meta">1本の編成が、日ごとにどの役を務めていくかの順序です。車庫で夜を越した翌朝を1日目にしています。色のついた行は、車庫に入らない日が目標より長く続くところです。</span></div>{cyc_html}</section>
<section><div class="sec-h"><h2>夜を越す場所</h2><span class="meta">1日の終わりに、各駅・車庫にいる編成の数です（予備の編成を含みます）。「要る線」は、1線に8両まで（奥雲温泉は4両まで）、編成を縦に並べて詰めたときの線の数。「置ける数」は、夜に使えるホームと留置線・車庫の線の数です。</span></div>
<div class="scrollx"><table class="t"><thead><tr><th>駅・車庫</th><th>4両編成</th><th>2両編成</th><th>両数</th><th>うち予備</th><th>要る線</th><th>置ける数</th></tr></thead><tbody>{rows_n}</tbody></table></div></section>
<section><div class="sec-h"><h2>前提と気になる点</h2></div><ul class="notes">{''.join(f'<li>{x}</li>' for x in notes)}</ul></section>
</main></body></html>"""
    open(OUT, "w", encoding="utf-8").write(page); print("書き出し", OUT, f"{len(page) // 1024}KB")
