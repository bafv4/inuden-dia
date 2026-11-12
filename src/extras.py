import pickle,sys,copy,os
import sys
PKF=sys.argv[1]
sys.argv=[sys.argv[0],PKF]
from morning_run import *
EXTRAS=[("急行","犬塚"),("各停","高島"),("急行","蓮木市"),("各停","就島"),("急行","犬塚"),("各停","高島"),("急行","蓮木市"),("各停","就島")]
# 候補を試すときは、増発列車の走る時間の前後 WIN 秒にかかる列車（と折返しの相手）だけで競合を判定する。
# 0 なら全列車で判定（従来どおり）。採用した位置は最後に全列車で解き直すので、そこで確認される。
WIN=int(os.environ.get("WIN","1200"))
def hold_sum(t): return sum(t.hold.values())
def window(tr,x):
    if not WIN: return tr
    x.compute(); a,b=x.dep(x.o)-WIN,x.arr(x.d)+WIN
    near=[t for t in tr if t.dep(t.o)<=b and t.arr(t.d)>=a]
    links,_=link_nl(tr)
    nxt={A:D for D,A in links.items() if A is not None}
    s=set(near)
    for t in near:
        if links.get(t) is not None: s.add(links[t])
        if t in nxt: s.add(nxt[t])
    return [t for t in tr if t in s]
def try_insert(tr,kind,o,t_ref,log):
    x=mk_up(kind,o,"軒屋",t_ref); x.frozen=False; x.nolink=True; x.extra=True
    x.label=kind+"（増発）"; x.cars=8 if kind=="急行" else 6
    trial=window(tr,x)+[x]
    snap={id(t):(t.dep0,dict(t.hold)) for t in tr}
    left=solve(trial,[],maxit=60,only=[x])
    ok=not left and hold_sum(x)<=480
    cost=hold_sum(x)+sum(hold_sum(t)-sum(snap[id(t)][1].values()) for t in tr)
    for t in tr: t.dep0,t.hold=snap[id(t)][0],dict(snap[id(t)][1])
    return ok,cost,x
if __name__=="__main__":
    if os.path.exists("extras.pkl") and os.environ.get("CONT"):
        tr,log,placed0=pickle.load(open("extras.pkl","rb"))
        # 残り＝EXTRAS から保存済みの分を除いたもの
        EX=list(EXTRAS)
        for p in placed0: EX.remove((p.kind,p.o))
    else:
        tr,log=pickle.load(open("base.pkl","rb")); placed0=[]; EX=EXTRAS
    for t in tr: t.compute()
    # ピーク方向の軒屋着の間隔を見て、空いた所へ入れる
    def gaps():
        a=sorted(t.arr("軒屋") for t in tr if t.d=="軒屋" and PEAK[0]-600<=t.arr("軒屋")<=PEAK[1]+300)
        return a
    placed=list(placed0)
    for kind,o in EX:
        best=None
        core=sorted(t.dep("新犬村") for t in tr if t.dir=="U" and "新犬村" in t.times)
        for tt in range(T(7,30),T(8,40),30):
            if min(abs(tt-c) for c in core)<90: continue
            ok,cost,x=try_insert(tr,kind,o,tt,log)
            if not ok: continue
            x.compute(); ar=x.arr("軒屋")
            if not (PEAK[0]-300<=ar<=PEAK[1]+600): continue
            # 他の増発と離す
            near=min([abs(ar-p.arr("軒屋")) for p in placed]+[9999])
            sc=cost*2-min(near,360)
            if best is None or sc<best[0]: best=(sc,tt,cost)
        if best is None: print("FAIL",kind,o); continue
        sc,tt,cost=best
        x=mk_up(kind,o,"軒屋",tt); x.frozen=False; x.nolink=True; x.extra=True
        x.label=kind+"（増発）"; x.cars=8 if kind=="急行" else 6
        tr.append(x); left=solve(tr,log,only=[x]); x.compute()
        for t in tr: 
            if not getattr(t,"extra",False): pass
        placed.append(x)
        print(kind,o,fmt(x.dep(x.o)),"軒屋着",fmt(x.arr("軒屋")),x.hold,"left",len(left),"cost",cost)
        for t in tr: t.frozen=True if not getattr(t,"extra",False) and getattr(t,"frozen",False) else t.frozen
        x.frozen=True
        # 1本入るごとに保存（途中で止めても CONT=1 で続きから再開できる）
        pickle.dump((tr,log,placed),open("extras.pkl","wb"))
    pickle.dump((tr,log,placed),open("extras.pkl","wb"))
