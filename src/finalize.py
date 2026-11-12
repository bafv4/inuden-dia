# 増発車の入庫の回送・運用のつなぎ・両数・夜間滞泊の集計。
# 使い方（data で）: PYTHONPATH=../src python ../src/finalize.py パターン.pkl [入力 extras.pkl] [出力 final.pkl]
#   入力は extras.pkl と同じ形（early.py の出力 early.pkl も同じ形）
import pickle,sys,json,math
PKF=sys.argv[1]; SRC=sys.argv[2] if len(sys.argv)>2 else "extras.pkl"; OUT=sys.argv[3] if len(sys.argv)>3 else "final.pkl"
sys.argv=[sys.argv[0],PKF]
from morning_run import *
tr,log,placed=pickle.load(open(SRC,"rb"))
for t in tr: t.compute()
log=[]
# ---- 増発列車の軒屋到着後：急行2本は軒屋の留置線、残りは就島車庫へ回送
ext=sorted([t for t in tr if getattr(t,"extra",False)],key=lambda t:t.arr("軒屋"))
kyu=[t for t in ext if t.kind=="急行"]
to_yard=kyu[-2:]
for x in to_yard: x.after="軒屋留置線へ"
# 回送の通り道の探し方：軒屋〜新犬村は下りの全列車が各駅に止まるので、通過で走る回送は軒屋の発車をずらすだけでは前の列車に追いつく
# （morning.fix は回送の発車しか動かせず、4本とも入らなかった）。そこで (1) 軒屋の発車 (2) 運転停車できる駅での待ち
# (3) 駅間の徐行（次の運転停車駅までの各駅間に同じ秒数）を、手前の区間から順に決めていく。競合は既存の判定（all_conf2）で数え、
# 既存の列車と増発は1本も動かさない。発車は早い順、徐行・待ちは少ない順に試して、最初に通ったものを採る。
K_SLOW=(0,15,30,45,60); K_HOLD=range(0,601,30); K_HOLD_SUM=900
before=sorted((t.dir,t.kind,t.o,t.d,t.dep0,tuple(sorted(t.hold.items())),tuple(sorted((getattr(t,"slow",None) or {}).items()))) for t in tr)
def kconf(trial,k):
    cs,_=all_conf2(trial); return [c for c in cs if any(z is k for z in involved(c))]
def kpos(c,k):
    """競合が回送の経路の何番目の駅で起きているか。決め終わった区間の競合は、その先の待ち方では直らない"""
    x=c[5] if c[0]=="seg" else c[4]
    return k.route.index(x) if isinstance(x,str) and x in k.route else 0
def kaiso_path(trial,k,st=None,slows=None):
    st=st or k.stops(); r=k.route; slows=slows or K_SLOW
    def go(i):                       # 運転停車駅 st[i] の発車までは決まっている
        lim=r.index(st[i+1]); sec=r[r.index(st[i])+1:lim+1]; last=(i+1==len(st)-1)
        for sv in slows:
            for x in sec:
                if sv: k.slow[x]=sv
                else: k.slow.pop(x,None)
            for h in ([0] if last else K_HOLD):
                if sum(k.hold.values())-k.hold.get(st[i+1],0)+h>K_HOLD_SUM: break
                if h: k.hold[st[i+1]]=h
                else: k.hold.pop(st[i+1],None)
                cs=kconf(trial,k)
                if last:
                    if not cs: return True
                    break
                if any(kpos(c,k)<lim or (kpos(c,k)==lim and c[0]=="seg") for c in cs): break     # 着くまでの競合：待ちを延ばしても直らない
                if any(kpos(c,k)==lim for c in cs): continue
                if go(i+1): return True
            k.hold.pop(st[i+1],None)
        for x in sec: k.slow.pop(x,None)
        return False
    return go(0)
# 2026-11-11 本人の指示：朝ラッシュの下りの入庫回送は、高島行きの営業列車として走らせる（KAISO_REV=0 で、もとの就島行きの回送に戻る）。
#   軒屋→高島は各停（どの駅にも止まる。両数は増発車のまま8両・6両）。待避のための停車延長は2面4線の駅だけで、手前の区間から順に決める。
#   同じ種別（各停）どうしで追い越し・追い越されにならない時刻だけを採る。高島に着いたあとは、回送で就島車庫へ戻す（高島の引上線は折返しに使うので置かない）
import os
def same_kind_ov(k,L):
    for B in L:
        if B is k or B.kind!=k.kind or B.dir!=k.dir or B.kind=="回送": continue
        com=[x for x in k.route if x in B.times]
        if len(com)<2: continue
        a0,b0=k.dep(com[0]),B.dep(com[0]); a1,b1=k.arr(com[-1]),B.arr(com[-1])
        if abs(a0-b0)<=3600 and (a0-b0)*(a1-b1)<0: return True
    return False
kaiso=[]
REV=os.environ.get("KAISO_REV","1")!="0"
# 高島行きの営業列車にするのは、留置線へ入らない増発車のうち KAISO_REV_PICK 番目（軒屋に着く順。0始まり）だけ。既定は1本目と3本目の2本
# （本人の指示「ちょっと多すぎるので減らして」で4本から2本に。残りは下の手順で就島行きの回送にする）
_ny=[x for x in ext if x not in to_yard]
_pick=[_ny[int(i)] for i in os.environ.get("KAISO_REV_PICK","0,2").split(",") if i.strip()!="" and int(i)<len(_ny)]
for x in (_pick if REV else []):
    # 出発は、軒屋を出る前後の下り列車（定期列車と、先に決めた増発車の折返し）との間隔が KAISO_GAP 秒（既定150秒）以上になる
    # いちばん早い時刻にする（本人の指示「間隔を空ける」）。着いてから20分以内にそういう時刻がなければ、間隔がいちばん広い時刻にする
    got=None; cand=[]; GAP=int(os.environ.get("KAISO_GAP","150"))
    others=[t.dep("軒屋") for t in tr+kaiso if t.dir=="D" and t.o=="軒屋" and t.kind!="回送"]
    for d in range(240,1201,15):
        k=Train("","各停","軒屋","高島",x.arr("軒屋")+d); k.frozen=False; k.nolink=True; k.src=x; k.cars=x.cars; k.slow={}
        k.label="各停（増発）"; k.note="増発車の折返し"
        st=["軒屋"]+[y for y in k.route[1:-1] if y in K2]+["高島"]
        if not kaiso_path(tr+kaiso+[k],k,st,(0,)) or same_kind_ov(k,tr+kaiso): continue
        g=min(abs(k.dep("軒屋")-o) for o in others); cand.append((g,-d,k))
        if g>=GAP: break
    for g,_,k in sorted(cand,key=lambda z:(z[0]<GAP,-z[0] if z[0]<GAP else -z[1])):       # GAP 以上のものがあればそれ（1つだけ）、なければ間隔の広い順
        n0=len(all_conf2(tr+kaiso+[k])[0])
        for d2 in range(360,3600,15):          # 高島で折り返して就島車庫へ
            r=Train("","回送","高島","就島",k.arr("高島")+d2); r.frozen=True; r.nolink=True; r.src=k; r.cars=x.cars; r.slow={}; r.label="回送"; r.note="増発車の入庫"; r.compute()
            if len(all_conf2(tr+kaiso+[k,r])[0])<=n0: got=(k,r); break
        if got: k.gap=g; break
    if not got: print("高島行きの営業列車が入らない",x.label,x.o,fmt(x.arr("軒屋"))); continue
    k,r=got; kaiso+=[k,r]; x.after="高島行きの各停で折り返し、高島から就島車庫へ回送"
    print("増発車の折返し",x.kind,x.o,"発 軒屋",fmt(x.arr("軒屋")),"着 → 各停 軒屋",fmt(k.dep("軒屋")),f"発（着後{(k.dep('軒屋')-x.arr('軒屋'))/60:.1f}分・前後の下りと{k.gap}秒以上）→ 高島",fmt(k.arr("高島")),"着（待避の停車延長",{a:b for a,b in k.hold.items() if b},"）→ 回送 高島",fmt(r.dep("高島")),"発 → 就島",fmt(r.arr("就島")),"着")
