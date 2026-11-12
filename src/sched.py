import os
from net import *
RANK={"快速":3,"急行":2,"各停":1,"回送":2}
H_DEP=90; H_ARR=90; PAD=30; SPAD=30
H_PASS=30     # 待避のあとの発車：抜いた列車がその駅を出て（通過して）から、抜かれた列車が出るまでの最低の間隔（2026-11-11 本人が「30秒でいい」と決めた。それまでは H_DEP と同じ90秒）
def need_dep(A,B,a):
    """A の次に B が駅 a を出るときに要る間隔。B が a で A に抜かれた直後（B が先に着いて止まっていて、A があとから着いて先に出る）なら H_PASS、それ以外の続行は H_DEP"""
    if a!=B.o and a!=A.o and B.stopped(a) and B.arr(a)<A.arr(a): return H_PASS
    return H_DEP
class Train:
    def __init__(s,id,kind,o,d,dep,cars=4,label=None,note=""):
        s.id=id;s.kind=kind;s.o=o;s.d=d;s.dep0=dep;s.cars=cars;s.hold={};s.xstop=set();s.note=note
        s.slow={}     # 徐行：駅 → その駅へ着く手前の1駅間で余分にかける秒（通過駅でもよい）
        s.route=route(o,d); s.label=label or kind
        s.dir=s._dir(); s.times=None
    def _dir(s):
        r=s.route
        a,b=r[0],r[1]
        if a in MN and b in MN: return "D" if MN.index(b)>MN.index(a) else "U"
        return "D" if HN.index(b)>HN.index(a) else "U"
    def stops(s):
        st=STOPS[s.kind]
        out=[]
        for x in s.route:
            if x==s.o or x==s.d or st is None or x in st or x in s.xstop or x in s.hold: out.append(x)
        return out
    def is_stop(s,x):
        st=STOPS[s.kind]
        return x==s.o or x==s.d or st is None or x in st
    def compute(s):
        # 始発時刻・停車延長・運転停車が前回と同じなら、前回の時刻表をそのまま返す（同じ dict を返すことが
        # 「変わっていない」の合図になり、conflicts が競合判定をやり直す範囲を絞るのに使う）
        slow=getattr(s,"slow",None) or {}      # 古い pickle の列車には slow がない
        key=(s.dep0,tuple(sorted(s.hold.items())),tuple(sorted(s.xstop)),tuple(sorted(slow.items())))
        if s.times is not None and getattr(s,"_key",None)==key: return s.times
        s._key=key
        r=s.route; sl=s.stops(); T={}
        t=s.dep0+s.hold.get(s.o,0); T[s.o]=[None,t,True]
        for a,b in zip(sl,sl[1:]):
            i,j=r.index(a),r.index(b)
            tot,ps=seg(tuple(r[i:j+1]))
            dep=T[a][1]; cum=0
            for x,p in zip(r[i+1:j],ps): cum+=slow.get(x,0); T[x]=[dep+p+cum,dep+p+cum,False]
            arr=dep+tot+cum+slow.get(b,0)
            if b==s.d: T[b]=[arr,None,True]
            else:
                dw=(dwell(b) if s.is_stop(b) else 0)+s.hold.get(b,0)
                T[b]=[arr,arr+dw,True]
        s.times=T; return T
    def arr(s,x): v=s.times[x]; return v[0] if v[0] is not None else v[1]
    def dep(s,x): v=s.times[x]; return v[1] if v[1] is not None else v[0]
    def stopped(s,x): return s.times[x][2]
def fmt(t):
    if t is None: return ""
    t=int(round(t)); h=t//3600; m=(t%3600)//60; sec=t%60
    return f"{h}:{m:02d}"+("" if sec==0 else f"½" if sec==30 else f"'{sec:02d}")
def hms(t): t=int(round(t)); return f"{t//3600}:{(t%3600)//60:02d}:{t%60:02d}"

