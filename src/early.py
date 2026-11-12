# 朝の始発まわりの調整（2026-11-11 本人の指示）。増発を入れ終えたダイヤ（extras.pkl）に次の3つを当てて、別ファイル（early.pkl）へ書く。
#   1) 早朝の間引き：軒屋の発着時刻（下りは軒屋発、上りは軒屋着）で区切り、5時台は半分・6時台は段階的に増やす
#      （蓮木線内の各停だけは、上り・下りとも学院前の時刻で区切る。上下の本数をそろえて、学院前に編成がたまらないようにするため）
#        〜6:00       各停は秋田台発着だけ・急行は蓮木市発着だけ・快速は30分ごと（奥雲温泉発着と、その30分後の犬塚発着）・蓮木線内各停は30分ごと → 毎時6本
#        6:00〜6:30   各停の高島発着と、蓮木線内各停を戻す → 毎時8本
#        6:30〜7:00   快速を全部戻す → 毎時10本
#        7:00〜       急行の犬塚発着を戻す → 日中どおり毎時12本
#   2) 奥雲線の各停は新狛野〜奥雲温泉の往復。下りの奥雲温泉行きは毎時の枠どおり5時台・6時台にも走らせる。犬塚で長めに止めて、
#      新狛野〜犬塚の列車間隔をならす。4両までなので専用の編成でまわす（以下の2行は犬塚折返しにしていたときの説明で、今は使っていない）
#      奥雲線の各停は4両までなので専用の編成でまわす。始発から FEED_OKU 本目までは新狛野発にして編成を送り込む
#      （本人の指示は「2本目くらいまで」。専用の編成は2本で足り、1本は奥雲温泉で夜を越すので、既定は1本。2本にすると編成が1本余る）
#   2') 朝の増発のうち犬塚発の急行は新狛野発にする（本人の指示「朝の増発は新狛野発」。新狛野から先の時刻は変えない。XORIGIN=0 でやめる）
#   3) 奥雲温泉・犬塚で夜を越す編成が置ける数（morning.CAP_STABLE）を超えるぶんは、新狛野から回送で送り込む
#      （奥雲温泉を先に決める。新狛野が置ける数いっぱいになったら、犬塚の残りは就島から送る）
#   4) 蓮木市で置ける数を超えるぶんは、学院前の留置線から回送で、それでも足りなければ就島車庫から学院前で折り返す回送で送り込む
#      （置ける数は環境変数 CAP="蓮木市:5" のようにして試せる。決まったら morning.CAP_STABLE を書き換える）
# 列車を消す・短くする・回送を足すだけで、残した列車の時刻は動かさない。競合は既存の判定（all_conf2）で数える。
# 使い方（data で）: PYTHONPATH=../src python ../src/early.py パターン.pkl [入力 extras.pkl] [出力 early.pkl]
# 環境変数: HOLD_U_UNTIL=20:00（奥雲線の上りで、犬塚にこの時刻以降に着く列車は犬塚ですぐ発車する） LEADMIN=240（早朝・夜の待避で、抜く列車よりこの秒数以上早く着いていたら先の駅へ移す。0 でやめる） LONELY=60（早朝・夜の、相手のいない停車の延長を外す下限の秒数。0 でやめる） AKI_CONN=120（朝いちばんの犬塚発の各停が、秋田台で快速の何秒前に着くか。0 でやめる） OKU_FIRST_ADV=480（奥雲温泉発の一本目を早める秒数。既定 480） FIRST_SHIFT=1800（始発を遅らせる秒数。既定 1800。FIRST_SHIFT=0 OKU_FIRST_ADV=0 で始発を遅らせる前の版になる。そのときは出力を別名にすること） HOLD_U_SKIP=1（奥雲線の上りで犬塚ですぐ発車する本数） LV="6:00,6:30,7:00"（段階の区切り） FEED_OKU=1（新狛野発にする奥雲温泉行きの本数） NOTHIN=1（間引かない） NOFEED=1（犬塚への回送を作らない）
import pickle, sys, os
PKF = sys.argv[1]; SRC = sys.argv[2] if len(sys.argv) > 2 else "extras.pkl"; OUT = sys.argv[3] if len(sys.argv) > 3 else "early.pkl"
sys.argv = [sys.argv[0], PKF]
from morning_run import *
from morning import CAP_STABLE
from ops import minturn
from sched import H_PASS
def hm(s): h, m = s.split(":"); return T(int(h), int(m))
LV = tuple(hm(x) for x in os.environ.get("LV", "6:00,6:30,7:00").split(","))
FEED_OKU = int(os.environ.get("FEED_OKU", "1"))
# 蓮木線内の各停は、上り・下りとも学院前の時刻でそのまま段階を決める（OFF=0）。はじめは軒屋の時刻に直して（下りは16分引き、上りは16分足して）
# 区切っていたが、学院前で見ると上りと下りの区切りが32分ずれ、上りだけ多く走って学院前に編成が2本たまった（折返し待ちが12分→42分、
# 蓮木線内の編成が4本→6本）。2026-11-11 に本人の了承を得て上下をそろえた
OFF = 0
tr, _, placed = pickle.load(open(SRC, "rb"))
for t in tr:
    if getattr(t, "slow", None) is None: t.slow = {}
    t.compute()
log = []
def say(*a):
    s = " ".join(str(x) for x in a); print(s); log.append(s)
def is_x(t): return bool(getattr(t, "extra", False))
def ref(t):
    """段階を決める時刻（軒屋の発着に直したもの）。奥雲線の各停は間引かない"""
    if t.note == "線内": return t.dep("学院前") - OFF if t.dir == "D" else t.arr("学院前") + OFF
    if t.note == "奥雲線" or "軒屋" not in t.times: return None
    return t.dep("軒屋") if t.dir == "D" else t.arr("軒屋")
def lvl(x): return 1 + sum(x >= b for b in LV)
# 秋田台より先（院庄・三宅・戌居・北川津・星野）は急行しか止まらないので、急行の犬塚発着を休む早朝・深夜は列車がなくなる。その手当て（FAR）：
#   FAR=ext  … その時間帯の各停の秋田台発着を、犬塚まで延ばす（軒屋〜秋田台の時刻は変えない）
#   FAR=ext3 … 既定。ext2 の就島始発・就島終着の各停のうち、既存の各停（軒屋〜秋田台）と秋田台で近い時刻に並ぶものは、別の列車にせず
#              その各停とつなげる（＝その各停を犬塚まで延ばす）。延ばせなかったときは、その各停の始発・終着の駅（秋田台）までの列車にする
#              （本人の指示「既存の各停と接近するところは既存の各停と繋げるか、その各停の始発駅どまりとしたい」）。
#              近くに各停のない時刻（朝いちばんの下り、夜の最後の上り）だけが就島始発・就島終着で残る
#   FAR=ext2 … 朝の上りと夜の下りは ext と同じく延長。朝の下りと夜の上りは延長せず、就島始発（就島→犬塚）・就島終着（犬塚→就島）の
#              各停を走らせる（本人の指示「朝の下り、夜の上りについては就島始発終着の各駅停車を走らせたい」。車庫のある就島から出て、就島へ戻る）
#   FAR=exp  … 急行の犬塚発着を、早朝・深夜も休まずに走らせる（毎時2本）
#   FAR=exp1 … 急行の犬塚発着を、早朝・深夜は1時間に1本だけ走らせる
FAR = os.environ.get("FAR", "ext3")      # 2026-11-11 に本人が決めた形（上の ext3）。FAR=none で手当てなし
def far_exp(t, x):
    if FAR == "exp": return True
    if FAR == "exp1":            # 1時間に1本：下りは軒屋発が毎時30分台、上りは軒屋着が毎時30分より前のもの
        return (x % 3600 >= 1800) if t.dir == "D" else (x % 3600 < 1800)
    return False
