---
id: I4
type: feature
title: "Limit for search()"
---

I only show the first 10 results in my app. Could `search` take a limit?

```python
db.search(Log.level == 'error', limit=10)
```

Same order as now, and no limit should work like today. Please check it doesn't break the cache,
e.g. `search(q, limit=1)` and then `search(q)` should still give me everything.
