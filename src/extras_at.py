# 増発を、狙った軒屋着の時刻に入れる（extras.py の自動配置の代わりに、位置を指定して入れ直すとき用）。
# 使い方（data で。base.pkl を読む）:
#   PYTHONPATH=../src python ../src/extras_at.py パターン.pkl 出力.pkl "急行,犬塚,7:46" "各停,高島,8:07-8:07:45" …
#   引数は「種別,始発駅,軒屋着」。書いた順に入れる。軒屋着は「8:07」か幅「8:10-8:14」で、幅のときは途中の待ちが
#   いちばん少なく、次に軒屋着の間隔がそろう位置を選ぶ。日中パターンの列車は動かさない。入らなければ保存しない。
#   先に入れた増発が後の増発の入り方を変える（同じ15分に2本目の各停を入れると、2本目は途中で待つ）ので、順番に注意。
import sys, pickle
PK, OUT, SPEC = sys.argv[1], sys.argv[2], sys.argv[3:]
sys.argv = ["x", PK]
import extras as E
from extras import *
def hm(s): a = s.split(":"); return T(int(a[0]), int(a[1]), int(a[2]) if len(a) > 2 else 0)
tr, _ = pickle.load(open("base.pkl", "rb"))
for t in tr: t.compute()
base_key = sorted((t.dir, t.kind, t.o, t.d, t.dep0, tuple(sorted(t.hold.items()))) for t in tr)
placed = []
SW = (T(7, 30), T(9, 0))
def spacing(arrs):
    a = sorted(x for x in arrs if SW[0] <= x <= SW[1])
    return sum((b - c - 180) ** 2 for c, b in zip(a, a[1:])) / 100
for spec in SPEC:           # 書いた順に入れる。時刻は「8:07」か、幅「8:04-8:07:45」（幅なら間隔がそろう位置を選ぶ）
    kind, o, target = spec.split(",")
    lo, hi = (hm(target.split("-")[0]), hm(target.split("-")[1])) if "-" in target else (hm(target), hm(target))
    core = sorted(t.dep("新犬村") for t in tr if t.dir == "U" and "新犬村" in t.times)
    arr0 = [t.arr("軒屋") for t in tr if t.d == "軒屋"]
    best = None
    for tt in range(lo - 1500, hi - 300, 15):
        if min(abs(tt - c) for c in core) < 90: continue
        ok, cost, x = E.try_insert(tr, kind, o, tt, [])
        if not ok or cost != sum(x.hold.values()): continue
        x.compute(); ar = x.arr("軒屋")
        if not (lo <= ar <= hi): continue
        key = (cost, spacing(arr0 + [ar]))
        if best is None or key < best[0]: best = (key, tt)
    if best is None: sys.exit(f"入らない: {spec}")
    x = mk_up(kind, o, "軒屋", best[1]); x.frozen = False; x.nolink = True; x.extra = True
    x.label = kind + "（増発）"; x.cars = 8 if kind == "急行" else 6
    tr.append(x); left = solve(tr, [], only=[x]); x.compute(); x.frozen = True; placed.append(x)
    if left: sys.exit(f"競合が残る: {spec}")
    print(f"   {kind} {o} {fmt(x.dep(o))}発 → 軒屋 {fmt(x.arr('軒屋'))}着  {dict(x.hold)}", flush=True)
cs, _ = all_conf2(tr)
ke = sorted((t.dir, t.kind, t.o, t.d, t.dep0, tuple(sorted(t.hold.items()))) for t in tr if not getattr(t, "extra", False))
print("列車", len(tr), "競合", len(cs), "日中パターンは不変", ke == base_key, "増発の待ち合計", sum(sum(x.hold.values()) for x in placed))
if cs or ke != base_key: sys.exit("保存しません")
pickle.dump((tr, [], placed), open(OUT, "wb"))
