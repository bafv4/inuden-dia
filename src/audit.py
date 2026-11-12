# ダイヤ全体の監査（2026-11-11 本人の依頼「全体を監査して、無駄な退避・停車時間、退避・行き違い不正をあぶりだして」）。ダイヤは書き換えない。
#   A) 停車の延長（hold）を全部洗い出し、その停車のあいだに何が起きているかで分ける：
#        待避（後から来た同じ向きの列車が先に出る）／先発（その駅始発の列車が先に出る）／接続（その駅止まりの列車が着く）／
#        行き違い（単線で反対向きの列車と交換）／相手なし。
#      相手なしの停車と、相手が出たあとも長く止まっている停車は、外して（縮めて）も競合が増えないかを2通りで試す：
#        前詰め＝その駅から先を早める、後ろ詰め＝その駅より手前を遅らせる（先の時刻は変えない）
#   B) 追い越しの検算（既存の判定 sched.conflicts とは別の計算）：駅間での順序の入れ替わり、待避線のない駅での追い越し、
#      止まっていない列車が抜かれる、同じ種別どうし・下位が上位を抜く追い越し
#   C) 単線の検算：単線区間（交換できる駅のあいだ）に2本が同時に入っていないか、交換駅の線数を超えていないか
# 使い方（data で）: PYTHONPATH=../src python ../src/audit.py パターン.pkl [day_final.pkl]
# 環境変数: NOTEST=1（外せるかの試算をしない） EXCESS=120（待避のあと、これ以上長く止まっていたら縮められるか試す秒数）
import sys, os, pickle
from collections import Counter, defaultdict
PKF = sys.argv[1]; SRC = sys.argv[2] if len(sys.argv) > 2 else "day_final.pkl"
sys.argv = [sys.argv[0], PKF]
from morning_run import *
import net
from sched import RANK, H_DEP, H_ARR, H_PASS, SPAD, need_dep
tr = pickle.load(open(SRC, "rb"))[0]
for t in tr:
    if getattr(t, "slow", None) is None: t.slow = {}
    t.compute()
sv = [t for t in tr if t.kind != "回送"]
EXCESS = int(os.environ.get("EXCESS", "120"))
def nm(t): return f"{t.kind}{'(' + t.note + ')' if t.note in ('奥雲線', '線内') else ''} {t.o}{fmt(t.dep(t.o))}発→{t.d}"
def zone(x): return "早朝(〜7時)" if x < T(7, 0) else "朝(7〜10時)" if x < T(10, 0) else "日中(10〜16時)" if x < T(16, 0) else "夕(16〜21時)" if x < T(21, 0) else "深夜(21時〜)"
SL = net.MN[net.MN.index("犬塚"):]                       # 単線のある区間（犬塚〜奥雲温泉）の駅
def single(a, b): return net.single_sec_of(a, b) is not None
def cap_total(x): return net.TOTAL_CAP.get(x)
n0 = len(all_conf2(tr)[0])
print(f"対象 {SRC}：列車 {len(tr)} 本（営業 {len(sv)}・回送 {len(tr) - len(sv)}）。既存の判定での競合 {n0} 件")
def skov1(k):
    """k が同じ種別の列車を追い越す・追い越される（共通区間の最初と最後で順序が逆）"""
    for B in tr:
        if B is k or B.kind != k.kind or B.dir != k.dir or B.kind == "回送": continue
        com = [x for x in k.route if x in B.times]
        if len(com) < 2: continue
        a0, b0 = k.dep(com[0]), B.dep(com[0]); a1, b1 = k.arr(com[-1]), B.arr(com[-1])
        if abs(a0 - b0) <= 3600 and (a0 - b0) * (a1 - b1) < 0: return True
    return False
# 駅ごとの列車（向き別）
at = defaultdict(list)
for t in tr:
    for x in t.times: at[x].append(t)
