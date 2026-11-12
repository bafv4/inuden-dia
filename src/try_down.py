from sched import *
def gen(offs,T0=10*3600,n=12):
    L=[]
    for b in range(n):
        T=T0+b*900; k=b%4
        L.append(Train(f"L{b}","各停","軒屋",["秋田台","高島"][k%2],T+offs[0]))
        L.append(Train(f"E{b}","急行","軒屋",["犬塚","蓮木市"][k%2],T+offs[1]))
        L.append(Train(f"R{b}","快速","軒屋","奥雲温泉" if k==0 else "犬塚",T+offs[2]))
    return L
