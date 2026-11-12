# 列車番号の附番：系統別の通し番号（2026-11-11 本人の指定「系統別通し番号にしてください」）
#   4桁の数字。千の位＝系統、下3桁＝その系統の1日の通し番号（始発駅の発車順）。下りは奇数、上りは偶数。
#     1000番台 快速（奥雲温泉発着）
#     2000番台 快速（そのほか。犬塚発着など）
#     3000番台 急行（蓮木線に入らないもの。犬塚発着など）
#     4000番台 急行（蓮木線に入るもの。蓮木市発着）
#     5000番台 各停（本線。高島発着を除く。秋田台・犬塚・新狛野・就島発着など）
#     6000番台 各停（高島発着）
#     7000番台 蓮木線内の各停（学院前〜蓮木市）
#     8000番台 奥雲線内の各停（新狛野〜奥雲温泉）
#     9000番台 回送
#   増発（増発車の折返しの高島行を含む）は、同じ系統の下3桁 501〜 に振る（元の列車の通し番号をずらさないため）。
#   例：1001＝下りの快速奥雲温泉行の1本目、4502＝上りの急行（蓮木市発）の増発の1本目。
#   番号は始発駅の発車時刻・種別・発着駅だけで決まる。列車の t.no に文字列で入れる。
#   はじめは「発車の時2桁＋種別・方向2桁」の規則で付けたが、本人の指定でこの規則に替えた。
#   使い方: import trainno; trainno.assign(tr)  （戻り値は、枠に入りきらない・番号が重なる列車のリスト。ふつうは空）
from collections import defaultdict
NAME = {1: "快速（奥雲温泉発着）", 2: "快速（犬塚発着ほか）", 3: "急行（犬塚発着ほか）", 4: "急行（蓮木市発着）", 5: "各停（秋田台・犬塚方面）",
        6: "各停（高島発着）", 7: "蓮木線内の各停", 8: "奥雲線内の各停", 9: "回送"}
def system_of(t):
    """系統（千の位）"""
    if t.kind == "回送": return 9
    if t.note == "線内": return 7
    if t.note == "奥雲線": return 8
    if t.kind == "快速": return 1 if "奥雲温泉" in (t.o, t.d) else 2
    if t.kind == "急行": return 4 if "蓮木市" in (t.o, t.d) else 3
    return 6 if "高島" in (t.o, t.d) else 5
def is_extra(t): return bool(getattr(t, "extra", False)) or t.note == "増発車の折返し"
def assign(tr):
    for t in tr: t.compute()
    seq = defaultdict(int); over = []; seen = {}
    for t in sorted(tr, key=lambda t: (t.dep(t.o), t.kind, t.o, t.d)):
        s = system_of(t); x = is_extra(t)
        seq[(s, x, t.dir)] += 1; n = seq[(s, x, t.dir)]
        v = (500 if x else 0) + 2 * n - (1 if t.dir == "D" else 0)
        if v > (999 if x else 499): over.append(t)
        t.no = f"{s}{v:03d}"; t.system = s
        if t.no in seen: over.append(t)
        seen[t.no] = t
    return over
