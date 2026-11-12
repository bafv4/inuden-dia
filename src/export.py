# extras.pkl（または指定の pickle）からダイヤグラムのページを書き出す
# 使い方（data で）: PYTHONPATH=../src python ../src/export.py cyc_420_330_690_750_c.pkl [入力pkl] [出力html]
import pickle,sys,json,os
PKF=sys.argv[1]
SRC=sys.argv[2] if len(sys.argv)>2 else "extras.pkl"
OUT=sys.argv[3] if len(sys.argv)>3 else "../page/dia_asa.html"
sys.argv=[sys.argv[0],PKF]
from morning_run import *
from morning import CAP_STABLE
import net
obj=pickle.load(open(SRC,"rb"))
tr=obj[0]
for t in tr: t.compute()
import ops
_st=getattr(tr[0],"stored",None)      # 置いたままの車両でふさがる線（finalize.py が入れる）。判定を finalize.py のときと同じにする
if _st is not None: ops.STORED.clear(); ops.STORED.update(_st)
cs,_=all_conf2(tr)
TRK=None                               # 番線・引上線の割り当て（tracks.py。finalize.py の出力のときだけ）
# 日中パターンの pickle（tr,S,下りオフセット,上りオフセット）なら、解いた範囲 9:30〜13:00 だけを描く
PATTERN=len(obj)==4 and isinstance(obj[2],tuple)
# finalize.py の出力（tr, 運用のリスト, 始発駅ごとの最初の列車）なら、回送・運用・両数まで決まっている
FINAL=len(obj)==3 and isinstance(obj[2],dict)
if PATTERN:
    import pat_eval
    PW=(T(9,30),T(13,0))
    cs=[c for c in cs if PW[0]<=c[1]<=PW[1]]
    tr=[t for t in tr if t.dep(t.o)<=PW[1] and t.arr(t.d)>=PW[0]]
MAJ_M={"軒屋","新犬村","学院前","就島","高島","秋田台","新狛野","犬塚","奥雲温泉"}
MAJ_H={"学院前","佐茂町","蓮木市"}
main=[[s,k,s in MAJ_M] for s,k in net.MAIN]
hasu=[[s,k,s in MAJ_H] for s,k in net.HASU]
def line_map(t):
    on_h=any(x in HN[1:] for x in t.route)
    m={}
    for x in t.route:
        if x in HN[1:]: m[x]="H"
        elif x=="学院前": m[x]="H" if (on_h and not any(y in MN and y!="学院前" for y in t.route)) else "M"
        else: m[x]="M"
    return m
def rows(t):
    out=[]
    for x in t.route:
        ar,dp,stp=t.times[x]
        if x==t.o: out.append([x,None,dp,1,t.hold.get(x,0)])
        elif x==t.d: out.append([x,ar,None,1,0])
        else: out.append([x,ar,dp,1 if stp else 0,t.hold.get(x,0)])
        if TRK is not None: out[-1].append(TRK.trk[t].get(x))
    return out
T0=T(4,45); T1=T(11,30)
ALLDAY=any(t.dep(t.o)>T(20,0) for t in tr)          # 終日のダイヤ（allday.py から作ったもの）
if ALLDAY: T1=T(25,30)
if PATTERN: T0,T1=PW
import trainno
_over=trainno.assign(tr)      # 列車番号（規則は trainno.py）。始発駅の発車時刻だけで決まるので、ここで付け直しても同じ番号になる
if _over: print("列車番号が枠に入りきらない・重なる列車",len(_over),[(t.kind,t.o,t.d,fmt(t.dep(t.o)),t.no) for t in _over][:6])
if FINAL:
    import tracks; from collections import Counter
    TRK=tracks.assign(tr)
    print("番線の割り当て：問題",len(TRK.problems),dict(Counter(p[0] for p in TRK.problems)) if TRK.problems else "")
def shunt(t):
    """到着後・発車前に、引上線・留置線・折返し線・車庫へ出入りする動き（文）"""
    if TRK is None: return []
    out=[]
    if t in TRK.side_before:
        X,nm,s,e,A=TRK.side_before[t]; out.append(f"発車前 {nm}から {fmt(e)} にホームへ（{A.no} で {fmt(A.arr(X))} に着いた編成）")
    if t in TRK.side_after:
        X,nm,s,e,D=TRK.side_after[t]; out.append(f"到着後 {fmt(s)} に{nm}へ（{D.no} になって {fmt(D.dep(X))} に発車）")
    return out
