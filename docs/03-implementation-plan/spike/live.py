import os,sys,json,time,re
from dotenv import load_dotenv
load_dotenv("/Users/ibrown/Code/claude-ai/equi-takehome/.env",override=True)
from openai import OpenAI
from openai.lib._pydantic import to_strict_json_schema
import run_extract as rx
from schema import Extraction, CsvMapping
from lean import LeanExtraction
from score import score
cl=OpenAI(timeout=900)
def pv(s):
    s=s.strip().replace("−","-").replace("–","-")
    neg=s.startswith("(") or s.startswith("-")
    m=re.search(r"[\d,]*\.?\d+",s)
    if not m: return None
    v=float(m.group().replace(",",""))
    if re.search(r"\d\s*m\b",s,re.I): v*=1e6
    if re.search(r"\d\s*bn\b",s,re.I): v*=1e9
    if "%" in s: v/=100
    return -v if neg and "(" in s or s.startswith("-") else v
def run(doc,model,lean,tag):
    sch=to_strict_json_schema(LeanExtraction if lean else Extraction)
    req=rx.build(rx.R+doc,model); req["text"]["format"]["schema"]=sch
    if lean: req["input"][0]["content"]+="\nValue_as_written is the printed string; unit 'percent' for % figures."
    t0=time.time(); r=cl.responses.create(**req,max_output_tokens=100000); dt=time.time()-t0
    u=r.usage; p=rx.PRICE[model]; cost=u.input_tokens*p[0]/1e6+u.output_tokens*p[1]/1e6
    ex=json.loads(r.output_text); name=os.path.basename(doc)
    json.dump(ex,open(f"out/{tag}_{name}.json","w"),indent=1)
    rows=[]
    for g in ex["rows"]:
        if lean:
            f=ex["funds"][g["fund_index"]] if 0<=g["fund_index"]<len(ex["funds"]) else {"name":"?","share_class":None}
            v=pv(g["value_as_written"]); 
            rows.append(dict(entity=f["name"],share_class=f["share_class"],measure=g["measure"],period_kind=g["period_kind"],period_end=g["period_end"],value=v))
        else: rows.append(g)
    t=json.load(open(rx.R+doc.rsplit(".",1)[0]+".truth.json")); s=score(t,rows)
    print(f"[{tag}] {name} {model} {dt:.1f}s in={u.input_tokens} out={u.output_tokens} ${cost:.3f} status={r.status} tables={len(ex['tables'])} rows={len(rows)} truth={s['truth']} hit={s['recall_hits']} extra={s['extra']} partial={s['partial']}")
    print("  missing",s["missing"][:6],"\n  wrong",s["wrong_value"][:6],"\n  extra_sample",s["extra_sample"][:8],flush=True)
    return cost
if __name__=="__main__":
    m="gpt-6.1-sol"; tot=0
    which=sys.argv[1]
    os.makedirs("out",exist_ok=True)
    if which=="man": 
        tot+=run(rx.DOCS[0],m,False,"cur"); tot+=run(rx.DOCS[0],m,True,"lean")
    else:
        for d in rx.DOCS[1:]: tot+=run(d,m,which=="lean","lean" if which=="lean" else "cur")
    print("total $",round(tot,3))
