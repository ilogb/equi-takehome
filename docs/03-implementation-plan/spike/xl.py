import pandas as pd, io, json
from csvmap import nw,R,apply
from score import score
import csvmap
f=R+"northwind-capital_monthly-returns_2026-09.csv"
df=pd.read_csv(f,dtype=str,keep_default_na=False)
# realistic xlsx: real dates and numbers
df2=df.copy(); df2["Period"]=pd.to_datetime(df2["Period"]); 
for c in ["Net Return %","Benchmark Return %"]: df2[c]=pd.to_numeric(df2[c],errors="coerce")
df2.to_excel("nw.xlsx",index=False,sheet_name="Returns")
x=pd.read_excel("nw.xlsx",sheet_name=None,dtype=str,keep_default_na=False)  # all sheets
print({k:v.shape for k,v in x.items()}); print(x["Returns"].head(3).to_string())
# bridge: sheet -> csv text -> same code path
buf=io.StringIO(); x["Returns"].to_csv(buf,index=False); open("nw_from_xlsx.csv","w").write(buf.getvalue())
rows=apply("nw_from_xlsx.csv",nw); s=score(json.load(open(R+"northwind-capital_monthly-returns_2026-09.truth.json")),rows)
print({k:s[k] for k in("truth","got","recall_hits","missing","wrong_value","extra")})