trains=[]
order=sorted(tr,key=lambda t:t.dep(t.o))
for i,t in enumerate(order):
    if t.dep(t.o)>T1: continue
    co,cd=getattr(t,"cars_o",t.cars),getattr(t,"cars_d",t.cars)      # 途中（新狛野）で分割・併合する直通列車は「8→4」「4→8」と書く
    trains.append({"id":f"t{i}","kind":t.kind,"label":t.label,"o":t.o,"d":t.d,"dir":t.dir,"cars":(t.cars if co==cd else f"{co}→{cd}"),
        "no":getattr(t,"no",""),"extra":bool(getattr(t,"extra",False)),"after":getattr(t,"after",""),"note":t.note or "",
        "local":t.note in ("線内","奥雲線"),"line":line_map(t),"rows":rows(t),"shunt":shunt(t)})
ext=sorted([t for t in tr if getattr(t,"extra",False)],key=lambda t:t.arr("軒屋"))
def _ms(v): v=int(round(v)); return (f"{v//60}分{v%60:02d}秒" if v%60 else f"{v//60}分") if v>=60 else f"{v}秒"
def slow(t): return sum((getattr(t,"slow",None) or {}).values())      # 徐行で余分にかかる秒
def waits(t):
    w=[f"{k} {v//60}分{v%60:02d}秒" if v>=60 else f"{k} {v}秒" for k,v in t.hold.items() if v]
    if slow(t): w.append(f"徐行 計{_ms(slow(t))}")
    return "、".join(w)
extras=[{"kind":t.kind,"label":t.label,"o":t.o,"dep":t.dep(t.o),"mid":t.dep("新犬村") if "新犬村" in t.times else None,
    "arr":t.arr("軒屋"),"cars":t.cars,"wait":waits(t),"after":getattr(t,"after","") or "未定（finalize.py 未実行）"} for t in ext]
# 夜間滞泊：始発で、到着した編成を受けない列車（増発は除く）
links,stabled=link_nl(tr)
firsts={}
for D_,A in links.items():
    if A is None: firsts.setdefault(D_.o,[]).append(D_)
stab=[]
for st,n in sorted(stabled.items(),key=lambda z:-z[1]):
    fs=sorted(firsts.get(st,[]),key=lambda t:t.dep(t.o))
    stab.append({"st":st,"n":n,"cap":CAP_STABLE.get(st,0),"first":"、".join(f"{fmt(t.dep(t.o)).replace('½',chr(39)+'30')} {t.kind}{t.d}行" for t in fs[:6])+("…" if len(fs)>6 else "")})
if FINAL:        # 運用をつないだ結果から数える（増発車の分も入る）
    stab=[]
    for st,hs in sorted(obj[2].items(),key=lambda z:-len(z[1])):
        fs=sorted(hs,key=lambda t:t.dep(t.o))
        stab.append({"st":st,"n":len(hs),"cap":CAP_STABLE.get(st,0),"first":"、".join(f"{fmt(t.dep(t.o)).replace('½',chr(39)+'30')} {t.kind}{t.d}行" for t in fs[:6])+("…" if len(fs)>6 else "")})
nk=[t for t in tr if t.d=="軒屋" and t.kind!="回送" and T(7,30)<=t.arr("軒屋")<=T(9,0)]
# 気になる点は今のダイヤから拾う（パターンや増発の位置を変えても古い記述が残らないように）
issues=[]
for t in ext:
    if sum(t.hold.values())+slow(t)>=180: issues.append(f"増発の{t.kind}{t.o}発（{fmt(t.dep(t.o))}）は途中で合わせて{_ms(sum(t.hold.values())+slow(t))}{'余分にかかります' if slow(t) else '待ちます'}（{waits(t)}）。")