def near(x, res): return any(min((x - r) % 1800, (r - x) % 1800) <= 60 for r in res)
def count(tr, label):
    """軒屋の1時間ごとの本数（下りは発、上りは着）"""
    for d, nm in (("D", "下り 軒屋発"), ("U", "上り 軒屋着")):
        row = []
        for h in (5, 6, 7):
            L = [t for t in tr if t.dir == d and "軒屋" in t.times and t.kind != "回送" and T(h, 0) <= (t.dep("軒屋") if d == "D" else t.arr("軒屋")) < T(h + 1, 0)]
            row.append(f"{h}時台 {len(L)}本（" + "・".join(f"{k}{sum(1 for t in L if t.kind == k)}" for k in ("各停", "急行", "快速")) + "）")
        say("  ", label, nm, " ".join(row))
# ---- 0) 始発を遅らせる（FIRST_SHIFT 秒。既定 1800 ＝ 30分。採用済み。0 にすると元の始発。2026-11-11 本人の依頼「朝の始発を1サイクルだけ遅らせたバージョンも」→ 全線の始発を30分）
#   始発の決め方（morning_run.build_base・morning.truncate）を、区切りを FIRST_SHIFT だけ遅らせて当て直す：
#     本線の下り … 始発駅の発車が 5:00＋FIRST_SHIFT より前の列車はやめる
#     本線の上り … 始発駅の発車が 4:50＋FIRST_SHIFT より前の列車は、それ以降に発車する駅（犬塚・新狛野・秋田台・高島・就島・新犬村）からに縮める。なければやめる
#     蓮木線内・奥雲線の各停 … 始発駅の発車が 4:50＋FIRST_SHIFT より前の列車はやめる
#   増発・変更済みの列車・回送には触らない。残した列車の時刻は変えない
SHIFT = int(os.environ.get("FIRST_SHIFT", "1800"))      # 既定 1800：2026-11-11 に本人が「30分遅れの版を採用する」と決めた。0 で元の始発（軒屋 5:00発から）
tr0 = list(tr)          # 間引きで「どの組を残すか」を決める基準（下の RES_*）は、始発を縮める前の列車から取る（縮めると始発駅が変わって基準から外れるため）
if SHIFT:
    import morning as _mo
    F_D = FIRST_D + SHIFT; F = _mo.FIRST + SHIFT; out = []; dropped = []; cutl = []
    for t in tr:
        if is_x(t) or getattr(t, "adjusted", None) or t.kind == "回送": out.append(t); continue
        lim = F if (t.note in ("線内", "奥雲線") or t.dir == "U") else F_D
        if t.dep(t.o) >= lim: out.append(t); continue
        if t.dir == "D" or t.note in ("線内", "奥雲線"): dropped.append(t); continue
        got = None
        for x in [x for x in ("犬塚", "新狛野", "秋田台", "高島", "就島", "新犬村") if x in t.route and t.route.index(x) > 0]:
            if t.dep(x) >= F and t.stopped(x):
                n = Train(t.id, t.kind, x, t.d, t.dep(x), cars=t.cars, label=t.label, note="始発繰り上げ")
                n.hold = {k: v for k, v in t.hold.items() if k in n.route and k != x}; n.slow = {k: v for k, v in getattr(t, "slow", {}).items() if k in n.route[1:]}
                n.frozen = True; n.compute()
                if all(abs(n.arr(y) - t.arr(y)) < 1 for y in n.route[1:]): got = n
                break
        if got: out.append(got); cutl.append((t, got))
        else: dropped.append(t)
    tr = out
    say(f"始発を {SHIFT // 60}分遅らせる：やめた列車 {len(dropped)} 本、途中の駅からに縮めた列車 {len(cutl)} 本")
    for t in sorted(dropped, key=lambda t: t.dep(t.o)): say(f"   やめる：{t.kind} {t.o}{fmt(t.dep(t.o))}発 {t.d}行" + (f"（{t.note}）" if t.note else ""))
    for t, n in cutl: say(f"   縮める：{t.kind} {t.o}{fmt(t.dep(t.o))}発 {t.d}行 → {n.o}{fmt(n.dep(n.o))}発")
# ---- 1) 早朝の間引き
if os.environ.get("NOTHIN") != "1":
    early = [t for t in tr0 if ref(t) is not None and ref(t) < LV[-1] and not is_x(t)]
    RES_A = {t.arr("軒屋") % 1800 for t in early if t.dir == "U" and t.kind == "各停" and t.o == "秋田台"}        # 上りの各停 秋田台発の軒屋着
    RES_H = {t.arr("軒屋") % 1800 for t in early if t.dir == "U" and t.kind == "急行" and t.o == "蓮木市"}        # 上りの急行 蓮木市発の軒屋着
    RES_K = {"D": {t.dep("軒屋") % 1800 for t in early if t.dir == "D" and t.kind == "快速" and t.d == "奥雲温泉"},
             "U": {t.arr("軒屋") % 1800 for t in early if t.dir == "U" and t.kind == "快速" and t.o == "奥雲温泉"}}
    # 蓮木線内の各停を30分ごとにするとき、どちらの組を残すか：急行（蓮木市発着）と学院前でなるべく離れるほう
    RES_S = {}
    for d in ("D", "U"):
        at = (lambda t: t.dep("学院前")) if d == "D" else (lambda t: t.arr("学院前"))
        ex = [at(t) % 1800 for t in early if t.dir == d and t.kind == "急行" and "蓮木市" in (t.o, t.d)]
        cand = sorted({ref(t) % 1800 for t in early if t.dir == d and t.note == "線内"})
        gap = lambda r: min([min((r + (OFF if d == "D" else -OFF) - e) % 1800, (e - r - (OFF if d == "D" else -OFF)) % 1800) for e in ex] or [0])
        RES_S[d] = {max(cand, key=gap)} if cand else set()
    def keep(t):
        if is_x(t) or getattr(t, "adjusted", None) or t.kind == "回送": return True
        x = ref(t)
        if x is None or lvl(x) == len(LV) + 1: return True
        L = lvl(x)
        if t.note == "線内": return L >= 2 or near(x, RES_S[t.dir])
        if t.kind == "各停":           # 5時台は秋田台発着だけ
            aki = t.d == "秋田台" if t.dir == "D" else (t.o == "秋田台" or (t.o != "高島" and near(x, RES_A)))
            return L >= 2 or aki
        if t.kind == "快速": return L >= 3 or near(x, RES_K[t.dir])
        if t.kind == "急行":           # 犬塚発着は7時から（FAR=exp・exp1 のときは残す）
            if t.d == "蓮木市" if t.dir == "D" else (t.o == "蓮木市" or (t.o != "犬塚" and near(x, RES_H))): return True
            return far_exp(t, x)
        return True
    say("早朝の間引き：区切り", " / ".join(fmt(b) for b in LV)); count(tr, "前")
    cut = [t for t in tr if not keep(t)]; tr = [t for t in tr if keep(t)]
    count(tr, "後"); say(f"   やめた列車 {len(cut)} 本：" + "、".join(f"{k} {sum(1 for t in cut if t.kind == k and t.note != '線内')}" for k in ("各停", "急行", "快速")) + f"、蓮木線内の各停 {sum(1 for t in cut if t.note == '線内')}")