for x in ext:
    if x in to_yard or getattr(x,"after",""): continue
    best=None
    for d in range(240,2400,15):
        k=Train("","回送","軒屋","就島",x.arr("軒屋")+d); k.frozen=False; k.nolink=True; k.src=x; k.cars=x.cars; k.slow={}
        k.label="回送"; k.note="増発車の入庫"
        if kaiso_path(tr+kaiso+[k],k): best=k; break
    if best is None: print("回送 FAIL",x.label,x.o); continue
    kaiso.append(best); x.after="就島車庫へ回送"
    print("回送",x.kind,x.o,"発 軒屋",fmt(x.arr("軒屋")),"着 →",fmt(best.dep("軒屋")),"発 → 就島",fmt(best.arr("就島")),"着  運転停車の待ち",best.hold,
          " 徐行 計",sum(best.slow.values()),"秒",{v:[a for a,b in best.slow.items() if b==v] for v in sorted(set(best.slow.values()))})
assert before==sorted((t.dir,t.kind,t.o,t.d,t.dep0,tuple(sorted(t.hold.items())),tuple(sorted((getattr(t,"slow",None) or {}).items()))) for t in tr),"回送のほかの列車が動いた"
tr+=kaiso
for i,t in enumerate(tr): t.compute()
cs,links=all_conf2(tr)
print("conflicts",len(cs))
for c in cs[:5]: print(c[0],hms(c[1]),[(x.kind,x.o,x.d,fmt(x.dep(x.o))) for x in involved(c)][:3],c[4])
# ---- 車両の連結（運用）
def build_chains(tr):
    links,stab=link_nl(tr)
    for t in tr:
        if getattr(t,"src",None) is not None: links[t]=t.src
    nxt={}
    for D,A in links.items():
        if A is not None: nxt[A]=D
    heads=[t for t in tr if links.get(t) is None and not (getattr(t,"src",None))]
    chains=[]
    seen=set()
    for h in sorted(heads,key=lambda t:t.dep(t.o)):
        c=[h]; seen.add(h)
        while c[-1] in nxt and nxt[c[-1]] not in seen: c.append(nxt[c[-1]]); seen.add(c[-1])
        chains.append(c)
    for t in tr:
        if t not in seen: chains.append([t]); seen.add(t)
    return chains
chains=build_chains(tr)
# ==== ここから下は、車両の運用（両数・増結・切り離し・車両の置き場所・夜の位置合わせ）。2026-11-11 に本人と決めた形 ====
#   両数は編成（運用）ごとに決める。
#   ・朝ラッシュ（軒屋着7:30〜9:00の上り）は優等8両・各停6両が最低限。その列車を走る編成は、始発から「最後のラッシュの列車の折返し1本」まで
#     長いまま走り、折り返した先の駅で4両に切り離す。すぐ車庫へ入る増発車は切り離さない
#   ・夕ラッシュ（軒屋発17:00〜19:00の下り）は増発せず、増結で対応する（本人の指示）。優等8両・各停6両。その列車を走る編成は、
#     ラッシュの列車の1本前（軒屋へ上る列車）の始発駅で増結し、ラッシュの列車が着いた駅で4両に切り離す
#   ・増結・切り離しができるのは、留置線・引上線のある 犬塚・秋田台・高島・蓮木市 だけ（CUT_OK）。奥雲温泉発着にあたる編成は、手前・先のこの4駅までさかのぼる・進む
#   ・上限は奥雲線の各停の4両だけ（early.py が専用の編成でまわしている）。蓮木線内の各停も専用の編成で4両
#   切り離した車両の置き場所（配線図の線の数に合わせる）：
#   ・犬塚：引上線は折返し待ちの編成で埋まるので置かない。切り離したら回送で狛野車庫（新狛野）へ、増結するときは狛野車庫などから回送で届ける
#   ・秋田台・高島：留置線・引上線2線のうち1線ぶん（8両）まで置く。あふれたぶんは回送で車庫へ
#   ・蓮木市：留置線2線（16両まで）
#   ・朝の増発車（就島車庫へ入った4本）は、車庫に入ったあとは車両として数え、夕方の増結に使う（終日のダイヤのとき）
#   1日の終わり（終日のダイヤのとき）：編成の数を翌朝の始発の置き場所に合わせ（夜の回送）、両数の過不足を車両だけの回送で運ぶ
from collections import Counter
import net, ops
from morning import CAP_STABLE,SIDING
def _km(x):
    if ("H",x) in net.KM and x!="学院前": return ("H",net.KM[("H",x)])
    return ("M",net.KM[("M",x)] if ("M",x) in net.KM else dict(net.MAIN)[x])
def _dist(a,b):
    (la,ka),(lb,kb)=_km(a),_km(b); g=dict(net.MAIN)["学院前"]
    if la==lb: return abs(ka-kb)
    return (ka if la=="H" else abs(ka-g))+(kb if lb=="H" else abs(kb-g))
def _cost(a,b):          # 距離。蓮木線と、学院前より先（就島側）の本線の駅とのあいだは、学院前で向きを変えることになるので避ける
    if a is None: return 0
    (la,ka),(lb,kb)=_km(a),_km(b); g=dict(net.MAIN)["学院前"]
    rev=(la!=lb) and ((ka if la=="M" else kb)>g)
    return _dist(a,b)+(1000 if rev else 0)