# 増発を入れるために日中パターンから時刻を変えた既存の列車（extras_opt.py が adjusted / before を付ける）
adj=sorted([t for t in tr if getattr(t,"adjusted",None)],key=lambda t:t.before[1])
for t in adj:
    dsh,dh,dsl=t.adjusted; w=[]
    if dsh: w.append(f"発車を{_ms(abs(dsh))}{'繰り下げ' if dsh>0 else '繰り上げ'}")
    w+=[f"{x}の停車を{_ms(abs(v))}{'延長' if v>0 else '短縮'}" for x,v in dh.items() if v]
    if dsl: w.append(f"徐行 計{_ms(sum(dsl.values()))}（{len(dsl)}駅間）")
    issues.append(f"既存の{t.kind}{t.o}発（日中パターンでは{fmt(t.before[0])}発・{t.d} {fmt(t.before[1])}着）は、増発を入れるために変えています：{'、'.join(w)} → {t.d} {fmt(t.arr(t.d))}着。")
_comp={}
for t in ext: _comp.setdefault(t.kind,{}).setdefault(t.o,0); _comp[t.kind][t.o]+=1
comp="・".join(f"{k}{sum(_comp[k].values())}（"+"・".join(f"{o}発{n}" for o,n in _comp[k].items())+"）" for k in ("快速","急行","各停") if k in _comp)
_a=sorted(t.arr("軒屋") for t in nk); _g=sorted((b-a,a,b) for a,b in zip(_a,_a[1:]))
if _g: issues.append(f"軒屋着 7:30〜9:00 のいちばん長い空きは {fmt(_g[-1][1])}〜{fmt(_g[-1][2])} の{_ms(_g[-1][0])}、いちばん短い間隔は{_ms(_g[0][0])}です。")
_long={}
for t in tr:
    if getattr(t,"extra",False) or t.kind=="回送": continue
    for x,v in t.hold.items():
        if v>=300: _long.setdefault((t.dir,t.kind,t.o,t.d,x),set()).add(v)
for (d_,k_,o_,dd_,x_),vs in sorted(_long.items()):
    issues.append(f"{'下り' if d_=='D' else '上り'}の{k_}{o_}発{dd_}行は{x_}で{_ms(min(vs))}"+(f"〜{_ms(max(vs))}" if len(vs)>1 else "")+"止まります（待避）。")
pending=["編成両数：ラッシュ時の8両・6両化は finalize.py で決めるため、表の両数は増発列車以外4両のままです。",
         "増発車の軒屋到着後の回送（軒屋の留置線・就島車庫）と運用のつながりは未作成です。",
         "夜間滞泊の数は折返しの対応づけから数えた仮の値で、増発車の分は入っていません。"]
