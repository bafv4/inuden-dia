# 番線・引上線の割り当て（2026-11-11 本人の依頼「どの列車（運用）が駅の何番線・何番引き上げ線を使うかを考慮してください」）
#   これまでの競合の判定（sched.conflicts・ops.turn_occ）は、駅ごと・向きごとに「同時にいる本数 ≦ 線の数」を見るだけで、
#   どの線かは決めていなかった。ここでは同じ在線の時間（判定と同じ式）を、配線図の線1本ずつに割り当て、
#   (1) 同じ線に2本が重ならないか、(2) 通過列車が本線を通れるか、(3) 引上線・留置線へ出入りできる線か、
#   (4) 終点（軒屋・蓮木市）の入口で、到着と出発の進路が交差しないか、を確かめる。ダイヤは書き換えない。
#   番線の付け方（配線図には番号がないので、ここで決めた。下り本線の外側から順に 1, 2, …）：
#     2面4線の待避駅（高砂町・新犬村・錦町・本位堂・就島・秋田台・新狛野・犬塚・佐茂町）：1 下り副本線、2 下り本線、3 上り本線、4 上り副本線
#     高島：1 下り本線（外側）、2 下り中線、3 上り中線、4 上り本線（外側）。引上線1・2は中線の先
#     学院前：1 下り本線（外側）、2 下り蓮木線（内側）、3 上り蓮木線（内側）、4 上り本線（外側）。折返し線1・2は内側線の軒屋方
#     三宅：1 下り本線、2 中線（上下共用）、3 上り本線
#     軒屋：1〜4（1・2が下り線側、3・4が上り線側）。留置線1・2
#     蓮木市：1（片面ホーム。下り線からまっすぐ）、2・3（島式。3番線がそのまま上り線）。留置線1は2番線の先、留置線2は3番線の先
#     奥雲温泉：1・2。単線の交換駅（下岩田・奥雲口・霧里）と小椋・東松田：1 下り、2 上り（下岩田は1が通過できる本線）
#     単線の途中の駅（長坂・羽土・東蔵寺）：1 のみ（線が1本。2026-11-13 本人の指示で、上りを2番線にしていたのを直した）
#     そのほかの駅：1 下り、2 上り
#   使い方（data で）: PYTHONPATH=../src python ../src/tracks.py パターン.pkl [day_final.pkl]
#   ほかのプログラムからは: import tracks; R = tracks.assign(tr)   （R.trk[列車][駅]＝番線の名前、R.side[列車]＝引上線などの出入り、R.problems）
import sys, os
from collections import defaultdict, Counter
if __name__ == "__main__":
    PKF = sys.argv[1]; SRC = sys.argv[2] if len(sys.argv) > 2 else "day_final.pkl"; sys.argv = [sys.argv[0], PKF]
