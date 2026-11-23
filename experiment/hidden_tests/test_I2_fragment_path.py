"""Hidden acceptance tests for I2: fragment() must take the field path into account. Never shown to agents."""
from tinydb import TinyDB, Query
from tinydb.storages import MemoryStorage


def _db():
    db = TinyDB(storage=MemoryStorage)
    db.insert_multiple([
        {'name': 'ann', 'home': {'city': 'Pune'}, 'work': {'city': 'Hyderabad'}},
        {'name': 'bob', 'home': {'city': 'Hyderabad'}, 'work': {'city': 'Pune'}},
    ])
    return db


def test_fragment_on_different_fields_returns_different_results():
    db = _db()
    User = Query()
    assert [d['name'] for d in db.search(User.home.fragment({'city': 'Pune'}))] == ['ann']
    assert [d['name'] for d in db.search(User.work.fragment({'city': 'Pune'}))] == ['bob']
    # and again in the other order, now that both are cached
    assert [d['name'] for d in db.search(User.home.fragment({'city': 'Pune'}))] == ['ann']


def test_fragment_queries_on_different_fields_are_not_equal():
    User = Query()
    assert User.home.fragment({'city': 'Pune'}) != User.work.fragment({'city': 'Pune'})


def test_fragment_same_field_still_equal_and_cacheable():
    User = Query()
    q1 = User.home.fragment({'city': 'Pune'})
    q2 = User.home.fragment({'city': 'Pune'})
    assert q1 == q2
    assert hash(q1) == hash(q2)
    assert q1.is_cacheable()
    # top-level fragment (no path) keeps working
    db = _db()
    assert [d['name'] for d in db.search(Query().fragment({'name': 'bob'}))] == ['bob']
