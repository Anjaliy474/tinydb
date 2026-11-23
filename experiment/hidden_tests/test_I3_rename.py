"""Hidden acceptance tests for I3: operations.rename. Never shown to agents."""
from tinydb import TinyDB, Query
from tinydb.storages import MemoryStorage


def test_rename_moves_value_and_removes_old_field():
    from tinydb.operations import rename
    db = TinyDB(storage=MemoryStorage)
    db.insert({'username': 'ann', 'age': 30})
    db.update(rename('username', 'login'))
    doc = db.get(doc_id=1)
    assert doc == {'login': 'ann', 'age': 30}


def test_rename_skips_documents_without_old_field_and_respects_query():
    from tinydb.operations import rename
    db = TinyDB(storage=MemoryStorage)
    db.insert_multiple([
        {'username': 'ann', 'active': True},
        {'username': 'bob', 'active': False},
        {'email': 'c@example.com', 'active': True},
    ])
    db.update(rename('username', 'login'), Query().active == True)  # noqa: E712
    assert db.get(doc_id=1) == {'login': 'ann', 'active': True}
    assert db.get(doc_id=2) == {'username': 'bob', 'active': False}
    assert db.get(doc_id=3) == {'email': 'c@example.com', 'active': True}


def test_rename_overwrites_existing_target_field():
    from tinydb.operations import rename
    db = TinyDB(storage=MemoryStorage)
    db.insert({'username': 'ann', 'login': 'old'})
    db.update(rename('username', 'login'))
    assert db.get(doc_id=1) == {'login': 'ann'}