from morning_run import *
import net, ops
LONG = ops.LONG
THROAT = int(os.environ.get("THROAT", "90"))        # 終点の入口：進路が交差する到着と出発は、出発が到着の前 THROAT 秒以内だとぶつかる
SHIN_X = os.environ.get("SHIN_X", "1") != "0"       # 新犬村：下り副本線（1番線）で夜を越した編成は、軒屋方のシーサス（2026-11-11 に配線図へ足した）で上り線へ出る（0：これまでの判定と同じく、始発は全部上り側に数える）
AKI_D = os.environ.get("AKI_D", "1") != "0"         # 秋田台の留置線から出る列車は、配線図どおり下り側のホームに戻って上り線へ渡る（0：これまでの判定と同じく上り側に数える）
SIDENAME = {"軒屋": "留置線", "蓮木市": "留置線", "学院前": "折返し線", "高島": "引上線", "秋田台": "留置線", "犬塚": "引上線", "就島": "就島車庫", "新狛野": "狛野車庫"}
TURN4 = ("就島", "秋田台", "新狛野", "犬塚")
SINGLE1 = ("長坂", "羽土", "東蔵寺")                 # 単線の途中の駅（交換できない。線は1本）
# 止まる列車が副本線と本線をおよそ交互に使う駅（2026-11-11 本人の指示「新犬村に発着する電車は番線をおよそ交互に使うようにしてください」）。
# 向きごとに、着く順に 本線・副本線・本線・… と振る。前の列車がまだいる・抜かれる列車は副本線、などで入らないときだけ、順番どおりでなくなる
ALT = set(filter(None, os.environ.get("ALT", "新犬村").split(",")))
# 留置線へ出ずに、着いたホームで発車まで待つ折返しの長さ（秒）。判定（ops.LONG＝15分）は、15分を超える折返しを留置線へ出す数え方だが、
# 蓮木市は留置線が2・3番線の先にあって、出入りできる番線が決まっている。15〜17分の折返しを全部いったん留置線へ出すと番線が足りないので、
# 20分までの折返しは着いた番線に居続ける形にする（3線で足りるかは、ここで確かめる）
STAY_PLAT = {"蓮木市": int(os.environ.get("STAY_HASU", "1200")), "軒屋": int(os.environ.get("STAY_NOKI", "1080"))}      # 軒屋は18分まで（21時ごろ、留置線へ出る時刻が出発と重なって取れない折返しが2本あったため。20分にすると逆に4線で足りなくなる）
def stored_at(X, s): return sum(n for t, n in ops.STORED.get(X, []) if t <= s)
def build_items(trains, links):
    """在線の時間を、判定（conflicts_full の2・ops.turn_occ）と同じ式で作る。1件＝dict(key, s, e, t, role, A, D, side)
       role：pass 通過、stop 途中の停車、turn 折返しでホームに居続ける、arr 着いたあと外へ出る・その駅止まり、dep 外から戻って出る・その駅始発"""
    items = []; sides = []                          # sides：(駅, 線の番号 or None, 出る時刻, 戻る時刻, 着いた列車, 出る列車)
    def add(key, s, e, t, role, A=None, D=None, side=None): items.append(dict(key=key, s=s, e=e, t=t, role=role, A=A, D=D, side=side))
    for tr in trains:
        for x, (ar, dp, stp) in tr.times.items():
            if x == tr.o or x == tr.d: continue
            key = (x, "*") if x in net.TOTAL_CAP else (x, tr.dir)
            if x == "学院前": key = (x, tr.dir, "H" if (tr.o in net.HN[1:] or tr.d in net.HN[1:]) else "M")
            if stp: add(key, ar, dp + PAD, tr, "stop")
            else: add(key, ar - 5, ar + PAD, tr, "pass")
    used = set(); pend = defaultdict(list)
    def keys(X, A, D):
        """(着いた側の鍵, 出る側の鍵, 着いてから外へ出るまで, 戻ってから出るまで)"""
        if X in ("軒屋", "蓮木市", "奥雲温泉"): return (X, "*"), (X, "*"), 180, 480
        if X == "学院前": return (A and (X, A.dir, "H")), (D and (X, D.dir, "H")), 90, 120
        if X == "高島": return (A and (X, A.dir)), (D and (X, D.dir)), 120, 180
        return (A and (X, A.dir)), (D and (X, D.dir)), 120, 240
    for D, A in links.items():
        X = D.o
        if A is not None: used.add(A)
        ka, kd, pa, pd = keys(X, A, D)
        if X in ("軒屋", "蓮木市", "奥雲温泉"):
            if A is None: add(kd, D.dep(X) - 600, D.dep(X) + PAD, D, "dep", D=D)
            elif D.dep(X) - A.arr(X) <= LONG: add(kd, A.arr(X), D.dep(X) + PAD, D, "turn", A, D)
            else: pend[X].append((A.arr(X) + 180, D.dep(X) - 480, A, D))
        elif X in ("学院前", "高島"):
            if A is None: add(kd, D.dep(X) - pd, D.dep(X) + PAD, D, "dep", D=D)
            else: pend[X].append((A.arr(X) + pa, D.dep(X) - pd, A, D))
        else:
            if A is not None and D.dep(X) - A.arr(X) <= LONG: add(ka, A.arr(X), D.dep(X) + PAD, D, "turn", A, D)
            elif A is None: add(kd, D.dep(X) - 240, D.dep(X) + PAD, D, "dep", D=D)
            else: pend[X].append((A.arr(X) + 120, D.dep(X) - 240, A, D))
    for X, L in pend.items():
        busy = {}                                   # 線の番号 → 戻る時刻
        for s, e, A, D in sorted(L, key=lambda z: z[0]):
            ka, kd, pa, pd = keys(X, A, D)
            if e <= s: out = True; line = None
            else:
                busy = {k: f for k, f in busy.items() if f > s}
                cap = ops.SIDING.get(X, 0) - stored_at(X, s)
                out = len(busy) < cap
                if out:
                    line = min(k for k in range(1, ops.SIDING.get(X, 0) + 1) if k not in busy); busy[line] = e
            if out:
                sd = (X, line, s, e, A, D) if e > s else None
                if sd: sides.append(sd)
                add(ka, A.arr(X), A.arr(X) + pa, A, "arr", A, D, sd); add(kd, D.dep(X) - pd, D.dep(X) + PAD, D, "dep", A, D, sd)
            elif X in ("軒屋", "蓮木市", "奥雲温泉"): add(kd, A.arr(X), D.dep(X) + PAD, D, "turn", A, D)
            elif X == "学院前": add(kd, A.arr(X), D.dep(X) + PAD, D, "turn", A, D)
            else: add(ka, A.arr(X), D.dep(X) + PAD, D, "turn", A, D)
    for A in trains:
        X = A.d
        if A in used: continue
        ka, _, pa, _ = keys(X, A, None)
        add(ka, A.arr(X), A.arr(X) + pa, A, "arr", A=A)
    return items, sides
