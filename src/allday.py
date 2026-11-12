# 終日に広げる（その1）：採用した朝ダイヤ（extras.pkl。11:30 ごろまで）のあとへ、日中パターンの列車を終電の時間帯まで足す → day_in.pkl
# 朝の列車は1本も変えない。足すのは、朝の基本ダイヤ（base.pkl）に入っていない、あとの時間帯のパターンの列車だけ。
# このあと early.py（早朝・深夜の間引き、奥雲線、送り込み）→ finalize.py（回送・運用・両数）の順に通す。
# 使い方（data で）: PYTHONPATH=../src python ../src/allday.py パターン.pkl [朝 extras.pkl] [出力 day_in.pkl]
# 環境変数: DAY_END="25:30"（パターンを当てはめる終わり。終電の切り方は early.py が決める）
import sys, os, pickle
PKF = sys.argv[1]; SRC = sys.argv[2] if len(sys.argv) > 2 else "extras.pkl"; OUT = sys.argv[3] if len(sys.argv) > 3 else "day_in.pkl"
sys.argv = [sys.argv[0], PKF]
from morning_run import *
h, m = os.environ.get("DAY_END", "25:30").split(":"); DAY_END = T(int(h), int(m))
def base_until(t_to):
    """morning_run.build_base と同じ作り方で、t_to までのパターンの列車を作る"""
    cyc.UP_OFF = UP_OFF; build.UP_OFF = UP_OFF; build.cnt.clear()
    tr = pattern(DOWN_OFF, UP_OFF, S, T(3, 30), t_to)
    tr = [t for t in tr if not (t.dir == "D" and (t.compute() or True) and t.dep(t.o) < FIRST_D)]
    tr = truncate(tr)
    for t in tr: t.frozen = (getattr(t, "note", "") != "始発繰り上げ"); t.compute()
    br = add_branch(tr)
    for b in br:
        b.anchor = b.dep0; s = S.get(cyc.slot_of(b))
        if s: b.dep0 = b.anchor + s["shift"]; b.hold = dict(s["hold"]); b.frozen = True
        else: b.frozen = False
        b.compute()
    br = [b for b in br if b.dep(b.o) >= FIRST]
    return tr + br
key = lambda t: (t.dir, t.kind, t.o, t.d, round(t.dep0), tuple(sorted(t.hold.items())))
if __name__ == "__main__":
    morning = pickle.load(open(SRC, "rb")); mt = morning[0]
    for t in mt:
        if getattr(t, "slow", None) is None: t.slow = {}
        t.compute()
    base = pickle.load(open("base.pkl", "rb"))[0]
    for t in base: t.compute()
    allb = base_until(DAY_END)
    K = {key(t) for t in base}; KA = {key(t) for t in allb}
    miss = [t for t in base if key(t) not in KA]
    print(f"朝の基本ダイヤ {len(base)} 本のうち、終日のパターンに同じ列車がないもの {len(miss)} 本", [(t.kind, t.o, t.d, fmt(t.dep(t.o)), t.note) for t in miss][:8])
    last = max(t.dep(t.o) for t in base)
    new = [t for t in allb if key(t) not in K]
    early = [t for t in new if t.dep(t.o) <= last - 3600]
    print(f"足す列車 {len(new)} 本（始発駅の発車 {fmt(min(t.dep(t.o) for t in new))}〜{fmt(max(t.dep(t.o) for t in new))}）。うち朝の時間帯（{fmt(last - 3600)} より前）に出るもの {len(early)} 本", [(t.kind, t.o, t.d, fmt(t.dep(t.o)), t.note) for t in early][:8])
    tr = mt + new
    cs, _ = all_conf2(tr)
    print("つないだあと：列車", len(tr), "競合", len(cs))
    for c in cs[:10]: print("   ", c[0], fmt(c[1]), [(x.kind, x.o, x.d, fmt(x.dep(x.o))) for x in involved(c)][:3], c[4])
    pickle.dump((tr, [], [t for t in tr if getattr(t, "extra", False)]), open(OUT, "wb")); print("保存", OUT)