def conflicts_full(trains, extra_occ=None):
    """競合判定（毎回すべて作り直す元の実装）。conflicts はこれと同じ結果を、変わった所だけやり直して返す"""
    out=[]
    for tr in trains: tr.compute()
    # 1 複線区間の続行・順序
    segs={}
    for tr in trains:
        r=tr.route
        for a,b in zip(r,r[1:]):
            if single_sec_of(a,b): continue
            segs.setdefault((a,b),[]).append(tr)
    for (a,b),L in segs.items():
        L=sorted(L,key=lambda t:t.dep(a))
        for A,B in zip(L,L[1:]):
            gd=B.dep(a)-A.dep(a); ga=B.arr(b)-A.arr(b)
            nd=need_dep(A,B,a)
            if gd<nd or ga<H_ARR:
                out.append(("seg",max(A.dep(a),B.dep(a)),A,B,a,b,max(nd-gd,H_ARR-ga)))
    # 2 駅の在線
    occ={}
    for tr in trains:
        for x,(ar,dp,stp) in tr.times.items():
            if x==tr.o or x==tr.d: continue  # 始終端は別扱い
            key=(x,"*") if x in TOTAL_CAP else (x,tr.dir)
            if x=="学院前": key=(x,tr.dir,"H" if (tr.o in HN[1:] or tr.d in HN[1:]) else "M")
            if stp: iv=(ar,dp+PAD)
            else: iv=(ar-5,ar+PAD)
            occ.setdefault(key,[]).append((iv[0],iv[1],tr))
    if extra_occ:
        for key,ivs in extra_occ.items(): occ.setdefault(key,[]).extend(ivs)
    # 学院前：内側線（蓮木線）と外側線（本線）。本線の列車は外側が埋まっていれば内側を使える
    for dr in ("D","U"):
        Hs=sorted(occ.pop(("学院前",dr,"H"),[]),key=lambda z:z[0])
        Ms=sorted(occ.pop(("学院前",dr,"M"),[]),key=lambda z:z[0])
        for A,B in zip(Hs,Hs[1:]):
            if B[0]<A[1]: out.append(("occ",B[0],B[2],[A[2],B[2]],"学院前",None,0))
        outer_free=-1e9; inner=[(a,b) for a,b,_ in Hs]; inner_extra=[]
        for a,b,tr in Ms:
            if a>=outer_free: outer_free=b; continue
            busy=any(not(b<=x or a>=y) for x,y in inner+inner_extra)
            if not busy: inner_extra.append((a,b)); continue
            cur=[z[2] for z in Ms if z[0]<b and z[1]>a]+[z[2] for z in Hs if z[0]<b and z[1]>a]
            out.append(("occ",a,tr,cur,"学院前",None,0))
    for key,L in occ.items():
        st=key[0]
        cap=TOTAL_CAP.get(st, 2 if st in K2 else 1)
        ev=sorted([(s,1,tr) for s,e,tr in L]+[(e,-1,tr) for s,e,tr in L],key=lambda z:(z[0],z[1]))
        cur=[]
        for t,k,tr in ev:
            if k==1:
                cur.append(tr)
                if len(cur)>cap:
                    out.append(("occ",t,tr,list(cur),st,None,0))
            else:
                if tr in cur: cur.remove(tr)
    # 3 単線区間
    sec={}
    for tr in trains:
        r=tr.route
        for x,y in SINGLE_SEC:
            if x in r and y in r:
                i,j=r.index(x),r.index(y)
                ent,ex=(x,y) if i<j else (y,x)
                sec.setdefault((x,y),[]).append((tr.dep(ent),tr.arr(ex),tr,ent,ex))
            elif (x in r) != (y in r):
                # 区間内に始終端（ありえない設定）
                pass
    for k,L in sec.items():
        L.sort(key=lambda z:z[0])
        for i in range(len(L)):
            for j in range(i+1,len(L)):
                s1,e1,t1,_,_=L[i]; s2,e2,t2,_,_=L[j]
                if s2 < e1+SPAD and s1 < e2+SPAD:
                    out.append(("single",max(s1,s2),t1,t2,k,L[i],L[j]))
    out.sort(key=lambda c:c[1])
    return out