NIGHT=any(t.dep(t.o)>T(20,0) for t in tr)
EVE=(T(17,0),T(19,0))
CUT_OK=("犬塚","秋田台","高島","蓮木市")
DAY_STORE={"犬塚":0,"秋田台":8,"高島":8,"蓮木市":16}; HAUL={"犬塚":"新狛野","秋田台":"新狛野","高島":"就島"}; READY=300   # READY：切り離してから動かせるまで・増結に間に合わせる余裕（秒）
KEEP_LONG=os.environ.get("KEEP_LONG")=="1"       # 朝も夕もラッシュを走る編成を、日中も長いまま走らせる（比べるための切り替え）
def dissolved(c):        # 朝の増発車で、車庫へ入った編成：そのあとは車両として数える
    return NIGHT and c[-1].kind=="回送" and c[-1].note=="増発車の入庫"
# ---- 1) 終日のダイヤのとき：1日の終わりの編成の位置を、翌朝の始発の置き場所に合わせる（夜の回送）
night=[]; formed=Counter()
if NIGHT:
    def tally():
        S=Counter(c[0].o for c in chains if c[0].dep(c[0].o)<T(10,0)); E={}
        for c in chains:
            if not dissolved(c) and c[-1].note!="増結用の車両の回送" and getattr(c[-1],"unyo",None)!=0: E.setdefault(c[-1].d,[]).append(c)
        return S,E
    S,E=tally()
    sur={X:len(v)-S.get(X,0) for X,v in E.items() if len(v)>S.get(X,0)}; de={X:S[X]-len(E.get(X,[])) for X in S if S[X]>len(E.get(X,[]))}
    print("1日の終わりの位置：余る駅",dict(sur),"／足りない駅",dict(de))
    src=[a for a,n in sur.items() for _ in range(n)]; dst=[b for b,n in de.items() for _ in range(n)]
    src+=[None]*max(0,len(dst)-len(src)); m=min(len(src),len(dst)); src,dst=src[:m],dst[:m]; better=True      # None：走ってくる編成がなく、車両から組む編成
    while better:
        better=False
        for i in range(m):
            for j in range(i+1,m):
                if _cost(src[i],dst[j])+_cost(src[j],dst[i])<_cost(src[i],dst[i])+_cost(src[j],dst[j])-1e-9: dst[i],dst[j]=dst[j],dst[i]; better=True
    for a,b in sorted(zip(src,dst),key=lambda z:(z[0] is None,z[0] or "",z[1])):
        if a is None: formed[b]+=1; continue
        c=min(E[a],key=lambda c:c[-1].arr(a)); E[a].remove(c); l=c[-1]
        n0=len(all_conf2(tr)[0]); t0=max(l.arr(a)+300,T(21,0)); ok=False
        for d in range(0,4*3600,60):
            k=Train("","回送",a,b,t0+d); k.frozen=True; k.nolink=True; k.src=l; k.label="回送"; k.note="夜の回送"; k.cars=l.cars; k.slow={}; k.compute()
            if len(all_conf2(tr+[k])[0])<=n0:
                tr.append(k); night.append(k); ok=True
                print(f"夜の回送 {a}{fmt(k.dep(a))}発 → {b}{fmt(k.arr(b))}着（{fmt(l.arr(a))}に着いた{l.kind}の編成）"); break
        if not ok: print("夜の回送が入らない",a,"→",b)
    chains=build_chains(tr)
    if formed: print("車両から組む編成（朝の増発車のぶん）：",dict(formed))
# ---- 2) 両数
def rush_cars(t):
    if t.dir=="U" and t.d=="軒屋" and t.kind!="回送" and RUSH[0]<=t.arr("軒屋")<=RUSH[1]:
        return 8 if t.kind in ("急行","快速") else 6
    return 0
def eve_cars(t):
    if NIGHT and t.dir=="D" and t.o=="軒屋" and t.kind!="回送" and t.note!="増発車の折返し" and EVE[0]<=t.dep("軒屋")<=EVE[1]:
        return 8 if t.kind in ("急行","快速") else 6
    return 0
# 奥雲線の両数の決まり（2026-11-11 本人の指示「奥雲線内の両数は最大4両とし、6両以上の直通列車は新狛野か犬塚で分割併合する。奥雲線内各停のデイタイムは2両」）
#   ・犬塚より先（奥雲温泉まで）へ入る列車は OKU_MAX 両まで。軒屋〜奥雲温泉を直通する快速は、SPLIT_ST（既定 新狛野。車庫のとなりなので
#     切り離した車両・増結する車両を回送で運ばずに済む。SPLIT_ST=犬塚 にもできる）の停車中に切り離し・増結する。
#     軒屋〜犬塚の列車（犬塚止まり・犬塚始発）は、これまでどおり8両で犬塚まで入る
#   ・奥雲線の各停（新狛野〜奥雲温泉の専用の編成）は、新狛野を OKU_DAY（既定 9:00〜17:00）に出る往復を OKU_DAYCARS 両（2両）、ほかは4両。
#     両数を変えるのは新狛野での折返しのとき（車庫のとなり）
#   両数は「脚」ごとに決める：ふつうの列車は1本で1脚、直通の快速は SPLIT_ST で本線側と奥雲線側の2脚。脚と脚の境目で両数を変えられるのは、
#   折返しの駅が CUT_OK のとき、直通の快速の SPLIT_ST、奥雲線の各停どうしの新狛野の折返し
OKU_MAX=4; SPLIT_ST=os.environ.get("SPLIT_ST","新狛野"); DEPOTS=("新狛野","就島")
def _hm(x): h,m_=x.split(":"); return T(int(h),int(m_))
OKU_DAY=tuple(_hm(x) for x in os.environ.get("OKU_DAY","9:00,17:00").split(",")); OKU_DAYCARS=int(os.environ.get("OKU_DAYCARS","2"))
def legs_of(t):
    """[(始点, 終点, 奥雲線側か)]"""
    if "奥雲温泉" in (t.o,t.d) and t.kind!="回送" and t.note!="奥雲線" and SPLIT_ST in t.route and SPLIT_ST not in (t.o,t.d):
        return [(t.o,SPLIT_ST,t.o=="奥雲温泉"),(SPLIT_ST,t.d,t.d=="奥雲温泉")]
    return [(t.o,t.d,"奥雲温泉" in (t.o,t.d) or t.note=="奥雲線")]
outs=[]
events=[]; bad=[]            # events＝(時刻, 種類, 駅, 両数)：種類は "cut"（切り離し）・"join"（増結）・"in"（車庫に入った増発車を車両として数える）
def _cc(L,i):                # L[i] と L[i+1] の境目で両数を変えられるか
    t1,a1,b1,o1=L[i]; t2=L[i+1][0]
    if t1 is t2 or b1 in CUT_OK: return True
    return b1 in DEPOTS and t1.note=="奥雲線" and t2.note=="奥雲線"
