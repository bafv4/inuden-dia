import pickle,sys
from sched import *
from build import T
tr,S,off,up=pickle.load(open(sys.argv[1],"rb"))
for t in tr: t.compute()
for d in "DU":
    for t in sorted([t for t in tr if t.dir==d and T(10,0)<=t.anchor<T(11,0)],key=lambda t:t.dep(t.o)):
        h=sum(t.hold.values())+(t.dep0-t.anchor)
        if h: print(d,f"{t.kind}{t.o}→{t.d}",fmt(t.dep(t.o)),t.hold)