# ---- 1') 深夜の間引きと終電（終日のダイヤ day_in.pkl を通すときだけ働く。2026-11-11 に本人が決めた形）
#   間引きは早朝の逆。軒屋の発着（下りは軒屋発、上りは軒屋着。蓮木線内の各停は学院前の時刻）で区切る：
#     21:00〜 急行の犬塚発着を休む（毎時10本） → 21:30〜 快速を30分ごとに（8本） → 22:00〜 各停の高島発着を休み、蓮木線内の各停を30分ごとに（6本）
#   終電：軒屋発の下り・軒屋着の上りとも 0:30 まで。着くのが 1:05 を過ぎる下りは、それまでに着ける車両を置ける駅（犬塚・新狛野・秋田台・高島・就島）止まりにする
NV = tuple(hm(x) for x in os.environ.get("NV", "21:00,21:30,22:00").split(","))
END = hm(os.environ.get("END", "24:30")); ARR_END = hm(os.environ.get("ARR_END", "25:05"))
if os.environ.get("NONIGHT") != "1" and os.environ.get("NOTHIN") != "1" and any(t.dep(t.o) > T(20, 0) for t in tr):
    def nkeep(t):
        if is_x(t) or getattr(t, "adjusted", None) or t.kind == "回送": return True
        if t.note == "奥雲線": return t.arr(t.d) <= hm("24:45")
        x = ref(t)
        if x is None or x < NV[0]: return True
        if x > END: return False
        L = sum(x >= b for b in NV)
        if t.note == "線内": return L < 3 or near(x, RES_S[t.dir])
        if t.kind == "急行": return ((t.d == "蓮木市") if t.dir == "D" else (t.o == "蓮木市")) or far_exp(t, x)
        if t.kind == "快速": return L < 2 or near(x, RES_K[t.dir])
        if t.kind == "各停": return L < 3 or ((t.d == "秋田台") if t.dir == "D" else (t.o == "秋田台"))
        return True
    cut = [t for t in tr if not nkeep(t)]; tr = [t for t in tr if nkeep(t)]
    say(f"深夜の間引きと終電：区切り {' / '.join(fmt(b) for b in NV)}、終電 {fmt(END)}。やめた列車 {len(cut)} 本（うち終電より後 {sum(1 for t in cut if t.note != '奥雲線' and ref(t) is not None and ref(t) > END)} 本）")
    for d, nm in (("D", "下り 軒屋発"), ("U", "上り 軒屋着")):
        f = (lambda t: t.dep("軒屋")) if d == "D" else (lambda t: t.arr("軒屋"))
        say("   " + nm + " " + " ".join(f"{h % 24}時台{sum(1 for t in tr if t.dir == d and t.kind != '回送' and '軒屋' in t.times and T(h, 0) <= f(t) < T(h + 1, 0))}本" for h in (20, 21, 22, 23, 24)))
    for t in [t for t in tr if t.dir == "D" and t.o == "軒屋" and t.kind != "回送" and t.arr(t.d) > ARR_END]:
        cand = [x for x in t.route if x in ("就島", "高島", "秋田台", "新狛野", "犬塚") and t.is_stop(x) and t.arr(x) <= ARR_END]
        if not cand: tr.remove(t); say(f"   終電：{t.kind} 軒屋{fmt(t.dep('軒屋'))}発 {t.d}行は、{fmt(ARR_END)} までに着ける止まり先がないのでやめる"); continue
        n = Train("", t.kind, t.o, cand[-1], t.dep0, cars=t.cars, label=t.label, note=t.note); n.id = t.id
        n.hold = {k: v for k, v in t.hold.items() if k in n.route and k != n.d}; n.frozen = True; n.compute()
        tr[tr.index(t)] = n
        say(f"   終電：{t.kind} 軒屋{fmt(t.dep('軒屋'))}発 {t.d}行（{fmt(t.arr(t.d))}着）→ {n.d}止まり（{fmt(n.arr(n.d))}着）")
# ---- 2) 奥雲線の各停：新狛野〜奥雲温泉の往復（2026-11-11 の本人の指示。いったん犬塚折返しにしたが、新狛野発着に戻した）。
#         下りは毎時の枠どおり5時台・6時台にも走らせる。4両までなので専用の編成でまわす（犬塚での停車時間と折返しのつなぎは 2'' で決める）
oku = sorted([t for t in tr if t.note == "奥雲線"], key=lambda t: t.dep(t.o))
down = [t for t in oku if t.dir == "D"]; up = [t for t in oku if t.dir == "U"]
if down and up:
    first = down[0]; have = {round(t.dep("犬塚")) for t in down}; k = 1
    while first.dep("犬塚") - 3600 * k >= up[0].arr("犬塚"):      # 上りの始発が犬塚に着くより前には出さない（単線の行き違いは毎時同じ形）
        if round(first.dep("犬塚") - 3600 * k) not in have:
            n = Train("", first.kind, first.o, first.d, first.dep0 - 3600 * k, cars=first.cars, label=first.label, note=first.note); n.id = first.id
            n.hold = dict(first.hold); n.frozen = True; n.compute(); tr.append(n)
        k += 1
# ---- 2') 犬塚発の増発を新狛野発に（車庫のある新狛野から直接出す。犬塚〜新狛野は走らない）
if os.environ.get("XORIGIN") != "0":
    for t in [t for t in tr if is_x(t) and t.o == "犬塚" and "新狛野" in t.route]:
        n = Train("", t.kind, "新狛野", t.d, t.dep("新狛野"), cars=t.cars, label=t.label, note=t.note); n.id = t.id
        n.hold = {k: v for k, v in t.hold.items() if k in n.route and k != "新狛野"}; n.slow = {k: v for k, v in t.slow.items() if k in n.route[1:]}
        n.extra = True; n.nolink = True; n.frozen = True; n.was = (t.o, t.dep(t.o)); n.compute()
        assert all(abs(n.arr(x) - t.arr(x)) < 1 for x in n.route[1:]), "新狛野から先の時刻が変わった"
        tr[tr.index(t)] = n
        say(f"増発 {t.kind} 犬塚{fmt(t.dep('犬塚'))}発 → 新狛野{fmt(n.dep('新狛野'))}発に変更（軒屋{fmt(n.arr('軒屋'))}着は同じ）")
# ---- 2'') 奥雲線の各停の犬塚での停車時間：新狛野〜犬塚で前後の列車との間隔がなるべく均等になる長さを、上り・下りそれぞれ選ぶ
#          （犬塚〜奥雲温泉の時刻は単線の行き違いで決まっているので動かさない。下りは新狛野の発車を早め、上りは新狛野の到着を遅らせる）
#          環境変数 HOLD_D・HOLD_U（秒）で指定もできる。HOLDMAX（既定 900）より長くは止めない
#          上りの朝いちばんの HOLD_U_SKIP 本（既定 1 ＝ 奥雲温泉 4:52'45発）は、犬塚で長く止めずにすぐ発車する
#          （2026-11-11 本人の指示「奥雲温泉始発の朝の各停は途中犬塚ですぐ発車するように」「一本目の話」）
def oku_hold(tr, d):
    sh = [t for t in tr if t.note == "奥雲線" and t.dir == d]; base = [(t.dep0, dict(t.hold)) for t in sh]
    skip = {id(t) for t in sorted(sh, key=lambda t: t.dep0)[:int(os.environ.get("HOLD_U_SKIP", "1"))]} if d == "U" else set()
    # 夜の上り（犬塚に HOLD_U_UNTIL 以降に着くもの。既定 20:00 ＝ 奥雲温泉 19:52'45発から）も、犬塚で長く止めずにすぐ発車する
    # （2026-11-11 本人の指示「夜はすぐ発車」。夜は急行がなく、止めると犬塚まで延ばした各停の約2分後を並んで走ることになり、
    #   最終列車は待つ相手もいなかった。18:52'45発より前は、すぐ発車すると急行の2分前になるので止めたまま）
    if d == "U":
        for t in sh: t.compute()
        skip |= {id(t) for t in sh if t.arr("犬塚") >= hm(os.environ.get("HOLD_U_UNTIL", "20:00"))}
    oth = [t for t in tr if t.dir == d and t.note != "奥雲線" and t.kind != "回送" and "新狛野" in t.times and "犬塚" in t.times]
    at = (lambda t, x: t.dep(x) if x == "新狛野" else t.arr(x)) if d == "D" else (lambda t, x: t.arr(x) if x == "新狛野" else t.dep(x))
    def put(h):
        for t, (d0, h0) in zip(sh, base):
            t.hold = dict(h0)
            if h and id(t) not in skip: t.hold["犬塚"] = t.hold.get("犬塚", 0) + h
            t.dep0 = d0 - (h if d == "D" else 0); t.compute()
    def gap():          # 9〜11時の奥雲線の各停について、新狛野と犬塚での前後の列車との間隔のうち、いちばん短いもの
        g = [abs(at(t, x) - at(o, x)) for t in sh if T(9, 0) <= t.dep(t.o) < T(11, 0) for x in ("新狛野", "犬塚") for o in oth]
        return min(g) if g else 0
    # 上りは 780秒（犬塚で13分45秒停車）に決めてある：いちばん均等になるのは870秒（15分15秒・最短間隔6分）だが、本人が「もっと短く」と選んだ（2026-11-11）。
    # HOLD_U=auto で選び直す
    n0 = len(all_conf2(tr)[0]); fix = os.environ.get("HOLD_" + d, "780" if d == "U" else ""); rows = []
    if fix in ("", "auto"): fix = None
    for h in ([int(fix)] if fix else range(0, int(os.environ.get("HOLDMAX", "900")) + 1, 15)):
        put(h); n = len(all_conf2(tr)[0])
        if n <= n0 or fix: rows.append((gap(), -h))
    best = max(rows) if rows else (0, 0); put(-best[1])
    say(f"奥雲線の各停（{'下り' if d == 'D' else '上り'}）：犬塚での停車を {(-best[1] + 45) // 60}分{(-best[1] + 45) % 60:02d}秒に（通常45秒＋{-best[1]}秒）。前後の列車とのいちばん短い間隔 {fmt(rows[0][0]) if rows and rows[0][1] == 0 else '-'} → {fmt(best[0])}"
        + "／試した長さ: " + " ".join(f"+{-h}秒={g // 60}分{g % 60:02d}秒" for g, h in rows if -h % 120 == 0))