def same_as_checker(trains, links, items):
    """作った在線が ops.turn_occ・判定と同じか（折返しのぶんだけ比べる）"""
    occ = ops.turn_occ(trains, links)
    a = sorted((k, round(s), round(e), id(t)) for k, L in occ.items() for s, e, t in L)
    b = sorted((i["key"], round(i["s"]), round(i["e"]), id(i["t"])) for i in items if i["role"] in ("turn", "arr", "dep"))
    return a == b, len(a), len(b)
# ---- 線の候補と、選びにくさ（1000 以上は「その線は使えない」＝問題として報告する）
KPREF = {"快速": (1, 2, 3, 4), "急行": (2, 1, 3, 4), "各停": (3, 4, 2, 1), "回送": (4, 3, 2, 1)}
def options(it):
    key = it["key"]; X = key[0]; role = it["role"]; t = it["t"]
    if X == "学院前":
        inner = 2 if key[1] == "D" else 3; outer = 1 if key[1] == "D" else 4
        if key[2] == "H": return [(inner, 0), (outer, 1000)]
        return [(outer, 0), (inner, 5 if role == "pass" else 6)]          # 本線の列車は外側。外側がふさがっていれば内側（配線図：外側で各停を待たせて優等列車を内側に通す）
    if X == "軒屋": return [(p, 0.1 * i) for i, p in enumerate(KPREF[t.kind])]
    if X == "蓮木市":
        sd = it["side"]
        if sd: return [(2, 0), (3, 0.2), (1, 1000)]      # 留置線1は2番線の先、留置線2は3番線の先。どちらの留置線を使うかは、番線と一緒にここで決める（cost_add）
        pref = (3, 2, 1) if t.kind == "急行" else (1, 2, 3)
        return [(p, 0.1 * i) for i, p in enumerate(pref)]
    if X == "奥雲温泉": return [(p, 0.1 * i) for i, p in enumerate((1, 2) if t.kind == "快速" else (2, 1))]
    if X == "三宅":
        main = 1 if t.dir == "D" else 3
        if role == "stop" and it.get("ovt"): return [(2, 0), (main, 1.5)]      # 抜かれる列車は中線で待つ
        return [(main, 0), (2, 1000 if role == "pass" else 2)]
    if X in ("小椋", "東松田"): return [(1, 0), (2, 1000)] if t.dir == "D" else [(2, 0), (1, 1000)]
    if X == "下岩田":
        if role == "pass": return [(1, 0), (2, 1000)]
        return [(1, 0), (2, 0.5)] if t.dir == "D" else [(2, 0), (1, 0.5)]
    if X in ("奥雲口", "霧里"): return [(1, 0), (2, 1)] if t.dir == "D" else [(2, 0), (1, 1)]
    if X in net.K2:
        d = key[1]; main, sub = (2, 1) if d == "D" else (3, 4)
        if X == "高島": main, sub = (1, 2) if d == "D" else (4, 3)
        if role == "pass": return [(main, 0), (sub, 1000)]
        if role == "stop" and it.get("alt") and not it.get("ovt"): return [(it["alt"], 0), (main if it["alt"] == sub else sub, 1)]      # 交互に使う駅
        if role == "stop": return [(sub, 0), (main, 1.5)] if it.get("ovt") else [(main, 0), (sub, 2)]      # 抜かれる列車（あとから着いた列車が先に出る）は副本線・中線で待ち、抜く列車が本線
        return [(sub, 0), (main, 1000 if X == "高島" else 3)]             # 折返し・始発・終着は副本線（高島は中線だけが引上線につながる）
    if X in SINGLE1: return [(1, 0)]                                       # 単線の途中の駅は線が1本（2026-11-13 本人の指示。それまでは上りを2番線にしていた）
    return [(1 if key[1] == "D" else 2, 0)]
