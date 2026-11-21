from pathlib import Path

source=Path(r'C:\Users\yusuf\Downloads\galaxy-nbody-simulation-master\galaxy-nbody-simulation-master')
stage=Path(__file__).resolve().parent/'nbody-linux-run'
stage.mkdir(exist_ok=True)
text=(source/'particle.py').read_text(encoding='utf-8')
old='collision = lines[4].split("=")[1].split("#")[0]'
assert old in text
line=next(line for line in text.splitlines() if line.strip().startswith(old))
text=text.replace(line,'    collision = lines[4].split("=")[1].split("#")[0].strip()')
(stage/'particle.py').write_text(text,encoding='utf-8')
print('Prepared collision-parser correction.')