sh = [t for t in tr if t.note == "奥雲線"]
if sh:
    for t in sh: t.nolink = True; t.src = None
    oku_hold(tr, "D"); oku_hold(tr, "U")
    # 上りの一本目（奥雲温泉発の始発）を OKU_FIRST_ADV 秒だけ早める（既定 480 ＝ 8分。本人が「8分でよい」と決めた。0 で早めない。始発を30分遅らせる前の版では使っていなかった。
    # 2026-11-11 本人の指示「奥雲温泉の始発列車の時刻を数分繰り上げ」「30分遅らせた案の話」）。
    # 8分早めると犬塚で快速（候補では犬塚 6:11'15発）に2分15秒で乗り継げる。7分だと1分15秒、11分なら犬塚で待たずに先行できる（乗り継ぎ5分15秒）。
    # 犬塚では、快速を先に出すのに要るぶんだけ止める（競合が増えないいちばん短い停車を選ぶ）。入らなければ元の時刻のまま
    ADV = int(os.environ.get("OKU_FIRST_ADV", "480")); ups = sorted([t for t in sh if t.dir == "U"], key=lambda t: t.dep0)
    if ADV and ups:
        f = ups[0]; d0, h0 = f.dep0, dict(f.hold); n0 = len(all_conf2(tr)[0]); ok = False
        for h in range(0, 601, 15):
            f.dep0 = d0 - ADV; f.hold = dict(h0)
            if h: f.hold["犬塚"] = f.hold.get("犬塚", 0) + h
            f.compute()
            if len(all_conf2(tr)[0]) <= n0: ok = True; break
        if ok: say(f"奥雲線の各停（上りの一本目）：奥雲温泉 {fmt(d0)}発 → {fmt(f.dep0)}発に繰り上げ（犬塚 {fmt(f.arr('犬塚'))}着／{fmt(f.dep('犬塚'))}発、新狛野 {fmt(f.arr('新狛野'))}着）")
        else: f.dep0, f.hold = d0, h0; f.compute(); say(f"奥雲線の各停（上りの一本目）：{ADV}秒の繰り上げは入らないので、元の時刻のまま")
    # 専用の編成でまわす：新狛野・奥雲温泉での折返しを奥雲線の各停どうしで着いた順につなぐ。相手のない発車は夜を越した編成
    for X in ("新狛野", "奥雲温泉"):
        arrs = sorted([t for t in sh if t.d == X], key=lambda t: t.arr(X)); pool = []; ai = 0
        for D in sorted([t for t in sh if t.o == X], key=lambda t: t.dep(X)):
            while ai < len(arrs) and arrs[ai].arr(X) + minturn(X) <= D.dep(X): pool.append(arrs[ai]); ai += 1
            if pool: D.src = pool.pop(0)
    say("奥雲線の各停：下り " + "、".join(f"新狛野{fmt(t.dep('新狛野'))}発→犬塚{fmt(t.arr('犬塚'))}着／{fmt(t.dep('犬塚'))}発" for t in sorted(sh, key=lambda t: t.dep(t.o)) if t.dir == "D" and t.dep(t.o) < T(7, 30))
        + " …　上り " + "、".join(f"犬塚{fmt(t.arr('犬塚'))}着／{fmt(t.dep('犬塚'))}発→新狛野{fmt(t.arr('新狛野'))}着" for t in sorted(sh, key=lambda t: t.dep(t.o)) if t.dir == "U" and t.dep(t.o) < T(7, 0)) + " …")
# ---- 2''') FAR=ext：早朝・深夜の各停の秋田台発着を犬塚まで延ばす。軒屋〜秋田台の時刻は変えず、秋田台から先で、快速に追いつかれるなら
#           待避できる駅（三宅・新狛野）で止まる時間を延ばす。同じ種別（奥雲線の各停）との追い越しにならないものだけを採る
if FAR in ("ext", "ext2", "ext3") and os.environ.get("NOTHIN") != "1":
    def skov(k, L):
        for B in L:
            if B is k or B.kind != k.kind or B.dir != k.dir: continue
            com = [x for x in k.route if x in B.times]
            if len(com) < 2: continue
            a0, b0 = k.dep(com[0]), B.dep(com[0]); a1, b1 = k.arr(com[-1]), B.arr(com[-1])
            if abs(a0 - b0) <= 3600 and (a0 - b0) * (a1 - b1) < 0: return True
        return False
    def win(t):
        x = ref(t); return x is not None and (x < LV[-1] or (x >= NV[0] and any(q.dep(q.o) > T(20, 0) for q in tr)))
    HS = sorted(((a, b, c) for a in range(0, 481, 60) for b in range(0, 481, 60) for c in range(0, 301, 60)), key=lambda z: (sum(z), z))
    done = []
    def side(t):          # ext2 では、朝は上りだけ・夜は下りだけを延ばす
        return FAR in ("ext", "ext3") or ((t.dir == "U") if ref(t) < LV[-1] else (t.dir == "D"))
    for t in sorted([t for t in tr if t.kind == "各停" and not t.note and not is_x(t) and "秋田台" in (t.o, t.d) and "軒屋" in (t.o, t.d) and win(t) and side(t)], key=lambda t: t.dep(t.o)):
        rest = [q for q in tr if q is not t]; n0 = len(all_conf2(tr)[0]); got = None
        for far in ("犬塚", "新狛野"):
            for h3, h2, h1 in HS:                # h1：秋田台、h2：三宅、h3：新狛野 での停車の延長
                if t.dir == "D":
                    n = Train("", "各停", "軒屋", far, t.dep0, cars=t.cars, label=t.label, note=t.note)
                    n.hold = dict(t.hold)
                else:
                    n = Train("", "各停", far, "軒屋", 0, cars=t.cars, label=t.label, note=t.note)
                    n.hold = {k: v for k, v in t.hold.items() if k != "秋田台"}
                for st, h in (("秋田台", h1), ("三宅", h2), ("新狛野", h3)):
                    if h and st in n.route and st not in (n.o, n.d): n.hold[st] = n.hold.get(st, 0) + h
                n.id = t.id; n.frozen = True; n.compute()
                if t.dir == "U": n.dep0 = t.dep("秋田台") - n.dep("秋田台"); n.compute()
                if t.dir == "D" and n.arr(far) > ARR_END: break
                if any(abs((n.arr(x) if x != n.o else n.dep(x)) - (t.arr(x) if x != t.o else t.dep(x))) > 0.5 for x in t.route if x not in ("秋田台",)): continue
                if len(all_conf2(rest + [n])[0]) <= n0 and not skov(n, rest): got = n; break
            if got: break
        if got: tr[tr.index(t)] = got; done.append((t, got))
        else: say(f"   延ばせない：各停 {t.o}{fmt(t.dep(t.o))}発 {t.d}行")
    say(f"各停の秋田台発着を犬塚まで延長：{len(done)} 本（下り {sum(1 for t, n in done if n.dir == 'D')}・上り {sum(1 for t, n in done if n.dir == 'U')}）")
    for t, n in done:
        ex = {k: v - t.hold.get(k, 0) for k, v in n.hold.items() if v - t.hold.get(k, 0)}
        say("   " + (f"軒屋{fmt(n.dep('軒屋'))}発 → 秋田台{fmt(n.arr('秋田台'))} → {n.d}{fmt(n.arr(n.d))}着" if n.dir == "D" else f"{n.o}{fmt(n.dep(n.o))}発 → 秋田台{fmt(n.dep('秋田台'))} → 軒屋{fmt(n.arr('軒屋'))}着") + (f"（待避の停車延長 {ex}）" if ex else ""))
