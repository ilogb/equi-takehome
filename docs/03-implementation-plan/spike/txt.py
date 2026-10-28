import pdfplumber,tiktoken
enc=tiktoken.get_encoding("o200k_base")
R="/Users/ibrown/Code/claude-ai/equi-takehome/fixtures/"
for f in ["real/man-ahl_factsheet_2026-08.pdf","real/fundsmith_factsheet_2026-01.pdf","real/uvic-pension_performance-report_2026-07.pdf","synthetic/harborline-custody_account-statement_2026-09.pdf"]:
    with pdfplumber.open(R+f) as p:
        t="\n".join(pg.extract_text() or "" for pg in p.pages)
        nt=sum(len(pg.find_tables()) for pg in p.pages)
    print(f,len(p.pages),"text tokens",len(enc.encode(t)),"pdfplumber tables",nt)
    if "man-ahl" in f: open("manahl.txt","w").write(t)
