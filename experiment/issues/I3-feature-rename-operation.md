---
id: I3
type: feature
title: "Add a rename operation"
---

We renamed `username` to `login` and I had to write my own function for it. It would be nice to have
this in `tinydb.operations`:

```python
from tinydb.operations import rename
db.update(rename('username', 'login'))
```

Docs without `username` should be left alone. If a doc already has `login`, just overwrite it.