# ---- 2d') 朝いちばんの犬塚発の各停（延ばした各停の一本目）：秋田台で、すぐ前を出る快速（秋田台始発）に乗り換えられるようにし、学院前の待避の停車をなくす
#   （2026-11-11 本人の指示「犬塚 5:06'30発の上り各停は秋田台で快速に乗り換えられるようにし、学院前の無駄な待避時間をなくして」）。
#   秋田台には快速の発車の AKI_CONN 秒前（既定 120）に着くように犬塚の発車を早め、快速が出た90秒後から15秒刻みで、競合が増えないいちばん早い時刻に秋田台を出る。
#   学院前の停車の延長（日中は快速に抜かれるための待ち。早朝はその快速を間引いている）は、外して入るなら外す。秋田台から先の時刻はそのぶん早くなる。AKI_CONN=0 でやめる
AKI_CONN = int(os.environ.get("AKI_CONN", "120"))
if FAR in ("ext", "ext3") and os.environ.get("NOTHIN") != "1" and AKI_CONN:
    ups = sorted([n for t, n in done if n.dir == "U" and n.o == "犬塚" and ref(n) < LV[-1]], key=lambda n: n.dep0)
    if ups:
        f = ups[0]; ks = [u for u in tr if u.kind == "快速" and u.dir == "U" and u.o == "秋田台" and f.arr("秋田台") - 600 <= u.dep("秋田台") <= f.arr("秋田台") + AKI_CONN]
        if ks:
            k = max(ks, key=lambda u: u.dep("秋田台")); rest = [t for t in tr if t is not f]; n0 = len(all_conf2(tr)[0]); got = None
            for keep in (0, f.hold.get("学院前", 0)):
                for g in range(H_PASS, 601, 15):
                    n = Train("", "各停", "犬塚", "軒屋", 0, cars=f.cars, label=f.label, note=f.note); n.id = f.id; n.frozen = True
                    n.hold = {x: v for x, v in f.hold.items() if x not in ("学院前", "秋田台")}
                    if keep: n.hold["学院前"] = keep
                    n.compute(); d0 = n.dep("秋田台") - n.arr("秋田台")
                    n.hold["秋田台"] = AKI_CONN + g - d0; n.compute()
                    n.dep0 += (k.dep("秋田台") - AKI_CONN) - n.arr("秋田台"); n.compute()
                    if len(all_conf2(rest + [n])[0]) <= n0 and not skov(n, rest): got = n; break
                if got or not f.hold.get("学院前", 0): break
            if got:
                tr[tr.index(f)] = got
                say(f"朝いちばんの犬塚発の各停：犬塚{fmt(f.dep0)}発 → {fmt(got.dep0)}発。秋田台 {fmt(got.arr('秋田台'))}着（快速 {fmt(k.dep('秋田台'))}発に乗り換え）／{fmt(got.dep('秋田台'))}発、学院前 {fmt(got.arr('学院前'))}着／{fmt(got.dep('学院前'))}発、軒屋 {fmt(f.arr('軒屋'))}着 → {fmt(got.arr('軒屋'))}着")
            else: say("朝いちばんの犬塚発の各停：秋田台で快速に乗り換えられる時刻は入らないので、元のまま")
