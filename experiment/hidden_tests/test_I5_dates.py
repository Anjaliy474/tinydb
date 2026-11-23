"""Hidden acceptance tests for I5 (vague): saving records with dates. Never shown to agents.

The issue is deliberately vague, so these tests only check what any reasonable fix must do:
saving works, the date comes back in a recognisable form, and nothing else breaks. A fix may
return a datetime, an ISO-8601 string, or str(datetime).
"""
import datetime
import json

from tinydb import TinyDB

WHEN = datetime.datetime(2026, 11, 23, 10, 30, 0)


def _accepted(value):
    return value in (WHEN, WHEN.isoformat(), str(WHEN))


def test_insert_with_datetime_does_not_crash(tmp_path):
    path = tmp_path / 'db.json'
    with TinyDB(path) as db:
        db.insert({'event': 'login', 'when': WHEN})
        assert len(db) == 1


def test_datetime_survives_reopen(tmp_path):
    path = tmp_path / 'db.json'
    with TinyDB(path) as db:
        db.insert({'event': 'login', 'when': WHEN})
    with TinyDB(path) as db:
        doc = db.all()[0]
        assert doc['event'] == 'login'
        assert _accepted(doc['when'])


def test_file_stays_valid_json_and_other_records_unchanged(tmp_path):
    path = tmp_path / 'db.json'
    with TinyDB(path) as db:
        db.insert({'event': 'plain', 'count': 3})
        db.insert({'event': 'dated', 'when': WHEN})
    with open(path, encoding='utf-8') as f:
        json.load(f)
    with TinyDB(path) as db:
        assert db.get(doc_id=1) == {'event': 'plain', 'count': 3}
