"""Export fixed fictional cases through the existing V2 coordinator; no network."""
import copy
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'poc/v2'))
from v2_poc.coordinator import run
base = json.loads((ROOT / 'poc/v2/fixtures/purchase.json').read_text())
cases = []
for key, title, detail in [
    ('overlap', 'The overlapping export', 'Two bank rows. One payment. What actually counts?'),
    ('conflict', 'The conflicting amount', 'The same payment appears as €49.90 and €59.90. Can we trust the total?'),
    ('missing', 'The missing receipt', 'A bank payment exists. Is that enough to add something to your home?')]:
    request = copy.deepcopy(base)
    request['run_id'] = request['request_id'] = 'public-demo-' + key
    if key == 'conflict':
        request['evidence'][2]['data']['amount_eur'] = '59.90'
    if key == 'missing':
        request['evidence'] = [e for e in request['evidence'] if e['source_type'] != 'receipt']
    result = run(request)
    assert result['simulation'] and result['read_only'] and result['executed_writes'] == []
    assert not result['specialist_results']['home']['proposed_writes']
    if key == 'conflict':
        assert result['specialist_results']['finance']['status'] == 'blocked'
    if key == 'missing':
        assert result['specialist_results']['home']['status'] == 'blocked'
    cases.append(dict(key=key, title=title, detail=detail, evidence=request['evidence'], result=result))
output = 'window.DEMO_CASES = ' + json.dumps(cases, ensure_ascii=False, indent=2) + ';\n'
target = ROOT / 'demo/cases.js'
if '--check' in sys.argv:
    assert target.read_text() == output, 'Run python3 demo/build.py and commit cases.js'
    print('PASS: three exported cases match V2; conflict, missing evidence and zero-write invariants')
else:
    target.write_text(output)
