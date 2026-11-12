from sched import *
def show(tr,stations=None):
    for t in tr:
        hs=" ".join(f"{k}+{v}" for k,v in t.hold.items())
        xs=" ".join(t.xstop)
        print(f"{t.id:6} {t.label}{t.d}行 {fmt(t.dep(t.o))}→{fmt(t.arr(t.d))}  {hs} {xs}")
