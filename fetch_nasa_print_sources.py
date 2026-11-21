from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
import urllib.request
import json
import re

folder=Path(__file__).resolve().parent/'tmp/pdfs/nasa'
folder.mkdir(parents=True,exist_ok=True)
pages={
 'rose':'https://science.nasa.gov/asset/hubble/a-rose-made-of-galaxies-highlights-hubbles-21st-anniversary/',
 'mice':'https://science.nasa.gov/asset/hubble/the-mice-ngc-4676-colliding-galaxies-with-tails-of-stars-and-gas/',
 'penguin':'https://science.nasa.gov/asset/webb/interacting-galaxies-arp-142-nircam-and-miri-image/',
 'heart':'https://www.kentbiggs.com/images/galaxies/N4038.htm'}
class Links(HTMLParser):
    def __init__(self):super().__init__();self.links=[]
    def handle_starttag(self,tag,attrs):
        for key,value in attrs:
            if value and (key in ('href','src','data-src','data-download-url') or 'download' in key):
                if re.search(r'\.(jpg|jpeg|png|tif|tiff)(?:[?#]|$)',value,re.I):self.links.append((tag,key,value))

def fetch(item):
    name,url=item
    request=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
    with urllib.request.urlopen(request,timeout=45) as response:content=response.read()
    (folder/f'{name}.html').write_bytes(content)
    parser=Links();parser.feed(content.decode('utf-8'))
    result=list(dict.fromkeys(parser.links))
    (folder/f'{name}-links.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(name,json.dumps(result[:30]),flush=True)

with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(fetch,pages.items()))