# ---- 2e) FAR=ext2：朝の下りは就島始発の各停（就島→犬塚）、夜の上りは就島終着の各停（犬塚→就島）を足す
#   時刻は SHU_AM（就島の発車の目安）・SHU_PM（犬塚の発車の目安）の −5分〜＋10分を30秒刻みで全部試し、入るものの中から
#   「乗り継ぎ込みの所要時間」がいちばん短いものを採る（上り：星野・院庄 → 軒屋。下り：軒屋 → 院庄・星野。乗り換えは SHU_CONN 秒以上）。
#   快速に追いつかれるところは 高島・秋田台・三宅・新狛野 で待つ。同じ種別（各停）どうしの追い越しにならないものだけを採る。
#   2026-11-11：はじめは「目安の時刻から後ろへ探して最初に入ったもの」を採っていたが、夜の就島行きが秋田台に快速・各停の出た直後に着き、
#   院庄から軒屋まで58分（秋田台・就島で20〜26分待ち）になったので、乗り継ぎで選ぶ形に直した。
if FAR in ("ext2", "ext3") and os.environ.get("NOTHIN") != "1":
    def hm2(x): return hm(x)
    AM = [hm2(x) for x in os.environ.get("SHU_AM", "4:50,5:35,6:05,6:35,7:05").split(",") if x]
    if SHIFT and AM: AM = [AM[0] + SHIFT] + [x for x in AM[1:] if x >= AM[0] + SHIFT + 1800]      # 始発を遅らせる候補では、朝いちばんの就島始発も同じだけ遅らせる
    PM = [hm2(x) for x in os.environ.get("SHU_PM", "20:00,20:30,21:00,21:30,22:00,22:30,23:00,23:30").split(",") if x]
    if not any(t.dep(t.o) > T(20, 0) for t in tr): PM = []
    SHU_CONN = int(os.environ.get("SHU_CONN", "45"))
    HS2 = sorted(((a, b, c, d) for a in (0, 240) for b in (0, 120, 240, 360, 480) for c in (0, 240, 360) for d in (0, 120, 240) if a + b + c + d <= 600), key=lambda z: (sum(z), z))
    def stp(t, s): return s in t.times and (STOPS.get(t.kind) is None or s in STOPS[t.kind] or s in (t.o, t.d))
    def shu_cost(n, L):
        """乗り継ぎ込みの所要時間（秒）と説明。つながる列車がなければ (None, "")"""
        if n.dir == "U":
            tot = 0; info = []
            for frm in ("星野", "院庄"):
                best = None
                for s in n.route[n.route.index(frm) + 1:]:
                    for u in L:
                        if u.kind != "回送" and u.dir == "U" and u.d == "軒屋" and stp(u, s) and n.arr(s) + SHU_CONN <= u.dep(s) and (best is None or u.arr("軒屋") < best[0]): best = (u.arr("軒屋"), s, u)
                if best is None: return None, ""
                tot += best[0] - n.dep(frm); info.append(f"{frm}→軒屋 {round((best[0] - n.dep(frm)) / 60)}分（{best[2].kind} 軒屋{fmt(best[0])}着に乗り継ぎ）")
            return tot, "、".join(info)
        tot = 0; info = []
        for to in ("院庄", "星野"):            # 乗り換えられるのは、行き先より手前の駅だけ
            best = None
            for s in n.route[:n.route.index(to)]:
                for u in L:
                    if u.kind != "回送" and u.dir == "D" and u.o == "軒屋" and stp(u, s) and u.arr(s) + SHU_CONN <= n.dep(s) and (best is None or u.dep("軒屋") > best[0]): best = (u.dep("軒屋"), s, u)
            if best is None: return None, ""
            tot += n.arr(to) - best[0]; info.append(f"軒屋→{to} {round((n.arr(to) - best[0]) / 60)}分（軒屋{fmt(best[0])}発の{best[2].kind}から{best[1]}で乗り継ぎ）")
        return tot, "、".join(info)
    SHU_CLOSE = int(os.environ.get("SHU_CLOSE", "900"))
    def near(o, d, T0):
        """目安の時刻で走らせたとき、秋田台で SHU_CLOSE 秒以内に並ぶ既存の各停（軒屋〜秋田台か、それを延ばしたもの）。なければ None
        つなげる相手は軒屋発着の各停だけ。奥雲線の各停（新狛野〜奥雲温泉）・蓮木線内の各停とはつなげない（本人の指示「奥雲線系統とは繋げない」）"""
        p = Train("", "各停", o, d, T0); p.compute(); best = None
        for u in tr:
            if u.kind != "各停" or u.note or getattr(u, "shu", False) or u.dir != p.dir or "秋田台" not in u.times or "軒屋" not in (u.o, u.d): continue
            g = abs((u.arr("秋田台") if u.dir == "D" else u.dep("秋田台")) - (p.dep("秋田台") if p.dir == "D" else p.arr("秋田台")))
            if g <= SHU_CLOSE and (best is None or g < best[0]): best = (g, u)
        return best[1] if best else None
    added = []; joined = []
    for o, d, T0 in [("就島", "犬塚", x) for x in AM] + [("犬塚", "就島", x) for x in PM]:
        n0 = len(all_conf2(tr)[0]); cand = []; u = near(o, d, T0) if FAR == "ext3" else None
        if u is not None and "秋田台" not in (u.o, u.d):       # 近くの各停がもう犬塚（新狛野）まで延びている → つながっているので、別の列車は足さない
            joined.append((T0, u)); continue
        if u is not None:                                      # 近くの各停を延ばせなかった → その各停の始発・終着の駅（秋田台）までの列車にして、秋田台で乗り継ぐ
            for k in range(0, 601, 30):
                for hs in HS2:
                    if hs[0] or hs[1]: continue
                    if o == "就島": n = Train("", "各停", "秋田台", "犬塚", u.arr("秋田台") + SHU_CONN + k)
                    else: n = Train("", "各停", "犬塚", "秋田台", 0)
                    n.id = ""; n.frozen = True; n.shu = True
                    for st, h in zip(("三宅", "新狛野"), hs[2:]):
                        if h: n.hold[st] = h
                    n.compute()
                    if o != "就島": n.dep0 = u.dep("秋田台") - SHU_CONN - k - n.arr("秋田台"); n.compute()
                    if len(all_conf2(tr + [n])[0]) <= n0 and not skov(n, tr):
                        cand.append(((0, k + sum(hs), 0, 0), n, f"秋田台で各停（軒屋{fmt(u.dep('軒屋')) + '発' if u.dir == 'D' else fmt(u.arr('軒屋')) + '着'}）と乗り継ぎ")); break
                if cand: break
        else:
          free = []
          if o == "犬塚":
              lk, _ = link_nl(tr)
              for t in tr:
                  if getattr(t, "src", None) is not None: lk[t] = t.src
              usedA = {id(a) for a in lk.values() if a is not None}
              free = sorted([a for a in tr if a.d == "犬塚" and a.kind != "回送" and id(a) not in usedA], key=lambda a: a.arr("犬塚"))
          for dt in range(-300, 601, 30):
            for hs in HS2:
                n = Train("", "各停", o, d, T0 + dt); n.id = ""; n.frozen = True; n.shu = True
                for st, h in zip(("高島", "秋田台", "三宅", "新狛野"), hs):
                    if h: n.hold[st] = h
                n.compute()
                if d == "就島" and n.arr(d) > ARR_END: break
                ok = len(all_conf2(tr + [n])[0]) <= n0
                if not ok and o == "犬塚":
                    # 折返しの相手は「先に着いた編成から」決まるので、夜の犬塚では古い編成が長く待つ形になって入らないことがある。
                    # そのときは、その日もう使わない編成のうち、直前に着いたものを相手に指定する
                    A = [a for a in free if a.arr("犬塚") + minturn("犬塚") <= n.dep0]
                    if A: n.nolink = True; n.src = A[-1]; ok = len(all_conf2(tr + [n])[0]) <= n0
                if ok and not skov(n, tr):
                    c, info = shu_cost(n, tr); cand.append(((0 if c is not None else 1, c if c is not None else 0, sum(hs), abs(dt)), n, info)); break
        if cand:
            cand.sort(key=lambda z: z[0]); got = cand[0][1]; got.shu_info = cand[0][2]; tr.append(got); added.append(got)
        else: say(f"   入らない：各停 {o}{fmt(T0)}ごろ発 {d}行")
    say(f"就島始発・就島終着の各停：{len(added)} 本（就島→犬塚 {sum(1 for n in added if n.o == '就島')}・犬塚→就島 {sum(1 for n in added if n.d == '就島')}・秋田台〜犬塚 {sum(1 for n in added if '秋田台' in (n.o, n.d))}）")
    if joined: say(f"   既存の各停とつなげたので足さなかったもの：{len(joined)} 本 " + "、".join(f"{'就島' if u.dir == 'D' else '犬塚'}{fmt(T0)}ごろ発 → 各停 {u.o}{fmt(u.dep(u.o))}発 {u.d}行" for T0, u in joined))
    for n in added: say(f"   {n.o}{fmt(n.dep(n.o))}発 → 秋田台{fmt(n.arr('秋田台'))} → {n.d}{fmt(n.arr(n.d))}着" + (f"（待避の停車延長 {n.hold}）" if n.hold else "") + (f" … {n.shu_info}" if n.shu_info else " … 軒屋方面とつながる列車なし"))