LEGS=[]
for ci,c in enumerate(chains):
    L=[(t,a,b,o) for t in c for a,b,o in legs_of(t)]; m=len(L)
    can_change=lambda i,L=L:_cc(L,i)
    am=[0 if o else rush_cars(t) for t,a,b,o in L]; pm=[0 if o else eve_cars(t) for t,a,b,o in L]; cars=[4]*m; LA=max(am); LP=max(pm)
    if LA:
        last=max(i for i,r in enumerate(am) if r); j=last+1
        while j<m-1 and (not can_change(j) or (L[j+1][0].kind=="回送" and L[j+1][0].note=="増発車の入庫")): j+=1
        for i in range(0,min(j,m-1)+1): cars[i]=LA
    if LP:
        f=min(i for i,r in enumerate(pm) if r); l=max(i for i,r in enumerate(pm) if r); g=max(f-1,0)
        while g>0 and not can_change(g-1): g-=1
        e=l
        while e<m-1 and not can_change(e): e+=1
        for i in range(0 if (KEEP_LONG and LA) else g,min(e,m-1)+1): cars[i]=max(cars[i],LP,LA if (KEEP_LONG and LA) else 0)
    for i,(t,a,b,o) in enumerate(L):
        if o: cars[i]=min(cars[i],OKU_MAX)
    for i,(t,a,b,o) in enumerate(L):
        if t.note=="奥雲線" and t.dir=="D" and OKU_DAY[0]<=t.dep(t.o)<OKU_DAY[1]:
            cars[i]=OKU_DAYCARS
            if i+1<m and L[i+1][0].note=="奥雲線" and L[i+1][0].dir=="U": cars[i+1]=OKU_DAYCARS
    k=0
    for t in c:
        n=len(legs_of(t)); seg=cars[k:k+n]; k+=n
        t.cars=max(seg); t.cars_o=seg[0]; t.cars_d=seg[-1]; t.split=SPLIT_ST if n==2 else None      # cars：本線側の両数。cars_o・cars_d：始発駅・終着駅での両数
        if t.note=="線内" and t.cars!=4: bad.append(t)
        if t.note=="奥雲線" and t.cars not in (OKU_DAYCARS,4): bad.append(t)
    LEGS.append((ci,c,L,cars))
# 分割・併合の作業時間：直通の快速が SPLIT_ST で切り離す・増結するとき、その駅の停車を 分割 SPLIT_CUT_SEC 秒・併合 SPLIT_JOIN_SEC 秒にする
# （2026-11-11 本人が試算を見て「分割1分・併合2分」。それまでは快速のふつうの停車45秒のまま）。延ばすぶんは、その駅から先を遅らせるか、
# 始発駅の発車を早めるか、その組み合わせ（15秒刻み）で、競合が増えない・同種別の追い越しにならない・折返しのつながりが変わらないものを選ぶ。
# 軒屋側の時刻を変えないものを先に採る（下りは軒屋の発車をそのままにして新狛野から先を遅らせ、上りは奥雲温泉の発車を早めて軒屋着をそのままにする）。
# 入らなければ、入るところまで短くして知らせる
SPLIT_SEC=(int(os.environ.get("SPLIT_CUT_SEC","60")),int(os.environ.get("SPLIT_JOIN_SEC","120")))
def _lmap():
    lk,_=link_nl(tr)
    for t in tr:
        if getattr(t,"src",None) is not None: lk[t]=t.src
    return {id(d):(id(a) if a is not None else None) for d,a in lk.items()}
def _sko(k):
    for B in tr:
        if B is k or B.kind!=k.kind or B.dir!=k.dir or B.kind=="回送": continue
        com=[x for x in k.route if x in B.times]
        if len(com)<2: continue
        a0,b0=k.dep(com[0]),B.dep(com[0]); a1,b1=k.arr(com[-1]),B.arr(com[-1])
        if abs(a0-b0)<=3600 and (a0-b0)*(a1-b1)<0: return True
    return False
if any(SPLIT_SEC):
    lmA=_lmap()
    for t in sorted([t for t in tr if getattr(t,"split",None) and t.cars_o!=t.cars_d],key=lambda t:t.dep(t.o)):
        X=t.split; cut=t.cars_d<t.cars_o; want=SPLIT_SEC[0 if cut else 1]; add0=int(round(want-(t.dep(X)-t.arr(X))))
        if add0<=0: continue
        n0=len(all_conf2(tr)[0]); h0=dict(t.hold); d0=t.dep0; a1=t.arr(t.d); got=None
        for add in range(add0,0,-15):
            for early in (range(0,add+1,15) if t.dir=="D" else range(add,-1,-15)):      # 軒屋側の時刻を変えない形を先に試す（下りは軒屋の発車をそのまま、上りは奥雲温泉の発車を早めて軒屋着をそのまま）
                t.hold=dict(h0); t.hold[X]=h0.get(X,0)+add; t.dep0=d0-early; t.compute()
                if len(all_conf2(tr)[0])<=n0 and not _sko(t) and _lmap()==lmA: got=(add,early); break
            if got: break
        if not got: t.hold=h0; t.dep0=d0; t.compute()
        print(f"{'分割' if cut else '併合'} {t.kind} {t.o}{fmt(d0)}発 {t.d}行：{X}の停車 {int(want-add0)}秒 → "+(f"{int(want-add0+got[0])}秒（{X} {fmt(t.arr(X))}着／{fmt(t.dep(X))}発）。"+(f"{t.o}の発車を{got[1]}秒早めて {fmt(t.dep0)}発、" if got[1] else "")+(f"{t.d} {fmt(a1)}着 → {fmt(t.arr(t.d))}着" if abs(t.arr(t.d)-a1)>0.5 else f"{t.d}着は同じ")+("" if got[0]==add0 else f"　※{want}秒は入らない") if got else "延ばせない（入らない）"))
for ci,c,L,cars in LEGS:
    m=len(L)
    for i in range(m-1):
        if cars[i+1]==cars[i]: continue
        t1,a1,X,o1=L[i]; t2=L[i+1][0]
        if cars[i+1]<cars[i]: events.append((t1.dep(X) if t1 is t2 else t1.arr(X),"cut",X,cars[i]-cars[i+1]))
        else: events.append((t2.arr(X) if t1 is t2 else t2.dep(X),"join",X,cars[i+1]-cars[i]))
        if not _cc(L,i): bad.append(t2)
    if dissolved(c): events.append((c[-1].arr(c[-1].d),"in",c[-1].d,cars[-1]))
    if NIGHT and c[0].dep(c[0].o)>=T(10,0) and c[0].kind!="回送": outs.append((c[0].dep(c[0].o),"out",c[0].o,cars[0],ci))      # 昼すぎ以降に、着いた編成の折返しでなく出る列車：車庫の車両で編成を組んで出す
for i,c in enumerate(chains):
    for t in c: t.unyo=i+1
