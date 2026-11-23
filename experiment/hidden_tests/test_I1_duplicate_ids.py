"""Hidden acceptance tests for I1: duplicate IDs in remove/update(doc_ids=...). Never shown to agents."""
from tinydb import TinyDB
from tinydb.operations import increment
from tinydb.storages import MemoryStorage


def _db():
    db = TinyDB(storage=MemoryStorage)
    db.insert_multiple([{'name': 'a', 'views': 0}, {'name': 'b', 'views': 0}])
    return db


def test_remove_with_duplicate_ids_removes_once():
    db = _db()
    removed = db.remove(doc_ids=[2, 2])
    assert removed == [2]
    assert [d.doc_id for d in db.all()] == [1]


def test_remove_with_duplicate_and_missing_ids():
    db = _db()
    removed = db.remove(doc_ids=[1, 99, 1])
    assert removed == [1]
    assert [d.doc_id for d in db.all()] == [2]


def test_update_with_duplicate_ids_applies_once():
    db = _db()
    updated = db.update(increment('views'), doc_ids=[1, 1])
    assert updated == [1]
    assert db.get(doc_id=1)['views'] == 1
    assert db.get(doc_id=2)['views'] == 0
