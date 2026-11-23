"""
Contains the :class:`base class <tinydb.storages.Storage>` for storages and
implementations.
"""

import io
import json
import os
import warnings
from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Any, Optional

__all__ = ('Storage', 'JSONStorage', 'MemoryStorage')

# Tag keys used to encode ``datetime``/``date`` values in the JSON file. The
# tag makes the on-disk form distinguishable from an ordinary string, so no
# already-stored string is ever reinterpreted when reading a database.
_DATETIME_TAG = '__tinydb_datetime__'
_DATE_TAG = '__tinydb_date__'


def _encode_value(obj: Any):
    """
    ``json.dumps`` ``default`` hook that encodes ``datetime`` and ``date``
    values in the tagged form.

    All other types raise :exc:`TypeError`, just like the default encoder.

    :param obj: The value that ``json`` cannot encode.
    """
    if isinstance(obj, datetime):
        return {_DATETIME_TAG: obj.isoformat()}

    if isinstance(obj, date):
        return {_DATE_TAG: obj.isoformat()}

    raise TypeError(
        f'Object of type {type(obj).__name__} is not JSON serializable'
    )


def _decode_value(obj: dict[str, Any]):
    """
    ``json.load`` ``object_hook`` that decodes the tagged form back into
    ``datetime``/``date`` objects.

    Dicts that don't carry exactly one of the tags with a parseable string
    value are returned unchanged, so foreign or malformed data never makes
    reading a database fail.

    :param obj: The decoded JSON object.
    """
    if len(obj) == 1:
        if _DATETIME_TAG in obj:
            value = obj[_DATETIME_TAG]
            try:
                if isinstance(value, str):
                    return datetime.fromisoformat(value)
            except ValueError:
                pass
        elif _DATE_TAG in obj:
            value = obj[_DATE_TAG]
            try:
                if isinstance(value, str):
                    return date.fromisoformat(value)
            except ValueError:
                pass

    return obj


def touch(path: str, create_dirs: bool):
    """
    Create a file if it doesn't exist yet.

    :param path: The file to create.
    :param create_dirs: Whether to create all missing parent directories.
    """
    if create_dirs:
        base_dir = os.path.dirname(path)

        # Check if we need to create missing parent directories
        if base_dir and not os.path.exists(base_dir):
            os.makedirs(base_dir)

    # Create the file by opening it in 'a' mode which creates the file if it
    # does not exist yet but does not modify its contents
    with open(path, 'a'):
        pass


class Storage(ABC):
    """
    The abstract base class for all Storages.

    A Storage (de)serializes the current state of the database and stores it in
    some place (memory, file on disk, ...).
    """

    # Using ABCMeta as metaclass allows instantiating only storages that have
    # implemented read and write

    @abstractmethod
    def read(self) -> Optional[dict[str, dict[str, Any]]]:
        """
        Read the current state.

        Any kind of deserialization should go here.

        Return ``None`` here to indicate that the storage is empty.
        """

        raise NotImplementedError('To be overridden!')

    @abstractmethod
    def write(self, data: dict[str, dict[str, Any]]) -> None:
        """
        Write the current state of the database to the storage.

        Any kind of serialization should go here.

        :param data: The current state of the database.
        """

        raise NotImplementedError('To be overridden!')

    def close(self) -> None:
        """
        Optional: Close open file handles, etc.
        """

        pass


class JSONStorage(Storage):
    """
    Store the data in a JSON file.

    ``datetime`` and ``date`` values are stored in a tagged form
    (``{"__tinydb_datetime__": ...}``) and are read back as
    ``datetime``/``date`` objects. All other values are stored and read back
    unchanged; in particular, strings that merely look like a date are never
    converted.
    """

    def __init__(self, path: str, create_dirs=False, encoding=None, access_mode='r+', **kwargs):
        """
        Create a new instance.

        Also creates the storage file, if it doesn't exist and the access mode
        is appropriate for writing.

        **Note:** Using an access mode other than `r` or `r+` will probably
        lead to data loss or data corruption!

        **Note:** **Never** pass untrusted or user-controlled code as ``kwargs``
        members like ``cls`` or ``default`` will be called on every write
        operation.

        :param path: Where to store the JSON data.
        :param access_mode: mode in which the file is opened (r, r+)
        :type access_mode: str
        """

        super().__init__()

        self._mode = access_mode
        self.kwargs = kwargs

        if access_mode not in ('r', 'rb', 'r+', 'rb+'):
            warnings.warn(
                'Using an `access_mode` other than \'r\', \'rb\', \'r+\' '
                'or \'rb+\' can cause data loss or corruption'
            )

        # Create the file if it doesn't exist and creating is allowed by the
        # access mode
        if any([character in self._mode for character in ('+', 'w', 'a')]):  # any of the writing modes
            touch(path, create_dirs=create_dirs)

        # Open the file for reading/writing
        self._handle = open(path, mode=self._mode, encoding=encoding)

    def close(self) -> None:
        self._handle.close()

    def read(self) -> Optional[dict[str, dict[str, Any]]]:
        # Get the file size by moving the cursor to the file end and reading
        # its location
        self._handle.seek(0, os.SEEK_END)
        size = self._handle.tell()

        if not size:
            # File is empty, so we return ``None`` so TinyDB can properly
            # initialize the database
            return None
        else:
            # Return the cursor to the beginning of the file
            self._handle.seek(0)

            # Load the JSON contents of the file
            return json.load(self._handle, object_hook=_decode_value)

    def write(self, data: dict[str, dict[str, Any]]):
        # Move the cursor to the beginning of the file just in case
        self._handle.seek(0)

        # Serialize the database state using the user-provided arguments
        kwargs = dict(self.kwargs)

        # Only add our own encoder if the user hasn't supplied one, so custom
        # ``default``/``cls`` arguments keep working as before
        if 'default' not in kwargs and 'cls' not in kwargs:
            kwargs['default'] = _encode_value

        serialized = json.dumps(data, **kwargs)

        # Write the serialized data to the file
        try:
            self._handle.write(serialized)
        except io.UnsupportedOperation:
            raise IOError('Cannot write to the database. Access mode is "{0}"'.format(self._mode))

        # Ensure the file has been written
        self._handle.flush()
        os.fsync(self._handle.fileno())

        # Remove data that is behind the new cursor in case the file has
        # gotten shorter
        self._handle.truncate()


class MemoryStorage(Storage):
    """
    Store the data as JSON in memory.
    """

    def __init__(self):
        """
        Create a new instance.
        """

        super().__init__()
        self.memory = None

    def read(self) -> Optional[dict[str, dict[str, Any]]]:
        return self.memory

    def write(self, data: dict[str, dict[str, Any]]):
        self.memory = data
