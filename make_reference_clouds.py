"""Sample observed galaxy light into explicitly illustrative particle clouds.

This prepares display assets, not initial conditions or an N-body trajectory.
The photos' image-plane positions and hues are preserved. Depth is invented
only for a slight parallax effect and is identified as illustrative in the UI.
"""
from pathlib import Path
from collections import deque
import json
import numpy as np
from PIL import Image,ImageFilter

root=Path(__file__).resolve().parent
sources=root/'output/pdf/source-images'
assets=root/'recognizable-shape-update/galaxy_app/assets/reference_shapes'
assets.mkdir(parents=True,exist_ok=True)
preview=root/'recognizable-shape-update/reference-previews';preview.mkdir(exist_ok=True)
items={
 'heart':dict(file='heart-photographer.jpg',crop=(1450,1210,2350,2160),
       title='The Heart',names=['NGC 4038','NGC 4039'],cores=[(.38,.42),(.65,.47)],
       source='https://science.nasa.gov/image-article/apod-2024-february-7-the-heart-shaped-antennae-galaxies/',
       credit='Kent E. Biggs; featured by NASA APOD'),
 'rose':dict(file='rose.jpg',crop=None,title='The Rose',names=['UGC 1810','UGC 1813'],
       cores=[(.49,.30),(.46,.76)],
       source='https://science.nasa.gov/asset/hubble/a-rose-made-of-galaxies-highlights-hubbles-21st-anniversary/',
       credit='NASA, ESA, Hubble Heritage Team (STScI/AURA)'),
 'mice':dict(file='mice.tif',crop=None,title='The Mice',names=['NGC 4676A','NGC 4676B'],
       cores=[(.32,.40),(.52,.38)],
       source='https://science.nasa.gov/asset/hubble/the-mice-ngc-4676-colliding-galaxies-with-tails-of-stars-and-gas/',
       credit='NASA, ESA, ACS Science Team'),
 'penguin':dict(file='penguin.png',crop=(180,1550,3000,4700),title='The Penguin and the Egg',
       names=['NGC 2936','NGC 2937'],cores=[(.55,.35),(.25,.67)],
       source='https://science.nasa.gov/asset/webb/interacting-galaxies-arp-142-nircam-and-miri-image/',
       credit='NASA, ESA, CSA, STScI'),
}

def largest_regions(mask,number=2):
    visited=np.zeros(mask.shape,bool);h,w=mask.shape;regions=[]
    for y,x in zip(*np.nonzero(mask)):
        if visited[y,x]:continue
        queue=deque([(int(y),int(x))]);visited[y,x]=True;region=[]
        while queue:
            yy,xx=queue.popleft();region.append(yy*w+xx)
            for ny,nx in ((yy-1,xx),(yy+1,xx),(yy,xx-1),(yy,xx+1)):
                if 0<=ny<h and 0<=nx<w and mask[ny,nx] and not visited[ny,nx]:
                    visited[ny,nx]=True;queue.append((ny,nx))
        if len(region)>100:regions.append(region)
    result=np.zeros(h*w,bool)
    for region in sorted(regions,key=len,reverse=True)[:number]:result[region]=True
    return result.reshape(h,w)