# ---------------- A) 停車の延長
print("\n==== A) 停車の延長（通常の停車時間に足している時間）")
rows = []
for t in tr:
    for x, h in t.hold.items():
        if h <= 0 or x == t.d or x not in t.times: continue
        a, d = t.arr(x), t.dep(x)
        if x == t.o: a = d - h              # 始発駅の延長は、発車を遅らせているだけ
        ov = []; first = []; conn = []; cross = []
        for u in at[x]:
            if u is t: continue
            if u.dir == t.dir:
                if u.o == x:
                    if a <= u.dep(x) <= d and len([y for y in u.route[1:3] if y in t.times]) > 0: first.append(u)
                elif u.d == x:
                    if a - 60 <= u.arr(x) <= d: conn.append(u)
                elif a <= u.arr(x) and u.dep(x) <= d and (u.arr(x) > a or u.dep(x) < d): ov.append(u)
            elif x in SL and x != "犬塚" or (x == "犬塚" and "下岩田" in t.times and "下岩田" in u.times):
                if u.arr(x) <= d and u.dep(x) >= a: cross.append(u)
        if t.note == "奥雲線" and x == "犬塚" and h >= 600: cls = "指示"       # 本人の指示：新狛野〜犬塚の間隔をならす停車
        elif ov: cls = "待避"
        elif cross: cls = "行き違い"
        elif first: cls = "先発"
        elif conn: cls = "接続"
        else: cls = "相手なし"
        last = max([u.dep(x) for u in ov + first] + [u.arr(x) for u in cross], default=None)
        exc = (d - last - (H_PASS if ov else H_DEP if first else SPAD)) if last is not None else None      # 相手が出てから、必要な間隔を超えて止まっている秒
        rows.append(dict(t=t, x=x, h=h, a=a, d=d, cls=cls, who=ov + cross + first + conn, exc=exc))
print(f"停車の延長 {len(rows)} か所、合計 {sum(r['h'] for r in rows) // 60} 分（営業列車 {sum(1 for r in rows if r['t'].kind != '回送')} か所・回送 {sum(1 for r in rows if r['t'].kind == '回送')} か所）")
X = [r for r in rows if r["cls"] != "指示"]          # 奥雲線の各停の犬塚の停車（本人の指示の間隔ならし）を除いたもの
sec = lambda R: f"{sum(r['h'] for r in R) // 60}分{sum(r['h'] for r in R) % 60:02d}秒"
print(f"うち奥雲線の各停の犬塚の停車 {len(rows) - len(X)} か所・{sec([r for r in rows if r['cls'] == '指示'])}。これを除くと {len(X)} か所・{sec(X)}（営業列車 {sum(1 for r in X if r['t'].kind != '回送')} か所・{sec([r for r in X if r['t'].kind != '回送'])}、回送 {sum(1 for r in X if r['t'].kind == '回送')} か所・{sec([r for r in X if r['t'].kind == '回送'])}）")
print("  除いたあとの内訳：" + "、".join(f"{c} {sum(1 for r in X if r['cls'] == c)}か所・{sec([r for r in X if r['cls'] == c])}" for c in ("待避", "行き違い", "先発", "接続", "相手なし")))
print("  除いたあとの時間帯別：" + "、".join(f"{z} {sum(1 for r in X if zone(r['a']) == z)}か所・{sec([r for r in X if zone(r['a']) == z])}" for z in ("早朝(〜7時)", "朝(7〜10時)", "日中(10〜16時)", "夕(16〜21時)", "深夜(21時〜)")))
print("  除いたあとの種別別（営業列車）：" + "、".join(f"{k} {sum(1 for r in X if r['t'].kind == k)}か所・{sec([r for r in X if r['t'].kind == k])}（{len([t for t in sv if t.kind == k])}本、1本あたり {sum(r['h'] for r in X if r['t'].kind == k) // max(1, len([t for t in sv if t.kind == k]))}秒）" for k in ("各停", "急行", "快速")))
for z in ("早朝(〜7時)", "朝(7〜10時)", "日中(10〜16時)", "夕(16〜21時)", "深夜(21時〜)"):
    R = [r for r in rows if zone(r["a"]) == z]
    print(f"  {z}: " + "、".join(f"{c} {sum(1 for r in R if r['cls'] == c)}か所（{sum(r['h'] for r in R if r['cls'] == c) // 60}分）" for c in ("待避", "行き違い", "先発", "接続", "指示", "相手なし")))