cuts=[e for e in events if e[1]=="cut"]; joins=[e for e in events if e[1]=="join"]
def _by(L): return "、".join(f"{st} {sum(1 for x in L if x[2]==st)}回（{sum(x[3] for x in L if x[2]==st)}両）" for st in sorted({x[2] for x in L},key=lambda s:-sum(1 for x in L if x[2]==s)))
print("運用",len(chains),"本  切り離し",len(cuts),"回："+_by(cuts)+("　／増結 "+str(len(joins))+"回："+_by(joins) if joins else ""))
if bad: print("両数の決まりに合わない列車",len(bad),[(t.kind,t.o,t.d,fmt(t.dep(t.o)),t.cars) for t in bad][:8])
# ---- 3) 切り離した車両の置き場所と、増結する車両の届け方。駅ごとの「置いてある車両（両）」の出入りを時刻順に帳簿につける
led={}                       # 駅 → [(時刻, 増減の両数)]
def bal(X,t): return sum(d for tt,d in led.get(X,[]) if tt<=t)
FLOOR=Counter()             # 車庫（DEPOTS）で、夜を越す予備の車両として置いておく両数（にマイナスをつけたもの）。車庫での増結・出庫が帳簿を下げたぶん
def can_take(X,t,n): return all(bal(X,x)-n>=FLOOR[X] for x in [t]+[tt for tt,_ in led.get(X,[]) if tt>t])
def depot_take(X,t,n):      # 車庫そのものでの増結・出庫：予備の車両から出す（足りなければ、夜を越す予備を増やす）
    note(X,t,-n); FLOOR[X]=min(FLOOR[X],min(bal(X,tt) for tt,_ in led[X]))
def note(X,t,d): led.setdefault(X,[]).append((t,d))
unit_trains=[]
def unit_run(a,b,n,what,t_dep=None,t_arr=None,src_ok=None,span=3600):
    """車両だけの回送 a→b。t_dep：これ以降のいちばん早い時刻、t_arr：これまでに着くいちばん遅い時刻。蓮木線と就島側の本線のあいだは学院前で折り返す2本にする"""
    legs=[(a,b)] if _cost(a,b)<1000 else [(a,"学院前"),("学院前",b)]
    n0=len(all_conf2(tr)[0])
    for d in range(0,span if t_dep is not None else 2700,15):      # span：t_dep から探す幅（秒）。夜の車両回送は 10800（奥雲線は最終列車のあと 24:33 以降でないと入らない）
        ks=[]
        if t_dep is not None:
            t=t_dep+d
            for x,y in legs:
                k=Train("","回送",x,y,t); k.compute(); ks.append(k); t=k.arr(y)+420
        else:
            t=t_arr-d
            for x,y in reversed(legs):
                k=Train("","回送",x,y,0); k.compute(); k.dep0=t-k.arr(y); k.compute(); ks.insert(0,k); t=k.dep(x)-420
        for i,k in enumerate(ks):
            k.frozen=True; k.nolink=True; k.label="回送"; k.note=what; k.cars=n; k.slow={}; k.unyo=0
            if i: k.src=ks[i-1]
        if src_ok is not None and not src_ok(ks[0].dep(a)): continue
        if len(all_conf2(tr+ks)[0])<=n0:
            tr.extend(ks); unit_trains.extend(ks); return ks
    return None
def legs_txt(ks): return " → ".join(f"{k.o}{fmt(k.dep(k.o))}発 {k.d}{fmt(k.arr(k.d))}着" for k in ks)
short=Counter()
for t,kind,X,n,ci in sorted([e+(None,) for e in events]+outs,key=lambda e:(e[0],e[1]!="cut")):
    if kind=="in": note(X,t,n); continue
    if kind=="out":
        c=chains[ci]; h=c[0]
        if X in DEPOTS: depot_take(X,t-READY,n); print(f"車庫から出す編成 {X} {fmt(t)}発 {h.kind}{h.d}行（{n}両）"); continue
        S=min(("新狛野","就島"),key=lambda S:_cost(S,X)); n0=len(all_conf2(tr)[0]); ok=False
        for lead in range(240,1801,15):
            k=Train("","回送",S,X,0); k.compute(); k.dep0=t-lead-k.arr(X); k.compute()
            k.frozen=True; k.nolink=True; k.label="回送"; k.note="出庫の送り込み"; k.cars=n; k.slow={}; k.unyo=getattr(h,"unyo",0)
            old=getattr(h,"src",None); h.src=k
            if len(all_conf2(tr+[k])[0])<=n0:
                tr.append(k); c.insert(0,k); note(S,k.dep(S),-n); ok=True
                print(f"車庫から出す編成 {S}{fmt(k.dep(S))}発 → {X}{fmt(k.arr(X))}着（回送）… {h.kind}{h.d}行 {fmt(t)}発（{n}両）"); break
            h.src=old
        if not ok: print("車庫から出す回送が入らない",X,fmt(t))
        continue
    if kind=="cut":
        if X in DEPOTS: note(X,t,n); continue                 # 車庫のとなりで切り離した車両は、そのまま車庫へ
        if bal(X,t)+n<=DAY_STORE.get(X,0): note(X,t,n); continue
        ks=unit_run(X,HAUL[X],n,"切り離した車両の入庫",t_dep=t+READY)
        if ks: note(HAUL[X],ks[-1].arr(HAUL[X]),n); print(f"切り離した車両の回送 {legs_txt(ks)} {n}両（{fmt(t)}着の編成から）")
        else: note(X,t,n); print("切り離した車両の回送が入らない",X,fmt(t))
        continue
    # 増結：発車の READY 秒前までに、その駅に車両があること
    if X in DEPOTS: depot_take(X,t-READY,n); continue          # 車庫のとなりでの増結は、車庫の車両から
    if can_take(X,t-READY,n): note(X,t-READY,-n); continue
    done=False
    for S in sorted([S for S in led if S!=X],key=lambda S:_cost(S,X)):
        ks=unit_run(S,X,n,"増結用の車両の回送",t_arr=t-READY,src_ok=lambda td,S=S:can_take(S,td,n))
        if ks: note(S,ks[0].dep(S),-n); done=True; print(f"増結用の車両の回送 {legs_txt(ks)} {n}両（{X} {fmt(t)}発の編成へ）"); break
    if not done:
        short[X]+=n; print(f"増結する車両が足りない・届けられない：{X} {fmt(t)}発 {n}両")
# 置いたままの車両でふさがる線を判定に入れる（ops.turn_occ が、外で待てる編成の数からこのぶんを引く）
ops.STORED.clear()
for X in DAY_STORE:
    lines=0
    for tt in sorted({tt for tt,_ in led.get(X,[])}):
        nl=(bal(X,tt)+ops.SIDING_CARS-1)//ops.SIDING_CARS
        if nl!=lines: ops.STORED.setdefault(X,[]).append((tt,nl-lines)); lines=nl
