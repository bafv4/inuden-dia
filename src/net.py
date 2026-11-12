# 路線・駅・走行時分
import math
from functools import lru_cache
MAIN=[("軒屋",0.0),("土佐浜",0.7),("大手通",1.4),("裏町",2.3),("高砂町",3.2),("千代町",4.0),("境橋",5.0),("新犬村",6.2),("船場町",7.0),("錦町",7.9),("羅丹庵",8.8),("学院前",9.8),("瑞法院",11.1),("本位堂",12.6),("城見台",14.2),("就島",16.2),("高島公園",17.7),("高島",19.5),("西高島",21.5),("吹上台",22.8),("朝日台",24.5),("岩瀬",26.6),("秋田台",28.4),("院庄",30.8),("三宅",32.7),("戌居",36.0),("狛野",38.0),("新狛野",39.1),("北川津",41.1),("星野",42.6),("犬塚",44.5),("長坂",46.2),("下岩田",49.1),("羽土",52.1),("小椋",54.4),("東松田",57.0),("東蔵寺",60.5),("奥雲口",62.6),("霧里",64.5),("奥雲温泉",65.5)]
HASU=[("学院前",0.0),("甲斐野",1.0),("佐茂町",2.2),("北洋台",3.7),("売布",4.7),("丑島",5.9),("桜湧水",7.6),("牧羊町",8.8),("蓮木市",9.8)]
MN=[s for s,_ in MAIN]; HN=[s for s,_ in HASU]
KM={}
for s,k in MAIN: KM[("M",s)]=k
for s,k in HASU: KM[("H",s)]=k
def line_of(a,b):
    # 区間の路線
    if a in HN and b in HN and not (a=="学院前" and b in MN and b!="学院前" ) : 
        if a=="学院前" and b=="学院前": return "M"
        if (a=="学院前" and b in HN) or (b=="学院前" and a in HN) or (a in HN and b in HN): return "H"
    return "M"
def pos(line,s): return KM[(line,s)]
SINGLE=[(44.5,54.4),(57.0,65.5)]
def lim_main(km):
    for a,b in SINGLE:
        if a<km<b: return 100
    return 120
def lim_h(km): return 120
# 車両
A0=2.5;V1=40.0;V2=80.0;BRK=3.0;VMAX=120.0
def res(v): return (13+0.15*v+0.0024*v*v)/1000/1.1*3.6
def acc(v):
    a=A0 if v<=V1 else (A0*V1/v if v<=V2 else A0*V1*V2/v/v)
    return max(a-res(v),0)
def run_profile(x0,x1,lim,dx=0.002):
    sgn=1 if x1>x0 else -1
    L_=abs(x1-x0); n=max(1,int(round(L_/dx))); d=L_/n
    lims=[min(lim(x0+sgn*(i+0.5)*d),VMAX) for i in range(n)]
    f=[0.0]*(n+1)
    for i in range(n):
        v=min(f[i],lims[i]); a=acc(v)
        f[i+1]=min(math.sqrt((v/3.6)**2+2*(a/3.6)*d*1000)*3.6,lims[i],lims[i+1] if i+1<n else lims[i])
    b=[0.0]*(n+1)
    for i in range(n,0,-1):
        b[i-1]=min(math.sqrt((b[i]/3.6)**2+2*(BRK/3.6)*d*1000)*3.6,lims[i-1],lims[i-2] if i>=2 else lims[i-1])
    v=[min(f[i],b[i]) for i in range(n+1)]
    t=[0.0]*(n+1)
    for i in range(n): t[i+1]=t[i]+d*1000/max((v[i]+v[i+1])/2/3.6,0.05)
    return d,t
def ceil15(s): return int(math.ceil(s/15-1e-9))*15
@lru_cache(maxsize=None)
def seg(names):
    """names: 停車駅a…通過…停車駅b（進行順）。(所要秒, [通過駅の経過秒])"""
    a,b=names[0],names[-1]
    # 路線判定
    if all(n in HN for n in names) and not all(n in MN for n in names): line="H"
    else: line="M"
    if line=="H": lim=lim_h
    else: lim=lim_main
    x0,x1=pos(line,a),pos(line,b)
    d,t=run_profile(x0,x1,lim)
    raw=t[-1]; tot=ceil15(raw*1.03)
    ps=[]
    for s in names[1:-1]:
        j=int(round(abs(pos(line,s)-x0)/d)); ps.append(tot*t[j]/raw)
    return tot,ps
EXP_STOP=set("軒屋 土佐浜 大手通 裏町 高砂町 千代町 境橋 新犬村 学院前 就島 高島 吹上台 朝日台 秋田台 院庄 三宅 戌居 狛野 新狛野 北川津 星野 犬塚 長坂 小椋 東松田 奥雲口 霧里 奥雲温泉 佐茂町 北洋台 牧羊町 蓮木市".split())
MAJOR={"学院前","就島","高島","秋田台","新狛野","犬塚","佐茂町"}
def dwell(s):
    if s=="新犬村": return 60
    if s in MAJOR: return 45
    if s in EXP_STOP: return 30
    return 15
CORE=MN[:8]
STOPS={
 "各停":None,  # 全駅
 "急行":set(CORE+["学院前","就島","高島","吹上台","朝日台","秋田台","院庄","三宅","戌居","狛野","新狛野","北川津","星野","犬塚","佐茂町","北洋台","牧羊町","蓮木市"]),
 "快速":set(CORE+["就島","高島","秋田台","狛野","新狛野","犬塚","長坂","小椋","東松田","奥雲口","霧里","奥雲温泉"]),
 "回送":set(),
}
def route(o,d):
    """o→d の駅列"""
    def path(o,d):
        if o in MN and d in MN:
            i,j=MN.index(o),MN.index(d)
            return MN[i:j+1] if i<=j else MN[j:i+1][::-1]
        if o in HN and d in HN:
            i,j=HN.index(o),HN.index(d)
            return HN[i:j+1] if i<=j else HN[j:i+1][::-1]
        if o in MN and d in HN: return path(o,"学院前")+path("学院前",d)[1:]
        if o in HN and d in MN: return path(o,"学院前")+path("学院前",d)[1:]
    return path(o,d)
# 駅の線路容量（片方向あたり）
K2=set("高砂町 新犬村 錦町 学院前 本位堂 就島 高島 秋田台 新狛野 犬塚 佐茂町 三宅".split())
TOTAL_CAP={"軒屋":4,"蓮木市":3,"三宅":3,"下岩田":2,"小椋":2,"東松田":2,"奥雲口":2,"霧里":2,"奥雲温泉":2}
SINGLE_SEC=[("犬塚","下岩田"),("下岩田","小椋"),("東松田","奥雲口"),("奥雲口","霧里"),("霧里","奥雲温泉")]
@lru_cache(maxsize=None)
def single_sec_of(a,b):
    """隣接駅 a,b を含む単線区間名"""
    for x,y in SINGLE_SEC:
        i,j=MN.index(x),MN.index(y)
        if a in MN and b in MN:
            ia,ib=MN.index(a),MN.index(b)
            if i<=min(ia,ib) and max(ia,ib)<=j: return (x,y)
    return None
PASS_SINGLE={"犬塚","下岩田","小椋","東松田","奥雲口","霧里","奥雲温泉"}
