import os
from sched import *
TERM=["軒屋","新犬村","学院前","蓮木市","就島","高島","秋田台","新狛野","犬塚","奥雲温泉"]
MINTURN={"軒屋":240,"蓮木市":240,"奥雲温泉":180,"学院前":360,"高島":360}
def minturn(x): return MINTURN.get(x,240)
LONG=900  # これより長く待つ編成は留置線・車庫へ
def link(trains):
    """終端駅での折返しの対応づけ。戻り値: links(dep_train->arr_train or None), stabled{駅:数}"""
    for t in trains:
        if t.times is None: t.compute()
    links={}; stabled={}
    for X in set([t.o for t in trains]+[t.d for t in trains]):
        arrs=sorted([t for t in trains if t.d==X],key=lambda t:t.arr(X))
        deps=sorted([t for t in trains if t.o==X],key=lambda t:t.dep(X))
        pool=[]; ai=0
        for D in deps:
            while ai<len(arrs) and arrs[ai].arr(X)+minturn(X)<=D.dep(X):
                pool.append(arrs[ai]); ai+=1
            if pool:
                A=pool.pop(0); links[D]=A
            else:
                links[D]=None; stabled[X]=stabled.get(X,0)+1
    return links,stabled
# 留置線・引上線・折返し線・車庫の線の数と長さ（ホームとは別の線。昼も使える）。2026-11-11 に本人が決めた値。
#   駅の留置線・引上線・折返し線は配線図「犬村電鉄 線路配線図.html」どおりの線数で、長さはすべて8両：
#     軒屋 留置線2、学院前 折返し線2、高島 引上線2、秋田台 留置線2、犬塚 引上線3（配線図の2線から1線増やす）、蓮木市 留置線2（新設）
#   車庫は配線図の仮4線から増やす：狛野車庫（新狛野の下り方）12線・各8両＋検車設備、就島車庫 8線・各8両
#   奥雲温泉・新犬村にはホームのほかに線はない
SIDING={"軒屋":2,"学院前":2,"就島":8,"高島":2,"秋田台":2,"新狛野":12,"犬塚":3,"蓮木市":2,"奥雲温泉":0}
SIDING_CARS=8      # 1線に置ける両数（どの線も同じ）
# 夜に編成を置いてよいホームの線（本人が決めた）：待避駅は副本線2線（本線は空ける。高島は中線2線）、終点の軒屋・蓮木市・奥雲温泉はホーム全部。
# 学院前は外側が本線・内側が蓮木線の本線なので、ホームには置かない
NIGHT_PLAT={"軒屋":4,"蓮木市":3,"奥雲温泉":2,"新犬村":2,"就島":2,"高島":2,"秋田台":2,"新狛野":2,"犬塚":2,"学院前":0}
STORED={}      # 駅 → [(時刻, 線の数)]：その時刻から、切り離した車両などでふさがっている線（finalize.py が入れる）
OLDOCC=os.environ.get("INUDEN_OLDOCC")=="1"     # 1 にすると、2026-11-11 より前の数え方（外で待てる編成の数に限りがない）に戻る
def turn_occ(trains,links):
    """折返し・滞泊編成の在線（駅の番線）。ホームを空けて待つ編成（15分を超える折返し待ち。学院前・高島は折返しのすべて）は、
    その駅の留置線・引上線・折返し線の数（SIDING）までしか外へ出せない。空きがなければ、着いたホームに発車まで居続ける。
    2026-11-11 に本人の了承を得てこの数え方にした。採用済みの日中パターンと朝の案19 は、数え方を変えても競合0件のまま（occ_impact.py で照合）"""
    if OLDOCC: return turn_occ_old(trains,links)
    occ={}
    def add(key,s,e,tr): occ.setdefault(key,[]).append((s,e,tr))
    used=set(); pend={}          # pend[駅]＝[(外へ出る時刻, 戻る時刻, 着いた列車, 出る列車)]
    for D,A in links.items():
        X=D.o
        if A is not None: used.add(A)
        if X in ("軒屋","蓮木市","奥雲温泉"):
            key=(X,"*")
            if A is None: add(key,D.dep(X)-600,D.dep(X)+PAD,D)
            elif D.dep(X)-A.arr(X)<=LONG: add(key,A.arr(X),D.dep(X)+PAD,D)
            else: pend.setdefault(X,[]).append((A.arr(X)+180,D.dep(X)-480,A,D))
            continue
        if X=="学院前":
            if A is None: add((X,D.dir,"H"),D.dep(X)-120,D.dep(X)+PAD,D)
            else: pend.setdefault(X,[]).append((A.arr(X)+90,D.dep(X)-120,A,D))
            continue
        if X=="高島":
            if A is None: add((X,D.dir),D.dep(X)-180,D.dep(X)+PAD,D)
            else: pend.setdefault(X,[]).append((A.arr(X)+120,D.dep(X)-180,A,D))
            continue
        # 2面4線の折返し（下り側で折り返して上りへ）・車庫
        if A is not None and D.dep(X)-A.arr(X)<=LONG: add((X,A.dir),A.arr(X),D.dep(X)+PAD,D)
        elif A is None: add((X,D.dir),D.dep(X)-240,D.dep(X)+PAD,D)
        else: pend.setdefault(X,[]).append((A.arr(X)+120,D.dep(X)-240,A,D))
    for X,L in pend.items():
        free=[]                     # 外で待っている編成が戻る時刻（線ごと）
        for s,e,A,D in sorted(L,key=lambda z:z[0]):
            if e<=s: out=True       # 着いてすぐ出る：外で待つ時間がない（もとの数え方と同じ在線）
            else:
                free=[f for f in free if f>s]
                out=len(free)<SIDING.get(X,0)-sum(n for t,n in STORED.get(X,[]) if t<=s)
                if out: free.append(e)
            if out:
                if X in ("軒屋","蓮木市","奥雲温泉"): add((X,"*"),A.arr(X),A.arr(X)+180,A); add((X,"*"),D.dep(X)-480,D.dep(X)+PAD,D)
                elif X=="学院前": add((X,A.dir,"H"),A.arr(X),A.arr(X)+90,A); add((X,D.dir,"H"),D.dep(X)-120,D.dep(X)+PAD,D)
                elif X=="高島": add((X,A.dir),A.arr(X),A.arr(X)+120,A); add((X,D.dir),D.dep(X)-180,D.dep(X)+PAD,D)
                else: add((X,A.dir),A.arr(X),A.arr(X)+120,A); add((X,D.dir),D.dep(X)-240,D.dep(X)+PAD,D)
            else:                   # 外に空きがない：着いたホームに発車まで居続ける
                if X in ("軒屋","蓮木市","奥雲温泉"): add((X,"*"),A.arr(X),D.dep(X)+PAD,D)
                elif X=="学院前": add((X,D.dir,"H"),A.arr(X),D.dep(X)+PAD,D)
                else: add((X,A.dir),A.arr(X),D.dep(X)+PAD,D)
    for A in trains:
        X=A.d
        if A in used: continue
        if X in ("軒屋","蓮木市","奥雲温泉"): add((X,"*"),A.arr(X),A.arr(X)+180,A)
        elif X=="学院前": add((X,A.dir,"H"),A.arr(X),A.arr(X)+90,A)
        else: add((X,A.dir),A.arr(X),A.arr(X)+120,A)
    return occ
