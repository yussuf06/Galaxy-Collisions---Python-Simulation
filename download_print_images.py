from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import urllib.request
import json

root=Path(__file__).resolve().parent
folder=root/'output/pdf/source-images';folder.mkdir(parents=True,exist_ok=True)
sources={
 'heart-nasa.jpg':'https://apod.nasa.gov/apod/image/2402/Antennae_Biggs_3840.jpg',
 'heart-photographer.jpg':'https://www.kentbiggs.com/images/galaxies/N4038_LRGB_4Kz.jpg',
 'rose.jpg':'https://assets.science.nasa.gov/content/dam/science/missions/hubble/releases/2011/04/STScI-01EVT4TA2ED9JNN2CA5CSZ7H1J.tif/jcr:content/renditions/7887x7994.jpg',
 'mice.tif':'https://assets.science.nasa.gov/content/dam/science/missions/hubble/releases/2002/04/STScI-01EVT9FFVJJAVPCRXS5PK1ZW3H.tif',
 'penguin.png':'https://assets.science.nasa.gov/content/dam/science/missions/webb/science/2024/07/STScI-01J06Y2CNAYAPKBW5EKM4S94XJ.png'}
def fetch(item):
    name,url=item
    try:
        request=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
        with urllib.request.urlopen(request,timeout=90) as response:content=response.read()
        (folder/name).write_bytes(content)
        print(name,len(content),flush=True)
    except Exception as error:print(name,type(error).__name__,str(error),flush=True)

with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(fetch,sources.items()))
(folder/'download-sources.json').write_text(json.dumps(sources,indent=2),encoding='utf-8')
