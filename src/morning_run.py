import pickle,sys,math
from morning import *
import ops
PK=sys.argv[1]
tr0,S,DOWN_OFF,UP_OFF=pickle.load(open(PK,"rb"))
# 支線の時分差：環境変数 BR か、パターンと同名の .json（pesp.py が書く）にあれば、それで支線を作る。
# なければ run_all.py の既定値。パターンを作ったときと同じ値でないと、支線が枠に合わず解き直しになる
import os,json,run_all
_j=os.path.splitext(PK)[0]+".json"
BR=os.environ.get("BR") or (json.load(open(_j,encoding="utf-8")).get("BR") if os.path.exists(_j) else None)
if BR:
    for _k,_v in zip(("HASU_D","HASU_U","OKU_D","OKU_U"),map(int,BR.split(","))): setattr(run_all,_k,_v)
FIRST_D=T(5,0)
RUSH=(T(7,30),T(9,0))
PEAK=(T(7,50),T(8,40))
def all_conf2(trains):
    for t in trains: t.compute()
    links,_=link_nl(trains)
    for t in trains:
        if getattr(t,"src",None) is not None: links[t]=t.src
    cs=conflicts(trains,turn_occ(trains,links))+cross_conf(trains,links)
    cs.sort(key=lambda c:c[1]); return cs,links
def solve(trains,log,maxit=3000,only=None):
    for i in range(maxit):
        cs,links=all_conf2(trains)
        if only is not None: cs=[c for c in cs if any(x in only for x in involved(c))]
        if not cs: return []
        ok=False
        for c in cs[:6]:
            if fix(trains,c,log): ok=True; break
        if not ok: return cs
    return cs
def build_base():
    cyc.UP_OFF=UP_OFF; build.UP_OFF=UP_OFF
    build.cnt.clear()
    tr=pattern(DOWN_OFF,UP_OFF,S,T(3,30),T(11,30))
    tr=[t for t in tr if not (t.dir=="D" and (t.compute() or True) and t.dep(t.o)<FIRST_D)]
    tr=truncate(tr)
    for t in tr: t.frozen=(getattr(t,"note","")!="始発繰り上げ"); t.compute()
    br=add_branch(tr)
    for b in br:
        b.anchor=b.dep0; s=S.get(cyc.slot_of(b))
        if s: b.dep0=b.anchor+s["shift"]; b.hold=dict(s["hold"]); b.frozen=True
        else: b.frozen=False
        b.compute()
    br=[b for b in br if b.dep(b.o)>=FIRST]
    return tr+br
if __name__=="__main__":
    log=[]
    tr=build_base()
    left=solve(tr,log)
    print("base left",len(left))
    for c in left[:8]: print(" ",c[0],hms(c[1]),[(x.kind,x.o,x.d,fmt(x.dep(x.o)),getattr(x,'frozen',0)) for x in involved(c)][:3],c[4])
    pickle.dump((tr,log),open("base.pkl","wb"))