# ---- 競合判定を、時刻が変わった列車の通る区間・駅だけやり直す版
# 判定のまとまり（区間・駅・単線区間）ごとに結果を覚えておき、そこを通る列車の時刻が前回と違うまとまりだけ
# 計算し直す。まとまりの中身と並べる順は conflicts_full と同じなので、返す競合のリストも同じになる。
def _seg_conf(g,L):
    a,b=g; out=[]
    L=sorted(L,key=lambda t:t.dep(a))
    for A,B in zip(L,L[1:]):
        gd=B.dep(a)-A.dep(a); ga=B.arr(b)-A.arr(b)
        nd=need_dep(A,B,a)
        if gd<nd or ga<H_ARR:
            out.append(("seg",max(A.dep(a),B.dep(a)),A,B,a,b,max(nd-gd,H_ARR-ga)))
    return out
def _gak_conf(Hs,Ms):
    out=[]
    Hs=sorted(Hs,key=lambda z:z[0]); Ms=sorted(Ms,key=lambda z:z[0])
    for A,B in zip(Hs,Hs[1:]):
        if B[0]<A[1]: out.append(("occ",B[0],B[2],[A[2],B[2]],"学院前",None,0))
    outer_free=-1e9; inner=[(a,b) for a,b,_ in Hs]; inner_extra=[]
    for a,b,tr in Ms:
        if a>=outer_free: outer_free=b; continue
        busy=any(not(b<=x or a>=y) for x,y in inner+inner_extra)
        if not busy: inner_extra.append((a,b)); continue
        cur=[z[2] for z in Ms if z[0]<b and z[1]>a]+[z[2] for z in Hs if z[0]<b and z[1]>a]
        out.append(("occ",a,tr,cur,"学院前",None,0))
    return out
def _occ_conf(key,L):
    out=[]; st=key[0]
    cap=TOTAL_CAP.get(st, 2 if st in K2 else 1)
    ev=sorted([(s,1,tr) for s,e,tr in L]+[(e,-1,tr) for s,e,tr in L],key=lambda z:(z[0],z[1]))
    cur=[]
    for t,k,tr in ev:
        if k==1:
            cur.append(tr)
            if len(cur)>cap: out.append(("occ",t,tr,list(cur),st,None,0))
        else:
            if tr in cur: cur.remove(tr)
    return out
def _sec_conf(k,M):
    out=[]
    L=[(tr.dep(ent),tr.arr(ex),tr,ent,ex) for tr,ent,ex in M]
    L.sort(key=lambda z:z[0])
    for i in range(len(L)):
        for j in range(i+1,len(L)):
            s1,e1,t1,_,_=L[i]; s2,e2,t2,_,_=L[j]
            if s2 < e1+SPAD and s1 < e2+SPAD:
                out.append(("single",max(s1,s2),t1,t2,k,L[i],L[j]))
    return out
