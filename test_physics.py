import sys,time,numpy as np
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from galaxy_app.physics import NBody,_forces_numpy,_forces_numba,NUMBA_AVAILABLE
start=time.perf_counter()
a=NBody(dict(seed=42,count=256,isolated=True))
p0=np.sum(a.positions*a.masses[:,None],axis=0)
e0=a.energy();l0=a.angularmomentum();r0=np.median(np.linalg.norm(a.positions[a.kind==0],axis=1));h0=np.median(np.linalg.norm(a.positions[a.kind==1],axis=1))
for i in range(1200): a.step()
e1=a.energy();r1=np.median(np.linalg.norm(a.positions[a.kind==0]-a.centers()[0],axis=1));h1=np.median(np.linalg.norm(a.positions[a.kind==1]-a.centers()[0],axis=1))
print('isolated',dict(energy_drift=(e1-e0)/abs(e0),disk_radius_initial=r0,disk_radius_final=r1,halo_radius_initial=h0,halo_radius_final=h1))
assert abs((e1-e0)/e0)<.02
assert .55<r1/r0<1.65
assert .6<h1/h0<1.6
assert np.linalg.norm(a.angularmomentum()-l0)<1e-8
assert np.linalg.norm(np.sum(a.positions*a.masses[:,None],axis=0)-p0)<1e-8
b=NBody(dict(seed=123,count=256,impact=1.8,speed=.8))
e=b.energy();mom=np.sum(b.velocities*b.masses[:,None],axis=0)
for i in range(1800):b.step()
print('encounter',b.metrics(),'energy_drift',(b.energy()-e)/abs(e))
assert np.isfinite(b.positions).all();assert abs((b.energy()-e)/e)<.02
assert np.linalg.norm(np.sum(b.velocities*b.masses[:,None],axis=0)-mom)<1e-8
snap=b.snapshot();b.step(20);p=b.positions.copy();b.restore(snap);b.step(20);assert np.array_equal(p,b.positions)
c=NBody(dict(seed=42,count=128));d=NBody(dict(seed=42,count=128));c.step(10);d.step(4);d.step(6);assert np.array_equal(c.positions,d.positions)
rng=np.random.default_rng(12);p=rng.normal(size=(32,3));m=rng.uniform(.1,1,32)
assert np.allclose(_forces_numpy(p,m,.15),_forces_numba(p,m,.15),rtol=1e-12,atol=1e-12)
for n in [512,1024,2048]:
 x=NBody(dict(count=n,seed=2));t=time.perf_counter();x.step(15);print('performance',n,(time.perf_counter()-t)/15,'seconds/step')
print('ALL PASS, seconds',time.perf_counter()-start)
for n in [512,1024]:
 x=NBody(dict(seed=42,count=n,isolated=True));stars=x.kind==0
 def stats(s):
  r=np.linalg.norm(s.positions[stars]-s.centers()[0],axis=1)
  W=-np.sum(s.masses[:,None]*(s.positions-np.average(s.positions,axis=0,weights=s.masses))*s.accelerations)
  return dict(r50=float(np.median(r)),r90=float(np.quantile(r,.9)),virial=float(np.sum(s.masses[:,None]*s.velocities**2)/W),tidal=s.metrics()['tidal'])
 before=stats(x); e0=x.energy();x.step(1200);after=stats(x)
 print('STABILITY',n,before,after,'energyrel',(x.energy()-e0)/abs(e0))
 assert after['r90']/before['r90']<1.3
 assert after['tidal']<.08
for n in [512,1024]:
 x=NBody(dict(seed=123,count=n,impact=2,speed=1))
 peak={'tidal':0.,'bridge':0.}
 for i in range(150):
  x.step(12);m=x.metrics()
  if m['after_pericentre']:
   for k in peak:peak[k]=max(peak[k],m[k])
 print('WITNESS',n,peak,'closest',x.closest)
 assert peak['tidal']>.08
 assert peak['bridge']>0
print('FINAL STABILITY AND GAME WITNESS CHECKS PASS')
