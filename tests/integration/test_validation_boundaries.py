"""Shared boundary regressions: valid integer inputs stay usable by processors."""
import copy
import json
import sqlite3
from pathlib import Path

import pytest

from adapters.spritegen.video_provider import validate_params
from services.api import store
from services.api.edits import apply


def test_manual_video_range_normalizes_integral_numbers():
    params = validate_params({'loopMode': 'manual', 'startFrame': 0.0, 'endFrame': 8.0}, generation=False)
    assert type(params['startFrame']) is int and type(params['endFrame']) is int
    assert list(range(10))[params['startFrame']:params['endFrame']] == list(range(8))
    for value in (True, 1.5):
        with pytest.raises(store.AppError):
            validate_params({'loopMode': 'manual', 'startFrame': value, 'endFrame': 8}, generation=False)


@pytest.mark.parametrize('width,height,edge,valid', [(64, 64, 31, True), (64, 64, 32, False), (63, 64, 31, True), (1, 1, 0, True)])
def test_cell_margin_preserves_nonempty_safe_area(width, height, edge, valid):
    snapshot = json.loads((Path(__file__).parents[1] / 'fixtures/review-transitions.json').read_text())['snapshot']
    before = copy.deepcopy(snapshot)
    operations = [{'type': 'setAlignmentGroup', 'alignmentGroupId': 'g', 'changes': {'cell': {'width': width, 'height': height, 'edge': edge}}}]
    if valid:
        result = apply(snapshot, operations)
        assert result['alignmentGroups'][0]['cell'] == operations[0]['changes']['cell']
    else:
        with pytest.raises(store.AppError) as error:
            apply(snapshot, operations)
        assert error.value.code == 'VALUE_RANGE'
    assert snapshot == before


@pytest.mark.parametrize('approval', [{}, {'approved':False}, {'approved':True}])
def test_body_measurement_approval_is_metadata(approval):
    snapshot = json.loads((Path(__file__).parents[1] / 'fixtures/review-transitions.json').read_text())['snapshot']
    measurement = {'topY':2, 'bottomY':6, 'targetHeight':5, **approval}
    result = apply(snapshot, [{'type':'setAlignmentGroup','alignmentGroupId':'g',
                              'changes':{'mode':'shared-scale-foot-anchor','bodyMeasurement':measurement}}])
    assert result['alignmentGroups'][0]['sharedScale'] == 1.25
    assert result['alignmentGroups'][0]['bodyMeasurement'] == measurement


@pytest.mark.parametrize('measurement', [
    None, [], 'invalid', {}, {'topY':'2','bottomY':'6','targetHeight':5},
    {'topY':False,'bottomY':6,'targetHeight':5}, {'topY':0,'bottomY':float('nan'),'targetHeight':5},
    {'topY':6,'bottomY':2,'targetHeight':5}, {'topY':2,'bottomY':2,'targetHeight':5},
    {'topY':2,'bottomY':6,'targetHeight':0}, {'topY':2,'bottomY':6,'targetHeight':True},
    {'topY':2,'bottomY':6},
])
def test_invalid_body_geometry_is_rejected_without_mutation(measurement):
    snapshot = json.loads((Path(__file__).parents[1] / 'fixtures/review-transitions.json').read_text())['snapshot']
    before = copy.deepcopy(snapshot)
    with pytest.raises(store.AppError):
        apply(snapshot, [{'type':'setAlignmentGroup','alignmentGroupId':'g',
                          'changes':{'mode':'shared-scale-foot-anchor','bodyMeasurement':measurement}}])
    assert snapshot == before


@pytest.mark.parametrize('fail', [False, True])
def test_connection_context_closes_on_success_and_failure(tmp_path, monkeypatch, fail):
    monkeypatch.setattr(store, 'DATA', tmp_path)
    connection = store.connect()
    try:
        with connection:
            connection.execute('CREATE TABLE sample(value INTEGER)')
            connection.execute('BEGIN')
            connection.execute('INSERT INTO sample VALUES (1)')
            if fail:
                raise RuntimeError('fixture failure')
    except RuntimeError:
        assert fail
    with pytest.raises(sqlite3.ProgrammingError, match='closed'):
        connection.execute('SELECT 1')
    with store.connect() as check:
        assert check.execute('SELECT count(*) FROM sample').fetchone()[0] == (0 if fail else 1)
