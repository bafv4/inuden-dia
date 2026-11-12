# 日中パターンのオフセット探索（詰まり・待避回数・待ち時間で評価）
# 使い方（src で）:
#   python grid2.py one  下り各停 下り急行 下り快速 上り各停 上り急行 上り快速   … 1通り解いて評価・保存
#   python grid2.py D    上り各停 上り急行 上り快速      … 上りを固定して下りを探索
#   python grid2.py U    下り各停 下り急行 下り快速      … 下りを固定して上りを探索
import sys,pickle,os
from multiprocessing import Pool
import build as BM, cyc
from build import T
from run_all import add_branch
import pat_eval
from sched import fmt
import math
from sched import K2,TOTAL_CAP,RANK,H_DEP,prev_stop_at_or_before
from ops import all_conf,resolve2
# 重み：待避1回＝W_OV秒の待ちとみなす。詰まり（目安間隔に足りない秒）は W_TIGHT 倍。優等の待ちは W_EXP 倍
W_OV=60; W_TIGHT=3; W_EXP=2; W_XF=0.5   # 乗り換え待ちは乗り換える人だけなので半分の重み
MAXWAIT=600      # 待避で待てる上限（秒）
NEW_STOP=int(os.environ.get("NEW_STOP","0"))  # 新しい駅で待避させるときの割増。0＝まとめず、待ちが最短の駅で待避（本人の選択）
SMALL=60         # これ以下の詰まりは後続を少し抑えて済ませる
def resolve3(trains,c,log):
    """続行の競合：遅い列車をまとめて1駅で待避させる。優等の抑止は小さな調整か、待避できないときだけ"""
    if c[0]!="seg": return resolve2(trains,c,240,log)
    _,t,A,B,a,b,deficit=c
    if RANK.get(B.kind,1)>RANK.get(A.kind,1) and deficit>SMALL:
        r=A.route; i=r.index(a); best=None
        for k in range(i,0,-1):
            p=r[k]
            if p not in B.times: break
            if not (p in K2 or TOTAL_CAP.get(p,1)>=2) or p in ("軒屋","蓮木市","奥雲温泉"): continue
            if not A.stopped(p) or A.times[p][1] is None: continue
            if B.arr(p) < A.arr(p)+60: continue
            w=B.dep(p)+H_DEP-A.dep(p)
            if w<=0: continue
            cost=w+(0 if p in A.hold else NEW_STOP)
            if best is None or cost<best[0]: best=(cost,w,p)
        if best and best[1]<=MAXWAIT:
            _,w,p=best
            A.hold[p]=A.hold.get(p,0)+int(math.ceil(w/15))*15
            log.append(f"待避 {A.id}@{p} +{w:.0f} ← {B.id}"); return True
    q=prev_stop_at_or_before(B,a)
    if q is None: return False
    add=int(math.ceil(deficit/15))*15
    B.hold[q]=B.hold.get(q,0)+add
    log.append(f"抑止 {B.id}@{q} +{add} (前 {A.id})"); return True
def cyc_solve3(trains,win,maxit=600,log=None):
    log=[] if log is None else log
    for i in range(maxit):
        cyc.sync(trains)
        cs,links=all_conf(trains)
        cs=[c for c in cs if win[0]<=c[1]<=win[1]]
        if not cs: return [],cyc.sync(trains)
        if not resolve3(trains,cs[0],log): return cs,None
    return cs,None
def prune(trains,S,win):
    """解いた後、不要になった停車延長・始発の繰り下げを外す（優等から順に。外して競合が出なければ採用）"""
    def apply():
        for t in trains:
            s=S.get(cyc.slot_of(t))
            if s: t.dep0=t.anchor+s["shift"]; t.hold=dict(s["hold"])
    def ok():
        apply(); cs,_=all_conf(trains)
        return not [c for c in cs if win[0]<=c[1]<=win[1]]
    keys=sorted(S,key=lambda k:(-RANK.get(k[1],1),-sum(S[k]["hold"].values())))
    def shrink(get,put,h):
        """h を競合が出ない最小の値（15秒単位）まで縮める。二分探索。縮んだら True"""
        put(0)
        if ok(): return True
        lo,hi=0,h//15        # lo×15 は不可、hi×15 は可
        while hi-lo>1:
            mid=(lo+hi)//2; put(mid*15)
            if ok(): hi=mid
            else: lo=mid
        put(hi*15)
        return hi*15<h
    changed=True
    while changed:
        changed=False
        for k in keys:
            s=S[k]
            for st in list(s["hold"]):
                def put(v,st=st):
                    if v: s["hold"][st]=v
                    else: s["hold"].pop(st,None)
                if shrink(None,put,s["hold"][st]): changed=True
            if s["shift"]>0:
                def put(v): s["shift"]=v
                if shrink(None,put,s["shift"]): changed=True
    apply()
    return S
