from pathlib import Path
from datetime import datetime
import hashlib,json,shutil

root=Path(__file__).resolve().parent
stage=root/'shape-colour-update'
project=Path(r'C:\Users\yusuf\Desktop\galaxy-python-desktop\galaxy-python-desktop').resolve()
files=[
    'galaxy_app/colour.py','galaxy_app/hdr_canvas.py','galaxy_app/shape_presets.py',
    'galaxy_app/gpu_view.py','galaxy_app/view.py','galaxy_app/window.py',
    'galaxy_app/physics.py','galaxy_app/dense_stars.py','galaxy_app/worker.py',
    'test_shapes.py','test_view_ui.py']

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

if '--install' not in __import__('sys').argv:
    for name in files:
        path=project/name
        print(name,'NEW' if not path.exists() else 'changed' if digest(path)!=digest(stage/name) else 'unchanged')
else:
    backup=project/'backups'/('before-shapes-and-colour-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    entries=[]
    for name in files:
        destination=(project/name).resolve()
        assert destination.is_relative_to(project) and (stage/name).is_file()
        old_hash=None
        if destination.exists():
            old_hash=digest(destination)
            saved=backup/name;saved.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(destination,saved)
        shutil.copy2(stage/name,destination)
        assert digest(destination)==digest(stage/name)
        entries.append(dict(file=name,before=old_hash,after=digest(destination)))
    backup.mkdir(parents=True,exist_ok=True)
    (backup/'manifest.json').write_text(json.dumps(entries,indent=2),encoding='utf-8')
    print('Installed and verified',len(files),'files. Backup:',backup)
