# OuDiaSecond（.oud2）に書き出す（2026-11-13 本人の依頼「OudiaSecondのダイヤとして使えるように書き出してほしい」）
#   finalize.py が作った day_final.pkl（終日）を読み、駅・番線・列車種別・列車（時刻・停車／通過・番線・列車番号・両数）を
#   OuDiaSecondV2（Ver2.06.25。ファイルの形式は FileType=OuDiaSecond.1.18）で開ける形で書く。ダイヤは書き換えない。
#   形式は、OuDiaSecond に付いている説明（OuDiaSecond説明.txt の「ファイル形式について」）と、本人が OuDiaSecondV2 で保存した
#   犬村電鉄_新案_最長区間.oud2 に合わせた：UTF-8（BOM 付き）・改行 CRLF・「名前.」で節を開き「.」で閉じる。
#   ・駅：本線 軒屋〜奥雲温泉（0〜39）のあとに、蓮木線を学院前（分岐駅。BrunchCoreEkiIndex=11）から蓮木市まで（40〜48）。
#     本線と蓮木線を直通する列車は、学院前の時刻を 11 と 40 の両方に書く（本人の .oud2 と同じ）。
#   ・番線：tracks.py の割り当て（ページの番線と同じ番号）。番線名は「2番線（下り本線）」のように役割を添える。
#     引上線・留置線・折返し線は、駅の番線の後ろに足す（入換の作業としては書かず、備考に文で書く）。
#   ・時刻：時は 24 で割った余り（KitenJikoku=400 なので、0時台の列車は前日の続きとして描かれる）。秒が 0 のときは時分だけ。
#   ・駅時刻：1＝停車、2＝通過、空＝走らない。上りは駅の並びを逆から書く。末尾の $N は番線（その駅の番線の並びで 0 始まり）。
#   入っていないもの：運用（列車どうしのつながり・運用番号）、入換・入出区・増結・解結の作業。両数・入換の動きは備考に書く。
#   使い方（data で）: PYTHONPATH=../src python ../src/oudia.py cyc3_375_720_135_300_855_c.pkl [day_final.pkl] [../oudia/犬村電鉄_平日.oud2]
import sys, os, pickle
PKF = sys.argv[1]; SRC = sys.argv[2] if len(sys.argv) > 2 else "day_final.pkl"
OUT = sys.argv[3] if len(sys.argv) > 3 else "../oudia/犬村電鉄_平日.oud2"
sys.argv = [sys.argv[0], PKF]
from morning_run import *
import net, ops, trainno, tracks
tr, chains, _start = pickle.load(open(SRC, "rb"))
for t in tr:
    if getattr(t, "slow", None) is None: t.slow = {}
    t.compute()
_st = getattr(tr[0], "stored", None)        # 置いたままの車両でふさがる線（finalize.py が入れる）。判定を finalize.py のときと同じにする
if _st is not None: ops.STORED.clear(); ops.STORED.update(_st)
trainno.assign(tr)
R = tracks.assign(tr)
if R.problems: print("番線の割り当てに問題があります", len(R.problems))
MN, HN = net.MN, net.HN
NE = len(MN) + len(HN)                         # 49 駅（学院前は本線と蓮木線で2回）
BR = len(MN)                                   # 蓮木線の学院前の位置（40）
# ---- 駅と番線
K2 = ("高砂町", "新犬村", "錦町", "本位堂", "就島", "秋田台", "新狛野", "犬塚", "佐茂町")      # 2面4線の待避駅
SINGLE1 = tracks.SINGLE1                       # 単線の途中の駅（線は1本）
def platforms(X):
    """[(番号, 役割)]、下り本線の番号、上り本線の番号。番号・役割は tracks.py の決まり"""
    if X in K2: return [(1, "下り副本線"), (2, "下り本線"), (3, "上り本線"), (4, "上り副本線")], 2, 3
    if X == "高島": return [(1, "下り本線"), (2, "中線・下り側"), (3, "中線・上り側"), (4, "上り本線")], 1, 4
    if X == "学院前": return [(1, "下り本線・外側"), (2, "蓮木線下り・内側"), (3, "蓮木線上り・内側"), (4, "上り本線・外側")], 1, 4
    if X == "三宅": return [(1, "下り本線"), (2, "中線"), (3, "上り本線")], 1, 3
    if X == "軒屋": return [(1, "下り線側"), (2, "下り線側"), (3, "上り線側"), (4, "上り線側")], 1, 3
    if X == "蓮木市": return [(1, "片面ホーム"), (2, "島式ホーム"), (3, "島式ホーム・上り線側")], 1, 3
    if X == "奥雲温泉": return [(1, ""), (2, "")], 1, 2
    if X == "下岩田": return [(1, "通過できる本線"), (2, "")], 1, 1
    if X in ("奥雲口", "霧里", "小椋", "東松田"): return [(1, "下り"), (2, "上り")], 1, 2
    if X in SINGLE1: return [(1, "単線")], 1, 1
    return [(1, "下り"), (2, "上り")], 1, 2
