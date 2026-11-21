"""Five clean A3 prints, with only shape, galaxy and phase names visible."""
from pathlib import Path
import io
import json
import zlib
from PIL import Image,ImageDraw,ImageFont
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from pypdf import PdfReader,PdfWriter
from pypdf._configuration import overwrite_configuration
from pypdf.generic import NameObject,NumberObject,DictionaryObject,DecodedStreamObject,EncodedStreamObject

root=Path(__file__).resolve().parent
# This locally generated pack contains an 82 MB original NASA JPEG stream.
overwrite_configuration(maximum_declared_stream_length=200_000_000)
out=root/'output/pdf';sources=out/'source-images'
temporary=root/'tmp/pdfs/clean';temporary.mkdir(parents=True,exist_ok=True)
font_regular=r'C:\Windows\Fonts\segoeui.ttf'
font_bold=r'C:\Windows\Fonts\segoeuib.ttf'
pdfmetrics.registerFont(TTFont('Segoe',font_regular))
pdfmetrics.registerFont(TTFont('SegoeBold',font_bold))

# One standalone A3-ratio image containing all four saved simulation moments.
W,H=7440,5261
combined=Image.new('RGB',(W,H),'white');draw=ImageDraw.Draw(combined)
title_font=ImageFont.truetype(font_bold,155)
pair_font=ImageFont.truetype(font_regular,100)
phase_font=ImageFont.truetype(font_bold,108)
draw.text((W//2,110),'The Four Phases',font=title_font,fill='#142435',anchor='mt')
draw.text((W//2,310),'Galaxy A + Galaxy B',font=pair_font,fill='#53616e',anchor='mt')
margin,gap,grid_top=180,100,510
cell_w=(W-2*margin-gap)//2
cell_h=(H-grid_top-margin-gap)//2
phase_names=['Phase 1 - Initial approach','Phase 2 - First close passage',
             'Phase 3 - Tidal stretching','Phase 4 - Later combined structure']
placements=[]
for index,label in enumerate(phase_names):
    x=margin+(index%2)*(cell_w+gap)
    y=grid_top+(index//2)*(cell_h+gap)
    image=Image.open(sources/f'simulation-phase-{index+1}.png').convert('RGB')
    original_size=image.size
    image.thumbnail((cell_w,cell_h-160),Image.Resampling.LANCZOS)
    ix=x+(cell_w-image.width)//2;iy=y+(cell_h-160-image.height)//2
    combined.paste(image,(ix,iy))
    draw.text((x+cell_w//2,y+cell_h-118),label,font=phase_font,fill='#142435',anchor='mt')
    placements.append(dict(phase=index+1,source_size=original_size,
                           placed_pixels=[ix,iy,image.width,image.height],label=label))
combined_path=out/'Galaxy-Encounter-Four-Phases-A3.png'
combined.save(combined_path,dpi=(450,450),optimize=True)
preview=combined.copy();preview.thumbnail((1400,1400));preview.save(temporary/'four-phases-preview.jpg',quality=95)
print('Created single four-phase A3 image.',flush=True)

labels=[('The Heart','NGC 4038 + NGC 4039 (Antennae Galaxies)'),
        ('The Rose','UGC 1810 + UGC 1813 (Arp 273)'),
        ('The Penguin and the Egg','NGC 2936 (Penguin) + NGC 2937 (Egg)'),
        ('The Mice','NGC 4676A + NGC 4676B')]
old_report=json.loads((out/'print-quality-report.json').read_text(encoding='utf-8'))
old_pdf=PdfReader(out/'Galaxy-Encounter-A3-Print-Pack.pdf')
header_file=temporary/'headers.pdf'
c=canvas.Canvas(str(header_file),pageCompression=1)
rectangles=[]
for index,(title,pair) in enumerate(labels):
    old_page=old_pdf.pages[index]
    pw,ph=float(old_page.mediabox.width),float(old_page.mediabox.height)
    c.setPageSize((pw,ph))
    c.setFont('SegoeBold',28);c.setFillColor(HexColor('#142435'))
    c.drawString(12*mm,ph-19*mm,title)
    c.setFont('Segoe',15);c.setFillColor(HexColor('#53616e'))
    c.drawString(12*mm,ph-28*mm,pair)
    iw,ih=old_report[index]['source_pixels']
    bottom=12*mm;top=ph-37*mm
    scale=min((pw-24*mm)/iw,(top-bottom)/ih)
    dw,dh=iw*scale,ih*scale
    x=(pw-dw)/2;y=bottom+(top-bottom-dh)/2
    rectangles.append((x,y,dw,dh))
    assert abs(dw/dh-iw/ih)<1e-10
    c.showPage()
c.setPageSize((420*mm,297*mm));c.showPage();c.save()

writer=PdfWriter()
for page in PdfReader(header_file).pages:writer.add_page(page)
def attach_image(page,image,rectangle):
    cloned=image.clone(writer)
    reference=getattr(cloned,'indirect_reference',None)
    if reference is None:reference=writer._add_object(cloned)
    resources=page['/Resources']
    if '/XObject' not in resources:resources[NameObject('/XObject')]=DictionaryObject()
    resources['/XObject'][NameObject('/Photo')]=reference
    x,y,w,h=rectangle
    original=page.get_contents()
    content=DecodedStreamObject()
    content.set_data((original.get_data() if original is not None else b'')+
                     f'\nq {w:.8f} 0 0 {h:.8f} {x:.8f} {y:.8f} cm /Photo Do Q\n'.encode('ascii'))
    page[NameObject('/Contents')]=writer._add_object(content)

for index in range(4):
    objects=old_pdf.pages[index]['/Resources']['/XObject']
    photos=[ref.get_object() for ref in objects.values()
            if ref.get_object().get('/Subtype')=='/Image' and ref.get_object().get('/Width',0)>1000]
    assert len(photos)==1
    attach_image(writer.pages[index],photos[0],rectangles[index])
    actual=writer.pages[index].extract_text().strip().splitlines()
    print('Page labels:',repr(actual),flush=True)
    assert [line.strip() for line in actual if line.strip()]==list(labels[index])

stream=EncodedStreamObject()
stream._data=zlib.compress(combined.tobytes(),6)
stream.update({NameObject('/Type'):NameObject('/XObject'),NameObject('/Subtype'):NameObject('/Image'),
    NameObject('/Width'):NumberObject(W),NameObject('/Height'):NumberObject(H),
    NameObject('/ColorSpace'):NameObject('/DeviceRGB'),NameObject('/BitsPerComponent'):NumberObject(8),
    NameObject('/Filter'):NameObject('/FlateDecode')})
scale=min(420*mm/W,297*mm/H)
attach_image(writer.pages[4],stream,((420*mm-W*scale)/2,(297*mm-H*scale)/2,W*scale,H*scale))
credits=' | '.join(item['credit']+' '+str(item['source']) for item in old_report[:4])
writer.add_metadata({'/Title':'Galaxy Encounter - Five Clean A3 Prints',
                     '/Subject':credits,'/Author':'Galaxy Encounter; image credits preserved in PDF metadata'})
writer.create_viewer_preferences();writer.viewer_preferences.print_scaling=NameObject('/None')
path=out/'Galaxy-Encounter-A3-Clean.pdf'
with path.open('wb') as output:writer.write(output)
verified=PdfReader(path);assert len(verified.pages)==5
for page in verified.pages:
    dimensions=sorted((float(page.mediabox.width)/mm,float(page.mediabox.height)/mm))
    assert abs(dimensions[0]-297)<.01 and abs(dimensions[1]-420)<.01
    text=page.extract_text()
    assert not any(unwanted in text for unwanted in ('Print at','Source:','Credit:','model time','A3 |'))
(out/'clean-print-layout.json').write_text(json.dumps(dict(pages=labels,
    combined_image=str(combined_path),combined_pixels=[W,H],phase_placements=placements),indent=2),encoding='utf-8')
print('Created',path,round(path.stat().st_size/1024**2,1),'MB',flush=True)
