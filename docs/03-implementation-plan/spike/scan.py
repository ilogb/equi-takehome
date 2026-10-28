import pdfplumber,glob,io,sys
from PIL import Image, ImageDraw
# image-only pdf: render text into a raster, save as PDF
img=Image.new("RGB",(1240,1754),"white"); d=ImageDraw.Draw(img)
for i in range(30): d.text((80,80+40*i),"Scanned factsheet line %d  Return +1.23%%"%i,fill="black")
img.save("scanned.pdf","PDF",resolution=150)
img.save("scanned3.pdf","PDF",resolution=150,save_all=True,append_images=[img,img])
R="/Users/ibrown/Code/claude-ai/equi-takehome/fixtures/"
for f in sorted(glob.glob(R+"*/*.pdf"))+["scanned.pdf","scanned3.pdf"]:
    with pdfplumber.open(f) as p:
        c=[len(pg.extract_text() or "") for pg in p.pages]
    low=sum(x<20 for x in c)
    print(f.split("/")[-1][:48].ljust(48),"pages",len(c),"chars",c[:8],"flag",low>len(c)/2)
