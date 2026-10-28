import pdfplumber,tiktoken,json,re
enc=tiktoken.get_encoding("o200k_base"); R="/Users/ibrown/Code/claude-ai/equi-takehome/fixtures/"
def est(f):
    tabs=[];nums=0
    with pdfplumber.open(R+f) as p:
        for pg in p.pages:
            for t in pg.extract_tables(): tabs.append({"title":"x","header_rows":[t[0]],"body_rows":t[1:]})
        txt="\n".join(pg.extract_text() or "" for pg in p.pages)
    nums=len(re.findall(r"-?\d+\.\d+%",txt))
    row=json.dumps(dict(entity="Man AHL Diversified plc",entity_kind="fund",share_class="Class DN USD",measure="return",period_kind="month",period_end="2026-01-31",value_as_written="8.42%",value=0.0842,unit="fraction",currency="USD",benchmark_name=None,table_index=0,row=3,col=1))
    t_tok=len(enc.encode(json.dumps(tabs))); r_tok=len(enc.encode(row))
    print(f,"pdfplumber tables",len(tabs),"body rows",sum(len(t['body_rows']) for t in tabs),"tables-json tokens",t_tok,"| pct figures in text",nums,"| tokens/row",r_tok,"| est rows tokens",nums*r_tok)
est("real/man-ahl_factsheet_2026-08.pdf"); est("real/fundsmith_factsheet_2026-01.pdf")