if FINAL:
    import compare_extras as CE
    from collections import Counter
    ks=sorted([t for t in tr if t.kind=="回送"],key=lambda t:t.dep(t.o))
    chains=[c for c in obj[1] if c[0].dep(c[0].o)<T(10,0)]       # 描いている範囲の端で相手の到着がないだけの発車は、編成の数に入れない
    mx=Counter(max(t.cars for t in c) for c in chains); nok=CE.nokiya(tr)
    over=[s for s in stab if s["n"]>s["cap"]]
    kcut=[k for k in ks if k.note=="切り離した車両の入庫"]; knight=[k for k in ks if k.note=="夜の回送"]; kunit=[k for k in ks if k.note=="増結用の車両の回送"]
    kin=[k for k in ks if k.note=="増発車の入庫"]; kout=[k for k in ks if k.note=="出庫の送り込み"]
    def per_hour(d):
        f=(lambda t:t.dep("軒屋")) if d=="D" else (lambda t:t.arr("軒屋"))
        return "・".join(f"{h}時台{sum(1 for t in tr if t.dir==d and t.kind!='回送' and '軒屋' in t.times and T(h,0)<=f(t)<T(h+1,0))}本" for h in (5,6,7))
    oku=[t for t in tr if t.note=="奥雲線"]
    krev=sorted([t for t in tr if t.note=="増発車の折返し"],key=lambda t:t.dep(t.o))
    decided=[(f"増発{len(ext)}本のうち{sum(1 for t in ext if '留置' in getattr(t,'after',''))}本は軒屋の留置線へ入ります。{len(krev)}本は高島行きの各停として折り返し（軒屋発 "+"、".join(fmt(k.dep(k.o)) for k in krev)+"。両数は増発車のまま）、高島から回送で就島車庫へ入ります（高島発 "+"、".join(fmt(k.dep(k.o)) for k in kin if k.o=="高島")+"）。"+(f"{sum(1 for k in kin if k.o=='軒屋')}本は軒屋から就島車庫へ回送します（軒屋発 "+"、".join(fmt(k.dep(k.o)) for k in kin if k.o=="軒屋")+"）。" if any(k.o=="軒屋" for k in kin) else "")) if krev else f"増発{len(ext)}本のうち{sum(1 for t in ext if '留置' in getattr(t,'after',''))}本は軒屋の留置線へ、{len(kin)}本は就島車庫へ回送します（軒屋発 "+"、".join(fmt(k.dep(k.o)) for k in kin)+"）。軒屋〜新犬村は下りの全列車が各駅に止まるので、回送は待避駅での運転停車と徐行で、下りの列車の間を同じ速さで走ります。",
             f"運用（編成）は{len(chains)}本：" + "・".join(f"{c}両 {n}本" for c,n in sorted(mx.items(),reverse=True)) + "。数字は編成ごとのいちばん長い両数です。ラッシュ（軒屋着7:30〜9:00）の上りは優等8両以上・各停6両以上です。",
             f"軒屋のホーム（4線）は、増発車が回送の発車を待つ時間も入れて、4線とも埋まる時間が7:00〜9:30に合わせて{_ms(nok['full'])}、3線以上は{_ms(nok['three'])}です（競合の判定では足りています）。"]
    if TRK is not None:
        _sc=Counter(nm for X,nm,s,e,D in TRK.side_after.values())
        decided.append("どの列車がどの番線・引上線を使うかを決めてあります（列車を選ぶと出る表の「番線」、駅の時刻表の小さい数字）。同じ線に2本が重なる、通過列車が本線を通れない、終点の入口で到着と出発の進路が交差する、といったところは"+("ありません" if not TRK.problems else f"{len(TRK.problems)}か所残っています")+"。折返しのあいだに外へ出る回数は、"+"、".join(f"{k} {v}回" for k,v in sorted(_sc.items()))+"。")
    decided.insert(0,f"早朝は本数を絞り、段階的に増やしています。軒屋発の下りは {per_hour('D')}、軒屋着の上りは {per_hour('U')}（日中は毎時12本）。")
    if any("犬塚" in (t.o,t.d) for t in oku):
        od=sorted([t for t in oku if t.dir=="D"],key=lambda t:t.dep(t.o)); fr=[t for t in od if t.o!="犬塚"]
        decided.insert(1,"奥雲線の各停は犬塚折返しです。"+(f"下りの始発から{len(fr)}本（"+"、".join(f"{t.o} {fmt(t.dep(t.o))}発" for t in fr)+"）は、編成を送り込むために新狛野発にしています。" if fr else ""))
    if oku and not any("犬塚" in (t.o,t.d) for t in oku):
        dw=lambda d:sorted({round(t.dep("犬塚")-t.arr("犬塚")) for t in oku if t.dir==d})
        decided.insert(1,"奥雲線の各停は新狛野〜奥雲温泉の往復です。新狛野〜犬塚の列車間隔をならすため、犬塚での停車は下り"+"・".join(_ms(x) for x in dw("D"))+"、上り"+"・".join(_ms(x) for x in dw("U"))+"にしています。")
    if kout:
        def leg(k): return f"{k.o} {fmt(k.dep(k.o))}発→{k.d} {fmt(k.arr(k.d))}着"
        nx={id(k.src):k for k in kout if getattr(k,"src",None) is not None}       # 学院前で折り返す回送は2本で1組
        runs=[leg(k)+("（折返し）"+leg(nx[id(k)]) if id(k) in nx else "") for k in kout if getattr(k,"src",None) is None]
        decided.append(f"夜を越す編成が置ける数を超える駅へは、車庫・留置線から回送{len(runs)}本で送り込みます："+"、".join(runs)+"。")
    kdin=[k for k in ks if k.note=="検査のための入庫"]; kdout=[k for k in ks if k.note=="検査のための出庫"]
    if kdin or kdout:
        decided.append("検査のため、蓮木線内を往復して学院前へ戻る編成は、夜に回送で就島車庫へ入れます"+("（"+"、".join(f"{k.o} {fmt(k.dep(k.o))}発→{k.d} {fmt(k.arr(k.d))}着" for k in kdin)+"）" if kdin else "")
                       +"。代わりに、朝いちばんに学院前を出る編成を就島車庫から回送で出します"+("（"+"、".join(f"{k.o} {fmt(k.dep(k.o))}発→{k.d} {fmt(k.arr(k.d))}着" for k in kdout)+"）" if kdout else "")+"。")
    cut={}; join={}
    CO=lambda t:getattr(t,"cars_o",t.cars); CD=lambda t:getattr(t,"cars_d",t.cars)
    for c in chains:
        for t in c:              # 直通列車の途中（新狛野）での分割・併合
            if getattr(t,"split",None) and CO(t)!=CD(t): (cut if CD(t)<CO(t) else join).setdefault(t.split,[]).append(abs(CO(t)-CD(t)))
        for a,b in zip(c,c[1:]):
            if CO(b)<CD(a): cut.setdefault(a.d,[]).append(CD(a)-CO(b))
            elif CO(b)>CD(a): join.setdefault(b.o,[]).append(CO(b)-CD(a))
    spl=sorted([t for t in tr if getattr(t,"split",None) and CO(t)!=CD(t)],key=lambda t:t.dep(t.o))
    oku2=sorted([t for t in oku if t.cars==2],key=lambda t:t.dep(t.o))
    def by(dc): return "、".join(f"{st} {len(v)}回・計{sum(v)}両" for st,v in sorted(dc.items(),key=lambda z:-len(z[1])))
    def some(L,n=6): return "、".join(L[:n])+(f" ほか{len(L)-n}本" if len(L)>n else "")
    decided.append("両数は編成ごとに決めています。朝ラッシュの列車を走る編成は、始発からその折返し1本まで同じ両数で通し、折り返した先の駅で4両に切り離します。"
        +(f"夕ラッシュ（軒屋発17:00〜19:00の下り）は増発せず、増結で対応します（優等8両・各停6両）。ラッシュの列車の1本前に軒屋へ上る列車の始発駅で増結し、ラッシュの列車が着いた駅で切り離します。増結は{sum(len(v) for v in join.values())}回（{by(join)}）、" if join else "")
        +(f"切り離しは{'1日で' if join else ''}{sum(len(v) for v in cut.values())}回（{by(cut)}）です。" if cut else "")+"蓮木線内の各停は4両の専用の編成でまわします。")
    if spl or oku2:
        sd=[t for t in spl if t.dir=="D"]; su=[t for t in spl if t.dir=="U"]
        decided.append("奥雲線（犬塚より先）へ入る列車は4両までです。"
            +(f"6両以上で走る直通の快速は、{spl[0].split}の停車中に分割・併合します：下り{len(sd)}本は{spl[0].split}で後ろを切り離して4両で奥雲温泉へ（軒屋 "+some([fmt(t.dep(t.o)) for t in sd],8)+"発）、上り"+f"{len(su)}本は4両で来て{spl[0].split}で増結します（奥雲温泉 "+some([fmt(t.dep(t.o)) for t in su],8)+"発）。一覧の両数は「8→4」「4→8」と書いています。" if spl else "")
            +(f"奥雲線の各停（新狛野〜奥雲温泉の専用の編成）は、日中（新狛野 {fmt(min(t.dep(t.o) for t in oku2 if t.dir=='D'))}〜{fmt(max(t.dep(t.o) for t in oku2 if t.dir=='D'))}発の往復、{len(oku2)}本）は2両、ほかは4両です。両数は新狛野での折返しのときに変えます。" if oku2 else "奥雲線の各停は4両の専用の編成でまわします。"))
    kdel=[k for k in kunit if k.dep(k.o)<T(22,0) and getattr(k,"src",None) is None]; knu=[k for k in kunit if k.dep(k.o)>=T(22,0)]
    if cut: decided.append("切り離した車両の置き場所（配線図の留置線・引上線の数に合わせています）：犬塚は引上線が折返し待ちの編成で埋まるので置かず、秋田台・高島は留置線・引上線2線のうち1線ぶん（8両）まで、蓮木市は留置線2線（16両）までにして、あふれるぶんは回送"+str(len(kcut))+"本で車庫へ運びます（"+some([f"{k.o} {fmt(k.dep(k.o))}発→{k.d} {k.cars}両" for k in kcut])+"）。"
        +(f"増結する駅に車両が足りないときは、車庫などから回送{len(kdel)}本で届けます（"+some([f"{k.o} {fmt(k.dep(k.o))}発→{k.d} {k.cars}両" for k in kdel])+"）。朝の増発車のうち就島車庫へ入った編成の車両も、夕方の増結に使います。" if kdel else ""))
    if ALLDAY:
        def ph(d,hs):
            f=(lambda t:t.dep("軒屋")) if d=="D" else (lambda t:t.arr("軒屋"))
            return "・".join(f"{h%24}時台{sum(1 for t in tr if t.dir==d and t.kind!='回送' and '軒屋' in t.times and T(h,0)<=f(t)<T(h+1,0))}本" for h in hs)
        lastd=max((t for t in tr if t.o=="軒屋" and t.kind!="回送"),key=lambda t:t.dep("軒屋")); lastu=max((t for t in tr if t.d=="軒屋" and t.kind!="回送"),key=lambda t:t.arr("軒屋"))
        decided.insert(1,f"深夜は21時から段階的に本数を減らしています。軒屋発の下りは {ph('D',(20,21,22,23,24))}。最終は軒屋 {fmt(lastd.dep('軒屋'))}発の{lastd.kind}{lastd.d}行、上りの最終は軒屋 {fmt(lastu.arr('軒屋'))}着の{lastu.kind}（{lastu.o} {fmt(lastu.dep(lastu.o))}発）です。")
        if knight: decided.append(f"1日の終わりに、編成の位置を翌朝の始発の置き場所に合わせる回送が{len(knight)}本あります（"+"、".join(f"{k.o} {fmt(k.dep(k.o))}発→{k.d}" for k in knight)+"）。")
        if knu:
            nx2={id(k.src):k for k in knu if getattr(k,"src",None) is not None}
            runs=[f"{k.o} {fmt(k.dep(k.o))}発→"+(f"学院前で折返し→{nx2[id(k)].d}" if id(k) in nx2 else k.d)+f" {k.cars}両" for k in knu if getattr(k,"src",None) is None]
            decided.append(f"翌朝の長い編成を組むための車両を、夜のうちに回送{len(runs)}本で運びます（"+"、".join(runs)+"）。")
    mis=sum(1 for c in chains for a,b in zip(c,c[1:]) if CO(b)>CD(a) and b.o not in ("犬塚","秋田台","高島","蓮木市") and not (b.o=="新狛野" and a.note=="奥雲線" and b.note=="奥雲線"))
    pending=[("夜間滞泊が仮の置ける数を超える駅があります（"+"、".join(f"{s['st']} {s['n']}本／{s['cap']}" for s in over)+"）。送り込む回送は未作成です。") if over else "夜間滞泊は置ける数に収まっています。",
             "軒屋の留置線への入れ換えの時刻は未作成です。"]
    if mis: pending.append(f"留置線・引上線のない駅で両数が増える箇所が{mis}か所あります。")
    if cut or join: pending.append("増結・切り離しは折返しのあいだに行う想定で、作業にかかる時間は見ていません。"+("夜に運んだ車両を翌朝までにつなぐ作業の時刻も作っていません。" if ALLDAY else ""))