SOLVER=os.environ.get("SOLVER","3")
PRUNE=os.environ.get("PRUNE","1")=="1"
def solve_pattern(down,up):
    BM.UP_OFF=tuple(up); cyc.UP_OFF=tuple(up)
    BM.cnt.clear()
    sv=cyc_solve3 if SOLVER=="3" else (lambda tr,w,log: cyc.cyc_solve(tr,w,log=log))
    tr=cyc.gen_pattern(T(8,0),T(14,30),down)
    left,S=sv(tr,(T(9,30),T(13,0)),log=[])
    if left: return None
    for t in tr: t.compute()
    br=add_branch(tr)
    for b in br: b.anchor=b.dep0
    tr+=br
    left,S=sv(tr,(T(9,30),T(13,0)),log=[])
    if left: return None
    if PRUNE: S=prune(tr,S,(T(9,30),T(13,0)))
    for t in tr: t.compute()
    return tr,S
def evaluate(down,up):
    r=solve_pattern(down,up)
    if r is None: return None
    tr,S=r
    m=pat_eval.score(tr)
    m["待避"]=len(set((id(A),w) for A,B,w in pat_eval.overtakes(tr)))  # 待避した回数（列車×駅）
    m["優等の待ち秒"]=sum(sum(t.hold.values())+(t.dep0-t.anchor) for t in tr
        if t.kind!="各停" and pat_eval.W0<=t.dep(t.o)<pat_eval.W1)
    sc=W_OV*m["待避"]+m["待ち秒"]+(W_EXP-1)*m["優等の待ち秒"]+W_TIGHT*m["詰まり"]+m["同種別のずれ"]+W_XF*m["乗換待ち秒"]
    return sc,m,tuple(down),tuple(up)
import run_all
BR_KEYS=("HASU_D","HASU_U","OKU_D","OKU_U")
def set_branch(p):
    for k,v in p.items(): setattr(run_all,k,v)
# 環境変数 BR="HASU_D,HASU_U,OKU_D,OKU_U" で支線の接続時分を指定
if os.environ.get("BR"): set_branch(dict(zip(BR_KEYS,map(int,os.environ["BR"].split(",")))))
def _run(a):
    try:
        if len(a)==3: set_branch(a[2]); r=evaluate(a[0],a[1]); return r and r+(a[2],)
        return evaluate(*a)
    except Exception as e: return None
if __name__=="__main__":
    mode=sys.argv[1]; v=[int(x) for x in sys.argv[2:]]
    if mode=="one":
        down,up=v[:3],v[3:6]
        r=solve_pattern(down,up)
        if r is None: print("解けない"); sys.exit(1)
        tr,S=r
        fn=f"../data/cyc2_{down[1]}_{down[2]}_{up[1]}_{up[2]}.pkl"
        pickle.dump((tr,S,tuple(down),tuple(up)),open(fn,"wb")); print("保存",fn)
        print(evaluate(down,up))
        sys.exit(0)
    if mode=="B":
        # 支線各停の接続時分を1つずつ探す（本線のオフセットは固定）。python grid2.py B 下り3つ 上り3つ
        down,up=tuple(v[:3]),tuple(v[3:6])
        cur={k:getattr(run_all,k) for k in BR_KEYS}
        rng={"HASU_D":range(60,901,15),"HASU_U":range(60,901,15),"OKU_D":range(60,3600,30),"OKU_U":range(60,3600,30)}
        with Pool(int(os.environ.get("PROCS",str(max(1,os.cpu_count()-1))))) as p:
            for rnd in range(2):
                for k in BR_KEYS:
                    cands=[(down,up,dict(cur,**{k:x})) for x in rng[k]]
                    res=sorted([x for x in p.map(_run,cands) if x],key=lambda r:r[0])
                    if res: cur=res[0][4]; print(rnd,k,"→",cur[k],res[0][:2],flush=True)
        print("支線の接続",cur)
        sys.exit(0)
    step=int(os.environ.get("STEP","30"))
    if mode=="D":
        up=v; cands=[((0,e,r),up) for e in range(0,900,step) for r in range(0,900,step) if len({0,e,r})==3]
    else:
        down=v; cands=[(down,(0,e,r)) for e in range(0,900,step) for r in range(0,900,step) if len({0,e,r})==3]
    # 始発駅（軒屋発・新犬村基準）で3種別が詰まりすぎる組は最初から除く
    def ok(c):
        o=sorted(c[0] if mode=="D" else c[1]); g=[o[1]-o[0],o[2]-o[1],900-o[2]+o[0]]
        return min(g)>=int(os.environ.get("MINGAP","120"))
    cands=[c for c in cands if ok(c)]
    print("候補",len(cands),flush=True)
    with Pool(int(os.environ.get("PROCS",str(max(1,os.cpu_count()-1))))) as p:
        res=[x for x in p.imap_unordered(_run,cands,chunksize=4) if x]
    res.sort(key=lambda r:r[0])
    out=f"../data/grid2_{mode}.txt"
    with open(out,"w",encoding="utf-8") as f:
        for r in res: f.write(repr(r)+"\n")
    print("解けた",len(res))
    for r in res[:15]: print(r)