def throat(X, a, pa, d, pd):
    """終点の入口で、到着（時刻 a、pa 番線）と出発（時刻 d、pd 番線）の進路がぶつかるか"""
    if not (0 <= a - d < THROAT) or pa == pd: return False
    if X == "軒屋": return not (pa in (3, 4) and pd in (1, 2))          # 上り線側（3・4）への到着と、下り線側（1・2）からの出発だけが同時に進める
    if X == "蓮木市": return (pa, pd) in ((2, 1), (3, 1), (3, 2))        # 1番線からの出発は2・3番線への到着と、2番線からの出発は3番線への到着と平面交差する
    return False
def moves(it):
    """終点での、入口を通る動き：[(種類, 時刻)]。到着は着く時刻、出発は出る時刻"""
    X = it["key"][0]; out = []
    if it["role"] in ("turn", "arr") and it["A"] is not None: out.append(("a", it["A"].arr(X)))
    if it["role"] in ("turn", "dep") and it["D"] is not None: out.append(("d", it["D"].dep(X)))
    return out
class Result: pass
def assign(trains, links=None, quiet=True):
    for t in trains: t.compute()
    if links is None:
        links, _ = link_nl(trains)
        for t in trains:
            if getattr(t, "src", None) is not None: links[t] = t.src
    items, sides = build_items(trains, links)
    R = Result(); R.same = same_as_checker(trains, links, items)
    R.stay = []
    for sd in list(sides):                          # STAY_PLAT：留置線へ出ずにホームで待つ折返しは、着いてから出るまでの1件にまとめる
        X, line, s_, e_, A, D = sd
        if X in STAY_PLAT and D.dep(X) - A.arr(X) <= STAY_PLAT[X]:
            mine = [i for i in items if i["side"] is sd]
            for i in mine: items.remove(i)
            items.append(dict(key=mine[0]["key"], s=A.arr(X), e=D.dep(X) + PAD, t=D, role="turn", A=A, D=D, side=None))
            sides.remove(sd); R.stay.append(sd)
    side_fixed = {}; line_busy = []                 # 蓮木市：留置線へ出る列車の番線（2＝留置線1、3＝留置線2）と、留置線がふさがっている時間
    def cross_hits(X, D):
        """下り側のホームから上り線へ渡って出る列車 D と、同じころに駅を通る本線の列車（ops.cross_conf と同じ見方）"""
        t0 = D.dep(X); out = []
        for T_ in trains:
            if T_ is D or X not in T_.times or T_.o == X or T_.d == X: continue
            tt = T_.arr(X) if T_.dir == "D" else T_.dep(X)
            if abs(tt - t0) < 60: out.append(T_)
        return out
    R.aki4 = None
    if AKI_D:                                        # 秋田台：留置線は下り副本線の先。留置線から戻る列車と、朝に留置線・下り副本線から出る列車は、下り側のホームから上り線へ渡る
        deps = sorted([i for i in items if i["key"] == ("秋田台", "U") and i["role"] == "dep"], key=lambda i: i["s"])
        st = [i for i in deps if i["A"] is None]      # 朝の始発。1本だけは、上り副本線（4番線）で夜を越した編成（渡らずに出られる）。渡ると本線の列車とぶつかるものを優先してそれにする
        keep = next((i for i in st if cross_hits("秋田台", i["D"])), st[0] if st else None)
        R.aki4 = keep and keep["D"]
        for i in deps:
            if i is keep: continue
            i["key"] = ("秋田台", "D"); i["cross"] = True
    R.shin4 = None
    if SHIN_X:                                       # 新犬村：朝の始発は、上り副本線（4番線）で夜を越した編成が1本、残りは下り副本線（1番線）からシーサスで上り線へ渡る
        st = sorted([i for i in items if i["key"] == ("新犬村", "U") and i["role"] == "dep" and i["A"] is None], key=lambda i: i["s"])
        ua = [i["A"] for i in items if i["key"] == ("新犬村", "U") and i["role"] == "arr" and i["D"] is None]      # 夜、上りで着いて4番線に入る編成
        cars = lambda t, w: getattr(t, w, t.cars)
        same = [i for i in st if any(cars(i["D"], "cars_o") == cars(a, "cars_d") for a in ua)]                    # 両数が同じ始発が、その編成
        keep = (same[0] if len(same) == 1 else st[-1]) if st else None                                            # 分からなければ、いちばん遅い始発を4番線にする（早い方が先に渡る）
        R.shin4 = keep and keep["D"]
        for i in st:
            if i is keep: continue
            i["key"] = ("新犬村", "D"); i["cross"] = True
    for i in items:                                  # 新犬村はホームのほかに線がないので、夜を越す編成は着いた副本線に朝までいる（その線は、着いたあと・出る前は使えない）
        if i["key"][0] == "新犬村" and i["role"] == "arr" and i["D"] is None: i["e"] = T(28, 0)
        if i["key"][0] == "新犬村" and i["role"] == "dep" and i["A"] is None: i["s"] = T(3, 0)
    by = defaultdict(list)
    for i in items:
        k = i["key"]; g = (k[0], k[1]) if k[0] == "学院前" else k
        by[g].append(i)
    for g, L in by.items():                         # 抜かれる列車に印をつける（同じ向きで、あとから着いて先に出る列車がある停車）
        for i in L:
            if i["role"] == "stop": i["ovt"] = any(j is not i and j["role"] in ("stop", "pass") and j["t"].dir == i["t"].dir and j["s"] > i["s"] and j["e"] < i["e"] for j in L)
    for g, L in by.items():                         # 交互に使う駅：向きごとに、着く順に本線・副本線を振る（折返し・始発・終着は副本線、通過は本線として数える）
        if g[0] not in ALT or g[0] not in net.K2 or g[0] in ("学院前", "高島"): continue
        main, sub = (2, 1) if g[1] == "D" else (3, 4); prev = sub
        for i in sorted(L, key=lambda i: (i["s"], i["e"])):
            if i["role"] == "pass": prev = main
            elif i["role"] != "stop" or i.get("ovt"): prev = sub
            else: i["alt"] = main if prev == sub else sub; prev = i["alt"]
    R.problems = []; R.items = items; R.sides = sides
    for g, L in by.items():
        X = g[0]; L.sort(key=lambda i: (i["s"], i["e"]))
        term = X in ("軒屋", "蓮木市")
        if X == "学院前":                           # 判定と同じ決め方：蓮木線の列車は内側、本線の列車は外側が空いていれば外側、ふさがっていれば内側
            inner = 2 if g[1] == "D" else 3; outer = 1 if g[1] == "D" else 4
            H = [i for i in L if i["key"][2] == "H"]; M = [i for i in L if i["key"][2] == "M"]
            for i in H: i["p"] = inner
            for a, b in zip(H, H[1:]):
                if b["s"] < a["e"]: R.problems.append(("同じ線に2本", X, inner, b["s"], [a["t"], b["t"]]))
            free = -1e9; ext = []
            for i in M:
                if i["s"] >= free: i["p"] = outer; free = i["e"]; continue
                busy = [j for j in H + ext if j["s"] < i["e"] and i["s"] < j["e"]]
                i["p"] = inner; ext.append(i)
                if busy: R.problems.append(("同じ線に2本", X, inner, i["s"], [busy[0]["t"], i["t"]]))
            continue
        # まとまり（時間が重なってつながっている在線。終点は入口の交差を見るので THROAT ぶん広げる）ごとに、選びにくさの合計が小さい割り当てを探す
        pad = THROAT if term else 0
        clusters = []; cur = []; end = -1e9
        for i in L:
            if cur and i["s"] >= end + pad: clusters.append(cur); cur = []
            cur.append(i); end = max(end, i["e"]) if len(cur) > 1 else i["e"]
        if cur: clusters.append(cur)
        prev = []                                   # 直前のまとまりの終わりのほう（入口の交差を見るため）
        for C in clusters:
            opts = [sorted(options(i), key=lambda z: z[1]) for i in C]
            n = len(C); asg = [None] * n; side_asg = {}
            rel = [[j for j in range(k) if C[j]["e"] + pad > C[k]["s"]] for k in range(n)]      # 手前の在線のうち、時間が重なる・入口でぶつかりうるもの
            mv = [moves(i) for i in C] if term else None
            def cost_add(k, p):
                i = C[k]; c = 0
                for j in rel[k]:
                    o = C[j]
                    if asg[j] == p and o["s"] < i["e"] and i["s"] < o["e"]: return None
                sd = i["side"]
                if X == "蓮木市" and sd and p != 1:  # 着いた番線の先の留置線へ入り、同じ番線へ戻る。同じ留置線に2本は入れない
                    if side_fixed.get(id(sd), p) != p or side_asg.get(id(sd), p) != p: return None
                    for q, s_, e_, sid in line_busy + [(q, x[2], x[3], id(x)) for x, q in ((C[j]["side"], asg[j]) for j in range(k)) if x]:
                        if q == p and sid != id(sd) and s_ < sd[3] and sd[2] < e_: return None
                if term:
                    for o, po, mo in [(C[j], asg[j], mv[j]) for j in rel[k]] + prev:
                        for ki, ti in mv[k]:
                            for ko, to in mo:
                                if ki == "a" and ko == "d" and throat(X, ti, p, to, po): c += 50
                                if ki == "d" and ko == "a" and throat(X, to, po, ti, p): c += 50
                return c
            # 少し先（WIN 件）まで見て、いまの1件の線を決め、1件ずつ進む
            WIN = 7; best = [0, None]; feasible = True
            for k0 in range(n):
                hi = min(n, k0 + WIN); bw = [1e18, None]
                def dfs(k, tot):
                    if tot >= bw[0]: return
                    if k == hi: bw[0] = tot; bw[1] = asg[k0]; return
                    for p, c0 in opts[k]:
                        c = cost_add(k, p)
                        if c is None: continue
                        sd = C[k]["side"]; had = sd is not None and id(sd) in side_asg
                        asg[k] = p
                        if sd is not None and not had: side_asg[id(sd)] = p
                        dfs(k + 1, tot + c0 + c)
                        asg[k] = None
                        if sd is not None and not had: del side_asg[id(sd)]
                dfs(k0, 0)
                if bw[1] is None:                   # 先まで見ると入らない：いまの1件だけで選ぶ
                    ok = [(c0 + c, p_) for p_, c0 in opts[k0] for c in [cost_add(k0, p_)] if c is not None]
                    if not ok: feasible = False; break
                    bw[1] = min(ok)[1]
                asg[k0] = bw[1]
                if C[k0]["side"] is not None: side_asg.setdefault(id(C[k0]["side"]), bw[1])
            best[1] = list(asg) if feasible else None
            if best[1] is None: asg = [None] * n
            if best[1] is None:                     # 線が足りない：重なりを許して、空いている線・いちばん早く空く線に入れる
                for k, i in enumerate(C):
                    ok = [p for p, c0 in opts[k] if c0 < 1000 and not any(asg[j] == p and C[j]["s"] < i["e"] and i["s"] < C[j]["e"] for j in range(k))]
                    asg[k] = ok[0] if ok else opts[k][0][0]
                    if not ok: R.problems.append(("同じ線に2本", X, asg[k], i["s"], [C[j]["t"] for j in range(k) if asg[j] == asg[k] and C[j]["s"] < i["e"] and i["s"] < C[j]["e"]] + [i["t"]]))
                best[1] = list(asg)
            for i, p in zip(C, best[1]):
                i["p"] = p
                if X == "蓮木市" and i["side"] and p != 1 and id(i["side"]) not in side_fixed: side_fixed[id(i["side"])] = p; line_busy.append((p, i["side"][2], i["side"][3], id(i["side"])))
            for k, i in enumerate(C):
                c0 = dict(opts[k])[i["p"]]
                if c0 >= 1000: R.problems.append(("使えない線", X, i["p"], i["s"], [i["t"]], i["role"]))
            prev = [(i, i["p"], moves(i)) for i in C if i["e"] >= C[-1]["e"] - 900] if term else []
        if term:                                    # 残った入口の交差を数える
            seen = set()
            for a in L:
                for b in L:
                    if a is b or abs(a["s"] - b["s"]) > 7200: continue
                    for ka, ta in moves(a):
                        for kb, tb in moves(b):
                            if ka == "a" and kb == "d" and throat(X, ta, a["p"], tb, b["p"]) and (id(a), id(b)) not in seen:
                                seen.add((id(a), id(b))); R.problems.append(("入口の交差", X, (a["p"], b["p"]), ta, [a["A"], b["D"]]))
    # ---- 2面4線の駅で、下り側のホームから上り線へ渡って出る列車と、本線の列車の交差（ops.cross_conf と同じ見方を、秋田台の留置線から出る列車にも当てる）
    for i in items:
        if not i.get("cross"): continue
        X = i["key"][0]; D = i["D"]
        for T_ in cross_hits(X, D): R.problems.append(("渡り線の交差", X, i["p"], D.dep(X), [D, T_]))
    # ---- 列車ごとにまとめる
    R.trk = defaultdict(dict); R.side_after = {}; R.side_before = {}
    def name(X, p): return f"{p}番線"
    for i in items:
        X = i["key"][0]; t = i["t"]
        if i["role"] == "turn":
            R.trk[i["D"]][X] = name(X, i["p"])
            if i["A"] is not None: R.trk[i["A"]][X] = name(X, i["p"])
        elif i["role"] == "arr": R.trk[i["A"]][X] = name(X, i["p"])
        elif i["role"] == "dep": R.trk[i["D"]][X] = name(X, i["p"])
        else: R.trk[t][X] = name(X, i["p"])
    # ---- 入換の時刻：引上線・留置線・車庫へ出る／戻る動きが本線の列車とぶつからない時刻を探す
    #   判定の決まった時刻（着いて2〜3分後に出る、発車の4〜8分前に戻る）から、出るのは最大4分遅らせ（次にその線を使う列車まで）、
    #   戻るのは発車の2分30秒前まで遅らせてよいことにする。
    #   軒屋：留置線は下り本線の先。出るのは出発と同じ線、戻るのは下り本線を逆向きに走るので、ほかの出発と重ならないこと。3・4番線からは到着の進路も横切る
    #   犬塚・就島・新狛野：引上線・車庫は上り線の側。出るときは上り線を横切り、戻るときは上り線からホームへ入るので、上りで着く・通る列車と重ならないこと
    #   秋田台（下り副本線の先）・高島（中線の先）・学院前（内側線の先）・蓮木市（2・3番線の先）は、本線を横切らない
    W = 60
    def shunt_hit(X, what, tm, p, A, D):
        if X == "軒屋":
            lo, hi = (-W, W) if what == "out" else (-90, W)
            if any(T_.o == X and T_ is not D and lo < tm - T_.dep(X) < hi for T_ in trains): return True
            if p in (3, 4) and any(T_.d == X and T_ is not A and (0 <= T_.arr(X) - tm < THROAT if what == "out" else abs(T_.arr(X) - tm) < W) for T_ in trains): return True
            return False
        if X in ("犬塚", "就島", "新狛野"):
            return any(T_.dir == "U" and X in T_.times and T_.o != X and T_ is not A and T_ is not D and abs(T_.arr(X) - tm) < W for T_ in trains)
        return False
    R.shunt = {}
    for sd in sides:
        X, line, s_, e_, A, D = sd
        ia = next((i for i in items if i["side"] is sd and i["role"] == "arr"), None); idp = next((i for i in items if i["side"] is sd and i["role"] == "dep"), None)
        if ia is None or idp is None: continue
        nxt = min([j["s"] for j in items if j is not ia and j["key"][0] == X and j.get("p") == ia["p"] and j["s"] >= ia["s"]] + [1e18])
        t_out = next((t for t in range(int(s_), int(max(s_, min(s_ + 240, nxt - PAD))) + 1, 15) if not shunt_hit(X, "out", t, ia["p"], A, D)), None)
        t_back = next((t for t in range(int(e_), int(max(e_, D.dep(X) - 150)) + 1, 15) if not shunt_hit(X, "back", t, idp["p"], A, D)), None)
        if t_out is None: R.problems.append(("入換の交差", X, ia["p"], s_, [A, D], "出る")); t_out = s_
        if t_back is None: R.problems.append(("入換の交差", X, idp["p"], e_, [A, D], "戻る")); t_back = e_
        if t_back < t_out + 60: t_back = max(t_back, t_out)           # 出てすぐ戻る形（外にいる時間がほとんどない）
        R.shunt[id(sd)] = (t_out, t_back)
    R.sides = [(sd[0], side_fixed[id(sd)] - 1 if id(sd) in side_fixed else sd[1]) + R.shunt.get(id(sd), sd[2:4]) + sd[4:] for sd in sides]
    for X, line, s, e, A, D in R.sides:
        nm = SIDENAME.get(X, "留置線") + (str(line) if line and X not in ("就島", "新狛野") else "")
        R.side_after[A] = (X, nm, s, e, D); R.side_before[D] = (X, nm, s, e, A)
    for t in trains:                                # 在線を作らない駅（ふつうの駅の始発・終着はない。念のため）
        for x in t.route:
            if x not in R.trk[t]: R.trk[t][x] = None
    return R
