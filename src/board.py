# 発車標のページを書き出す（任意の駅・任意の番線の発車標を、ダイヤから表示する）
# 使い方（data で）: PYTHONPATH=../src python ../src/board.py cyc3_375_720_135_300_855_c.pkl [入力pkl] [出力html]
#   入力の既定は day_final.pkl（終日のダイヤ）、出力の既定は ../page/board.html。画面は page/board_tmpl.html。
#   ダイヤは書き換えない。番線は tracks.assign、列車番号は trainno.assign（export.py と同じ付け方）。
import pickle, sys, json, os, datetime
from collections import Counter, defaultdict
PKF = sys.argv[1]
SRC = sys.argv[2] if len(sys.argv) > 2 else "day_final.pkl"
OUT = sys.argv[3] if len(sys.argv) > 3 else "../page/board.html"
sys.argv = [sys.argv[0], PKF]
from morning_run import *
import net, ops, tracks, trainno
obj = pickle.load(open(SRC, "rb"))
tr = obj[0]
for t in tr: t.compute()
_st = getattr(tr[0], "stored", None)      # 置いたままの車両でふさがる線（finalize.py が入れる）。判定を finalize.py のときと同じにする
if _st is not None: ops.STORED.clear(); ops.STORED.update(_st)
_over = trainno.assign(tr)
if _over: print("列車番号が枠に入りきらない・重なる列車", len(_over))
R = tracks.assign(tr)
print("番線の割り当て：問題", len(R.problems))

# 駅名の英語表記（犬電 停車駅図 – 停車駅のご案内.html の駅一覧から写した）
EN = {"軒屋": "Nokiya", "土佐浜": "Tosahama", "大手通": "Otedori", "裏町": "Uramachi", "高砂町": "Takasagocho", "千代町": "Sendaicho", "境橋": "Sakaibashi", "新犬村": "Shin-Inumura", "船場町": "Sembacho", "錦町": "Nishikicho", "羅丹庵": "Ranian", "学院前": "Gakuin-mae", "瑞法院": "Zuihoin", "本位堂": "Hon-ido", "城見台": "Shiromidai", "就島": "Shujima", "高島公園": "Takashima-koen", "高島": "Takashima", "西高島": "Nishi-Takashima", "吹上台": "Fukiagedai", "朝日台": "Asahidai", "岩瀬": "Iwase", "秋田台": "Akitadai", "院庄": "In-nosho", "三宅": "Miyake", "戌居": "Inui", "狛野": "Komano", "新狛野": "Shin-Komano", "北川津": "Kita-Kawatsu", "星野": "Hoshino", "犬塚": "Inuzuka", "長坂": "Nagasaka", "下岩田": "Shimoiwata", "羽土": "Hado", "小椋": "Ogura", "東松田": "Higashi-Matsuda", "東蔵寺": "Tozoji", "奥雲口": "Ogumoguchi", "霧里": "Kirinosato", "奥雲温泉": "Ogumo-Onsen", "甲斐野": "Kaino", "佐茂町": "Samocho", "北洋台": "Hokuyodai", "売布": "Urufu", "丑島": "Ushijima", "桜湧水": "Sakurayusui", "牧羊町": "Bokuyocho", "蓮木市": "Hasukishi"}
BOUND_EN = {"上り 学院前・軒屋方面": "for Gakuin-mae / Nokiya", "下り 蓮木市方面": "for Hasukishi", "上り 軒屋方面": "for Nokiya",
            "下り 犬塚・蓮木市方面": "for Inuzuka / Hasukishi", "下り 犬塚・奥雲温泉方面": "for Inuzuka / Ogumo-Onsen", "下り 奥雲温泉方面": "for Ogumo-Onsen"}
BOUNDS = ["上り 軒屋方面", "上り 学院前・軒屋方面", "下り 犬塚・蓮木市方面", "下り 犬塚・奥雲温泉方面", "下り 奥雲温泉方面", "下り 蓮木市方面"]   # 方面で選ぶときの並び
assert set(BOUNDS) == set(BOUND_EN)
BI = {n: i for i, n in enumerate(BOUNDS)}
ST = [s for s, _ in net.MAIN] + [s for s, _ in net.HASU if s != "学院前"]
# 駅ナンバリング（サインシステム デザインガイドラインと停車駅図のとおり）：本線 軒屋〜新狛野 IM01〜28、
#   奥雲線 北川津〜奥雲温泉 IM61〜72、蓮木線 甲斐野〜蓮木市 IM41〜48。影の色は路線色（本線 藍・奥雲線 金茶・蓮木線 ティール）
_MN = [s for s, _ in net.MAIN]; _HN = [s for s, _ in net.HASU if s != "学院前"]
NO = {s: (i + 1 if i < _MN.index("北川津") else 61 + i - _MN.index("北川津")) for i, s in enumerate(_MN)}
NO.update({s: 41 + j for j, s in enumerate(_HN)})
assert (NO["軒屋"], NO["学院前"], NO["三宅"], NO["新狛野"], NO["犬塚"], NO["奥雲温泉"], NO["甲斐野"], NO["蓮木市"]) == (1, 12, 25, 28, 63, 72, 41, 48), NO
SI = {s: i for i, s in enumerate(ST)}
IDX = {s: i for i, s in enumerate(net.MN)}
I_GAKU, I_INU = IDX["学院前"], IDX["犬塚"]
HN1 = set(net.HN[1:])

