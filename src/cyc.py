# 毎時同じ形になるように、同じ枠（slot）の列車に同じ調整を当てる解法
import pickle,sys
from ops import *
import build as BM
from build import T,UP_BASE,UP_OFF,mkt,mk_up
from run_all import add_branch
def slot_of(t):
    return (t.dir,t.kind,t.o,t.d,int(round(t.anchor))%3600)
def gen_pattern(t_from,t_to,down_off):
    tr=[]
    B=t_from - (t_from%900)
    while B<t_to:
        k=(B//900)%4
        for kd,d,off in (("各停",["秋田台","高島"][k%2],down_off[0]),("急行",["犬塚","蓮木市"][k%2],down_off[1]),("快速","奥雲温泉" if k==0 else "犬塚",down_off[2])):
            x=mkt(kd,"軒屋",d,B+off); x.anchor=x.dep0; tr.append(x)
        B+=900
    B=UP_BASE
    while B<t_to:
        if B>=t_from:
            k=((B-UP_BASE)//900)%4
            for kd,o,off in (("各停",["秋田台","高島"][k%2],UP_OFF[0]),("急行",["犬塚","蓮木市"][k%2],UP_OFF[1]),("快速","奥雲温泉" if k==0 else "犬塚",UP_OFF[2])):
                x=mk_up(kd,o,"軒屋",B+off); x.anchor=x.dep0; tr.append(x)
        B+=900
    return tr
def sync(trains):
    S={}
    for t in trains:
        k=slot_of(t); s=S.setdefault(k,{"shift":0,"hold":{}})
        s["shift"]=max(s["shift"],t.dep0-t.anchor)
        for st,v in t.hold.items(): s["hold"][st]=max(s["hold"].get(st,0),v)
    for t in trains:
        s=S[slot_of(t)]; t.dep0=t.anchor+s["shift"]; t.hold=dict(s["hold"])
    return S
def cyc_solve(trains,win,maxit=600,log=None,maxwait=240):
    for i in range(maxit):
        sync(trains)
        cs,links=all_conf(trains)
        cs=[c for c in cs if win[0]<=c[1]<=win[1]]
        if not cs: return [],sync(trains)
        if not resolve2(trains,cs[0],maxwait,log): return cs,None
    return cs,None
if __name__=="__main__":
    off=tuple(int(x) for x in sys.argv[1:4]) if len(sys.argv)>3 else BM.DOWN_OFF
    if len(sys.argv)>6:
        import build; build.UP_OFF=tuple(int(x) for x in sys.argv[4:7])
        globals()["UP_OFF"]=build.UP_OFF
    BM.cnt.clear()
    tr=gen_pattern(T(8,0),T(14,30),off)
    log=[]
    left,S=cyc_solve(tr,(T(9,30),T(13,0)),log=log)
    print("main",len(left))
    for t in tr: t.compute()
    br=add_branch(tr)
    for b in br: b.anchor=b.dep0
    tr+=br
    left,S=cyc_solve(tr,(T(9,30),T(13,0)),log=log)
    print("all",len(left))
    for c in left[:6]: print(c[0],hms(c[1]),getattr(c[2],'id',''),c[2].kind,c[2].o,c[2].d,c[4])
    pickle.dump((tr,S,off,UP_OFF),open(f"cyc_{off[1]}_{off[2]}_{UP_OFF[1]}_{UP_OFF[2]}.pkl","wb"))
    # 評価
    mid=[t for t in tr if T(10,0)<=t.anchor<T(11,0)]
    lw=sum(sum(t.hold.values()) for t in mid if t.kind=="各停")
    ew=sum(sum(t.hold.values()) for t in mid if t.kind!="各停")
    ups=[t for t in mid if t.dir=="U"]; dns=[t for t in mid if t.dir=="D"]
    f=lambda L,k: sum(sum(t.hold.values())+(t.dep0-t.anchor) for t in L if (t.kind=="各停")==k)
    print("score D各停",f(dns,True),"D優等",f(dns,False),"U各停",f(ups,True),"U優等",f(ups,False))
