"""Hidden acceptance tests for I4: search(cond, limit=N). Never shown to agents."""
from tinydb import TinyDB, Query
from tinydb.storages import MemoryStorage


def _db():
    db = TinyDB(storage=MemoryStorage)
    db.insert_multiple([{'level': 'error', 'n': i} for i in range(5)] +
                       [{'level': 'info', 'n': 99}])
    return db


def test_limit_returns_first_n_in_order():
    db = _db()
    result = db.search(Query().level == 'error', limit=3)
    assert [d['n'] for d in result] == [0, 1, 2]


def test_limit_larger_than_matches_and_default():
    db = _db()
    q = Query().level == 'error'
    assert [d['n'] for d in db.search(q, limit=50)] == [0, 1, 2, 3, 4]
    assert [d['n'] for d in db.search(q)] == [0, 1, 2, 3, 4]


def test_limited_search_does_not_poison_cache():
    db = _db()
    q = Query().level == 'error'
    assert len(db.search(q, limit=1)) == 1
    assert len(db.search(q)) == 5
    assert len(db.search(q, limit=2)) == 2
    assert len(db.search(q)) == 5


def test_limit_on_named_table():
    db = _db()
    t = db.table('logs')
    t.insert_multiple([{'level': 'error'}] * 4)
    assert len(t.search(Query().level == 'error', limit=2)) == 2
