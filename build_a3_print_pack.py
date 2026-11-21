"""Produce eight proportion-preserving A3 pages from verified original files."""
from pathlib import Path
import json
from PIL import Image,ImageOps
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
from pypdf import PdfReader

root=Path(__file__).resolve().parent
out=root/'output/pdf';images=out/'source-images'
temporary=root/'tmp/pdfs';temporary.mkdir(parents=True,exist_ok=True)
pdfmetrics.registerFont(TTFont('Segoe',r'C:\Windows\Fonts\segoeui.ttf'))
pdfmetrics.registerFont(TTFont('SegoeBold',r'C:\Windows\Fonts\segoeuib.ttf'))
NASA='https://science.nasa.gov/'
pages=[
 dict(file='heart-photographer.jpg',title='The Heart',subtitle='Antennae Galaxies | NGC 4038 and NGC 4039',
      credit='Image copyright: Kent E. Biggs. Featured by NASA Astronomy Picture of the Day, 7 February 2024.',
      source=NASA+'image-article/apod-2024-february-7-the-heart-shaped-antennae-galaxies/'),
 dict(file='rose.jpg',title='The Rose',subtitle='Arp 273 | UGC 1810 and UGC 1813 | Hubble Space Telescope',
      credit='Credit: NASA, ESA, and the Hubble Heritage Team (STScI/AURA).',
      source=NASA+'asset/hubble/a-rose-made-of-galaxies-highlights-hubbles-21st-anniversary/'),
 dict(file='penguin.png',title='The Penguin and the Egg',subtitle='Arp 142 | NGC 2936 and NGC 2937 | James Webb Space Telescope',
      credit='Credit: NASA, ESA, CSA, STScI. NIRCam and MIRI observations.',
      source=NASA+'asset/webb/interacting-galaxies-arp-142-nircam-and-miri-image/'),
 dict(file='mice.tif',title='The Mice',subtitle='NGC 4676 | Hubble Space Telescope',
      credit='Credit: NASA, H. Ford, G. Illingworth, M. Clampin, G. Hartig, the ACS Science Team, and ESA.',
      source=NASA+'asset/hubble/the-mice-ngc-4676-colliding-galaxies-with-tails-of-stars-and-gas/')]
phases=json.loads((root/'our-simulation-phases/phases.json').read_text(encoding='utf-8'))
titles=['Initial approach','First close passage','Tidal stretching','Later combined structure']
descriptions=[
 'Two initially separate spiral galaxies approach each other.',
 'The galaxies pass close to one another and their stellar disks distort.',
 'Stellar material spreads into extended tidal structures.',
 'The central regions lie close together while extended stellar debris remains.']
for i,(title,description,phase) in enumerate(zip(titles,descriptions,phases['phases']),1):
    pages.append(dict(file=f'simulation-phase-{i}.png',title=f'Phase {i}: {title}',
       subtitle=f'Galaxy Encounter | Slow approach | Model time {phase["model_time"]:.2f}',
       credit='Source: our live Galaxy Encounter simulation. Direct high-resolution render of the same saved encounter.',
       source=None,description=description,
       note='Educational collisionless model; no gas or star formation. Later central overlap does not prove a fully settled remnant.'))

path=out/'Galaxy-Encounter-A3-Print-Pack.pdf'
c=canvas.Canvas(str(path),pageCompression=1)
c.setTitle('Galaxy Encounter - Eight A3 Photo Prints')
c.setAuthor('Galaxy Encounter; original image credits appear on each page')
c.setViewerPreference('PrintScaling','None')
report=[]
for number,item in enumerate(pages,1):
    image_path=images/item['file']
    image=Image.open(image_path);image.load()
    iw,ih=image.size
    landscape=iw>ih
    pw,ph=(420*mm,297*mm) if landscape else (297*mm,420*mm)
    c.setPageSize((pw,ph));margin=12*mm
    c.setFillColor(HexColor('#53616e'));c.setFont('Segoe',9)
    c.drawString(margin,ph-14*mm,'GALAXY ENCOUNTER  /  '+('SIMULATION' if number>4 else 'OBSERVED GALAXIES'))
    c.setFillColor(HexColor('#142435'));c.setFont('SegoeBold',24)
    c.drawString(margin,ph-26*mm,item['title'])
    c.setFillColor(HexColor('#53616e'));c.setFont('Segoe',10.5)
    c.drawString(margin,ph-33*mm,item['subtitle'])
    bottom=34*mm if number>4 else 28*mm
    top=ph-40*mm
    scale=min((pw-2*margin)/iw,(top-bottom)/ih)
    dw,dh=iw*scale,ih*scale
    x=(pw-dw)/2;y=bottom+(top-bottom-dh)/2
    assert x>=margin-.01 and y>=bottom-.01
    assert abs(dw/dh-iw/ih)<1e-10
    # Preserve source pixels; ReportLab embeds original JPEG data unchanged.
    source_image=str(image_path) if image.format=='JPEG' else ImageReader(image.convert('RGB'))
    c.drawImage(source_image,x,y,width=dw,height=dh,mask='auto')
    c.setStrokeColor(HexColor('#d5dce2'));c.setLineWidth(.4)
    c.line(margin,23*mm,pw-margin,23*mm)
    c.setFillColor(HexColor('#44515e'));c.setFont('Segoe',8)
    c.drawString(margin,18*mm,item['credit'])
    if item.get('description'):
        c.setFont('Segoe',9);c.drawString(margin,28*mm,item['description'])
        c.setFont('Segoe',7.5);c.drawString(margin,13*mm,item['note'])
    else:
        c.setFont('Segoe',8)
        text='NASA image source - click to open'
        c.drawString(margin,13*mm,text)
        c.linkURL(item['source'],(margin,12*mm,margin+pdfmetrics.stringWidth(text,'Segoe',8),16*mm),relative=0)
    c.setFont('Segoe',7.5)
    c.drawString(margin,7*mm,'A3 | Print at actual size (100%) | Preserve page orientation | No stretching or cropping')
    c.drawRightString(pw-margin,7*mm,f'{number} / 8')
    dpi=iw/(dw/72)
    report.append(dict(page=number,title=item['title'],source_image=item['file'],
        source_pixels=[iw,ih],page_mm=[round(pw/mm,2),round(ph/mm,2)],
        image_rect_mm=[round(v/mm,2) for v in (x,y,dw,dh)],effective_ppi=round(dpi,1),
        source=item['source'],credit=item['credit']))
    c.showPage()
c.save()
reader=PdfReader(path)
assert len(reader.pages)==8
for page in reader.pages:
    size=sorted([float(page.mediabox.width)/mm,float(page.mediabox.height)/mm])
    assert abs(size[0]-297)<.01 and abs(size[1]-420)<.01
assert min(item['effective_ppi'] for item in report)>240
(out/'print-quality-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
(out/'PRINT-INSTRUCTIONS.txt').write_text(
    'Send Galaxy-Encounter-A3-Print-Pack.pdf to the print shop.\n'
    'Print all 8 pages on A3 paper, single-sided, in colour, at actual size (100%).\n'
    'Use the orientation of each PDF page. No borderless enlargement, stretching or cropping.\n'
    'The white margins are intentional.\n',encoding='utf-8')
print('Created',path,round(path.stat().st_size/1024**2,1),'MB',flush=True)
for item in report:print(item['page'],item['title'],item['source_pixels'],item['effective_ppi'],'ppi',flush=True)
