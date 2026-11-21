from pathlib import Path
from html.parser import HTMLParser
from PIL import Image
import re

root=Path(__file__).resolve().parent
class Text(HTMLParser):
    def __init__(self):super().__init__();self.parts=[]
    def handle_data(self,data):self.parts.append(data.strip())
for name in ('mice','rose'):
    parser=Text();parser.feed((root/f'tmp/pdfs/nasa/{name}.html').read_text(encoding='utf-8'))
    text=' '.join(parser.parts)
    print(name,re.findall(r'.{0,50}(?:Ford|Illingworth|Riess|Macri).{0,180}',text))
for i in range(1,5):
    im=Image.open(root/f'output/pdf/source-images/simulation-phase-{i}.png')
    im.thumbnail((900,900));im.save(root/f'tmp/pdfs/simulation-{i}-preview.png')
bad=root/'output/pdf/source-images/heart-nasa.jpg'
if bad.exists():bad.replace(root/'tmp/pdfs/nasa/heart-redirect.html')
