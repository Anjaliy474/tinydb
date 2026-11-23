from tinydb import where
from tinydb.operations import delete, increment, decrement, add, subtract, set


def test_delete(db):
    db.update(delete('int'), where('char') == 'a')
    assert 'int' not in db.get(where('char') == 'a')


def test_add_int(db):
    db.update(add('int', 5), where('char') == 'a')
    assert db.get(where('char') == 'a')['int'] == 6


def test_add_str(db):
    db.update(add('char', 'xyz'), where('char') == 'a')
    assert db.get(where('char') == 'axyz')['int'] == 1


def test_subtract(db):
    db.update(subtract('int', 5), where('char') == 'a')
    assert db.get(where('char') == 'a')['int'] == -4


def test_set(db):
    db.update(set('char', 'xyz'), where('char') == 'a')
    assert db.get(where('char') == 'xyz')['int'] == 1


def test_increment(db):
    db.update(increment('int'), where('char') == 'a')
    assert db.get(where('char') == 'a')['int'] == 2


def test_decrement(db):
    db.update(decrement('int'), where('char') == 'a')
    assert db.get(where('char') == 'a')['int'] == 0


def test_rename_seeded(db):
    from tinydb.operations import rename
    db.update(rename('char', 'letter'), where('char') == 'a')
    assert db.get(where('letter') == 'a') == {'int': 1, 'letter': 'a'}
    assert db.count(where('char').exists()) == 2


def test_rename_missing_and_existing_field_seeded(db):
    from tinydb.operations import rename
    db.insert({'other': 1})
    db.insert({'char': 'x', 'letter': 'old'})
    db.update(rename('char', 'letter'))
    assert db.get(where('other') == 1) == {'other': 1}
    assert db.count(where('letter') == 'x') == 1
    assert db.count(where('char').exists()) == 0
