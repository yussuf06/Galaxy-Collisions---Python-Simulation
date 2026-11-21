from pathlib import Path
from datetime import datetime
import shutil

root=Path(__file__).resolve().parent
stage=root/'nbody-linux-run'
project=Path(r'C:\Users\yusuf\Downloads\galaxy-nbody-simulation-master\galaxy-nbody-simulation-master').resolve()
current=(project/'particle.py').read_text(encoding='utf-8')
prefix='collision = lines[4].split("=")[1].split("#")[0]'
line=next(line for line in current.splitlines() if line.strip().startswith(prefix))
normalized=current.replace(line,'    collision = lines[4].split("=")[1].split("#")[0].strip()')
assert normalized==(stage/'particle.py').read_text(encoding='utf-8'),'Source changed during preparation'
assert (project/'config.ini').read_text(encoding='utf-8')==(stage/'config.ini').read_text(encoding='utf-8')
backup=project/'backups'/('before-linux-run-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
backup.mkdir(parents=True)
for name in ('particle.py','halo.txt'):
    destination=(project/name).resolve();assert destination.is_relative_to(project)
    if destination.exists():shutil.copy2(destination,backup/name)
    shutil.copy2(stage/name,destination)
print('Installed corrected parser and two-galaxy input. Backup:',backup)
