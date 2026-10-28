import re,json
def norm(n):
    n=re.sub(r"\(.*?\)","",n or "").lower().replace("&","and")
    n=re.sub(r"[^a-z0-9 ]"," ",n)
    n=re.sub(r"\b(lp|ltd|llc|fund|l p)\b"," ",n)
    return " ".join(n.split())
def key(r): return (norm(r["entity"]),norm(r.get("share_class") or ""),r["measure"],r["period_kind"],r["period_end"])
def truth_rows(t):
    return [dict(entity=o["fund"],share_class=o["share_class"],measure=o["metric"],period_kind=o["period_kind"],period_end=o["period_end"],value=float(o["value"])) for o in t["observations"]]
def score(truth,got,tol=0.00005):
    T=truth_rows(truth); G={}
    for g in got: G.setdefault(key(g),[]).append(g)
    hit=0;miss=[];wrongval=[]
    for t in T:
        c=G.get(key(t),[])
        if any(g["value"] is not None and abs(g["value"]-t["value"])<=tol for g in c): hit+=1
        else: (wrongval if c else miss).append((key(t),t["value"],[g["value"] for g in c]))
    tk={key(t) for t in T}
    extra=[g for g in got if key(g) not in tk]
    return dict(truth=len(T),got=len(got),recall_hits=hit,missing=miss,wrong_value=wrongval,extra=len(extra),extra_sample=[key(g)+(g["value"],) for g in extra[:8]],partial=truth.get("partial",False))