def test(r, amount):
    """停車を amount 秒縮めたとき：前詰め・後ろ詰めそれぞれの（競合の増減, 同種別の追い越し, 軒屋着7〜11時が変わる）"""
    t, x = r["t"], r["x"]; h0 = dict(t.hold); d0 = t.dep0; out = {}
    for mode in ("前詰め", "後ろ詰め"):
        if mode == "後ろ詰め" and x == t.o: continue
        t.hold = dict(h0); t.hold[x] = h0[x] - amount
        if t.hold[x] <= 0 and (t.is_stop(x) or x == t.o): del t.hold[x]
        t.dep0 = d0 + (amount if mode == "後ろ詰め" else 0); t.compute()
        fix = mode == "前詰め" and t.kind != "回送" and t.d == "軒屋" and T(7, 0) <= t.arr("軒屋") + amount <= T(11, 0)
        out[mode] = (len(all_conf2(tr)[0]) - n0, skov1(t), fix)
    t.hold = h0; t.dep0 = d0; t.compute()
    return out
def verdict(res):
    ok = [m for m, (dc, sk, fix) in res.items() if dc <= 0 and not sk and not fix]
    if ok: return "外せる（" + "・".join(ok) + "）"
    why = []
    for m, (dc, sk, fix) in res.items(): why.append(m + ("：競合+" + str(dc) if dc > 0 else "：同種別の追い越し" if sk else "：朝の軒屋着が変わる" if fix else ""))
    return "外せない（" + "、".join(why) + "）"
NOTEST = os.environ.get("NOTEST") == "1"
print("\n-- A1) 相手のいない停車（その停車のあいだに、待避・行き違い・先発・接続の相手が1本もない）")
none = sorted([r for r in rows if r["cls"] == "相手なし"], key=lambda r: r["a"])
grp = defaultdict(list)
for r in none:
    if not NOTEST: r["v"] = verdict(test(r, r["h"]))
    grp[(r["t"].kind, r["t"].note, r["t"].o, r["t"].d, r["x"], r["h"], r.get("v", ""))].append(r)
for (kind, note, o, d, x, h, v), L in sorted(grp.items(), key=lambda z: (z[1][0]["a"])):
    print(f"   {kind}{'(' + note + ')' if note else ''} {o}→{d}　{x}で+{h}秒　{len(L)}本：" + " ".join(fmt(r["a"]) for r in L[:14]) + (" …" if len(L) > 14 else "") + (f"　→ {v}" if v else ""))
print(f"   計 {len(none)} か所・{sum(r['h'] for r in none) // 60} 分" + ("" if NOTEST else f"。うち外しても競合が増えないもの {sum(1 for r in none if r['v'].startswith('外せる'))} か所・{sum(r['h'] for r in none if r['v'].startswith('外せる')) // 60} 分"))
if not NOTEST:
    for z in ("早朝(〜7時)", "朝(7〜10時)", "日中(10〜16時)", "夕(16〜21時)", "深夜(21時〜)"):
        R = [r for r in none if zone(r["a"]) == z]; ok = [r for r in R if r["v"].startswith("外せる")]
        print(f"     {z}: 相手なし {len(R)}か所（{sum(r['h'] for r in R)}秒）のうち、外せる {len(ok)}か所（{sum(r['h'] for r in ok)}秒。うち60秒以上のもの {sum(1 for r in ok if r['h'] >= 60)}か所・{sum(r['h'] for r in ok if r['h'] >= 60)}秒）、外すと競合 {len(R) - len(ok)}か所（{sum(r['h'] for r in R) - sum(r['h'] for r in ok)}秒）")
