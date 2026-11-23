"""
A collection of update operations for TinyDB.

They are used for updates like this:

>>> db.update(delete('foo'), where('foo') == 2)

This would delete the ``foo`` field from all documents where ``foo`` equals 2.
"""


from collections.abc import Callable, MutableMapping
from typing import Any, Union


def delete(field: str) -> Callable[[MutableMapping], None]:
    """
    Delete a given field from the document.
    """
    def transform(doc: MutableMapping):
        del doc[field]

    return transform


def add(field: str, n: Union[int, float, str]) -> Callable[[MutableMapping], None]:
    """
    Add ``n`` to a given field in the document.

    Also works for strings (concatenation), matching the documented behavior.
    """
    def transform(doc: MutableMapping):
        doc[field] += n

    return transform


def subtract(field: str, n: Union[int, float]) -> Callable[[MutableMapping], None]:
    """
    Subtract ``n`` to a given field in the document.
    """
    def transform(doc: MutableMapping):
        doc[field] -= n

    return transform


def set(field: str, val: Any) -> Callable[[MutableMapping], None]:
    """
    Set a given field to ``val``.
    """
    def transform(doc: MutableMapping):
        doc[field] = val

    return transform


def increment(field: str) -> Callable[[MutableMapping], None]:
    """
    Increment a given field in the document by 1.
    """
    def transform(doc: MutableMapping):
        doc[field] += 1

    return transform


def decrement(field: str) -> Callable[[MutableMapping], None]:
    """
    Decrement a given field in the document by 1.
    """
    def transform(doc: MutableMapping):
        doc[field] -= 1

    return transform


def rename(old_key: str, new_key: str) -> Callable[[MutableMapping], None]:
    """
    Rename a given field in the document.

    The value of ``old_key`` is moved to ``new_key`` and ``old_key`` is
    removed. If the document does not contain ``old_key``, it is left
    untouched. If it already contains ``new_key``, its value is overwritten.
    Only top-level keys are supported, so a ``new_key`` containing dots is
    stored literally.
    """
    def transform(doc: MutableMapping):
        if old_key in doc:
            value = doc[old_key]
            del doc[old_key]
            doc[new_key] = value

    return transform
