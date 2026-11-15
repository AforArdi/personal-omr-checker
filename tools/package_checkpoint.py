"""Package implementation and extraction checkpoints, excluding secrets/photos."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'dist/omr-check-checkpoint.zip'
out.parent.mkdir(exist_ok=True)
files=[]
for folder in ('omr_check','tools','tests'):
    files.extend((ROOT/folder).glob('*.py'))
for folder in ('data','assets'):
    files.extend(p for p in (ROOT/folder).iterdir() if p.is_file())
for folder in ('key-extraction','key-extraction-v2','key-recovered'):
    files.extend((ROOT/'var'/folder).glob('*.json'))
for name in ('README.md','VALIDATION.md','AGENT_HANDOFF.md','requirements.txt','pyproject.toml','run.ps1','Dockerfile','.gitignore','.dockerignore','.env.example'):
    files.append(ROOT/name)
with ZipFile(out,'w',ZIP_DEFLATED) as archive:
    for file in sorted(files):
        archive.write(file,file.relative_to(ROOT))
with ZipFile(out) as archive:
    assert archive.testzip() is None
    names=archive.namelist()
    assert '.env' not in names
    assert not any('/sessions/' in name or name.startswith('.venv/') or name.startswith('.runtime/') for name in names)
print(out)
print(f'{len(names)} files; {out.stat().st_size:,} bytes; CRC check passed')
