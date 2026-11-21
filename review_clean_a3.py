from pathlib import Path
import shutil
import subprocess
from PIL import Image,ImageDraw,ImageFont

root=Path(__file__).resolve().parent
folder=root/'tmp/pdfs/clean-review';folder.mkdir(parents=True,exist_ok=True)
subprocess.run([shutil.which('pdftoppm'),'-r','70','-png',
    str(root/'output/pdf/Galaxy-Encounter-A3-Clean.pdf'),str(folder/'page')],check=True)
files=sorted(folder.glob('page-*.png'));assert len(files)==5
sheet=Image.new('RGB',(1500,1380),'#dce2e7');draw=ImageDraw.Draw(sheet)
font=ImageFont.truetype(r'C:\Windows\Fonts\segoeui.ttf',20)
for index,path in enumerate(files):
    image=Image.open(path).convert('RGB');image.thumbnail((470,620))
    x=(index%3)*500+(500-image.width)//2;y=(index//3)*690+20
    sheet.paste(image,(x,y));draw.text(((index%3)*500+20,(index//3)*690+650),f'Page {index+1}',fill='#253c50',font=font)
sheet.save(root/'output/pdf/A3-clean-preview.jpg',quality=94)
print('Rendered all five clean pages.',flush=True)
