import asyncio, json, httpx
from typing import Annotated, Literal, Optional
from fastapi import FastAPI, Depends, Query, Header, HTTPException
app=FastAPI()
def user(x_user: Annotated[int,Header()]): return x_user
@app.get("/api/rows",tags=["ask"],operation_id="query_common_rows",summary="Query common rows")
def rows(u:Annotated[int,Depends(user)], measure:Optional[Literal["return","aum"]]=None, period_end_from:Optional[str]=Query(None,description="YYYY-MM-DD"), sort:Literal["value_desc","value_asc"]="value_desc", limit:int=Query(20,le=100)):
    """Return common rows for the signed-in user. Filter by measure and date."""
    return {"user":u,"measure":measure,"limit":limit}
@app.get("/api/documents/{doc_id}",tags=["ask"],operation_id="get_document")
def doc(doc_id:int,u:Annotated[int,Depends(user)]): return {"user":u,"id":doc_id}
@app.post("/api/files/resync",tags=["admin"])
def resync(): return {}
@app.get("/api/files/{fid}/content")
def content(fid:int): return {}
def tools(app):
    sp=app.openapi(); out=[]; comp=sp.get("components",{}).get("schemas",{})
    for path,ops in sp["paths"].items():
        for meth,op in ops.items():
            if meth!="get" or "ask" not in op.get("tags",[]): continue
            props={};req=[]
            for p in op.get("parameters",[]):
                if p["name"]=="x-user": continue   # injected auth header, not a model parameter
                if p["in"] not in("query","path"): continue
                sc=dict(p["schema"]); 
                if p.get("description"): sc["description"]=p["description"]
                props[p["name"]]=sc
                if p.get("required"): req.append(p["name"])
            out.append({"type":"function","name":op["operationId"],"description":(op.get("description") or op.get("summary") or ""),
                        "parameters":{"type":"object","properties":props,"required":req,"additionalProperties":False},"strict":False,"_path":path})
    return out
async def call(t,args,uid):
    path=t["_path"]
    for k,v in list(args.items()):
        if "{"+k+"}" in path: path=path.replace("{"+k+"}",str(args.pop(k)))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://app") as c:
        r=await c.get(path,params={k:v for k,v in args.items() if v is not None},headers={"x-user":str(uid)})
        return r.status_code,r.json()
T=tools(app); print(json.dumps([{k:v for k,v in t.items() if k!="_path"} for t in T],indent=1)[:1800])
print(asyncio.run(call(T[0],{"measure":"return","limit":5},42)))
print(asyncio.run(call(T[1],{"doc_id":9},7)))
print("anyOf-nullable params:",[ (n,p) for n,p in T[0]["parameters"]["properties"].items() if "anyOf" in p][:1])
