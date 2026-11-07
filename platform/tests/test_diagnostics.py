from backend import diagnostics


def test_events_are_allowlisted_and_deletable(tmp_path, monkeypatch):
    monkeypatch.setattr(diagnostics, '_PATH', tmp_path / 'diagnostics.sqlite3')
    diagnostics.emit('trace', 'device_action', action='secret screen text', status='ok', seconds=1, prompt='private prompt')
    diagnostics.emit('trace', 'verification', status='not_matched', reason='destination_text_not_found', observations=3, screen_changed=False)
    result = diagnostics.read('trace')
    assert len(result['events']) == 2
    assert result['events'][0]['details']['action'] == 'other'
    assert 'private prompt' not in str(result)
    assert 'secret screen text' not in str(result)
    diagnostics.delete('trace')
    assert diagnostics.read('trace')['events'] == []


def test_store_failure_does_not_raise(tmp_path, monkeypatch):
    monkeypatch.setattr(diagnostics, '_PATH', tmp_path / 'missing' / 'db.sqlite3')
    diagnostics.emit('failed-trace', 'task_started', screen_mode='ocr')
    assert diagnostics.read('failed-trace')['incomplete']