# ---- 2g) 相手のいない停車の延長を外す（2026-11-11 本人の指示。監査 audit.py で見つけたもののうち「1分以上を直す」）
#   早朝（LV の最後の区切りより前）と夜（NV の最初の区切りの30分前から）の営業列車で、停車の延長が LONELY 秒以上あり、
#   その停車のあいだに 待避（後から来た列車が先に出る）・先発（その駅始発の列車が出る）・接続（その駅止まりの列車が着く）・
#   単線の行き違い の相手が1本もないもの。日中パターンが間隔を空けるために入れている停車を間引いた時間帯にそのまま残したもの、
#   延長した各停に入れた待ちなど。外し方は前詰め（その駅から先を早める）だけ。後ろ詰め（その駅より手前を遅らせる）は、
#   下りだと軒屋の発車時刻が動くので使わない（いったん使う形で作ったら、軒屋 5:30発が 5:33発、21:00発が 21:03発になった）。
#   全部は外せないときは60秒ずつ残して試す。送り込みの回送と折返しの相手の入れ替え（下の 3〜と fix_cross）が済んだあとに行う
#   （その前だと、犬塚の折返しの都合で外せないと出るものがある）。競合が増えない・同じ種別の追い越しにならない・朝7〜11時の軒屋着が変わらないものだけ。
#   増発と変更済みの列車（案19）、奥雲線の各停の犬塚の停車（本人の指示）には触らない。LONELY=0 でやめる
LONELY = int(os.environ.get("LONELY", "60"))
def lonely_fix():
    import net as _net
    SLS = set(_net.MN[_net.MN.index("犬塚"):])
    def lonely(t, x):
        a, d = t.arr(x), t.dep(x)
        for u in tr:
            if u is t or x not in u.times: continue
            if u.dir == t.dir:
                if u.o == x:
                    if a <= u.dep(x) <= d: return False
                elif u.d == x:
                    if a - 60 <= u.arr(x) <= d: return False
                elif a <= u.arr(x) and u.dep(x) <= d and (u.arr(x) > a or u.dep(x) < d): return False
            elif x in SLS and x != "犬塚" and u.arr(x) <= d and u.dep(x) >= a: return False
        return True
    cands = []
    for t in tr:
        if t.kind == "回送" or is_x(t) or getattr(t, "adjusted", None): continue
        for x, h in t.hold.items():
            if h < LONELY or x in (t.o, t.d) or (t.note == "奥雲線" and x == "犬塚"): continue
            if not (t.arr(x) < LV[-1] or t.arr(x) >= NV[0] - 1800): continue
            if lonely(t, x): cands.append((t.arr(x), t, x))
    fixed = []
    for _, t, x in sorted(cands, key=lambda z: z[0]):
        if not lonely(t, x): continue
        n0 = len(all_conf2(tr)[0]); h0 = dict(t.hold); d0 = t.dep0; h = h0[x]; a1 = t.arr(t.d); got = None
        for cut in range(h, 0, -60):
            for mode in ("前詰め",):
                t.hold = dict(h0); t.hold[x] = h - cut
                if t.hold[x] <= 0: del t.hold[x]
                t.dep0 = d0; t.compute()
                if t.d == "軒屋" and T(7, 0) <= a1 <= T(11, 0): continue
                if len(all_conf2(tr)[0]) <= n0 and not skov(t, tr): got = (cut, mode); break
            if got: break
        if got: fixed.append((t, x, h, got, a1))
        else: t.hold = h0; t.dep0 = d0; t.compute()
    say(f"相手のいない停車の延長（{LONELY}秒以上。早朝と夜）：{len(cands)} か所のうち {len(fixed)} か所を外した・縮めた（計 {sum(g[0] for _, _, _, g, _ in fixed) // 60}分{sum(g[0] for _, _, _, g, _ in fixed) % 60:02d}秒）")
    for t, x, h, (cut, mode), a1 in fixed:
        say(f"   {t.kind} {t.o}{fmt(t.dep(t.o))}発 {t.d}行　{x}の +{h}秒 → +{h - cut}秒（{mode}）。{t.d} {fmt(a1)}着 → {fmt(t.arr(t.d))}着")
    left = [(t, x) for _, t, x in cands if x in t.hold and t.hold[x] >= LONELY and lonely(t, x)]
    for t, x in left: say(f"   残った：{t.kind} {t.o}{fmt(t.dep(t.o))}発 {t.d}行　{x}の +{t.hold[x]}秒（外すと競合が出る）")
# ---- 2h) 早く着きすぎの待避を、先の駅へ移す（2026-11-11 本人の指示「本位堂の早く着きすぎも直して」）
#   早朝・夜の営業列車で、待避のために止まっている駅に、抜く列車より LEADMIN 秒（既定 240）以上早く着いているもの。
#   日中は本位堂で急行と快速の2本に抜かれる下りの各停が、急行（犬塚行）を間引いた時間帯は快速1本を5分29秒待っていた。
#   その駅では待たずに先へ進み、次に待避できる駅（本位堂の次は就島）で抜かれるようにする。先の駅の停車の延長は、
#   競合が増えないいちばん短い長さを15秒刻みで選ぶ（抜く列車が出た90秒後に発車する形になり、そこから先も早くなることが多い）。
#   軒屋の発車は動かさない。増発と変更済みの列車には触らない。LEADMIN=0 でやめる
LEADMIN = int(os.environ.get("LEADMIN", "240"))
def late_pass():
    import net as _net
    cands = []
    for t in tr:
        if t.kind == "回送" or is_x(t) or getattr(t, "adjusted", None) or t.note in ("奥雲線", "線内"): continue
        for x, h in t.hold.items():
            if h < 60 or x in (t.o, t.d) or not (t.arr(x) < LV[-1] or t.arr(x) >= NV[0] - 1800): continue
            a, d = t.arr(x), t.dep(x)
            ov = [u for u in tr if u is not t and u.dir == t.dir and x in u.times and u.o != x and u.d != x and a <= u.arr(x) and u.dep(x) <= d and (u.arr(x) > a or u.dep(x) < d)]
            if not ov or min(u.arr(x) for u in ov) - a < LEADMIN: continue
            nx = [y for y in t.route[t.route.index(x) + 1:-1] if y in _net.K2]
            if nx: cands.append((a, t, x, nx[0]))
    done = []
    for _, t, x, y in sorted(cands, key=lambda z: z[0]):
        n0 = len(all_conf2(tr)[0]); h0 = dict(t.hold); a1 = t.arr(t.d); ay = t.arr(y); got = None
        for g in range(0, 601, 15):
            t.hold = {k: v for k, v in h0.items() if k != x}
            if h0.get(y, 0) + g: t.hold[y] = h0.get(y, 0) + g
            t.compute()
            if len(all_conf2(tr)[0]) <= n0 and not skov(t, tr): got = g; break
        if got is None: t.hold = h0; t.compute(); say(f"   移せない：{t.kind} {t.o}{fmt(t.dep(t.o))}発 {t.d}行の {x} の待避"); continue
        done.append((t, x, y, h0[x], got, a1, ay))
    say(f"早く着きすぎの待避を先の駅へ移す：{len(cands)} か所のうち {len(done)} か所")
    for t, x, y, h, g, a1, ay in done:
        say(f"   {t.kind} {t.o}{fmt(t.dep(t.o))}発 {t.d}行　{x}の +{h}秒 → 0、{y}で +{g}秒（{y} {fmt(ay)}着 → {fmt(t.arr(y))}着／{fmt(t.dep(y))}発）。{t.d} {fmt(a1)}着 → {fmt(t.arr(t.d))}着")
def links_of(tr):
    links, _ = link_nl(tr)
    for t in tr:
        if getattr(t, "src", None) is not None: links[t] = t.src
    return links
def heads(tr, X):
    """X で夜を越した編成で出る列車（折返しの相手がいない発車。増発は送り込みの回送がなければここに入る）"""
    links = links_of(tr)       # 10時より後の発車は数えない（描いている範囲の端で、相手の到着がまだ作られていないだけのものが混じる）
    return sorted([t for t in tr if t.o == X and t.dep(X) < T(10, 0) and links.get(t) is None and getattr(t, "src", None) is None], key=lambda t: t.dep(X))
cs, _ = all_conf2(tr); say("間引きと奥雲線の変更のあと：列車", len(tr), "競合", len(cs))
for c in cs[:6]: say("   ", c[0], fmt(c[1]), [(x.kind, x.o, x.d, fmt(x.dep(x.o))) for x in involved(c)][:3], c[4])
# ---- 3) 犬塚で置ける数を超えるぶんを、新狛野から回送で送り込む
def kconf(trial, k):
    cs, _ = all_conf2(trial); return [c for c in cs if any(z is k for z in involved(c))]
