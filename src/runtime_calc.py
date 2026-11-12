import math
VMAX=120.0
A0=2.5; V1=40.0; V2=80.0   # 起動加速度、定トルク域上限、定出力域上限
BRK=3.0                    # 計算に使う減速度（常用最大4.2の約7割）
def res(v):
    return (13 + 0.15*v + 0.0024*v*v)/1000/1.1*3.6
def acc(v):
    if v<=V1: a=A0
    elif v<=V2: a=A0*V1/v
    else: a=A0*V1*V2/v/v
    return max(a-res(v),0)
from rt import MAIN,HASU
def limit_main(km):
    single=(44.5<km<54.4) or km>57.0
    return min(100 if single else 120,VMAX)
def lim_h(km): return min(120,VMAX)
def run(x0,x1,lim,dx=0.001):
    n=max(1,int(round((x1-x0)/dx))); d=(x1-x0)/n
    xs=[x0+i*d for i in range(n+1)]
    L=[lim(x0+(i+0.5)*d) for i in range(n)]
    f=[0.0]*(n+1)
    for i in range(n):
        v=min(f[i],L[i]); a=acc(v)
        f[i+1]=min(math.sqrt((v/3.6)**2+2*(a/3.6)*d*1000)*3.6,L[i],L[i+1] if i+1<n else L[i])
    b=[0.0]*(n+1)
    for i in range(n,0,-1):
        b[i-1]=min(math.sqrt((b[i]/3.6)**2+2*(BRK/3.6)*d*1000)*3.6,L[i-1],L[i-2] if i>=2 else L[i-1])
    v=[min(f[i],b[i]) for i in range(n+1)]
    t=[0.0]*(n+1)
    for i in range(n):
        t[i+1]=t[i]+d*1000/max((v[i]+v[i+1])/2/3.6,0.05)
    return xs,t,max(v)
def ceil15(s): return int(math.ceil(s/15-1e-9))*15
# 停車時間（駅ごと）
MAJOR={"学院前","就島","高島","秋田台","犬塚","佐茂町","蓮木市","新狛野"}
EXP_STOP=set("軒屋 土佐浜 大手通 裏町 高砂町 千代町 境橋 学院前 就島 高島 吹上台 朝日台 秋田台 院庄 三宅 戌居 狛野 新狛野 北川津 星野 犬塚 長坂 小椋 東松田 奥雲口 霧里 奥雲温泉 佐茂町 北洋台 牧羊町 蓮木市".split())
def dwell(s):
    if s=="新犬村": return 60
    if s in MAJOR: return 45
    if s in EXP_STOP: return 30
    return 15
def timetable(stations,stops,lim):
    names=[s for s,_ in stations]; km=dict(stations)
    seq=[s for s in names if s in stops]
    rows=[(seq[0],None,0)]; T=0
    for a,b in zip(seq,seq[1:]):
        xs,t,vm=run(km[a],km[b],lim); raw=t[-1]
        ia,ib=names.index(a),names.index(b)
        seg=ceil15(raw*1.03)
        for s in names[ia+1:ib]:
            j=min(range(len(xs)),key=lambda k:abs(xs[k]-km[s]))
            rows.append((s,"pass",T+seg*t[j]/raw))
        T+=seg
        if b!=seq[-1]:
            rows.append((b,"stop",T,T+dwell(b))); T+=dwell(b)
        else: rows.append((b,"end",T))
    return rows,T
def fmt(s): s=int(round(s)); return f"{s//60}:{s%60:02d}"
