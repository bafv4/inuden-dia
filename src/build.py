from ops import *
from try_up import nominal
H=3600
FIRST=4*H+50*60
END=11*H
def T(h,m,s=0): return h*H+m*60+s
DOWN_OFF=(0,510,300)   # 各停・急行・快速（軒屋発、15分枠の頭から）
UP_OFF=(0,180,720)     # 同（新犬村発）
UP_BASE=T(4,57,30)      # 上りの枠の基準（新犬村）
RUSH_UP=(T(7,15),T(9,15))   # 軒屋着でラッシュ編成（8両・6両）
cnt={}
def nid(p):
    cnt[p]=cnt.get(p,0)+1; return f"{p}{cnt[p]:03d}"
def mk_ref(kind,o,d,t_ref,ref,**kw):
    return Train(nid(kind[0]+("U" if MN.index(d) < (MN.index(o) if o in MN else 11) or d=="軒屋" else "D") if False else kind),kind,o,d,t_ref-nominal(kind,o,d,ref),**kw)
def mkt(kind,o,d,dep,**kw):
    tr=Train("",kind,o,d,dep,**kw); tr.id=nid(("U" if tr.dir=="U" else "D")); return tr
def mk_up(kind,o,d,t_ref,ref="新犬村",**kw):
    return mkt(kind,o,d,t_ref-nominal(kind,o,d,ref),**kw)
def build(rush=True):
    trains=[]
    # ---- 下り（軒屋発）
    b=0
    t0=T(5,0)
    while t0+b*900 < END:
        B=t0+b*900; k=(B//900)%4
        trains.append(mkt("各停","軒屋",["秋田台","高島"][k%2],B+DOWN_OFF[0]))
        trains.append(mkt("急行","軒屋",["犬塚","蓮木市"][k%2],B+DOWN_OFF[1]))
        if B>=T(5,45):
            trains.append(mkt("快速","軒屋","奥雲温泉" if k==0 else "犬塚",B+DOWN_OFF[2]))
        b+=1
    # ---- 上り（新犬村基準）
    b=0
    while UP_BASE+b*900 < END-15*60:
        B=UP_BASE+b*900; k=((B-UP_BASE)//900)%4
        lo=["秋田台","高島"][k%2]
        cand=[lo,"高島","就島","新犬村"]
        for o in cand:
            t=B+UP_OFF[0]-nominal("各停",o,"軒屋","新犬村")
            if t>=FIRST: trains.append(mkt("各停",o,"軒屋",t)); break
        eo=["犬塚","蓮木市"][k%2]
        t=B+UP_OFF[1]-nominal("急行",eo,"軒屋","新犬村")
        if t>=FIRST: trains.append(mkt("急行",eo,"軒屋",t))
        ro="奥雲温泉" if k==0 else "犬塚"
        t=B+UP_OFF[2]-nominal("快速",ro,"軒屋","新犬村")
        if t>=FIRST and B>=T(5,30): trains.append(mkt("快速",ro,"軒屋",t))
        b+=1
    # ---- ラッシュの増発（上り）
    if rush:
        slots=[]
        for B in [UP_BASE+i*900 for i in range(40)]:
            if T(7,45)<=B<=T(8,30):
                slots+=[B+9*60,B+15*60]
        kinds=[("急行","犬塚"),("各停","高島"),("急行","蓮木市"),("各停","就島"),("急行","犬塚"),("各停","高島"),("急行","蓮木市"),("各停","就島")]
        for (kd,o),s in zip(kinds,slots):
            tr=mk_up(kd,o,"軒屋",s,note="増発"); tr.label=kd+"（増発）"; trains.append(tr)
    for t in trains:
        if t.dir=="U" and t.d=="軒屋":
            t.compute()
            if RUSH_UP[0]<=t.arr("軒屋")<=RUSH_UP[1]: t.cars=8 if t.kind!="各停" else 6
    return trains
if __name__=="__main__":
    tr=build()
    print(len(tr))
    for t in tr: t.compute()
    print(min(t.dep(t.o) for t in tr)/3600)