class _Inc:
    def __init__(s,trains):
        s.trains=list(trains)
        s.segs={}; s.occ={}; s.sec={}
        s.touch={}     # 列車 → {駅: その駅の時刻を使うまとまり}
        for tr in trains:
            r=tr.route; tch=s.touch.setdefault(tr,{})
            for a,b in zip(r,r[1:]):
                if single_sec_of(a,b): continue
                s.segs.setdefault((a,b),[]).append(tr)
                tch.setdefault(a,[]).append(("seg",(a,b))); tch.setdefault(b,[]).append(("seg",(a,b)))
        for tr in trains:
            tch=s.touch[tr]
            for x in tr.route:
                if x==tr.o or x==tr.d: continue
                key=(x,"*") if x in TOTAL_CAP else (x,tr.dir)
                if x=="学院前": key=(x,tr.dir,"H" if (tr.o in HN[1:] or tr.d in HN[1:]) else "M")
                s.occ.setdefault(key,[]).append((tr,x))
                tch.setdefault(x,[]).append(("occ",key))
        for tr in trains:
            r=tr.route; tch=s.touch[tr]
            for x,y in SINGLE_SEC:
                if x in r and y in r:
                    i,j=r.index(x),r.index(y)
                    ent,ex=(x,y) if i<j else (y,x)
                    s.sec.setdefault((x,y),[]).append((tr,ent,ex))
                    tch.setdefault(ent,[]).append(("sec",(x,y))); tch.setdefault(ex,[]).append(("sec",(x,y)))
        s.seen={}      # 列車 → 前回見た時刻表（dict そのもの）
        s.cache={}     # まとまり → 前回の競合
        s.xlast={}     # 駅のキー → 前回の折返し在線（extra_occ）
    def same(s,trains):
        return len(s.trains)==len(trains) and all(a is b for a,b in zip(s.trains,trains))
    def entries(s,key):
        out=[]
        for tr,x in s.occ.get(key,()):
            ar,dp,stp=tr.times[x]
            out.append((ar,dp+PAD,tr) if stp else (ar-5,ar+PAD,tr))
        return out
    def conflicts(s,extra):
        dirty=set(); seen=s.seen
        for tr in s.trains:
            new=tr.times; old=seen.get(tr)
            if new is old: continue
            if old is None:
                for gl in s.touch[tr].values(): dirty.update(gl)
            else:
                for x,gl in s.touch[tr].items():
                    if old[x]!=new[x]: dirty.update(gl)
            seen[tr]=new
        extra=extra or {}
        cache=s.cache; xlast=s.xlast; out=[]
        for g,L in s.segs.items():
            k=("seg",g)
            if k in dirty or k not in cache: cache[k]=_seg_conf(g,L)
            out+=cache[k]
        for dr in ("D","U"):
            kH=("学院前",dr,"H"); kM=("学院前",dr,"M")
            eH=extra.get(kH,[]); eM=extra.get(kM,[])
            k=("gak",dr)
            if ("occ",kH) in dirty or ("occ",kM) in dirty or k not in cache or xlast.get(kH)!=eH or xlast.get(kM)!=eM:
                cache[k]=_gak_conf(s.entries(kH)+eH,s.entries(kM)+eM)
                xlast[kH]=list(eH); xlast[kM]=list(eM)
            out+=cache[k]
        for key in s.occ:
            if key[0]=="学院前": continue
            e=extra.get(key,[]); k=("occ",key)
            if k in dirty or k not in cache or xlast.get(key)!=e:
                cache[k]=_occ_conf(key,s.entries(key)+e); xlast[key]=list(e)
            out+=cache[k]
        for key,e in extra.items():      # 通過列車のない駅（終端）の在線
            if key in s.occ or key[0]=="学院前": continue
            k=("occ",key)
            if k not in cache or xlast.get(key)!=e:
                cache[k]=_occ_conf(key,list(e)); xlast[key]=list(e)
            out+=cache[k]
        for g,M in s.sec.items():
            k=("sec",g)
            if k in dirty or k not in cache: cache[k]=_sec_conf(g,M)
            out+=cache[k]
        out.sort(key=lambda c:c[1])
        return out
_inc=None
FULL=os.environ.get("INUDEN_FULL")=="1"     # 1 にすると毎回すべて作り直す元の判定を使う（結果は同じ。検算用）
def conflicts(trains, extra_occ=None):
    """競合のリスト（時刻順）。同じ列車リストで続けて呼ぶあいだは、時刻が変わった所だけ判定し直す"""
    global _inc
    if FULL: return conflicts_full(trains,extra_occ)
    for tr in trains: tr.compute()
    if _inc is None or not _inc.same(trains): _inc=_Inc(trains)
    return _inc.conflicts(extra_occ)