DEPOTS = ("就島", "新狛野")                    # 就島車庫・狛野車庫は駅の番線としては書かない（備考に書く）
def sidings(X):
    if X in DEPOTS: return []
    return [f"{tracks.SIDENAME[X]}{k}" for k in range(1, ops.SIDING.get(X, 0) + 1)] if X in tracks.SIDENAME else []
STA = [(x, False) for x in MN] + [("学院前", True)] + [(x, False) for x in HN[1:]]
TRACKS = []                                     # 駅の位置ごと：[(番線名, 略称)]、{tracks.py の名前: 位置}、下り本線の位置、上り本線の位置
for X, br in STA:
    pl, dm, um = platforms(X)
    if br: dm, um = 2, 3                        # 蓮木線の学院前は、内側の線が蓮木線の本線
    names = [(f"{n}番線（{r}）" if r else f"{n}番線", str(n)) for n, r in pl]
    idx = {f"{n}番線": i for i, (n, r) in enumerate(pl)}
    for s in sidings(X):
        idx[s] = len(names); names.append((s, s[0] + s[-1]))
    TRACKS.append((names, idx, [n for n, r in pl].index(dm), [n for n, r in pl].index(um)))
CHAKU = {"軒屋": "Jikokukeisiki_NoboriChaku", "奥雲温泉": "Jikokukeisiki_KudariChaku", "蓮木市": "Jikokukeisiki_KudariChaku"}
MAJOR = set(K2) | {"軒屋", "学院前", "高島", "三宅", "下岩田", "小椋", "東松田", "奥雲口", "霧里", "蓮木市"}
def eki_block(i):
    X, br = STA[i]; names, idx, dm, um = TRACKS[i]
    kei = CHAKU.get(X, "Jikokukeisiki_Hatsuchaku" if X in MAJOR else "Jikokukeisiki_Hatsu")
    show = X in MAJOR                           # 番線を時刻表に出す駅（本人の .oud2 と同じ：主要駅だけ）
    L = ["Eki.", f"Ekimei={X}", f"Ekijikokukeisiki={kei}", f"Ekikibo={'Ekikibo_Syuyou' if X in MAJOR else 'Ekikibo_Ippan'}",
         f"DownMain={dm}", f"UpMain={um}"]
    if br: L.append("BrunchCoreEkiIndex=" + str(MN.index("学院前")))
    if show: L += ["JikokuhyouTrackDisplayKudari=1", "JikokuhyouTrackDisplayNobori=1"]
    L.append("DiagramTrackOmit=" + ",".join("0" for _ in names))
    L.append("EkiTrack2Cont.")
    for n, r in names: L += ["EkiTrack2.", f"TrackName={n}", f"TrackRyakusyou={r}", "."]
    L.append(".")
    if not show: L.append("JikokuhyouTrackOmit=1")
    jk, jn = {"Jikokukeisiki_NoboriChaku": ("0,1", "1,0"), "Jikokukeisiki_KudariChaku": ("1,0", "0,1"),
              "Jikokukeisiki_Hatsuchaku": ("1,1", "1,1"), "Jikokukeisiki_Hatsu": ("0,1", "0,1")}[kei]
    L += [f"JikokuhyouJikokuDisplayKudari={jk}", f"JikokuhyouJikokuDisplayNobori={jn}",
          "JikokuhyouSyubetsuChangeDisplayKudari=0,0,0,0,1", "JikokuhyouSyubetsuChangeDisplayNobori=0,0,0,0,1", "DiagramColorNextEki=0",
          "JikokuhyouOuterDisplayKudari=0,0", "JikokuhyouOuterDisplayNobori=0,0",
          "JikokuhyouPrevSyubetsuChangeDisplayKudari=0,0,0,0,1", "JikokuhyouPrevSyubetsuChangeDisplayNobori=0,0,0,0,1", "."]
    return L
# ---- 列車種別（色は本人の .oud2 と同じ。色は 00BBGGRR）
KINDS = [("快速", "003B49BE", "003B49BE", 1, "SenStyle_Jissen", True), ("急行", "008C6B45", "008C6B45", 0, "SenStyle_Jissen", False),
         ("各停", "00000000", "003B3835", 0, "SenStyle_Jissen", False), ("回送", "006E767E", "00848F9A", 0, "SenStyle_Hasen", False)]
