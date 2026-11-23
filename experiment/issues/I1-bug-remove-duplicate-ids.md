---
id: I1
type: bug
title: "remove() crashes if the same id is passed twice"
---

If an id shows up twice in `doc_ids`, `remove` throws a KeyError:

```python
db = TinyDB(storage=MemoryStorage)
db.insert_multiple([{'name': 'a'}, {'name': 'b'}])
db.remove(doc_ids=[2, 2])   # KeyError: 2
```

I get the ids from two searches so duplicates happen. I'd expect it to just remove doc 2.

`update` has a similar problem: `db.update(increment('views'), doc_ids=[1, 1])` adds 2 instead of 1
and returns `[1, 1]`.