print(f"\n-- A2) 相手が出たあとも {EXCESS} 秒以上長く止まっている停車（待避・行き違い・先発）")
exc = sorted([r for r in rows if r["cls"] in ("待避", "行き違い", "先発") and r["exc"] is not None and r["exc"] >= EXCESS], key=lambda r: r["a"])
grp = defaultdict(list)
for r in exc:
    cut = min(r["h"], int(r["exc"]) // 15 * 15)
    if not NOTEST: r["v"] = verdict(test(r, cut)) if cut > 0 else ""
    grp[(r["t"].kind, r["t"].note, r["t"].o, r["t"].d, r["x"], r["h"], cut, r["cls"], r.get("v", ""))].append(r)
for (kind, note, o, d, x, h, cut, cls, v), L in sorted(grp.items(), key=lambda z: (z[1][0]["a"])):
    print(f"   {kind}{'(' + note + ')' if note else ''} {o}→{d}　{x}で+{h}秒（{cls}。相手が出てから必要より {cut}秒長い）{len(L)}本：" + " ".join(fmt(r["a"]) for r in L[:12]) + (" …" if len(L) > 12 else "") + (f"　→ {cut}秒ぶん {v}" if v else ""))
print(f"   計 {len(exc)} か所" + ("" if NOTEST else f"。うち縮めても競合が増えないもの {sum(1 for r in exc if r.get('v', '').startswith('外せる'))} か所"))
W = [r for r in rows if r["cls"] == "待避"]
if W:
    for r in W: r["lead"] = min(u.arr(r["x"]) for u in r["who"] if u.dir == r["t"].dir) - r["a"]
    q = lambda L, p: sorted(L)[int((len(L) - 1) * p)]
    E = [r["exc"] for r in W]; Ld = [r["lead"] for r in W]
    print(f"   待避 {len(W)} か所：抜く列車が出てから発車までは、必要な{H_PASS}秒に対して余りが 最小{int(q(E, 0))}・中央{int(q(E, .5))}・最大{int(q(E, 1))}秒。着いてから抜く列車が来るまでは 最小{int(q(Ld, 0))}・中央{int(q(Ld, .5))}・最大{int(q(Ld, 1))}秒")
    kai = [r for r in W if r["t"].kind != "回送" and all(u.kind == "回送" for u in r["who"])]
    print(f"   うち、抜いていくのが回送だけの待避 {len(kai)} か所：" + "、".join(f"{nm(r['t'])} {r['x']}{fmt(r['a'])}（+{r['h']}秒）" for r in kai[:10]))
    LONG = int(os.environ.get("LEAD", "240"))
    print(f"\n-- A2') 待避で、着いてから抜く列車が来るまで {LONG} 秒以上ある停車（早く着きすぎ。手前を遅らせて縮められるか）")
    early = sorted([r for r in W if r["lead"] >= LONG], key=lambda r: r["a"]); grp = defaultdict(list)
    for r in early:
        cut = min(r["h"], int(r["lead"] - 90) // 15 * 15)
        if not NOTEST:
            res = test(r, cut); res.pop("前詰め", None); r["v"] = verdict(res) if res else "（始発駅）"
        grp[(r["t"].kind, r["t"].note, r["t"].o, r["t"].d, r["x"], r["h"], cut, r.get("v", ""))].append(r)
    for (kind, note, o, d, x, h, cut, v), L in sorted(grp.items(), key=lambda z: (z[1][0]["a"])):
        print(f"   {kind}{'(' + note + ')' if note else ''} {o}→{d}　{x}で+{h}秒（抜く列車の {int(L[0]['lead'])}秒前に着く）{len(L)}本：" + " ".join(fmt(r["a"]) for r in L[:12]) + (" …" if len(L) > 12 else "") + (f"　→ {cut}秒ぶん {v}" if v else ""))
    print(f"   計 {len(early)} か所" + ("" if NOTEST else f"。うち縮めても競合が増えないもの {sum(1 for r in early if r.get('v', '').startswith('外せる'))} か所"))
print("\n-- A3) 徐行（駅間で余分にかけている時間）")
sl = [(t, sum(t.slow.values())) for t in tr if sum(t.slow.values()) > 0]
print(f"   営業列車 {sum(1 for t, s in sl if t.kind != '回送')} 本・計 {sum(s for t, s in sl if t.kind != '回送') // 60} 分、回送 {sum(1 for t, s in sl if t.kind == '回送')} 本・計 {sum(s for t, s in sl if t.kind == '回送') // 60} 分")
for t, s in sorted(sl, key=lambda z: z[0].dep0):
    if t.kind != "回送": print(f"   {nm(t)}（{fmt(t.arr(t.d))}着）　徐行 計{s}秒 {dict(t.slow)}")
# ---------------- B) 追い越しの検算
print("\n==== B) 追い越しの検算")
bad = Counter(); ex = defaultdict(list); nov = 0; byst = Counter(); minm = 1e9
for x, L in at.items():
    for dr in ("D", "U"):
        S = sorted([t for t in L if t.dir == dr and x != t.d], key=lambda t: t.arr(x) if x != t.o else t.dep(x))
        for i, A in enumerate(S):
            if x == A.o: continue
            for B in S[i + 1:]:
                if B.arr(x) >= A.dep(x): break
                if x == B.o: continue
                if B.dep(x) < A.dep(x) and B.arr(x) > A.arr(x):          # B が x で A を追い越す
                    nxt = [y for y in A.route[A.route.index(x) + 1:A.route.index(x) + 2] if y in B.times]
                    if not nxt: continue                                  # x から先は別の線へ分かれる（追い越しではない）
                    nov += 1; byst[x] += 1; minm = min(minm, A.dep(x) - B.dep(x), B.arr(x) - A.arr(x))
                    if x not in net.K2 and (cap_total(x) or 1) < 2: bad["待避線のない駅での追い越し"] += 1; ex["待避線のない駅での追い越し"].append((x, A, B))
                    if not A.stopped(x): bad["止まっていない列車が抜かれる"] += 1; ex["止まっていない列車が抜かれる"].append((x, A, B))
                    if A.kind != "回送" and B.kind != "回送":
                        if A.kind == B.kind: bad["同じ種別どうしの追い越し"] += 1; ex["同じ種別どうしの追い越し"].append((x, A, B))
                        elif RANK[B.kind] < RANK[A.kind]: bad["下位の種別が上位を追い越す"] += 1; ex["下位の種別が上位を追い越す"].append((x, A, B))
print(f"駅での追い越し {nov} 回：" + "、".join(f"{x}{n}" for x, n in byst.most_common()) + f"。抜かれる列車と抜く列車の時間差のいちばん短いもの {int(minm)}秒")
flip = []
segs = defaultdict(list)
for t in tr:
    for a, b in zip(t.route, t.route[1:]): segs[(a, b)].append(t)
close = []
for (a, b), L in segs.items():
    L.sort(key=lambda t: t.dep(a))
    for i, A in enumerate(L):
        for B in L[i + 1:]:
            if B.dep(a) - A.dep(a) > 3600: break
            if B.arr(b) < A.arr(b): flip.append((a, b, A, B))
        if i + 1 < len(L):
            B = L[i + 1]; g = min(B.dep(a) - A.dep(a) - need_dep(A, B, a), B.arr(b) - A.arr(b) - H_ARR)      # 基準（続行90秒、待避のあとの発車は30秒）に対する不足
            if g < 0 and not single(a, b): close.append((a, b, A, B, g))
bad["駅間で順序が入れ替わる"] = len(flip); ex["駅間で順序が入れ替わる"] = [(a + "→" + b, A, B) for a, b, A, B in flip]
bad["続行の間隔が90秒未満（複線）"] = len(close); ex["続行の間隔が90秒未満（複線）"] = [(a + "→" + b, A, B) for a, b, A, B, g in close]
for k in ("駅間で順序が入れ替わる", "待避線のない駅での追い越し", "止まっていない列車が抜かれる", "同じ種別どうしの追い越し", "下位の種別が上位を追い越す", "続行の間隔が90秒未満（複線）"):
    print(f"   {k}：{bad[k]} 件")
    for x, A, B in ex[k][:8]: print(f"      {x}　{nm(A)}（{fmt(A.arr(x)) if x in A.times else ''}）／{nm(B)}（{fmt(B.arr(x)) if x in B.times else ''}）")
# ---------------- C) 単線の検算
print("\n==== C) 単線の検算（犬塚〜奥雲温泉）")
print("   単線区間（交換できる駅のあいだ）：" + "、".join(f"{a}〜{b}" for a, b in net.SINGLE_SEC) + "。交換できる駅の線数：" + "、".join(f"{x}{net.TOTAL_CAP[x]}" for x in SL if x in net.TOTAL_CAP))
headon = []; follow = []; ncross = Counter(); mn = 1e9
for a, b in net.SINGLE_SEC:
    L = []
    for t in tr:
        if a in t.times and b in t.times:
            i, j = t.route.index(a), t.route.index(b); e, x_ = (a, b) if i < j else (b, a)
            L.append((t.dep(e), t.arr(x_), t))
    L.sort(key=lambda z: z[0])
    for i in range(len(L)):
        for j in range(i + 1, len(L)):
            s1, e1, t1 = L[i]; s2, e2, t2 = L[j]
            if s2 > e1 + 3600: break
            if s2 < e1 and s1 < e2: (headon if t1.dir != t2.dir else follow).append((a, b, t1, t2))
            elif j == i + 1: mn = min(mn, s2 - e1)
print(f"   同じ単線区間に同時に2本：反対向き（正面）{len(headon)} 件、同じ向き（続行）{len(follow)} 件。前の列車が抜けてから次の列車が入るまでのいちばん短い時間 {int(mn)}秒（判定の基準は {SPAD}秒）")
for a, b, t1, t2 in (headon + follow)[:8]: print(f"      {a}〜{b}　{nm(t1)}／{nm(t2)}")
over = []
for x in SL:
    c = cap_total(x)
    if c is None: continue
    ev = []
    for t in at[x]:
        if x in (t.o, t.d): continue
        a, d = t.arr(x), t.dep(x)
        if not t.stopped(x): a, d = a - 5, a + 5          # 通過列車は一瞬なので、前後5秒の幅で数える
        ev += [(a, 1, t), (d, -1, t)]
    ev.sort(key=lambda z: (z[0], -z[1])); cur = []
    for tm, k, t in ev:
        if k == 1:
            cur.append(t)
            if len(cur) > c: over.append((x, tm, list(cur)))
            if len(cur) == 2 and cur[0].dir != cur[1].dir: ncross[x] += 1
        elif t in cur: cur.remove(t)
print(f"   交換駅での行き違い（同時に2本いる回数）：" + "、".join(f"{x}{n}" for x, n in ncross.items()) + f"。線数を超える在線 {len(over)} 件")
for x, tm, cur in over[:8]: print(f"      {x} {fmt(tm)}　" + "／".join(nm(t) for t in cur))
# 反対向きの2本がどこですれ違っているか（単線の駅間ですれ違っていれば不正）
where = Counter(); badx = []
Ds = [t for t in tr if t.dir == "D" and sum(1 for x in t.route if x in SL) >= 2]; Us = [t for t in tr if t.dir == "U" and sum(1 for x in t.route if x in SL) >= 2]
for A in Ds:
    ra = [x for x in A.route if x in SL]
    for B in Us:
        com = [x for x in ra if x in B.times]
        if len(com) < 2: continue
        if A.dep(com[0]) > B.arr(com[0]) or A.arr(com[-1]) < B.dep(com[-1]): continue          # 共通区間の中ではすれ違わない
        for x, y in zip(com, com[1:]):
            if A.arr(x) <= B.dep(x) and B.arr(x) <= A.dep(x): where[x + "（駅）"] += 1; break
            if A.dep(x) <= B.arr(x) and A.arr(y) >= B.dep(y):
                where[f"{x}〜{y}（{'単線' if single(x, y) else '複線'}）"] += 1
                if single(x, y): badx.append((x, y, A, B))
                break
        else:
            if A.arr(com[-1]) <= B.dep(com[-1]) and B.arr(com[-1]) <= A.dep(com[-1]): where[com[-1] + "（駅）"] += 1
print("   すれ違いの場所：" + "、".join(f"{k} {n}回" for k, n in where.most_common()) + f"。単線の駅間でのすれ違い {len(badx)} 件")
for x, y, A, B in badx[:8]: print(f"      {x}〜{y}　{nm(A)}／{nm(B)}")
# 行き違いの待ち時間（単線の駅で、通常の停車より長く止まっている時間）
w = [(r["t"], r["x"], r["h"], r["cls"]) for r in rows if r["x"] in SL and r["x"] != "犬塚"]
print(f"   単線の駅での停車の延長 {len(w)} か所・計 {sum(h for _, _, h, _ in w) // 60} 分（" + "、".join(f"{c}{n}" for c, n in Counter(c for _, _, _, c in w).items()) + "）")
