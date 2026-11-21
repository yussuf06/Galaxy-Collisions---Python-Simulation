from datetime import datetime
import hashlib
from pathlib import Path
import shutil

project=Path(r'C:\Users\yusuf\Desktop\galaxy-python-desktop\galaxy-python-desktop').resolve()
stage=Path(__file__).resolve().parent/'free-simulation-ui'
files=['galaxy_app/window.py','galaxy_app/worker.py','galaxy_app/smoke_test.py','test_simulation_only.py']
backup=project/'backups'/('before-free-simulation-ui-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
physics=hashlib.sha256((project/'galaxy_app/physics.py').read_bytes()).hexdigest()
for name in files:
    destination=(project/name).resolve()
    assert destination.is_relative_to(project) and (stage/name).is_file()
    if destination.exists():
        saved=backup/name;saved.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(destination,saved)
    shutil.copy2(stage/name,destination)
    assert destination.read_bytes()==(stage/name).read_bytes()
assert hashlib.sha256((project/'galaxy_app/physics.py').read_bytes()).hexdigest()==physics
print('Installed four files. Physics unchanged. Backup:',backup)