up=sum(1 for t in trains if t["dir"]=="U"); dn=len(trains)-up
D={"t0":T0,"t1":T1,"scrollTo":T(7,0),
 "lead":("始発から終電までの1日ぶんのダイヤです。" if ALLDAY else "")+f"日中パターン（15分ごとに各停・急行・快速）を始発から当てはめ、朝の最混雑時間帯（軒屋着7:30〜9:00）にだけ上りの増発{len(ext)}本を入れた途中段階のダイヤです。"+(f"増発を入れるために、既存の上り{len(adj)}本は日中パターンから時刻を少し変えています。" if adj else "")+("増発車の入庫の回送・運用・両数まで入れています。" if FINAL else "編成両数・回送・運用はまだ決めていません。"),
 "facts":[["列車本数（終日。回送を含む）" if ALLDAY else "列車本数（4:50〜11:30）",f"<span class='n'>{len(trains)}</span>本",f"上り{up}・下り{dn}"],
          ["朝の増発（上り）",f"<span class='n'>{len(ext)}</span>本",comp],
          ["軒屋着 7:30〜9:00",f"<span class='n'>{len(nk)}</span>本","上り・ピーク方向"],
          ["競合",f"<span class='n'>{len(cs)}</span>件","続行90秒・駅の在線・単線の行き違い・学院前の内外線・折返し"]],
 "notes":([["回送・運用・両数",decided]] if FINAL else [])+[["まだ反映していないもの",pending],
          ["気になる点",issues]],
 "main":main,"hasu":hasu,"single":[list(x) for x in net.SINGLE],
 "trains":trains,"extras":extras,"stab":stab}
