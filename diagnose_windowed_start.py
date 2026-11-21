import sys
from pathlib import Path
import runpy
import traceback

project=Path(r'C:\Users\yusuf\Desktop\galaxy-python-desktop\galaxy-python-desktop')
sys.path.insert(0,str(project))
sys.argv=[str(project/'main.py')]
with (Path(__file__).resolve().parent/'windowed-diagnostic.log').open('w',encoding='utf-8') as log:
    sys.stdout=sys.stderr=log
    print('Starting application with windowed Python.',flush=True)
    try:runpy.run_path(str(project/'main.py'),run_name='__main__')
    except BaseException:
        traceback.print_exc(file=log);log.flush()