def plat(t, x):
    v = R.trk[t].get(x)
    return v.replace("番線", "") if v else None

def bound(t, x, k):
    """その駅から先の向き（方面）"""
    up = t.dir == "U"
    if x in HN1: return "上り 学院前・軒屋方面" if up else "下り 蓮木市方面"
    if up: return "上り 軒屋方面"
    nxt = t.route[k + 1] if k + 1 < len(t.route) else None
    if x == "学院前" and nxt in HN1: return "下り 蓮木市方面"
    i = IDX[x]
    if i < I_GAKU: return "下り 犬塚・蓮木市方面"
    if i < I_INU: return "下り 犬塚・奥雲温泉方面"
    return "下り 奥雲温泉方面"

trains = []; labels = defaultdict(Counter); nolane = Counter(); dirs = defaultdict(set)   # dirs: 駅ごとの、営業列車が発車する方面
order = sorted(tr, key=lambda t: t.dep(t.o))
for t in order:
    co, cd = getattr(t, "cars_o", t.cars), getattr(t, "cars_d", t.cars)
    stops = []
    for k, x in enumerate(t.route):
        ar, dp, stp = t.times[x]
        p = plat(t, x)
        if p is None: nolane[(t.kind, x)] += 1
        elif k < len(t.route) - 1: labels[(x, p)][bound(t, x, k)] += 1      # 方面は、そこから先へ向かう列車で数える（終着の到着は入れない）
        else: labels[(x, p)]                                                 # 到着だけの番線（高島2番線など）も番線として出す
        b = BI[bound(t, x, k)] if k < len(t.route) - 1 else None                  # その駅から先の方面（終着は無し）
        if b is not None and t.kind != "回送" and (stp or x == t.o): dirs[x].add(b)
        stops.append([SI[x], None if ar is None else int(ar), None if dp is None else int(dp), 1 if (stp or x in (t.o, t.d)) else 0, p, b])
    trains.append([getattr(t, "no", ""), t.kind, t.d, t.o, t.dir, co, cd, getattr(t, "split", None) if co != cd else None,
                   1 if getattr(t, "extra", False) else 0, stops])
if nolane: print("番線が決まっていない停車・通過（車庫の出入りなど。発車標には番線なしで出す）", sum(nolane.values()), dict(nolane.most_common(6)))

stations = []
for s in ST:
    ps = sorted({p for (x, p) in labels if x == s}, key=lambda z: int(z) if z.isdigit() else 99)
    pl = []
    for p in ps:
        c = labels[(s, p)]; tot = sum(c.values())
        if not tot: pl.append([p, "当駅止まり（到着のみ）", "Arrivals only", 1]); continue
        names = [n for n, v in c.most_common() if v >= max(3, tot * 0.1)][:2] or [c.most_common(1)[0][0]]
        pl.append([p, " / ".join(names), " / ".join(BOUND_EN[n] for n in names), 0])
    stations.append([s, "H" if s in HN1 else "M", EN[s], pl, NO[s], sorted(dirs[s])])

D = {"bounds": [[n, BOUND_EN[n]] for n in BOUNDS], "src": os.path.basename(SRC), "made": datetime.date.today().isoformat(), "stations": stations, "trains": trains,
     "count": sum(1 for t in tr if t.kind != "回送"), "deadhead": sum(1 for t in tr if t.kind == "回送")}
PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "page")
tmpl = open(os.path.join(PAGE, "board_tmpl.html"), encoding="utf-8").read()
js = json.dumps(D, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

# LEDの字の表（page/ledfont16.txt・ledfont24.txt。作り方・書き方は src/ledfont.py）をページに埋め込む
import ledfont
LF = {}
for n in ledfont.SIZES:
    tb = ledfont.load(os.path.join(PAGE, f"ledfont{n}.txt"), n)
    LF[str(n)] = {"n": {}, "b": {}}
    for (v, cp), g in tb.items():
        LF[str(n)][v][chr(cp)] = [g["w"], ledfont.tohex(g["rows"])]
    print(f"LEDの字（縦{n}点）", len(LF[str(n)]["n"]), "字・大きい数字", len(LF[str(n)]["b"]), "字",
          "" if tb else "（表がない。src/ledfont.py で作る）")
lf = json.dumps(LF, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
open(OUT, "w", encoding="utf-8").write(tmpl.replace("__DATA__", js).replace("__LEDFONT__", lf))
print("書き出し", OUT, "列車", len(trains), "駅", len(stations), "番線", sum(len(s[3]) for s in stations), f"{len(js)//1024}KB", f"LEDの字 {len(lf)//1024}KB")