def turn_occ_old(trains,links):
    """もとの数え方（外で待てる編成の数に限りがない）。比べるために残してある"""
    occ={}
    def add(key,s,e,tr): occ.setdefault(key,[]).append((s,e,tr))
    used=set()
    for D,A in links.items():
        X=D.o
        if A is not None: used.add(A)
        if X in ("軒屋","蓮木市","奥雲温泉"):
            key=(X,"*")
            if A is None: add(key,D.dep(X)-600,D.dep(X)+PAD,D)
            elif D.dep(X)-A.arr(X)<=LONG: add(key,A.arr(X),D.dep(X)+PAD,D)
            else: add(key,A.arr(X),A.arr(X)+180,A); add(key,D.dep(X)-480,D.dep(X)+PAD,D)
            continue
        if X=="学院前":
            if A is not None: add((X,A.dir,"H"),A.arr(X),A.arr(X)+90,A)
            add((X,D.dir,"H"),D.dep(X)-120,D.dep(X)+PAD,D)
            continue
        if X=="高島":
            if A is not None: add((X,A.dir),A.arr(X),A.arr(X)+120,A)
            add((X,D.dir),D.dep(X)-180,D.dep(X)+PAD,D)
            continue
        # 2面4線の折返し（下り側で折り返して上りへ）・車庫
        if A is not None and D.dep(X)-A.arr(X)<=LONG:
            add((X,A.dir),A.arr(X),D.dep(X)+PAD,D)
        else:
            if A is not None: add((X,A.dir),A.arr(X),A.arr(X)+120,A)
            add((X,D.dir),D.dep(X)-240,D.dep(X)+PAD,D)
    for A in trains:
        X=A.d
        if A in used: continue
        if X in ("軒屋","蓮木市","奥雲温泉"): add((X,"*"),A.arr(X),A.arr(X)+180,A)
        elif X=="学院前": add((X,A.dir,"H"),A.arr(X),A.arr(X)+90,A)
        else: add((X,A.dir),A.arr(X),A.arr(X)+120,A)
    return occ
