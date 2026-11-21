from pathlib import Path
from datetime import datetime
import hashlib,json,shutil,sys

root=Path(__file__).resolve().parent
stage=root/'recognizable-shape-update'
project=Path(r'C:\Users\yusuf\Desktop\galaxy-python-desktop\galaxy-python-desktop').resolve()
existing=['galaxy_app/window.py','galaxy_app/gpu_view.py','galaxy_app/hdr_canvas.py','galaxy_app/view.py']
files=existing+['galaxy_app/reference_shapes.py','test_reference_ui.py','SHAPE_VIEWS.md']
files += [str(p.relative_to(stage)).replace('\\','/') for p in sorted((stage/'galaxy_app/assets/reference_shapes').glob('*')) if p.suffix in ('.npz','.json')]
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
for name in existing:
    # Do not overwrite changes made since this task's baseline was copied.
    assert digest(project/name)==digest(root/'shape-colour-update'/name),f'Changed baseline: {name}'
if '--install' not in sys.argv:
    for name in files:print(name,'replace' if (project/name).exists() else 'new')
else:
    backup=project/'backups'/('before-recognizable-shapes-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    backup.mkdir(parents=True,exist_ok=False);entries=[]
    for name in files:
        destination=(project/name).resolve();source=stage/name
        assert destination.is_relative_to(project) and source.is_file()
        old_hash=None
        if destination.exists():
            old_hash=digest(destination);saved=backup/name;saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(destination,saved)
        destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,destination)
        assert digest(destination)==digest(source)
        entries.append(dict(file=name,before=old_hash,after=digest(destination)))
    (backup/'manifest.json').write_text(json.dumps(entries,indent=2),encoding='utf-8')
    print('Installed and hash-verified',len(files),'files. Backup:',backup)