def feed(tr, X, FROM, cap):
    n = 0
    while True:
        H = heads(tr, X)
        if len(H) <= cap or len(heads(tr, FROM)) >= CAP_STABLE.get(FROM, 0): return n
        D = H[cap]; ok = False; n0 = len(all_conf2(tr)[0])            # 置ける数を超えた最初の発車に合わせて1本送る
        for lead in range(minturn(X), 1801, 15):
            k = Train("", "回送", FROM, X, 0); k.compute(); k.dep0 = D.dep(X) - lead - k.arr(X); k.compute()
            k.frozen = True; k.label = "回送"; k.note = "出庫の送り込み"; k.cars = D.cars; k.slow = {}
            if getattr(D, "nolink", False): k.nolink = True; D.src = k
            if len(all_conf2(tr + [k])[0]) <= n0 and len(heads(tr + [k], X)) < len(H):       # 回送そのものの競合のほか、折返しの交差・ホームの在線も増やさない
                tr.append(k); ok = True; n += 1
                say(f"   回送 {FROM}{fmt(k.dep(FROM))}発 → {X}{fmt(k.arr(X))}着 … {D.kind}{D.d}行 {fmt(D.dep(X))}発の編成"); break
            if getattr(D, "nolink", False): D.src = None
        if not ok: say(f"   回送が入らない：{X} {fmt(D.dep(X))}発 {D.kind}{D.d}行"); return n
def kaiso(o, d, arr, D):
    k = Train("", "回送", o, d, 0); k.compute(); k.dep0 = arr - k.arr(d); k.compute()
    k.frozen = True; k.nolink = True; k.label = "回送"; k.note = "出庫の送り込み"; k.cars = D.cars; k.slow = {}; return k
def feed_via(tr, X, sources, cap, leadmax=2400, waitmax=1200):
    """X で置ける数を超える発車に、sources＝[(出どころ, 折り返す駅 or None)] の順で回送を送る。出どころの置ける数を超えたら次の出どころへ。
    回送と相手の列車は src で直接つなぐ（ほかの折返しの対応づけを変えない）"""
    n = 0
    while True:
        H = heads(tr, X)
        if len(H) <= cap: return n
        got = None; n0 = len(all_conf2(tr)[0])
        for D in H[cap:] + H[:cap][::-1]:      # 置ける数を超えた発車から順に試す。どれにも入らなければ、もっと早い発車に合わせる
            for FROM, via in sources:
                if len(heads(tr, FROM)) >= CAP_STABLE.get(FROM, 0): continue
                old = getattr(D, "src", None)
                for lead in range(minturn(X), leadmax + 1, 15):
                    k2 = kaiso(via or FROM, X, D.dep(X) - lead, D)
                    if kconf(tr + [k2], k2): continue
                    D.src = k2                      # 相手の列車とつないだ状態（折返し中の在線も入る）で判定する
                    if via is None:
                        if len(all_conf2(tr + [k2])[0]) <= n0: got = [k2]; break
                        continue
                    for w in range(minturn(via), waitmax + 1, 15):
                        k1 = kaiso(FROM, via, k2.dep(via) - w, D); k2.src = k1
                        if len(all_conf2(tr + [k1, k2])[0]) <= n0: got = [k1, k2]; break
                    if got: break
                if not got: D.src = old
                if got: break
            if got: break
        if not got: say(f"   回送が入らない：{X}（" + "、".join(fmt(t.dep(X)) + "発" for t in H[cap:]) + "）"); return n
        D.src = got[-1]; tr.extend(got); n += 1
        assert len(all_conf2(tr)[0]) <= n0, "回送で競合が増えた"
        say("   回送 " + " → ".join(f"{k.o}{fmt(k.dep(k.o))}発 {k.d}{fmt(k.arr(k.d))}着" for k in got) + f" … {D.kind}{D.d}行 {fmt(D.dep(X))}発の編成" + ("（増発）" if is_x(D) else ""))
if os.environ.get("NOFEED") != "1":
    say(f"奥雲温泉への送り込み（置ける数 {CAP_STABLE['奥雲温泉']}）：夜を越す編成で出る列車は " + "、".join(fmt(t.dep(t.o)) + t.kind for t in heads(tr, "奥雲温泉")))
    feed_via(tr, "奥雲温泉", [("新狛野", None)], CAP_STABLE["奥雲温泉"], leadmax=3600)
    say(f"犬塚への送り込み（置ける数 {CAP_STABLE['犬塚']}）：夜を越す編成で出る列車は " + "、".join(fmt(t.dep(t.o)) + t.kind for t in heads(tr, "犬塚")))
    feed(tr, "犬塚", "新狛野", CAP_STABLE["犬塚"])
    if len(heads(tr, "犬塚")) > CAP_STABLE["犬塚"]:
        say(f"   新狛野が置ける数（{CAP_STABLE['新狛野']}）いっぱいなので、残りは就島から送る")
        feed_via(tr, "犬塚", [("就島", None)], CAP_STABLE["犬塚"], leadmax=3600)
    say(f"蓮木市への送り込み（置ける数 {CAP_STABLE['蓮木市']}）：夜を越す編成で出る列車は " + "、".join(fmt(t.dep(t.o)) + t.kind for t in heads(tr, "蓮木市")))
    feed_via(tr, "蓮木市", [("学院前", None), ("就島", "学院前")], CAP_STABLE["蓮木市"])
# ---- 折返しの交差：折返しの相手を入れ替えれば消えるものは、相手を指定して消す（列車の時刻は動かさない）
def fix_cross(tr):
    while True:
        cs, links = all_conf2(tr); cr = [c for c in cs if c[0] == "cross"]; done = False
        for c in cr:
            D, X = c[2], c[4]; A = links.get(D)
            for D2 in sorted([t for t in tr if t.o == X and t is not D and links.get(t) is not None and abs(t.dep(X) - D.dep(X)) <= 1800], key=lambda t: abs(t.dep(X) - D.dep(X))):
                A2 = links[D2]
                if len({x.note == "奥雲線" for x in (D, D2, A, A2)}) > 1: continue       # 奥雲線の専用編成と本線の編成は入れ替えない
                if A2.arr(X) + minturn(X) > D.dep(X) or A.arr(X) + minturn(X) > D2.dep(X): continue
                old = (getattr(D, "src", None), getattr(D2, "src", None)); D.src, D2.src = A2, A
                if len(all_conf2(tr)[0]) < len(cs):
                    say(f"   {X}の折返しの相手を入れ替え：{fmt(D.dep(X))}発{D.kind} ← {fmt(A2.arr(X))}着、{fmt(D2.dep(X))}発{D2.kind} ← {fmt(A.arr(X))}着（{fmt(D.dep(X))}発が本線の列車と交差するため）"); done = True; break
                D.src, D2.src = old
            if done: break
        if not done: return
for t in tr: t.compute()
fix_cross(tr)
if LEADMIN and os.environ.get("NOTHIN") != "1" and FAR in ("ext", "ext3"): late_pass()
if LONELY and os.environ.get("NOTHIN") != "1" and FAR in ("ext", "ext3"): lonely_fix()
cs, _ = all_conf2(tr); say("できあがり：列車", len(tr), "競合", len(cs))
for c in cs[:6]: say("   ", c[0], fmt(c[1]), [(x.kind, x.o, x.d, fmt(x.dep(x.o))) for x in involved(c)][:3], c[4])
say("夜を越す編成の数（置ける数）")
for X in sorted({t.o for t in tr}, key=lambda X: -len(heads(tr, X))):
    H = heads(tr, X)
    if H: say(f"   {X} {len(H)}（{CAP_STABLE.get(X, 0)}）" + (" 超過" if len(H) > CAP_STABLE.get(X, 0) else ""), " ", "、".join(fmt(t.dep(X)) + t.kind + ("(増発)" if is_x(t) else "") for t in H[:12]))
pickle.dump((tr, log, [t for t in tr if is_x(t)]), open(OUT, "wb")); print("保存", OUT)