def prev_stop_at_or_before(tr,a,need_cap2=False):
    r=tr.route; i=r.index(a)
    for k in range(i,-1,-1):
        x=r[k]
        if x==tr.d: continue
        if need_cap2:
            if not (x in K2 or TOTAL_CAP.get(x,1)>=2): continue
            if x in ("軒屋","蓮木市","奥雲温泉"): continue
        if tr.stopped(x) and tr.times[x][1] is not None: return x
    return None

def resolve(trains,c,maxwait=420,log=None):
    typ=c[0]
    if typ=="seg":
        _,t,A,B,a,b,deficit=c
        if RANK.get(B.kind,1)>RANK.get(A.kind,1) and deficit>60:
            r=A.route; i=r.index(a); best=None
            for k in range(i,0,-1):
                p=r[k]
                if p not in B.times: break
                if not (p in K2 or TOTAL_CAP.get(p,1)>=2) or p in ("軒屋","蓮木市","奥雲温泉"): continue
                if not A.stopped(p) or A.times[p][1] is None: continue
                if B.arr(p) < A.arr(p)+60: continue
                w=B.dep(p)+H_DEP-A.dep(p)
                if w<=0: continue
                if best is None or w<best[0]: best=(w,p)
            if best and best[0]<=maxwait:
                w,p=best
                A.hold[p]=A.hold.get(p,0)+int(math.ceil(w/15))*15
                if log is not None: log.append(f"待避 {A.id}@{p} +{w:.0f} ← {B.id}")
                return True
        q=prev_stop_at_or_before(B,a)
        if q is None: return False
        add=int(math.ceil(deficit/15))*15
        B.hold[q]=B.hold.get(q,0)+add
        if log is not None: log.append(f"抑止 {B.id}@{q} +{add} (前 {A.id})")
        return True
    if typ=="occ":
        _,t,tr,cur,st,_,_=c
        # 遅く着いた tr を手前で抑える
        others=[x for x in cur if x is not tr]
        need=min(o.dep(st) if o.times[st][1] is not None else o.arr(st) for o in others)+PAD-tr.arr(st)+15
        r=tr.route; i=r.index(st)
        q=prev_stop_at_or_before(tr,r[i-1]) if i>0 else None
        if q is None or need<=0: return False
        add=int(math.ceil(need/15))*15
        tr.hold[q]=tr.hold.get(q,0)+add
        if log is not None: log.append(f"在線 {tr.id}@{q} +{add} ({st})")
        return True
    if typ=="single":
        _,t,t1,t2,k,L1,L2=c
        s1,e1,_,en1,ex1=L1; s2,e2,_,en2,ex2=L2
        w1=e2+SPAD-s1; w2=e1+SPAD-s2   # t1が待つ / t2が待つ
        def cost(tr,w): return w*(2 if tr.kind=="快速" else 1)
        opts=[]
        if w1>0 and en1!=t1.o or w1>0: opts.append((cost(t1,w1),t1,en1,w1))
        if w2>0: opts.append((cost(t2,w2),t2,en2,w2))
        opts.sort(key=lambda z:z[0])
        for _,tr,en,w in opts:
            add=int(math.ceil(w/15))*15
            if en==tr.o: tr.dep0+=add
            else: tr.hold[en]=tr.hold.get(en,0)+add
            if log is not None: log.append(f"交換 {tr.id}@{en} +{add}")
            return True
    return False

def solve(trains,maxit=3000,log=None,maxwait=420,extra=None):
    for it in range(maxit):
        cs=conflicts(trains,extra(trains) if extra else None)
        if not cs: return []
        if not resolve(trains,cs[0],maxwait,log): return cs
    return conflicts(trains)
