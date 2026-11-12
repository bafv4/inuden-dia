# 検算：変わった所だけ判定し直す競合判定（sched.conflicts）が、毎回すべて作り直す元の判定（sched.conflicts_full）と
# 同じ競合リストを返すことを、日中パターンを1通り解きながら毎回突き合わせて確かめる。
# 使い方（src で）: BR=375,660,2370,3570 python check_fast.py 0 360 690 0 150 720
# sched.py / ops.py の規則を変えたら、conflicts_full と _Inc 側の両方を直してからこれを通すこと。
import sys
import sched, ops, grid2
n = {"calls": 0}
def both(trains, extra_occ=None):
    a = sched.conflicts(trains, extra_occ); b = sched.conflicts_full(trains, extra_occ)
    n["calls"] += 1
    if a != b: raise SystemExit(f"{n['calls']} 回目の判定で食い違い: 高速版 {len(a)} 件 / 元の判定 {len(b)} 件")
    return a
ops.conflicts = both          # ops.all_conf が呼ぶ判定を差し替える
if __name__ == "__main__":
    v = [int(x) for x in sys.argv[1:7]] if len(sys.argv) > 6 else [0, 360, 690, 0, 150, 720]
    r = grid2.solve_pattern(v[:3], v[3:6])
    print("解けた" if r else "解けない", f"／判定 {n['calls']} 回すべて一致")
