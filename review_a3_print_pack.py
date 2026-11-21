from pathlib import Path
import shutil
import subprocess
from PIL import Image,ImageOps,ImageDraw,ImageFont

root=Path(__file__).resolve().parent
folder=root/'tmp/pdfs/review';folder.mkdir(parents=True,exist_ok=True)
pdf=root/'output/pdf/Galaxy-Encounter-A3-Print-Pack.pdf'
subprocess.run([shutil.which('pdftoppm'),'-r','65','-png',str(pdf),str(folder/'page')],check=True)
files=sorted(folder.glob('page-*.png'))
assert len(files)==8
sheet=Image.new('RGB',(1600,1280),'#dce2e7')
draw=ImageDraw.Draw(sheet)
font=ImageFont.truetype(r'C:\Windows\Fonts\segoeui.ttf',18)
for i,path in enumerate(files):
    image=Image.open(path).convert('RGB')
    image.thumbnail((380,575))
    x=(i%4)*400+(400-image.width)//2;y=(i//4)*640+20
    sheet.paste(image,(x,y));draw.text(((i%4)*400+18,(i//4)*640+608),f'Page {i+1}',fill='#253c50',font=font)
sheet.save(root/'output/pdf/A3-print-preview.jpg',quality=94)
print('Rendered and assembled all 8 page previews.',flush=True)
