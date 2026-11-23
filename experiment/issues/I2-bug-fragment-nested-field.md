---
id: I2
type: bug
title: "fragment() on two different fields gives the same result"
---

```python
db.insert_multiple([
    {'name': 'ann', 'home': {'city': 'Pune'}, 'work': {'city': 'Hyderabad'}},
    {'name': 'bob', 'home': {'city': 'Hyderabad'}, 'work': {'city': 'Pune'}},
])
User = Query()
db.search(User.home.fragment({'city': 'Pune'}))   # [ann], ok
db.search(User.work.fragment({'city': 'Pune'}))   # [ann], should be [bob]
```

The second search returns the first one's result. With `db.clear_cache()` in between it works, so
I guess it's the cache. Also `User.home.fragment({'city': 'Pune'}) == User.work.fragment({'city': 'Pune'})`
is True, which looks wrong.