cs,links=all_conf2(tr)
print("車両を置いた状態での競合",len(cs))
for c in cs[:8]: print("   ",c[0],fmt(c[1]),[(x.kind,x.o,x.d,fmt(x.dep(x.o))) for x in involved(c)][:3],c[4])
for t in tr:
    if getattr(t,"src",None) is not None: links[t]=t.src
# ---- 4) 終日のダイヤのとき：両数のつじつま。朝の始発の編成の両数（駅ごと）と、1日の終わりにその駅にある車両（走り終えた編成＋置いてある車両）を比べ、
#         余る駅から足りない駅へ、夜に車両だけを回送で運ぶ（翌朝までにつなぐ）
low={X:min(bal(X,tt) for tt,_ in led[X])-FLOOR[X] for X in led}
if any(FLOOR.values()): print("車庫で夜を越す予備の車両：",{X:-v for X,v in FLOOR.items() if v})
if any(v<0 for v in low.values()) or short: print("昼のあいだに車両が足りなくなる駅（帳簿がマイナス）：",{X:v for X,v in low.items() if v<0},"／届けられなかった増結",dict(short))
if NIGHT:
    TE=T(22,0)
    def car_diff():
        need=Counter(); have=Counter()
        for c in chains:
            if c[0].dep(c[0].o)<T(10,0): need[c[0].o]+=c[0].cars_o
            if not dissolved(c): have[c[-1].d]+=c[-1].cars_d
        for X in led: have[X]+=bal(X,T(30,0))
        return {X:have[X]-need[X] for X in set(need)|set(have) if have[X]!=need[X]}
    df=car_diff(); print("1日の終わりの両数の過不足（＋は余り）：",dict(sorted(df.items(),key=lambda z:-z[1])) or "なし","合計",sum(df.values()))
    sur={X:v for X,v in df.items() if v>0}; de={X:-v for X,v in df.items() if v<0}; um=[]
    while sur and de:
        a,b=min(((a,b) for a in sur for b in de),key=lambda ab:_cost(*ab)); n=min(sur[a],de[b],8); um.append((a,b,n))
        sur[a]-=n; de[b]-=n
        if not sur[a]: del sur[a]
        if not de[b]: del de[b]
    for a,b,n in um:
        ks=unit_run(a,b,n,"増結用の車両の回送",t_dep=TE,span=10800)
        if ks: note(a,ks[0].dep(a),-n); note(b,ks[-1].arr(b),n); print(f"夜に車両を運ぶ回送 {legs_txt(ks)} {n}両")
        else:
            # 直接は入らないとき：車両を置いている別の駅 X から b へ運び、そのぶんを a から X へ埋める（2026-11-11。始発を遅らせる候補で 蓮木市→奥雲温泉 が入らなかった）
            done=False
            for X in sorted([X for X in led if X not in (a,b) and bal(X,T(30,0))>=n],key=lambda X:_cost(X,b)):
                k1=unit_run(X,b,n,"増結用の車両の回送",t_dep=TE,span=10800)
                if not k1: continue
                note(X,k1[0].dep(X),-n); note(b,k1[-1].arr(b),n); print(f"夜に車両を運ぶ回送 {legs_txt(k1)} {n}両（{a} からは直接入らないので {X} の車両を運ぶ）")
                k2=unit_run(a,X,n,"増結用の車両の回送",t_dep=TE,span=10800)
                if k2: note(a,k2[0].dep(a),-n); note(X,k2[-1].arr(X),n); print(f"夜に車両を運ぶ回送 {legs_txt(k2)} {n}両（{X} から運んだぶんを埋める）")
                else: print("夜に車両を運ぶ回送が入らない",a,"→",X,n,"両（埋めるぶん）")
                done=True; break
            if not done: print("夜に車両を運ぶ回送が入らない",a,"→",b,n,"両")
    print("運んだあとの両数の過不足：",car_diff() or "なし")
# ---- 4') 仕上げ：相手のいない停車の延長を、その駅から先を早める形で縮める（2026-11-11 本人の指示「15分45秒ぶん直す」）
#   回送まで入れ終えた状態で、停車の延長のうち、そのあいだに 待避・先発・接続・単線の行き違い の相手が1本もないものを時刻順に見て、
#   TRIM 秒刻み（既定 15）で、縮められるだけ縮める。始発駅の発車は変えない（その駅より手前を遅らせる形は使わない）。
#   競合が増えない・同じ種別の追い越しにならない・朝7〜11時の軒屋着が変わらない・折返しのつながり（運用）が変わらない ものだけ。
#   朝だけのダイヤ（11:30 ごろまで）を通すときは、10時より前の停車だけを見る（描いている範囲の端は、後ろの列車がまだないので縮みすぎる）。
#   奥雲線の各停の犬塚の停車（本人の指示）には触らない。日中の列車も対象（日中は快速の15秒などごく小さいものだけが縮む）。TRIM=0 でやめる
TRIM=int(os.environ.get("TRIM","15"))
if TRIM:
    _SLS=set(net.MN[net.MN.index("犬塚"):])
    def _lonely(t,x):
        a,d=t.arr(x),t.dep(x)
        for u in tr:
            if u is t or x not in u.times: continue
            if u.dir==t.dir:
                if u.o==x:
                    if a<=u.dep(x)<=d and [y for y in u.route[1:3] if y in t.times]: return False
                elif u.d==x:
                    if a-60<=u.arr(x)<=d: return False
                elif a<=u.arr(x) and u.dep(x)<=d and (u.arr(x)>a or u.dep(x)<d): return False
            elif (x in _SLS and x!="犬塚") or (x=="犬塚" and "下岩田" in t.times and "下岩田" in u.times):
                if u.arr(x)<=d and u.dep(x)>=a: return False
        return True
    def _skov(k):
        for B in tr:
            if B is k or B.kind!=k.kind or B.dir!=k.dir or B.kind=="回送": continue
            com=[x for x in k.route if x in B.times]
            if len(com)<2: continue
            a0,b0=k.dep(com[0]),B.dep(com[0]); a1,b1=k.arr(com[-1]),B.arr(com[-1])
            if abs(a0-b0)<=3600 and (a0-b0)*(a1-b1)<0: return True
        return False
    def _linkmap():
        lk,_=link_nl(tr)
        for t in tr:
            if getattr(t,"src",None) is not None: lk[t]=t.src
        return {id(d):(id(a) if a is not None else None) for d,a in lk.items()}
    cand=sorted([(t.arr(x),i,t,x) for i,t in enumerate(tr) for x,h in t.hold.items() if h>0 and x in t.times and x not in (t.o,t.d) and not (t.note=="奥雲線" and x=="犬塚") and getattr(t,"split",None)!=x and (NIGHT or t.arr(x)<T(10,0)) and _lonely(t,x)],key=lambda z:z[:2])
    lm0=_linkmap(); trimmed=[]
    for _,_,t,x in cand:
        n0=len(all_conf2(tr)[0]); h0=dict(t.hold); h=h0[x]; a1=t.arr(t.d); ok=None
        if t.kind!="回送" and t.d=="軒屋" and T(7,0)<=a1<=T(11,0): continue
        for cut in range(h,0,-TRIM):
            t.hold=dict(h0); t.hold[x]=h-cut
            if t.hold[x]<=0: del t.hold[x]
            t.compute()
            if len(all_conf2(tr)[0])<=n0 and not _skov(t) and _linkmap()==lm0: ok=cut; break
        if ok: trimmed.append((t,x,h,ok,a1))
        else: t.hold=h0; t.compute()
    print(f"仕上げ：相手のいない停車の延長 {len(cand)} か所（計 {sum(t.hold.get(x,0) for _,_,t,x in cand)+sum(c for _,_,_,c,_ in trimmed)}秒）のうち {len(trimmed)} か所を縮めた。計 {sum(c for _,_,_,c,_ in trimmed)}秒（{sum(c for _,_,_,c,_ in trimmed)//60}分{sum(c for _,_,_,c,_ in trimmed)%60:02d}秒）")
    for t,x,h,c,a1 in trimmed: print(f"   {t.kind} {t.o}{fmt(t.dep(t.o))}発 {t.d}行　{x} +{h}秒 → +{h-c}秒。{t.d} {fmt(a1)}着 → {fmt(t.arr(t.d))}着")
    print("仕上げのあとの競合",len(all_conf2(tr)[0]))
