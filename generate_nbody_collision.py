from pathlib import Path
import subprocess,sys,re
import numpy as np

root=Path(__file__).resolve().parent
project=Path(r'C:\Users\yusuf\Downloads\galaxy-nbody-simulation-master\galaxy-nbody-simulation-master')
stage=root/'nbody-linux-run'
config=(project/'config.ini').read_text(encoding='utf-8')
(stage/'config.ini').write_text(config,encoding='utf-8')
subprocess.run([sys.executable,str(stage/'particle.py')],cwd=stage,check=True)
data=np.loadtxt(stage/'halo.txt',skiprows=1)
per_galaxy=int(re.search(r'^N\s*=\s*(\d+)',config,re.M).group(1))
assert data.shape==(per_galaxy*2,6) and np.isfinite(data).all()
smoke=stage/'smoke'
smoke.mkdir(exist_ok=False)
np.savetxt(smoke/'halo.txt',data[:256],header='256',comments='')
print('Generated',len(data),'particles in two galaxies; prepared separate 256-particle smoke test.',flush=True)
