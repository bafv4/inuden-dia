import pickle,sys,copy
import cyc,build
from cyc import *
f=sys.argv[1]
tr,S,off,up=pickle.load(open(f,"rb"))
build.UP_OFF=up; cyc.UP_OFF=up
WIN=(T(9,30),T(13,0))
def ok():
    cs,_=all_conf(tr); return not [c for c in cs if WIN[0]<=c[1]<=WIN[1]]
def apply(S):
    for t in tr:
        s=S.get(slot_of(t))
        if s: t.dep0=t.anchor+s["shift"]; t.hold=dict(s["hold"])
def total(): return sum(sum(s["hold"].values()) for s in S.values())
print("before",total())
changed=True
while changed:
    changed=False
    for k,s in sorted(S.items(),key=lambda kv:-sum(kv[1]["hold"].values())):
        if not s["hold"]: continue
        # 経路順で最初の待ち
        t=next(x for x in tr if slot_of(x)==k)
        firsts=[p for p in t.route if p in s["hold"]]
        for p in firsts[:1]:
            h=s["hold"][p]
            for move in (h, h//2//15*15):
                if move<=0: continue
                old=copy.deepcopy(s)
                s["shift"]+=move; s["hold"][p]-=move
                if s["hold"][p]<=0: del s["hold"][p]
                apply(S)
                if ok(): changed=True; break
                S[k]=old; s=old; apply(S)
            if changed: break
        if changed: break
apply(S)
print("after",total(), "ok",ok())
pickle.dump((tr,S,off,up),open(f.replace(".pkl","_c.pkl"),"wb"))
