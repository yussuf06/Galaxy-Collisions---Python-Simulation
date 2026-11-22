"""Observed-image particle illustrations, kept outside the gravity worker."""
from functools import lru_cache
from pathlib import Path
import json
import numpy as np

IDENTIFIERS=('heart','rose','mice','penguin')
ASSET_FOLDER=Path(__file__).resolve().parent/'assets/reference_shapes'

@lru_cache(maxsize=4)
def _load(ident):
    if ident not in IDENTIFIERS:raise ValueError('Unknown reference shape')
    info=json.loads((ASSET_FOLDER/f'{ident}.json').read_text(encoding='utf-8'))
    with np.load(ASSET_FOLDER/f'{ident}.npz',allow_pickle=False) as saved:
        data={key:saved[key].copy() for key in ('positions','colours','origin','centers')}
    n=len(data['positions'])
    if not 1000<=n<=200000 or data['positions'].shape!=(n,3) or data['colours'].shape!=(n,4):
        raise ValueError('Invalid illustration asset dimensions')
    if any(not np.isfinite(array).all() for array in data.values()):
        raise ValueError('Invalid illustration asset values')
    for array in data.values():array.setflags(write=False)
    return data,info

def reference_frame(ident):
    data,info=_load(ident);n=len(data['positions'])
    return dict(type='illustration',positions=data['positions'],kind=np.zeros(n,np.int8),
                origin=data['origin'],centers=data['centers'],tracer_positions=data['positions'],
                tracer_colors=data['colours'],tracer_origin=data['origin'],
                config=dict(seed=93000+IDENTIFIERS.index(ident),isolated=False,reference_length_scale=1.),
                galaxy_names=tuple(info['names']),illustration={**info,'id':ident},
                time=0.,phase='paused',mode='illustration',count=n,backend='Photo-based illustration')
