from PIL import Image
from pathlib import Path
root=Path(__file__).resolve().parent
for p in (root/'output/pdf/source-images').iterdir():
    if p.suffix.lower() not in ('.jpg','.png','.tif'):continue
    try:
        im=Image.open(p);print(p.name,im.size,im.mode)
        im.thumbnail((800,800));im.convert('RGB').save(root/'tmp/pdfs'/(p.stem+'-preview.jpg'))
    except Exception as error:print(p.name,repr(error))
