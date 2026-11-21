import asyncio

_locks: dict[int, asyncio.Lock] = {}

def lock(uid: int) -> asyncio.Lock:
    return _locks.setdefault(uid, asyncio.Lock())

def busy(uid: int) -> bool:
    l = _locks.get(uid)
    return bool(l and l.locked())