KIDX = {k[0]: i for i, k in enumerate(KINDS)}
def syubetsu_blocks():
    L = []
    for nm, moji, sen, font, style, bold in KINDS:
        L += ["Ressyasyubetsu.", f"Syubetsumei={nm}", f"Ryakusyou={nm}", f"JikokuhyouMojiColor={moji}", f"JikokuhyouFontIndex={font}",
              "JikokuhyouBackColor=00FFFFFF", f"DiagramSenColor={sen}", f"DiagramSenStyle={style}"]
        if bold: L.append("DiagramSenIsBold=1")
        L += ["StopMarkDrawType=EStopMarkDrawType_DrawOnStop", "."]
    return L
# ---- 列車
def hms(s):
    """OuDiaSecond の時刻：時（0 埋めなし。24 で割った余り）＋分 2 桁＋秒 2 桁（0 秒なら書かない）"""
    s = int(round(s)); h, m, x = (s // 3600) % 24, s // 60 % 60, s % 60
    return f"{h}{m:02d}{x:02d}" if x else f"{h}{m:02d}"
def clock(s): s = int(round(s)); return f"{s // 3600}:{s // 60 % 60:02d}'{s % 60:02d}"
def positions(t, x):
    """駅 x が、駅の並び（0〜48）のどこに入るか。学院前は、本線の駅も通るなら 11、蓮木線の駅も通るなら 40"""
    if x == "学院前":
        p = []
        if any(y in MN and y != "学院前" for y in t.route): p.append(MN.index("学院前"))
        if any(y in HN[1:] for y in t.route): p.append(BR)
        return p
    if x in HN: return [BR + HN.index(x)]
    return [MN.index(x)]
NOTRK = []                                      # tracks.py で番線が決まっていない発着（駅の本線を書く）
def trk_of(t, x, i):
    names, idx, dm, um = TRACKS[i]; v = R.trk[t].get(x)
    if v is None:
        NOTRK.append((t, x)); return dm if t.dir == "D" else um
    return idx[v]
def bikou(t):
    co, cd = getattr(t, "cars_o", t.cars), getattr(t, "cars_d", t.cars)
    w = [f"{co}両" if co == cd else f"{co}→{cd}両（{t.split}で{'分割' if cd < co else '併合'}）"]
    if t.note: w.append(t.note)
    if t in R.side_before:
        X, nm, s, e, A = R.side_before[t]; w.append(f"発車前 {nm}から{clock(e)}にホームへ")
    if t in R.side_after:
        X, nm, s, e, D = R.side_after[t]; w.append(f"到着後 {clock(s)}に{nm}へ（{D.no}になる）")
    if any(u is t for u, x in NOTRK): w.append("始発駅の番線は未定")
    return "、".join(w)
def ressya(t):
    E = [""] * NE
    for x in t.route:
        ar, dp, stp = t.times[x]
        for i in positions(t, x):
            k = trk_of(t, x, i)
            if x == t.o: E[i] = f"1;{hms(dp)}${k}"
            elif x == t.d: E[i] = f"1;{hms(ar)}/${k}"
            elif stp: E[i] = f"1;{hms(ar)}/{hms(dp)}${k}"
            else: E[i] = f"2;{hms(dp if dp is not None else ar)}${k}"
    if t.dir == "U": E = E[::-1]                 # 上りは駅の並びを逆から
    L = ["Ressya.", f"Houkou={'Kudari' if t.dir == 'D' else 'Nobori'}", f"Syubetsu={KIDX[t.kind]}", f"Ressyabangou={t.no}",
         "EkiJikoku=" + ",".join(E)]
    b = bikou(t)
    if b: L.append("Bikou=" + b)
    return L + ["."]
# 時刻の確かめ：停車駅の着発は秒単位の整数（書き出しで丸めるのは通過時刻だけ）、駅の順に時刻が戻らない
for t in tr:
    for x in t.route:
        ar, dp, stp = t.times[x]
        if stp: assert all(v is None or v == int(v) for v in (ar, dp)), (t.no, x, ar, dp)
    seq = [round(v) for x in t.route for v in t.times[x][:2] if v is not None]
    assert all(a <= b for a, b in zip(seq, seq[1:])), (t.no, seq)
order = sorted(tr, key=lambda t: (t.dep(t.o), t.no))
dia = ["Dia.", "DiaName=平日", "MainBackColorIndex=0", "SubBackColorIndex=1", "BackPatternIndex=0"]
for d, nm in (("D", "Kudari"), ("U", "Nobori")):
    dia.append(nm + ".")
    for t in order:
        if t.dir == d: dia += ressya(t)
    dia.append(".")
dia.append(".")
comment = "\\n".join([
    "犬村電鉄 平日ダイヤ（終日）。src/oudia.py が data/day_final.pkl から書き出したもの。",
    "番線は src/tracks.py の割り当て（ダイヤ図のページ・運用表と同じ番号）。2面4線の待避駅は 1 下り副本線・2 下り本線・3 上り本線・4 上り副本線。",
    "蓮木線は末尾に学院前（分岐駅）から並べている。直通列車の学院前の時刻は、本線側と蓮木線側の両方に書いている。",
    "運用（列車のつながり・運用番号）と、入換・入出区・増結・解結の作業は入れていない。両数と引上線・留置線・折返し線への出入りは備考に書いた。",
    "0時台の列車は、ダイヤグラムの起点 4:00 より前なので前日の続きとして描かれる。"])
DISP = """DispProp.
JikokuhyouFont=PointTextHeight=9;Facename=Meiryo UI
JikokuhyouFont=PointTextHeight=9;Facename=Meiryo UI;Bold=1
JikokuhyouFont=PointTextHeight=9;Facename=Meiryo UI;Itaric=1
JikokuhyouFont=PointTextHeight=9;Facename=Meiryo UI;Bold=1;Itaric=1
JikokuhyouFont=PointTextHeight=9;Facename=Meiryo UI
JikokuhyouFont=PointTextHeight=9;Facename=Meiryo UI
JikokuhyouFont=PointTextHeight=9;Facename=Meiryo UI
JikokuhyouFont=PointTextHeight=9;Facename=Meiryo UI
JikokuhyouVFont=PointTextHeight=9;Facename=@メイリオ
DiaEkimeiFont=PointTextHeight=9;Facename=Meiryo UI
DiaJikokuFont=PointTextHeight=9;Facename=Meiryo UI
DiaRessyaFont=PointTextHeight=9;Facename=Meiryo UI
OperationTableFont=PointTextHeight=9;Facename=Meiryo UI
AllOperationTableJikokuFont=PointTextHeight=8;Facename=Meiryo UI
CommentFont=PointTextHeight=9;Facename=Meiryo UI
DiaMojiColor=00000000
DiaBackColor=00FFFFFF
DiaBackColor=00FFFFFF
DiaBackColor=00FFFFFF
DiaBackColor=00FFFFFF
DiaBackColor=00FFFFFF
DiaRessyaColor=00000000
DiaJikuColor=00C0C0C0
JikokuhyouBackColor=00FFFFFF
JikokuhyouBackColor=00F0F0F0
JikokuhyouBackColor=00FFFFFF
JikokuhyouBackColor=00FFFFFF
StdOpeTimeLowerColor=00E0E0FF
StdOpeTimeHigherColor=00FFFFE0
StdOpeTimeUndefColor=0080FFFF
StdOpeTimeIllegalColor=00A0A0A0
OperationStringColor=00000000
OperationGridColor=00000000
EkimeiLength=6
JikokuhyouRessyaWidth=6
AnySecondIncDec1=5
AnySecondIncDec2=15
DisplayRessyamei=1
DisplayOuterTerminalEkimeiOriginSide=0
DisplayOuterTerminalEkimeiTerminalSide=0
DiagramDisplayOuterTerminal=0
SecondRoundChaku=0
SecondRoundHatsu=0
Display2400=0
OperationNumberRows=1
DisplayInOutLinkCode=0
.""".split("\n")
lines = ["FileType=OuDiaSecond.1.18", "Rosen.", "Rosenmei=犬村電鉄 犬村本線・奥雲線・蓮木線", "KudariDiaAlias=", "NoboriDiaAlias="]
for i in range(NE): lines += eki_block(i)
lines += syubetsu_blocks() + dia
lines += ["KitenJikoku=400", "DiagramDgrYZahyouKyoriDefault=60", "Comment=" + comment, "."] + DISP + ["FileTypeAppComment=犬電 src/oudia.py"]
os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
with open(OUT, "w", encoding="utf-8-sig", newline="\r\n") as f: f.write("\n".join(lines) + "\n")
nd = sum(1 for t in tr if t.dir == "D")
print("書き出し", OUT, "列車", len(tr), f"（下り{nd}・上り{len(tr) - nd}）", "駅", NE)
if NOTRK: print("番線が決まっていない発着（駅の本線を書いた）", len(NOTRK), sorted({x for t, x in NOTRK}))
