"""Create an Anki-installable zip. Run: py tools/build.py"""
from pathlib import Path
import json
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'spanish_helper'
OUTPUT = ROOT / 'output' / 'spanish-helper.ankiaddon'


def build():
    OUTPUT.parent.mkdir(exist_ok=True)
    with ZipFile(OUTPUT, 'w', ZIP_DEFLATED) as archive:
        for path in sorted(SOURCE.rglob('*')):
            if not path.is_file() or any(part in ('user_files', '__pycache__') for part in path.relative_to(SOURCE).parts):
                continue
            archive.write(path, path.relative_to(SOURCE).as_posix())
    with ZipFile(OUTPUT) as archive:
        assert archive.testzip() is None
        assert json.loads(archive.read('manifest.json'))['package'] == 'spanish_helper'
        assert '__init__.py' in archive.namelist()
    print(OUTPUT)
    return OUTPUT


if __name__ == '__main__':
    build()
