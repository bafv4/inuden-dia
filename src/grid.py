import subprocess,sys,re,itertools
from multiprocessing import Pool
mode=sys.argv[1]
def run(a):
    if mode=="D": args=["0",str(a[0]),str(a[1]),"0","630","540"]
    else: args=["0","420","330","0",str(a[0]),str(a[1])]
    try:
        o=subprocess.run(["python3","cyc.py"]+args,capture_output=True,text=True,timeout=120).stdout
    except Exception: return None
    m=re.search(r"all (\d+)",o); s=re.search(r"D各停 (\d+) D優等 (\d+) U各停 (\d+) U優等 (\d+)",o)
    if not m or not s or m.group(1)!="0": return None
    v=list(map(int,s.groups()))
    sc=(v[0]+2*v[1]) if mode=="D" else (v[2]+2*v[3])
    return (sc,v,a)
if __name__=="__main__":
    if mode=="D": cands=[(e,r) for r in range(150,451,30) for e in range(r+90,r+400,30)]
    else: cands=[(e,r) for e in range(300,811,30) for r in range(e+60,e+241,15)]
    with Pool(2) as p: res=[x for x in p.map(run,cands) if x]
    res.sort()
    for r in res[:10]: print(r)
