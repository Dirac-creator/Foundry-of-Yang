import importlib.util
import json
from pathlib import Path
from foundry.service.models import PARAMETERS, PROCESS_TYPES

ROOT=Path(__file__).resolve().parents[1]

def test_catalog_stays_in_sync():
    generated=json.loads((ROOT/"src/foundry/service/static/catalog.json").read_text(encoding="utf-8"))
    assert generated == json.loads(json.dumps({"parameters":PARAMETERS,"process_types":PROCESS_TYPES}))

def test_pages_only_publishes_allowlisted_assets(tmp_path):
    spec=importlib.util.spec_from_file_location("build_pages",ROOT/"scripts/build_pages.py")
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.build(tmp_path)
    assert {str(p.relative_to(tmp_path)).replace("\\","/") for p in tmp_path.rglob("*") if p.is_file()} == {"index.html",".nojekyll","assets/app.js","assets/app.css","assets/github-store.js","assets/catalog.json"}
    html=(tmp_path/"index.html").read_text(encoding="utf-8")
    assert 'src="./assets/github-store.js"' in html
    assert 'value="github" selected' in html
