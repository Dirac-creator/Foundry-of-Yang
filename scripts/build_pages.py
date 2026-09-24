"""Build an allowlisted static site; never copy local databases or credentials."""
import argparse
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/foundry/service/static"

def build(destination):
    destination.mkdir(parents=True, exist_ok=True)
    assets = destination / "assets"
    assets.mkdir(exist_ok=True)
    for name in ("app.css", "app.js", "github-store.js", "catalog.json"):
        shutil.copyfile(SOURCE / name, assets / name)
    html = (SOURCE / "index.html").read_text(encoding="utf-8").replace('"/assets/', '"./assets/')
    html = html.replace('<option value="local">本机数据库</option>', '<option value="local" disabled>本机数据库（此页面不可用）</option>').replace('<option value="github">', '<option value="github" selected>')
    html = html.replace('id="githubSettings" hidden', 'id="githubSettings"')
    (destination / "index.html").write_text(html, encoding="utf-8")
    (destination / ".nojekyll").write_text("", encoding="utf-8")

if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",default=str(ROOT / "dist/pages"))
    build(Path(parser.parse_args().output))
