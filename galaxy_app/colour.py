"""Illustrative colour grading. Never modifies a simulation state."""
from __future__ import annotations
import numpy as np

PALETTES={
    'aurora':('Cyan & coral',((.12,.48,1.),(.12,.85,1.)),((1.,.17,.45),(1.,.49,.22))),
    'violet':('Violet & gold',((.30,.15,1.),(.65,.36,1.)),((1.,.32,.08),(1.,.74,.24))),
    'ocean':('Blue & amber',((.12,.31,1.),(.24,.67,1.)),((1.,.23,.08),(1.,.66,.20))),
    'classic':('Original blue & gold',None,None),
}

def grade_colours(colours,origin,palette='aurora'):
    """Use the reference radial alpha gradient, retaining every star's alpha."""
    if palette not in PALETTES:raise ValueError('Unknown colour palette')
    colours=np.asarray(colours,dtype=np.float32)
    origin=np.asarray(origin)
    if palette=='classic':return colours
    result=colours.copy()
    core=np.clip((colours[:,3]-.26)/.39,0.,1.)[:,None]
    for galaxy,endpoints in enumerate(PALETTES[palette][1:]):
        mask=origin==galaxy
        outer,inner=np.asarray(endpoints,dtype=np.float32)
        result[mask,:3]=outer+(inner-outer)*core[mask]
    return result

def compress_light(rgb,exposure=1.,detail=1.):
    """CPU equivalent of the hue-preserving display shader for validation."""
    rgb=np.maximum(np.asarray(rgb,dtype=np.float64),0.)
    maximum=np.max(rgb,axis=-1,keepdims=True)
    value=1.-np.exp(-np.log1p(maximum*max(.01,float(exposure)))*(.42/max(.3,float(detail))))
    return rgb/np.maximum(maximum,1e-8)*value**.72
