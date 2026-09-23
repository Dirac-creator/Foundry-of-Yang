import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
import pytest
from foundry.data.validation import DataError, validate_dataset

EXAMPLE = Path(__file__).resolve().parents[1] / 'examples/demo_dataset.json'

@pytest.fixture
def dataset():
    return json.loads(EXAMPLE.read_text(encoding='utf-8'))

def test_example(dataset):
    assert validate_dataset(dataset)['measurements'] == 2

@pytest.mark.parametrize('change', [
    lambda d: d['samples'].append(deepcopy(d['samples'][0])),
    lambda d: d['samples'][1].update(parent_id='UNKNOWN'),
    lambda d: d['samples'][2].update(parent_id='LOT-001'),
    lambda d: d['measurements'][0]['quantities']['etch_depth'].update(unit='s'),
    lambda d: d['measurements'][0]['quantities']['etch_depth'].update(value=float('nan')),
    lambda d: d['measurements'][0]['quantities']['etch_depth'].update(uncertainty=-1),
    lambda d: d['measurements'][0].update(measured_at='2026-09-23T10:30:00'),
    lambda d: d['measurements'][0].update(measured_at='2026-09-23T09:00:00+08:00'),
    lambda d: d['measurements'][0].update(sample_id='LOT-001'),
    lambda d: d['measurements'][0].update(supersedes_id='MEA-001'),
    lambda d: d['process_runs'][0].update(ended_at='2026-09-23T09:00:00+08:00'),
    lambda d: d['process_runs'][0].update(previous_run_ids=['UNKNOWN']),
    lambda d: d['process_runs'][0].update(previous_run_ids=['RUN-001'], ended_at='2026-09-23T10:00:00+08:00'),
    lambda d: d.update(unknown_field=True),
])
def test_invalid_data(dataset, change):
    change(dataset)
    with pytest.raises(DataError):
        validate_dataset(dataset)

def test_repeated_processing(dataset):
    run = deepcopy(dataset['process_runs'][0])
    run.update(id='RUN-002', sample_id='DIE-001', previous_run_ids=['RUN-001'], started_at='2026-09-23T10:02:00+08:00', ended_at='2026-09-23T10:03:00+08:00')
    dataset['process_runs'].append(run)
    assert validate_dataset(dataset)['process_runs'] == 2

def test_cli_failure(tmp_path):
    path = tmp_path / 'bad.json'
    path.write_text('{}', encoding='utf-8')
    result = subprocess.run([sys.executable, '-m', 'foundry', 'validate', str(path)], capture_output=True, text=True)
    assert result.returncode == 1
    assert 'Validation failed' in result.stderr


def test_correction_preserves_history(dataset):
    correction = deepcopy(dataset['measurements'][0])
    correction.update(id='MEA-003', supersedes_id='MEA-001')
    dataset['measurements'].append(correction)
    assert validate_dataset(dataset)['measurements'] == 3


def test_artifact_requires_valid_uri(dataset):
    dataset['artifacts'].append({'id': 'FILE-001', 'uri': 'not a uri', 'sha256': '0' * 64})
    with pytest.raises(DataError):
        validate_dataset(dataset)