for index,(ident,info) in enumerate(items.items()):
    image=Image.open(sources/info['file']).convert('RGB')
    if info['crop']:image=image.crop(info['crop'])
    image.thumbnail((900,900),Image.Resampling.LANCZOS)
    image.save(preview/f'{ident}-source.png')
    pixels=np.asarray(image,dtype=np.float32)/255.
    light=pixels.max(axis=2)
    smoothed=np.asarray(image.filter(ImageFilter.GaussianBlur(3)),dtype=np.float32).max(axis=2)/255.
    floor=float(np.quantile(smoothed,.12))
    threshold=max(.047,floor+.025)
    candidate=(smoothed>threshold)
    # Join adjacent light patches before selecting the extended galaxies;
    # isolated foreground stars do not become part of the illustration.
    closed=Image.fromarray(candidate.astype(np.uint8)*255).filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.MinFilter(9))
    mask=largest_regions(np.asarray(closed)>0,2 if ident=='penguin' else 1)
    # Fill enclosed background holes so masking does not introduce hard patches.
    outside=np.zeros(mask.shape,bool);queue=deque()
    for y,x in [(0,x) for x in range(mask.shape[1])]+[(mask.shape[0]-1,x) for x in range(mask.shape[1])]+[(y,0) for y in range(mask.shape[0])]+[(y,mask.shape[1]-1) for y in range(mask.shape[0])]:
        if not mask[y,x] and not outside[y,x]:outside[y,x]=True;queue.append((y,x))
    while queue:
        y,x=queue.popleft()
        for ny,nx in ((y-1,x),(y+1,x),(y,x-1),(y,x+1)):
            if 0<=ny<mask.shape[0] and 0<=nx<mask.shape[1] and not mask[ny,nx] and not outside[ny,nx]:
                outside[ny,nx]=True;queue.append((ny,nx))
    mask=~outside
    mask=np.asarray(Image.fromarray(mask.astype(np.uint8)*255).filter(ImageFilter.GaussianBlur(3)),dtype=np.float32)/255.
    signal=np.maximum(light-floor,0.)
    assert mask.sum()>0
    rng=np.random.default_rng(4871+index)
    h,w=light.shape
    yy,xx=np.mgrid[0:h:2,0:w:2];yy=yy.ravel();xx=xx.ravel()
    valid=mask[yy,xx]>.03
    yy,xx=yy[valid],xx[valid];n=len(xx)
    sample_xy=np.column_stack((xx+rng.uniform(-.2,.2,n),yy+rng.uniform(-.2,.2,n)))
    scale=24./max(w,h)
    positions=np.column_stack(((sample_xy[:,0]-w/2)*scale,(h/2-sample_xy[:,1])*scale,
                              rng.normal(0,.055,n))).astype(np.float32)
    colour=np.clip((pixels[yy,xx]-floor*.7)/(1.-floor*.7),0.,1.)
    neutral=colour.mean(axis=1,keepdims=True)
    colour=np.clip(neutral+(colour-neutral)*1.3,0.,1.)
    colour=colour**1.35
    edge=np.minimum.reduce([sample_xy[:,0],w-1-sample_xy[:,0],sample_xy[:,1],h-1-sample_xy[:,1]])
    fade=np.clip(edge/(min(w,h)*.06),0.,1.)
    alpha=.75*mask[yy,xx]*fade
    if ident=='heart':
        # Focus on the observed heart's inner filaments with a smooth falloff;
        # a per-pixel saturation mask amplifies JPEG blocks in the faint halo.
        focus=np.exp(-.5*(((sample_xy[:,0]/w-.50)/.27)**2+((sample_xy[:,1]/h-.43)/.22)**2))
        alpha*=focus**1.7
    colours=np.column_stack((colour,alpha)).astype(np.float32)
    centres=np.array([[(x*w-w/2)*scale,(h/2-y*h)*scale,0.] for x,y in info['cores']],np.float32)
    distances=np.linalg.norm(positions[:,:2,None]-centres[:,:2].T[None,:,:],axis=1)
    origin=np.argmin(distances,axis=1).astype(np.int8)
    np.savez_compressed(assets/f'{ident}.npz',positions=positions,colours=colours,origin=origin,
                        centers=centres,source_xy=sample_xy.astype(np.float32),source_size=np.array([w,h]))
    metadata={**info,'points':n,'source_size':[w,h],'kind':'photo-derived illustration',
              'depth':'synthetic thin depth for parallax; not measured 3D structure'}
    (assets/f'{ident}.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    masked=(pixels*mask[:,:,None]*255).clip(0,255).astype(np.uint8)
    Image.fromarray(masked).save(preview/f'{ident}-mask.png')
    print(ident,'asset prepared',w,h,flush=True)
