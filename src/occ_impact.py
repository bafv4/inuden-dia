# 照合用：折返し待ちの在線の数え方を、もとの数え方（ops.turn_occ_old：外で待てる編成の数に限りがない）と
# いまの数え方（ops.turn_occ：配線図の留置線・引上線・折返し線の数 ops.SIDING まで）で比べ、競合がどう変わるかを見る。
# 使い方（data で）: PYTHONPATH=../src python ../src/occ_impact.py [調べる pickle …]
#   引数なしなら、日中パターン（採用案）・base.pkl・extras.pkl・early.pkl・final.pkl を調べる
import sys, pickle, os
from collections import Counter
ARGS = sys.argv[1:]; sys.argv = [sys.argv[0], "cyc3_375_720_135_300_855_c.pkl"]
import compare_extras as CE
from morning_run import *
import ops, sched
def links_of(tr):
    links, _ = link_nl(tr)
    for t in tr:
        if getattr(t, "src", None) is not None: links[t] = t.src
    return links
def study(name, tr, win):
    for t in tr: t.compute()
    links = links_of(tr)
    o_old = ops.turn_occ_old(tr, links); o_new = ops.turn_occ(tr, links)
    old = [c for c in sched.conflicts_full(tr, o_old) + cross_conf(tr, links) if win[0] <= c[1] <= win[1]]
    new = [c for c in sched.conflicts_full(tr, o_new) + cross_conf(tr, links) if win[0] <= c[1] <= win[1]]
    # ホームに居続ける扱いになった折返し：在線の区間が長くなったもの
    longer = Counter()
    for key in o_new:
        a = {(id(t), round(e - s)) for s, e, t in o_old.get(key, [])}
        for s, e, t in o_new[key]:
            if (id(t), round(e - s)) not in a and win[0] <= s <= win[1]: longer[key[0]] += 1
    print(f"===== {name}（{fmt(win[0])}〜{fmt(win[1])}）  競合：もとの数え方 {len(old)} 件 → いまの数え方 {len(new)} 件")
    print("   留置線などに入れずホームで待つ折返し：", sorted(longer.items(), key=lambda z: -z[1]) or "なし")
    if new:
        print("   競合の内訳（駅・種類）：", sorted(Counter((c[4] if isinstance(c[4], str) else c[4][0], c[0]) for c in new).items(), key=lambda z: -z[1]))
        for c in sorted(new, key=lambda c: c[1])[:10]: print("      ", fmt(c[1]), CE.conf_text(c))
    return len(old), len(new)
if __name__ == "__main__":
    if ARGS:
        for fn in ARGS: study(fn, pickle.load(open(fn, "rb"))[0], (T(5, 0), T(11, 0)))
    else:
        study("日中パターン（採用案）", pickle.load(open("cyc3_375_720_135_300_855_c.pkl", "rb"))[0], (T(9, 30), T(13, 0)))
        for fn in ("base.pkl", "extras.pkl", "early.pkl", "final.pkl"):
            if os.path.exists(fn): study(fn, pickle.load(open(fn, "rb"))[0], (T(5, 0), T(11, 0)))
