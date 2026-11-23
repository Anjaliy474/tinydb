from tinydb import where
from tinydb.operations import (
    delete, increment, decrement, add, subtract, set, rename,
)


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


def test_rename_ac1(db):
    db.truncate()
    doc_id = db.insert({'username': 'jane', 'age': 30})

    db.update(rename('username', 'login'))

    assert db.all() == [{'login': 'jane', 'age': 30}]
    # The document keeps its original doc_id
    assert len(db) == 1
    assert db.contains(doc_id=doc_id)
    assert db.get(doc_id=doc_id) == {'login': 'jane', 'age': 30}


def test_rename_missing_key_ac2(db):
    db.truncate()
    db.insert({'name': 'no-user'})
    db.insert({'username': 'bob'})

    db.update(rename('username', 'login'))

    assert db.all() == [{'name': 'no-user'}, {'login': 'bob'}]


def test_rename_overwrite_ac3(db):
    db.truncate()
    db.insert({'username': 'new-name', 'login': 'old-name'})

    db.update(rename('username', 'login'))

    assert db.all() == [{'login': 'new-name'}]


def test_rename_with_condition_ac4(db):
    db.truncate()
    db.insert({'username': 'a', 'char': 'a'})
    db.insert({'username': 'b', 'char': 'b'})

    db.update(rename('username', 'login'), where('char') == 'a')

    assert db.all() == [
        {'login': 'a', 'char': 'a'},
        {'username': 'b', 'char': 'b'},
    ]


def test_delete_and_set_unchanged_ac5(db):
    db.update(delete('int'), where('char') == 'a')
    db.update(set('char', 'xyz'), where('char') == 'a')

    assert db.all() == [
        {'char': 'xyz'},
        {'int': 1, 'char': 'b'},
        {'int': 1, 'char': 'c'},
    ]