# ---- 4'') 待避のあとの発車を詰める（既定で行う。PASSTRIM=0 でやめる。2026-11-11 本人の指示「日中パターンの待避も30秒に詰めて」）
#   待避で止まっている列車は、抜く列車が出てから sched.H_PASS 秒（30秒）で発車できるようになった（それまでは90秒）。
#   日中パターンの待避は90秒後に発車する時刻のままなので、その余りを、その駅から先を早める形で詰める（15秒刻み、時刻順、3回まで繰り返す）。
#   最初の待避の駅で60秒詰めると、その先の時刻が全部60秒早くなり、次の待避の駅でも抜く列車の30秒後に出る形になる。
#   条件は 4' と同じ：競合が増えない・同じ種別の追い越しにならない・朝7〜11時の軒屋着が変わらない・折返しのつながり（運用）が変わらない。
#   日中パターンの列車の時刻が終日にわたって変わる。はじめは候補として別名で出し、本人が採用した
PASSTRIM_RUSH=os.environ.get("PASSTRIM_RUSH","1")=="1"      # 既定 1：朝7〜11時に軒屋へ着く上り（案19 の軒屋着）の待避も詰める（2026-11-11 本人の指示「朝ラッシュの待避も30秒に詰めて」。候補を見て本人が採用した）。0 で案19 の軒屋着のまま
PASSTRIM=os.environ.get("PASSTRIM","1")=="1"      # 既定 1：2026-11-11 に本人が候補を見て「採用する」と決めた。PASSTRIM=0 で詰める前の形
if PASSTRIM and TRIM:
    from sched import H_PASS
    def _ovs(t,x):
        a,d=t.arr(x),t.dep(x); nx=t.route[t.route.index(x)+1]
        return [u for u in tr if u is not t and u.dir==t.dir and x in u.times and nx in u.times and u.o!=x and u.d!=x and a<=u.arr(x) and u.dep(x)<=d and (u.arr(x)>a or u.dep(x)<d)]
    lm0=_linkmap(); ptrim={}
    for rnd in range(3):
        cand=sorted([(t.arr(x),i,t,x) for i,t in enumerate(tr) for x,h in t.hold.items() if h>0 and x in t.times and x not in (t.o,t.d) and not (t.note=="奥雲線" and x=="犬塚") and getattr(t,"split",None)!=x and (NIGHT or t.arr(x)<T(10,0))],key=lambda z:z[:2])
        nch=0
        for _,_,t,x in cand:
            if x not in t.hold: continue
            ov=_ovs(t,x)
            if not ov: continue
            cut0=min(t.hold[x],int(t.dep(x)-max(u.dep(x) for u in ov)-H_PASS)//15*15)
            if cut0<=0: continue
            if not PASSTRIM_RUSH and t.kind!="回送" and t.d=="軒屋" and T(7,0)<=t.arr(t.d)<=T(11,0): continue
            n0=len(all_conf2(tr)[0]); h0=dict(t.hold); h=h0[x]; ok=None
            for cut in range(cut0,0,-15):
                t.hold=dict(h0); t.hold[x]=h-cut
                if t.hold[x]<=0: del t.hold[x]
                t.compute()
                if len(all_conf2(tr)[0])<=n0 and not _skov(t) and _linkmap()==lm0: ok=cut; break
            if ok: ptrim[(id(t),x)]=(t,x,ptrim.get((id(t),x),(t,x,0))[2]+ok); nch+=1
            else: t.hold=h0; t.compute()
        print(f"待避のあとの発車を詰める（{rnd+1}回目）：{nch} か所")
        if not nch: break
    tot=sum(c for _,_,c in ptrim.values())
    print(f"待避のあとの発車を詰めた：{len(ptrim)} か所、計 {tot}秒（{tot//60}分{tot%60:02d}秒）。列車 {len({id(t) for t,_,_ in ptrim.values()})} 本。競合 {len(all_conf2(tr)[0])}")
    for (kind,o,d,x,c),n in sorted(Counter((t.kind,t.o,t.d,x,c) for t,x,c in ptrim.values()).items(),key=lambda z:-z[1]): print(f"   {kind} {o}→{d}　{x} −{c}秒　{n}本")
# ---- 4''') 検査のための入出庫（2026-11-11 本人の指示「回送を足して直す」。DEPOT_SWAP=0 でやめる。既定は "学院前:就島"）
#   学院前で夜を越して、その日のうちに学院前へ戻ってくる運用（蓮木線内を往復する編成）は、車庫に入る機会がない
#   （unyo.py の日またぎの順序で、車庫に入らない日が4日続く箇所になる。順序の入れ替えでは直らない）。
#   そこで、その運用の最後の列車が学院前に着いたあと、回送で就島車庫へ入れる（検査のための入庫）。代わりに、朝いちばんに学院前を出る
#   別の運用の編成を、就島車庫から回送で出す（検査のための出庫）。ほかの列車の時刻は変えない（競合が増えない時刻に回送を足すだけ）。
#   朝だけのダイヤでは1日の終わりが分からないので、終日のダイヤと同じになるよう、朝いちばんに学院前を出る運用に出庫の回送だけを足す
DSWAP=os.environ.get("DEPOT_SWAP","学院前:就島")
if DSWAP not in ("","0"):
    _X,_S=DSWAP.split(":"); _REV=420          # 学院前で向きを変える時間（車両だけの回送 unit_run と同じ）
    _heads=sorted([c for c in chains if c[0].o==_X and c[0].dep(_X)<T(10,0) and not dissolved(c) and getattr(c[0],"unyo",None)!=0],key=lambda c:c[0].dep(_X))
    _loops=[c for c in _heads if c[-1].d==_X] if NIGHT else []
    _outs=[c for c in _heads if c not in _loops][:len(_loops) if NIGHT else 1]
    _n0=len(all_conf2(tr)[0])
    for c in _loops:
        l=c[-1]; ok=False
        for d in range(0,3600,15):
            k=Train("","回送",_X,_S,l.arr(_X)+_REV+d); k.frozen=True; k.nolink=True; k.src=l; k.label="回送"; k.note="検査のための入庫"
            k.cars=getattr(l,"cars_d",l.cars); k.slow={}; k.unyo=getattr(l,"unyo",0); k.compute()
            if len(all_conf2(tr+[k])[0])<=_n0:
                tr.append(k); c.append(k); ok=True
                print(f"検査のための入庫 {_X}{fmt(k.dep(_X))}発 → {_S}{fmt(k.arr(_S))}着（{fmt(l.arr(_X))}に着いた{l.kind}の編成。{k.cars}両）"); break
        if not ok: print("検査のための入庫の回送が入らない",_X,fmt(l.arr(_X)))
    for c in _outs:
        h=c[0]; t=h.dep(_X); ok=False
        for lead in range(_REV,1801,15):
            k=Train("","回送",_S,_X,0); k.compute(); k.dep0=t-lead-k.arr(_X); k.compute()
            k.frozen=True; k.nolink=True; k.label="回送"; k.note="検査のための出庫"; k.cars=getattr(h,"cars_o",h.cars); k.slow={}; k.unyo=getattr(h,"unyo",0)
            old=getattr(h,"src",None); h.src=k
            if len(all_conf2(tr+[k])[0])<=_n0:
                tr.append(k); c.insert(0,k); ok=True
                print(f"検査のための出庫 {_S}{fmt(k.dep(_S))}発 → {_X}{fmt(k.arr(_X))}着 … {h.kind}{h.d}行 {fmt(t)}発（{k.cars}両）"); break
            h.src=old
        if not ok: print("検査のための出庫の回送が入らない",_X,fmt(t))
    cs,links=all_conf2(tr)
    for t in tr:
        if getattr(t,"src",None) is not None: links[t]=t.src
    print("検査のための入出庫を足したあとの競合",len(cs))
# ---- 5) 置き場所の確認
print("置き場所の確認（1線に8両まで。夜は置ける数 CAP_STABLE、昼は留置線・引上線・車庫の数 SIDING と比べる）")
yard={}
for X in sorted(SIDING,key=lambda x:-SIDING[x]):
    ev=[]
    for D,A in links.items():       # 折返しの待ちが15分を超える編成は、ホームを空けて留置線・引上線で待つ扱い（ops.LONG）
        if A is not None and D.o==X and D.dep(X)-A.arr(X)>ops.LONG: ev+=[(A.arr(X),1,"折"),(D.dep(X),-1,"折")]
    L=list(led.get(X,[]))
    if not NIGHT: L+=[(k.arr(X),k.cars) for k in tr if k.kind=="回送" and k.d==X and k.note=="増発車の入庫"]      # 朝だけのダイヤでは、車庫に入った増発車も置いてある車両に数える
    tot=-FLOOR[X]; lines=(tot+ops.SIDING_CARS-1)//ops.SIDING_CARS; peak=tot       # 車庫は、夜を越す予備の車両を最初から置いてある
    if lines: ev.append((0,lines,"車"))
    for tt,d in sorted(L):
        if tt>=T(22,0): break            # 22時以降に運び込む車両は、夜を越す編成につなぐぶんなので昼の置き場所には数えない
        tot+=d; nl=(tot+ops.SIDING_CARS-1)//ops.SIDING_CARS; peak=max(peak,tot)
        if nl!=lines: ev.append((tt,nl-lines,"車")); lines=nl
    ev.sort(key=lambda z:(z[0],z[1])); cur={"折":0,"車":0}; wmax=0; umax=0; plat=(0,0)
    for t,d,w in ev:
        cur[w]+=d
        if t>=T(8,0):
            wmax=max(wmax,cur["折"]); umax=max(umax,cur["車"])
            if cur["折"]+cur["車"]-SIDING[X]>plat[0]: plat=(cur["折"]+cur["車"]-SIDING[X],t)
    nightn=len([c for c in chains if c[0].o==X and c[0].dep(X)<T(10,0)])
    yard[X]={"night":nightn,"cap":CAP_STABLE.get(X,0),"siding":SIDING[X],"cars":peak,"units":umax,"wait":wmax,"plat":plat[0],"at":plat[1]}
    print(f"   {X}：夜 {nightn}／{CAP_STABLE.get(X,0)}"+(" 超過" if nightn>CAP_STABLE.get(X,0) else "")+f"　昼に置く車両 最大{peak}両＝{umax}線／留置線など {SIDING[X]}線"+(" 超過" if umax>SIDING[X] else "")
          +f"　折返し待ち（15分超）の最大 {wmax}本"+(f" → 留置線などに入りきらず、ホームで待つことになるのが最大 {plat[0]}本（{fmt(plat[1])}）" if plat[0]>0 else ""))
for t in tr: t.yard=None
tr[0].yard=yard; tr[0].stored={k:list(v) for k,v in ops.STORED.items()}          # 書き出し（export.py）で使う。stored：置いたままの車両でふさがる線（番線の割り当て tracks.py が、判定と同じ在線を作るのに使う）
# ---- 夜間滞泊（始発前に各駅にいる編成）
start={}
edge=[]
for c in chains:
    h=c[0]; st=h.o
    if h.dep(st)>=T(10,0): edge.append(h); continue      # 描いている範囲の端で相手の到着がまだ作られていないだけの発車は、夜を越す編成に数えない
    start.setdefault(st,[]).append(h)
print("滞泊",{k:len(v) for k,v in start.items()},"合計",sum(len(v) for v in start.values()),"／範囲の端で相手がない発車",[(h.o,fmt(h.dep(h.o)),h.kind) for h in edge])
import trainno
_over=trainno.assign(tr)      # 列車番号（規則は trainno.py）
if _over: print("列車番号が枠に入りきらない・重なる列車",len(_over),[(t.kind,t.o,t.d,fmt(t.dep(t.o)),t.no) for t in _over][:6])
json.dump({"chains":len(chains)},open("meta.json","w"))
pickle.dump((tr,chains,start),open(OUT,"wb")); print("保存",OUT)