def cross_conf(trains,links):
    """2面4線駅で下り側から上りへ折り返す出発が、本線の列車と交差しないか"""
    out=[]
    for D,A in links.items():
        X=D.o
        if X not in ("就島","秋田台","新狛野","犬塚"): continue
        if A is None or D.dep(X)-A.arr(X)>LONG: continue
        if D.dir!="U": continue
        t0=D.dep(X)
        for T in trains:
            if T is D or T is A or X not in T.times: continue
            if T.o==X or T.d==X: continue
            tt=T.arr(X) if T.dir=="D" else T.dep(X)
            if abs(tt-t0)<60:
                out.append(("cross",t0,D,T,X,None,60-abs(tt-t0)))
    return out
def all_conf(trains):
    for t in trains: t.compute()
    links,_=link(trains)
    cs=conflicts(trains,turn_occ(trains,links))+cross_conf(trains,links)
    cs.sort(key=lambda c:c[1]); return cs,links
def resolve2(trains,c,maxwait,log):
    if c[0]=="cross":
        _,t0,D,T,X,_,need=c
        add=int(math.ceil((need+1)/15))*15
        D.dep0+=add
        if log is not None: log.append(f"折返交差 {D.id}@{X} +{add} ({T.id})")
        return True
    if c[0]=="occ":
        _,t,tr,cur,st,_,_=c
        if st==tr.o:   # 折返し・始発の列車が入れない → 発車を遅らせるのではなく、在線中の通過列車側を見る
            tr.dep0+=60
            if log is not None: log.append(f"始発在線 {tr.id}@{st} +60")
            return True
        if st==tr.d:
            q=prev_stop_at_or_before(tr,tr.route[-2])
            if q: tr.hold[q]=tr.hold.get(q,0)+30; 
            if log is not None: log.append(f"終着在線 {tr.id}@{q} +30 ({st})")
            return True
    return resolve(trains,c,maxwait,log)
def solve2(trains,maxit=4000,maxwait=240,log=None):
    for i in range(maxit):
        cs,links=all_conf(trains)
        if not cs: return [],links
        if not resolve2(trains,cs[0],maxwait,log): return cs,links
    cs,links=all_conf(trains); return cs,links
