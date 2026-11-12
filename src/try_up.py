from sched import *
_nom={}
def nominal(kind,o,d,ref):
    k=(kind,o,d,ref)
    if k not in _nom:
        t=Train("x",kind,o,d,0); t.compute(); _nom[k]=t.dep(ref)
    return _nom[k]
def mk(id,kind,o,d,ref_t,ref="新犬村",**kw):
    return Train(id,kind,o,d,ref_t-nominal(kind,o,d,ref),**kw)
def gen(offs,T0=11*3600,n=12):
    L=[]
    for b in range(n):
        T=T0+b*900; k=b%4
        L.append(mk(f"L{b}","各停",["秋田台","高島"][k%2],"軒屋",T+offs[0]))
        L.append(mk(f"E{b}","急行",["犬塚","蓮木市"][k%2],"軒屋",T+offs[1]))
        L.append(mk(f"R{b}","快速","奥雲温泉" if k==0 else "犬塚","軒屋",T+offs[2]))
    return L
if __name__=="__main__":
    res=[]
    grid=range(0,900,30)
    for o1 in grid:
        for o2 in grid:
            offs=(0,o1,o2)
            d=sorted([0,o1,o2]); gaps=[d[1]-d[0],d[2]-d[1],900-d[2]+d[0]]
            if min(gaps)<150: continue
            tr=gen(offs); log=[]
            left=solve(tr,maxit=400,log=log,maxwait=300)
            mid=[t for t in tr if 3<=int(t.id[1:])<=8]
            lw=sum(sum(t.hold.values()) for t in mid if t.kind=="各停")
            ew=sum(sum(t.hold.values()) for t in mid if t.kind!="各停")
            # 新犬村の間隔のばらつき
            res.append((lw+3*ew,lw,ew,len(left),offs))
    res.sort()
    for r in res[:15]: print(r)
