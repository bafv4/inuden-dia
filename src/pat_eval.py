# 日中パターンの評価：始発駅の発車・終着駅の到着の詰まり、待避（追い抜かれ）の回数と待ち時間
# 使い方（data で）: PYTHONPATH=../src python ../src/pat_eval.py cyc_xxx.pkl
import sys,pickle
from sched import *
from build import T
W0,W1=T(10,0),T(11,0)   # 1時間分（パターンは毎時同じ）
GAP_MIN=150             # これより詰まった発着は減点（秒）
def events(tr):
    """{(駅,'発'/'着'): [(時刻,種別,列車)]}  始発駅の発車・終着駅の到着だけ"""
    ev={}
    for t in tr:
        a=t.dep(t.o)
        if W0<=a<W1: ev.setdefault((t.o,"発"),[]).append((a,t.kind,t))
        b=t.arr(t.d)
        if W0<=b<W1: ev.setdefault((t.d,"着"),[]).append((b,t.kind,t))
    return ev
def gaps(times):
    s=sorted(x%3600 for x in times)
    if len(s)<2: return []
    return [b-a for a,b in zip(s,s[1:])]+[s[0]+3600-s[-1]]
def spacing(tr):
    """駅ごと：全種別の最小間隔、同種別の間隔の理想（3600/本数）からのずれ"""
    out=[]
    for (st,k),L in sorted(ev_items(tr)):
        allg=gaps([x[0] for x in L])
        kinds={}
        for x in L: kinds.setdefault((x[1],x[2].note or ""),[]).append(x[0])
        same=[]
        for kd,ts in kinds.items():
            g=gaps(ts)
            if g: same.append((kd,min(g),max(g),3600//len(ts)))
        out.append((st,k,len(L),min(allg) if allg else None,same,sorted(x%3600 for x,_,_ in L)))
    return out
def ev_items(tr): return events(tr).items()
def overtakes(tr):
    """W0〜W1 に始発駅を出た列車が、途中で後続に抜かれる回数と待避駅"""
    res=[]
    L=[t for t in tr if W0<=t.dep(t.o)<W1]
    for A in L:
        for B in tr:
            if B is A or B.dir!=A.dir: continue
            com=[x for x in A.route if x in B.times]
            if len(com)<2: continue
            # 共通区間の最初と最後で順序が入れ替わる＝抜かれる（終着後・始発前は除く）
            a0,b0=A.dep(com[0]),B.dep(com[0])
            a1,b1=A.arr(com[-1]),B.arr(com[-1])
            if a0<b0 and b1<a1:
                # 抜かれた駅：A が停まっていて B がその間に通る駅
                where=next((x for x in com if A.stopped(x) and A.arr(x)<=B.arr(x)<=A.dep(x)),"?")
                res.append((A,B,where))
    return res
XFER={"線内":("学院前",("各停","急行")),"奥雲線":("新狛野",("快速","急行"))}
def transfers(tr):
    """支線の各停と本線の乗り換え待ち（秒、最低60秒）。下りは本線から支線へ、上りは支線から本線へ"""
    out=[]
    for t in tr:
        if t.note not in XFER or not (W0<=t.dep(t.o)<W1): continue
        st,kinds=XFER[t.note]
        if st not in t.times: st=t.o if t.dir=="D" else t.d   # 旧パターン（奥雲線が犬塚始発）
        mains=[x for x in tr if x.kind in kinds and x.note not in XFER and x.dir==t.dir and st in x.times and x.stopped(st)]
        if t.o==st:   # 支線へ：本線列車が着いてから支線が出るまで
            w=[t.dep(st)-x.arr(st) for x in mains if t.dep(st)-x.arr(st)>=60]
        else:         # 本線へ：支線が着いてから本線列車が出るまで
            w=[x.dep(st)-t.arr(st) for x in mains if x.dep(st)-t.arr(st)>=60]
        out.append((t,st,min(w) if w else 3600))
    return out
def score(tr):
    sp=spacing(tr); ov=overtakes(tr)
    # 詰まり：駅ごとの目安間隔（均等割りの6割）に足りない秒を、すべての間隔について合計
    tight=0
    for st,k,n,mg,same,ts in sp:
        if n<2: continue
        target=0.6*3600/n
        tight+=sum(max(0,target-g) for g in gaps(ts))
    same_dev=sum(max(0,ideal-mn) for *_,same,_ in sp for _,mn,mx,ideal in same)
    hold=sum(sum(t.hold.values())+(t.dep0-t.anchor) for t in tr if W0<=t.dep(t.o)<W1)
    xf=sum(w for _,_,w in transfers(tr))
    return {"待避回数":len(ov),"待ち秒":hold,"詰まり":tight,"同種別のずれ":same_dev,"乗換待ち秒":xf}
if __name__=="__main__":
    tr,S,off,up=pickle.load(open(sys.argv[1],"rb"))
    for t in tr: t.compute()
    print("オフセット 下り",off,"上り",up)
    print("== 始発駅の発車・終着駅の到着（毎時の分秒）")
    for st,k,n,mg,same,ts in spacing(tr):
        tl=" ".join(f"{x//60:02d}:{x%60:02d}" for x in ts)
        sm=" / ".join(f"{kd[0]}{'('+kd[1]+')' if kd[1] else ''} 間隔{mn//60}:{mn%60:02d}〜{mx//60}:{mx%60:02d}" for kd,mn,mx,_ in same)
        print(f"{st}{k} {n}本 最小間隔 {mg//60 if mg else '-'}:{mg%60 if mg else 0:02d}  [{tl}]  {sm}")
    print("== 待避（10時台に始発駅を出た列車）")
    for A,B,w in overtakes(tr):
        print(f"  {A.kind}{A.o}→{A.d} {fmt(A.dep(A.o))} が {w} で {B.kind}{B.o}→{B.d} に抜かれる")
    print("== 待ち（10時台に始発駅を出た列車。始発の繰り下げ＝shift）")
    for t in sorted([t for t in tr if W0<=t.dep(t.o)<W1],key=lambda t:(t.dir,t.dep(t.o))):
        sh=t.dep0-t.anchor
        if t.hold or sh:
            print(f"  {t.dir} {t.kind}{t.o}→{t.d} {fmt(t.dep(t.o))} shift{sh} {t.hold}")
    print("== 支線の乗り換え待ち（10時台）")
    for t,st,w in transfers(tr):
        print(f"  {t.kind}{t.o}→{t.d} {fmt(t.dep(t.o))} {st}で {w//60}分{w%60:02d}秒")
    print("== 評価",score(tr))
