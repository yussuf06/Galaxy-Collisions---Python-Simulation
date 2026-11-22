"""Photo missions measured from the live visible stellar population.

These are educational morphology criteria, not a research galaxy classifier.
No time-based success window, imposed path, or additional force is used.
"""
from __future__ import annotations
import copy
import math
import numpy as np

OBJECTIVES = {
    'tidal': ('ذيل نجمي', 'التقط ذيلًا من النجوم ينسحب خارج قرص المجرّة.'),
    'bridge': ('جسر نجمي', 'التقط شريطًا من النجوم يصل بين المجرّتين.'),
}


def evaluate_feature(positions, origins, centers, initial_radii, objective,
                     *, after_pericentre, closest, isolated=False):
    """Return evidence indices in the supplied visible population and its score."""
    if objective not in OBJECTIVES: raise ValueError('Unknown photo objective')
    pos=np.asarray(positions,dtype=float); origin=np.asarray(origins)
    center=np.asarray(centers,dtype=float); radii0=np.asarray(initial_radii,dtype=float)
    if pos.ndim!=2 or pos.shape[1]!=3 or origin.shape!=(len(pos),) or radii0.shape!=(len(pos),):
        raise ValueError('Invalid photo population')
    if center.shape!=(2,3) or not np.isfinite(pos).all() or not np.isfinite(center).all() or not np.isfinite(radii0).all():
        raise ValueError('Invalid photo geometry')
    if not np.isin(origin,(0,1)).all() or np.any(radii0<0): raise ValueError('Invalid photo origins')
    mask=np.zeros(len(pos),dtype=bool)
    valid=bool(not isolated and after_pericentre and closest<6.)
    if valid and len(pos):
        if objective=='tidal':
            radius=np.linalg.norm(pos-center[origin],axis=1)
            mask=radius>np.maximum(4.6,1.8*radii0)
        else:
            axis=center[1]-center[0]; sep=float(np.linalg.norm(axis))
            if sep>3.:
                offset=pos-center[0]
                along=offset@axis/(sep*sep)
                cross=np.linalg.norm(offset-along[:,None]*axis,axis=1)
                d0=np.linalg.norm(offset,axis=1);d1=np.linalg.norm(pos-center[1],axis=1)
                mask=(along>.12)&(along<.88)&(cross<.9)&(d0>1.8)&(d1>1.8)
    indices=np.flatnonzero(mask)
    fraction=float(len(indices)/len(pos)) if len(pos) else 0.
    target=.05 if objective=='tidal' else .015
    score=int(np.clip(round(100*fraction/target),0,100))
    minimum=max(2,int(math.ceil(len(pos)*(.02 if objective=='tidal' else .006))))
    success=bool(valid and len(indices)>=minimum and score>=40)
    if not valid:
        feedback='لسّه بكّير! انتظر مرور المجرّتين وراقب النجوم التي تسحبها الجاذبية.'
    elif objective=='bridge' and np.linalg.norm(center[1]-center[0])<=3.:
        feedback='المركزان متقاربان جدًا الآن؛ انتظر انفصالهما حتى يظهر الجسر بينهما.'
    elif success:
        feedback='لقطة موفّقة! النجوم المضيئة توضّح الميزة التي التقطتها.'
    else:
        feedback='الميزة ليست واضحة بما يكفي بعد. كمّل المشاهدة وجرّب توقيتًا آخر.'
    return dict(indices=indices,feature_count=len(indices),fraction=fraction,
                score=score,success=success,feedback=feedback)


class PhotoHunt:
    max_shots=3
    total_rounds=2

    @classmethod
    def from_scene(cls, engine, tracers, objective='tidal', round_number=1):
        if objective not in OBJECTIVES:raise ValueError('Unknown photo objective')
        self=cls();self.objective=objective;self.round=int(round_number)
        self.shot_count=0;self.best_score=0;self.last_capture=None
        self.source='tracers' if tracers is not None else 'stars'
        pos,origin=self.population(engine,tracers)
        self.initial_radii=np.linalg.norm(pos-engine.centers()[origin],axis=1)
        return self

    def population(self,engine,tracers):
        if self.source=='tracers':
            if tracers is None:raise ValueError('Photo checkpoint needs its visible tracer population')
            return tracers.positions,tracers.origin
        mask=engine.kind==0
        return engine.positions[mask],engine.origin[mask]

    def capture(self,engine,tracers):
        if self.shot_count>=self.max_shots:raise ValueError('All photo attempts used')
        positions,origin=self.population(engine,tracers)
        result=evaluate_feature(positions,origin,engine.centers(),self.initial_radii,
                                self.objective,after_pericentre=engine.after_pericentre,
                                closest=engine.closest,isolated=engine.config['isolated'])
        self.shot_count+=1;self.best_score=max(self.best_score,result['score'])
        summary={k:v for k,v in result.items() if k!='indices'}
        summary.update(objective=self.objective,label=OBJECTIVES[self.objective][0],
                       time=float(engine.time),source=self.source)
        self.last_capture=copy.deepcopy(summary)
        ids=result['indices'];ids=ids[::max(1,int(math.ceil(len(ids)/3000)))]
        return {**summary,'feature_positions':np.asarray(positions[ids],dtype=np.float32).copy()}

    def summary(self):
        label,prompt=OBJECTIVES[self.objective]
        return dict(objective=self.objective,label=label,prompt=prompt,
                    shot_count=self.shot_count,max_shots=self.max_shots,round=self.round,
                    total_rounds=self.total_rounds,best_score=self.best_score,
                    last_capture=copy.deepcopy(self.last_capture),
                    completed=self.round==2 and bool(self.last_capture and self.last_capture['success']))

    def snapshot(self):
        return dict(objective=self.objective,round=self.round,shot_count=self.shot_count,
                    best_score=self.best_score,last_capture=copy.deepcopy(self.last_capture),
                    source=self.source,initial_radii=self.initial_radii.copy())

    @classmethod
    def restore(cls,state,engine,tracers):
        if not isinstance(state,dict):raise ValueError('Invalid photo state')
        self=cls()
        self.objective=state.get('objective')
        if self.objective not in OBJECTIVES:raise ValueError('Invalid photo objective')
        self.round=int(state['round']);self.shot_count=int(state['shot_count']);self.best_score=int(state['best_score'])
        self.source=state.get('source')
        if self.source not in ('tracers','stars') or self.round not in (1,2) or not 0<=self.shot_count<=3 or not 0<=self.best_score<=100:
            raise ValueError('Invalid photo progress')
        self.initial_radii=np.asarray(state['initial_radii'],dtype=float).copy()
        positions,_=self.population(engine,tracers)
        if self.initial_radii.shape!=(len(positions),) or not np.isfinite(self.initial_radii).all() or np.any(self.initial_radii<0):
            raise ValueError('Invalid initial photo radii')
        last=state.get('last_capture')
        if last is not None:
            if not isinstance(last,dict) or last.get('objective')!=self.objective or not isinstance(last.get('success'),bool):
                raise ValueError('Invalid photo capture')
            for key in ('score','fraction','time','feature_count'):
                if not math.isfinite(float(last.get(key,float('nan')))):raise ValueError('Invalid photo capture value')
            if not 0<=last['score']<=100 or not 0<=last['fraction']<=1 or last['time']<0 or not 0<=last['feature_count']<=len(positions):
                raise ValueError('Invalid photo capture value')
        self.last_capture=copy.deepcopy(last)
        return self
