import json
from openai.lib._pydantic import to_strict_json_schema
from schema import Extraction, CsvMapping
BAD={"allOf","not","if","then","else","dependentRequired","dependentSchemas","oneOf"}
def walk(s,d,st):
    st["depth"]=max(st["depth"],d)
    if isinstance(s,dict):
        for k in s:
            if k in BAD: st["bad"].append(k)
        if s.get("type")=="object" or "properties" in s:
            st["props"]+=len(s.get("properties",{}))
            assert s.get("additionalProperties") is False, s
            assert set(s.get("required",[]))==set(s.get("properties",{})), s
        for v in s.values(): walk(v, d+(1 if isinstance(v,dict) and "properties" in v else 0), st)
    elif isinstance(s,list):
        for v in s: walk(v,d,st)
for M in (Extraction,CsvMapping):
    sch=to_strict_json_schema(M); st={"depth":0,"props":0,"bad":[]}
    walk(sch,1,st); print(M.__name__,"props",st["props"],"objdepth",st["depth"],"bad",st["bad"],"chars",len(json.dumps(sch)))
    json.dump(sch,open(M.__name__+".schema.json","w"))
