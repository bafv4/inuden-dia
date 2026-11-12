import pickle,sys,math,os
import net, sched, ops, build
from sched import *
from ops import *
from build import T,mkt,mk_up
import cyc
from run_all import add_branch
from try_up import nominal
# 回送：2面4線の駅で運転停車できる（停車時間0）
net.STOPS["回送"]=set(K2)|{"軒屋","蓮木市"}
_dw=net.dwell
FIRST=T(4,50)
# 夜に置ける編成の数＝夜に置いてよいホームの線＋留置線・引上線・折返し線・車庫（どちらも ops.py。2026-11-11 に本人が決めた）
#   軒屋6・新犬村2・学院前2・就島10・高島4・秋田台4・新狛野14・犬塚5・蓮木市5・奥雲温泉2
CAP_STABLE={X:NIGHT_PLAT.get(X,0)+SIDING.get(X,0) for X in ("軒屋","新犬村","学院前","就島","高島","秋田台","新狛野","犬塚","蓮木市","奥雲温泉")}
# 昼も使える線の数 SIDING（留置線・引上線・折返し線・車庫）は ops.py にある（from ops import * で入ってくる）
for _kv in filter(None,os.environ.get("CAP","").split(",")):      # 置ける数を試しに変える（例 CAP="蓮木市:5"）
    _k,_v=_kv.split(":"); CAP_STABLE[_k]=int(_v)
def kaiso_dwell(tr):
    return tr.kind=="回送"
_compute=Train.compute
def compute(s):
    if s.kind!="回送": return _compute(s)
    r=s.route; sl=s.stops(); Tm={}; slow=getattr(s,"slow",None) or {}     # slow：徐行（駅 → その駅へ着く手前の1駅間で余分にかける秒）。sched.Train.compute と同じ扱い
    t=s.dep0+s.hold.get(s.o,0); Tm[s.o]=[None,t,True]
    for a,b in zip(sl,sl[1:]):
        i,j=r.index(a),r.index(b)
        tot,ps=seg(tuple(r[i:j+1]))
        dep=Tm[a][1]; cum=0
        for x,p in zip(r[i+1:j],ps): cum+=slow.get(x,0); Tm[x]=[dep+p+cum,dep+p+cum,False]
        arr=dep+tot+cum+slow.get(b,0)
        if b==s.d: Tm[b]=[arr,None,True]
        else: Tm[b]=[arr,arr+s.hold.get(b,0),True]
    s.times=Tm; return Tm
Train.compute=compute
def pattern(down_off,up_off,S,t_from,t_to):
    build.UP_OFF=up_off; cyc.UP_OFF=up_off
    tr=cyc.gen_pattern(t_from,t_to,down_off)
    for t in tr:
        s=S.get(cyc.slot_of(t))
        if s: t.dep0=t.anchor+s["shift"]; t.hold=dict(s["hold"])
    return tr
def truncate(tr):
    out=[]
    for t in tr:
        t.compute()
        if t.dep(t.o)>=FIRST: out.append(t); continue
        if t.dir=="D": continue
        # 上り：始発時刻に間に合う駅から始める
        cands=[x for x in ["犬塚","新狛野","秋田台","高島","就島","新犬村"] if x in t.route and t.route.index(x)>0]
        done=False
        for x in cands:
            if t.dep(x)>=FIRST and t.stopped(x):
                n=Train(t.id,t.kind,x,t.d,0); n.hold={k:v for k,v in t.hold.items() if k in n.route and k!=x}
                n.compute(); n.dep0=t.dep(x)-(n.dep(x)-n.dep0) if False else t.dep(x)
                n.anchor=t.anchor; n.slotfix=cyc.slot_of(t); n.note="始発繰り上げ" ; out.append(n); done=True; break
    return out
def involved(c):
    if c[0]=="seg": return [c[2],c[3]]
    if c[0]=="occ": return list(c[3])+[c[2]]
    if c[0]=="single": return [c[2],c[3]]
    if c[0]=="cross": return [c[2],c[3]]
    return []
def two_track(p): return (p in K2 or TOTAL_CAP.get(p,1)>=2) and p not in ("軒屋","蓮木市","奥雲温泉")
def fix(trains,c,log):
    """凍結していない列車だけを動かして競合を解く"""
    typ=c[0]
    mut=lambda t: not getattr(t,"frozen",False)
    if typ=="seg":
        _,t,A,B,a,b,deficit=c
        if mut(B):
            # 後続Bが速く、Aも動かせるなら待避
            if mut(A) and RANK.get(B.kind,1)>RANK.get(A.kind,1):
                return resolve(trains,c,300,log)
            q=prev_stop_at_or_before(B,a)
            if q is None: return False
            add=int(math.ceil(deficit/15))*15
            if q==B.o: B.dep0+=add
            else: B.hold[q]=B.hold.get(q,0)+add
            log.append(f"抑止 {B.id}@{q}+{add}"); return True
        if mut(A):
            r=A.route; i=r.index(a); best=None
            for k in range(i,0,-1):
                p=r[k]
                if p not in B.times: break
                if not two_track(p) or not A.stopped(p) or A.times[p][1] is None: continue
                if B.arr(p) < A.arr(p)+60: continue
                w=B.dep(p)+H_DEP-A.dep(p)
                if w>0 and (best is None or w<best[0]): best=(w,p)
            if best and best[0]<=600:
                w,p=best; A.hold[p]=A.hold.get(p,0)+int(math.ceil(w/15))*15
                log.append(f"待避 {A.id}@{p}+{w:.0f}"); return True
            # 先に出す
            add=int(math.ceil(deficit/15))*15
            A.dep0-=add; log.append(f"繰上 {A.id}-{add}"); return True
        return False
    if typ=="occ":
        _,t,tr,cur,st,_,_=c
        cands=[x for x in cur if mut(x)]
        if not cands: return False
        x=max(cands,key=lambda z:z.arr(st) if st in z.times else 0)
        if st==x.o: x.dep0+=30; log.append(f"始発在線 {x.id}@{st}+30"); return True
        i=x.route.index(st)
        q=prev_stop_at_or_before(x,x.route[i-1])
        if q is None: return False
        if q==x.o: x.dep0+=30
        else: x.hold[q]=x.hold.get(q,0)+30
        log.append(f"在線 {x.id}@{q}+30 ({st})"); return True
    if typ=="single":
        _,t,t1,t2,k,L1,L2=c
        s1,e1,_,en1,_=L1; s2,e2,_,en2,_=L2
        opts=[]
        for tr,en,w in ((t1,en1,e2+SPAD-s1),(t2,en2,e1+SPAD-s2)):
            if mut(tr) and w>0: opts.append((w,tr,en))
        if not opts: return False
        w,tr,en=min(opts,key=lambda z:z[0]); add=int(math.ceil(w/15))*15
        if en==tr.o: tr.dep0+=add
        else: tr.hold[en]=tr.hold.get(en,0)+add
        log.append(f"交換 {tr.id}@{en}+{add}"); return True
    if typ=="cross":
        _,t0,D,Tt,X,_,need=c
        if mut(D): D.dep0+=int(math.ceil((need+1)/15))*15; return True
        return False
    return False
_link=ops.link
def link_nl(trains):
    keep=[t for t in trains if not getattr(t,"nolink",False)]
    links,st=_link(keep)
    return links,st
ops.link=link_nl
def solve_m(trains,log,maxit=4000):
    for i in range(maxit):
        cs,links=all_conf(trains)
        if not cs: return []
        ok=False
        for c in cs[:5]:
            if fix(trains,c,log): ok=True; break
        if not ok: return cs
    return all_conf(trains)[0]