if ALLDAY: D["title"]="始発から終電までのダイヤ"; D["scrollTo"]=T(6,30); D["links"]=[["車両運用表","unyo.html","編成1本ずつの動きと、日またぎの順序"]] if FINAL else []      # 運用表（unyo.py が作る page/unyo.html）へのリンク
if PATTERN:
    full=obj[0]
    m=pat_eval.score(full); ov=pat_eval.overtakes(full); sp=pat_eval.spacing(full)
    def mg(st,k):
        x=[s for s in sp if s[0]==st and s[1]==k]
        return f"{x[0][3]//60}分{x[0][3]%60:02d}秒" if x and x[0][3] else "-"
    xf=pat_eval.transfers(full)
    D.update({"title":"日中パターン（"+os.path.basename(SRC)+"）","t0":T(9,30),"t1":T(13,0),"scrollTo":T(9,45),
     "lead":f"15分ごとに各停・急行・快速を1本ずつ。下りは軒屋発で各停:{obj[2][0]//60:02d}・急行+{obj[2][1]/60:g}分・快速+{obj[2][2]/60:g}分、上りは新犬村基準で各停{'' if not obj[3][0] else f'+{obj[3][0]/60:g}分'}・急行+{obj[3][1]/60:g}分・快速+{obj[3][2]/60:g}分。9:30〜13:00を描いています。",
     "facts":[["待避（10時台に始発駅を出た列車）",f"<span class='n'>{len(set((id(a),w) for a,b,w in ov))}</span>回",f"抜かれた本数 {len(ov)}"],
              ["待ち（停車延長・始発繰り下げ）",f"<span class='n'>{m['待ち秒']//60}</span>分",f"10時台に始発駅を出た列車の合計"],
              ["軒屋 発・着の最小間隔",f"{mg('軒屋','発')} / {mg('軒屋','着')}",f"犬塚 {mg('犬塚','発')} / {mg('犬塚','着')}"],
              ["競合",f"<span class='n'>{len(cs)}</span>件","9:30〜13:00"]],
     "notes":[["支線の乗り換え待ち（10時台）",[f"{t.kind}{t.o}→{t.d} {fmt(t.dep(t.o))}：{st}で{w//60}分{w%60:02d}秒" for t,st,w in xf]],
              ["待避",[f"{a.kind}{a.o}→{a.d} {fmt(a.dep(a.o))} が {w} で {b.kind}{b.d}行に抜かれる" for a,b,w in ov]]],
     "extras":[],"stab":[]})
tmpl=open(os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","page","page_tmpl.html"),encoding="utf-8").read()
js=json.dumps(D,ensure_ascii=False).replace("</","<\\/")
page=tmpl.replace("__DATA__",js)
if "charset" not in page[:300].lower(): page='<meta charset="utf-8">'+chr(10)+page       # ファイルを直接ブラウザで開いても文字化けしないように
open(OUT,"w",encoding="utf-8").write(page)
print("書き出し",OUT,"列車",len(trains),"競合",len(cs))
