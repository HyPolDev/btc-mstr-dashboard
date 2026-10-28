"""Produce a standard static site; no ChatGPT runtime or build dependencies."""
from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parents[1]
def build():
    # Copy only explicit public assets. Never copy the workspace or environment.
    for target in ['dist','docs']:
        out=ROOT/target;out.mkdir(exist_ok=True)
        for name in ['index.html','app.js','style.css']:shutil.copyfile(ROOT/name,out/name)
        for name in ['assets','data']:shutil.copytree(ROOT/name,out/name,dirs_exist_ok=True)
        (out/'.nojekyll').touch()
    print('Built dist/ preview and docs/ GitHub Pages publication.')
if __name__=='__main__':build()
