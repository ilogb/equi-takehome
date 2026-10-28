import json,glob,calendar,datetime,os
from score import norm,truth_rows
R="/Users/ibrown/Code/claude-ai/equi-takehome/fixtures/"
def snap(d):
    y,m,_=map(int,d.split("-")); return f"{y}-{m:02d}-{calendar.monthrange(y,m)[1]:02d}"
def sc(s): return set(norm(s or "").replace("class","").split())-{"eur","usd","gbp"}
def ent_ok(a,b): a,b=set(norm(a).split()),set(norm(b).split()); return a<=b or b<=a
PK={"calendar_year":"1y"}
def rows_of(ex):
    out=[]
    for g in ex["rows"]:
        if "fund_index" in g:
            f=ex["funds"][g["fund_index"]]; g=dict(g,entity=f["name"],share_class=f["share_class"])
            from live import pv
            g["value"]=pv(g["value_as_written"])
        out.append(g)
    return out
def lenient(truth,got,tol=0.00005):
    T=truth_rows(truth); hit=0; miss=[]
    used=set()
    for t in T:
        ok=False
        for i,g in enumerate(got):
            if g["value"] is None or abs(g["value"]-t["value"])>tol: continue
            if g["measure"]!=t["measure"] or PK.get(g["period_kind"],g["period_kind"])!=t["period_kind"]: continue
            if snap(g["period_end"])!=snap(t["period_end"]) and not (t["period_kind"]=="other" and g["period_end"]==t["period_end"]): continue
            if not ent_ok(g["entity"],t["entity"]): continue
            if sc(t["share_class"]) and sc(g["share_class"]) and not (sc(t["share_class"])<=sc(g["share_class"]) or sc(g["share_class"])<=sc(t["share_class"])): continue
            ok=True; used.add(i); break
        hit+=ok
        if not ok: miss.append((t["entity"],t["share_class"],t["measure"],t["period_kind"],t["period_end"],t["value"]))
    return hit,len(T),miss,len(got)
if __name__=="__main__":
    for f in sorted(glob.glob("out/*_*.json")):
        tag,name=os.path.basename(f).split("_",1); name=name[:-5]
        d=("real/" if os.path.exists(R+"real/"+name) else "synthetic/")+name
        t=json.load(open(R+d.rsplit(".",1)[0]+".truth.json")); ex=json.load(open(f))
        h,n,m,ng=lenient(t,rows_of(ex)); print(tag,name,"lenient recall",h,"/",n,"rows out",ng,"precision",round(h/ng,2) if not t.get("partial") else "n/a(partial)"); 
        for x in m[:6]: print("   MISS",x)
