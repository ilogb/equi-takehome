import pandas as pd, io, re, json, sys
from score import score
R="/Users/ibrown/Code/claude-ai/equi-takehome/fixtures/synthetic/"
def parse_val(s,unit):
    s=str(s).strip().replace("−","-")
    if s=="" or s.lower() in("n/a","nan","–","-","n/m"): return None
    neg=s.startswith("(") and s.endswith(")")
    s=s.strip("()*").replace("%","").replace(",","")
    v=float(s); v=-v if neg else v
    return v/100 if unit in("percent_number","percent_string") else v
def apply(path,m):
    raw=open(path,encoding="utf-8-sig",newline="").read()
    df=pd.read_csv(io.StringIO(raw),header=m["header_row_index"],dtype=str,keep_default_na=False)
    ec=m["entity_column"]
    for p in m["skip_footer_starting_with"]: df=df[~df[df.columns[0]].str.startswith(p)]
    df=df[df[ec].str.strip()!=""]
    out=[]
    for _,r in df.iterrows():
        sc=r[m["share_class_column"]] if m["share_class_column"] else None
        if m["layout"]=="long":
            pe=pd.to_datetime(r[m["date_column"]]).strftime("%Y-%m-%d")
            for vc in m["value_columns"]:
                out.append(dict(entity=r[ec],share_class=sc,measure=vc["measure"],period_kind=vc["period_kind"],period_end=pe,value=parse_val(r[vc["column"]],vc["unit"]),benchmark=r.get(vc.get("benchmark_name_column") or "")))
        else:
            for c in m["wide_date_columns"]:
                pe=(pd.to_datetime(c,format=m["wide_date_format"])+pd.offsets.MonthEnd(0)).strftime("%Y-%m-%d")
                out.append(dict(entity=r[ec],share_class=sc,measure="return",period_kind="month",period_end=pe,value=parse_val(r[c],"percent_string")))
            for vc in m["value_columns"]:
                out.append(dict(entity=r[ec],share_class=sc,measure=vc["measure"],period_kind=vc["period_kind"],period_end=vc["period_end_literal"],value=parse_val(r[vc["column"]],vc["unit"]),_col=vc["column"]))
    for o in out:
        for ov in m.get("period_end_overrides",[]):
            if o.get("_col")==ov["column"] and ov["entity"].lower() in o["entity"].lower(): o["period_end"]=ov["period_end"]
    return [o for o in out if o["value"] is not None]
nw=dict(layout="long",header_row_index=0,skip_footer_starting_with=[],entity_column="Fund",share_class_column="Share Class",date_column="Period",wide_date_columns=[],wide_date_format=None,
  value_columns=[dict(column="Net Return %",measure="return",period_kind="month",unit="percent_number",benchmark_name_column=None,period_end_literal=None),
                 dict(column="Benchmark Return %",measure="benchmark_return",period_kind="month",unit="percent_number",benchmark_name_column="Benchmark",period_end_literal=None)])
ab=dict(layout="wide",header_row_index=3,skip_footer_starting_with=["*","Source"],entity_column="Fund",share_class_column="Class",date_column=None,
  wide_date_columns=["Jan-26","Feb-26","Mar-26","Apr-26","May-26","Jun-26","Jul-26","Aug-26","Sep-26"],wide_date_format="%b-%y",
  value_columns=[dict(column="YTD",measure="return",period_kind="ytd",unit="percent_string",benchmark_name_column=None,period_end_literal="2026-09-30")])
if __name__=="__main__":
    for f,m in (("northwind-capital_monthly-returns_2026-09",nw),("alderbank_performance-summary_2026-09",ab)):
        rows=apply(R+f+".csv",m); t=json.load(open(R+f+".truth.json"))
        s=score(t,rows); print(f,{k:v for k,v in s.items()})