if __name__ == "__main__":
    import pickle
    tr, chains, start = pickle.load(open(SRC, "rb"))
    for t in tr:
        if getattr(t, "slow", None) is None: t.slow = {}
        t.compute()
    st = getattr(tr[0], "stored", None)
    if st is not None: ops.STORED.clear(); ops.STORED.update(st)
    import trainno; trainno.assign(tr)
    cs, links = all_conf2(tr)
    R = assign(tr, links)
    print(f"対象 {SRC}：列車 {len(tr)}本、これまでの判定での競合 {len(cs)}件。置いてある車両の記録（STORED）{'あり' if st is not None else 'なし'}")
    print("折返しの在線が判定と同じか：", R.same)
    def tn(t): return f"{t.no} {t.kind} {t.o}{fmt(t.dep(t.o))}→{t.d}{fmt(t.arr(t.d))}"
    kinds = Counter(p[0] for p in R.problems)
    print("問題：", dict(kinds) if kinds else "なし")
    for k in kinds:
        L = [p for p in R.problems if p[0] == k]
        print(f"  ■ {k} {len(L)}件：", dict(Counter(p[1] for p in L)))
        for p in sorted(L, key=lambda p: p[3])[:int(os.environ.get("SHOW", "12"))]: print("     ", p[1], p[2], fmt(p[3]), " ／ ".join(tn(t) for t in p[4] if t is not None), *p[5:])
    print("線ごとの使われ方（1日の在線の回数）")
    use = defaultdict(Counter)
    for i in R.items: use[i["key"][0]][i["p"]] += 1
    for X in ["軒屋", "高砂町", "新犬村", "錦町", "学院前", "本位堂", "就島", "高島", "秋田台", "三宅", "新狛野", "犬塚", "下岩田", "奥雲口", "霧里", "奥雲温泉", "佐茂町", "蓮木市"]:
        print(f"   {X}：" + "、".join(f"{p}番線 {n}" for p, n in sorted(use[X].items())))
    sc = Counter((X, line) for X, line, s, e, A, D in R.sides)
    print("引上線・留置線・折返し線・車庫へ出る回数：", {f"{X}{SIDENAME.get(X, '')}{line or ''}": n for (X, line), n in sorted(sc.items(), key=lambda z: (z[0][0], z[0][1] or 0))})
