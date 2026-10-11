"""Cross-process locked, atomic JSON transactions shared by web and Hermes."""
import copy
import json
import os
import tempfile
from contextlib import contextmanager

@contextmanager
def locked(path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(str(path) + '.lock', 'a+b') as f:
        if os.name == 'nt':
            import msvcrt
            f.write(b'0'); f.flush(); f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == 'nt':
                f.seek(0); msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(f, fcntl.LOCK_UN)

def read_json(path, default=None):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return copy.deepcopy(default)

def atomic_write(path, data):
    fd, temp = tempfile.mkstemp(prefix='.pending-', dir=os.path.dirname(os.path.abspath(path)))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
            f.flush(); os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)

def transaction(path, update, default=None):
    with locked(path):
        data = read_json(path, default)
        result = update(data)
        atomic_write(path, data)
        return result

def identity(item, section):
    if not isinstance(item, dict):
        return None
    if section == 'reports' and item.get('date') and item.get('type'):
        return ('report', item['date'], item['type'])
    if item.get('id'):
        return ('id', item['id'])
    if section == 'daily_log' and item.get('date'):
        return ('date', item['date'])
    return None

def deep_merge(dst, src):
    for key, value in src.items():
        if isinstance(value, dict) and isinstance(dst.get(key), dict):
            deep_merge(dst[key], value)
        elif isinstance(value, list) and isinstance(dst.get(key), list):
            for item in value:
                ident = identity(item, key)
                existing = next((x for x in dst[key] if ident and identity(x, key) == ident), None)
                if existing is not None:
                    deep_merge(existing, item)
                elif item not in dst[key]:
                    dst[key].append(copy.deepcopy(item))
        else:
            dst[key] = copy.deepcopy(value)
