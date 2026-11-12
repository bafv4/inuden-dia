import pickle,sys
from build import *
OKU_D=90; OKU_U=120     # 奥雲線各停と快速の新狛野での接続（秒）
HASU_D=75; HASU_U=150   # 蓮木線内各停と本線各停の学院前での接続（秒）
def add_branch(trains):
    new=[]
    # 蓮木線内の各停：本線各停と学院前で同じホーム乗り換え
    for L in trains:
        if L.kind!="各停" or "学院前" not in L.route or L.o=="学院前" or L.d=="学院前": continue
        if L.d in HN or L.o in HN: continue
        if L.dir=="D":
            dep=L.arr("学院前")+HASU_D
            if dep<FIRST: continue
            new.append(mkt("各停","学院前","蓮木市",dep,note="線内"))
        else:
            a=L.arr("学院前")-HASU_U
            tr=mkt("各停","蓮木市","学院前",0,note="線内"); tr.compute()
            tr.dep0=a-tr.arr("学院前")
            if tr.dep0>=FIRST: new.append(tr)
    # 奥雲線の各停：毎時1本（新狛野〜奥雲温泉）。新狛野（2面4線）で快速犬塚行・犬塚発と対面接続
    # 下りは快速の発車の OKU_D 秒後に出る。上りは快速の到着の OKU_U 秒前に着く（新狛野までに快速に追いつかれない）
    for R in trains:
        if R.kind!="快速" or "犬塚" not in (R.o,R.d): continue
        if R.dir=="D" and ((R.dep("軒屋")//900)%4)==2:
            dep=R.dep("新狛野")+OKU_D
            new.append(mkt("各停","新狛野","奥雲温泉",dep,note="奥雲線"))
        if R.dir=="U" and R.o=="犬塚":
            k=((R.dep("新犬村")-UP_BASE)//900)%4 if R.times else None
            if k==2:
                tr=mkt("各停","奥雲温泉","新狛野",0,note="奥雲線"); tr.compute()
                tr.dep0=R.arr("新狛野")-OKU_U-tr.arr("新狛野")
                if tr.dep0>=FIRST: new.append(tr)
    return new
if __name__=="__main__":
    tr=build()
    log=[]
    left,links=solve2(tr,log=log)
    print("main left",len(left))
    for t in tr: t.compute()
    br=add_branch(tr); tr+=br
    left,links=solve2(tr,log=log)
    print("all left",len(left), left[:3])
    l2,stab=link(tr)
    print("stabled",stab)
    pickle.dump((tr,log),open("res.pkl","wb"))
    print(len(log)); print("\n".join(log[-40:]))
