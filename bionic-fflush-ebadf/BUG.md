# BUG: `IOError [Errno 9] Bad file descriptor` on Android with Python 2.7

## Summary

PC-version Ren'Py 7.3.5 games that wrap `renpy.file()` with Python's `io.BufferedReader` / `io.TextIOWrapper` crash on Android with:

```
IOError: [Errno 9] Bad file descriptor
```

The error occurs during `close()`, not during `read()`.

## Root Cause

Android's **Bionic libc** treats `fflush()` on a read-only file descriptor as an error and returns `EBADF`. Desktop C libraries (glibc on Linux, libSystem on macOS) silently ignore it.

The POSIX standard leaves the behavior of `fflush()` on input streams as **undefined**, so both implementations are technically correct — but Bionic's strict interpretation breaks Python 2.7 code that calls `file.flush()` on read-only files.

### Call Chain

```
TextIOWrapper.close()
  → BufferedReader.close()
    → BufferedReader.flush()          # C-level io module always flushes before close
      → ReadableFile.__getattr__("flush")   # proxied to underlying file object
        → file.flush()               # Python 2.7 built-in file type
          → fflush(fp)               # C standard library call
            → EBADF on Bionic        # ← Android-specific failure
```

### Platform Comparison

| Platform | `open("file", "rb")` → `flush()` | Underlying `fflush()` behavior |
|---|---|---|
| Linux (glibc) | OK (silent no-op) | Ignores input streams |
| macOS (libSystem) | OK (silent no-op) | Ignores input streams |
| Android (Bionic) | **IOError [Errno 9]** | Returns `EBADF` for input streams |

## Reproduction

The issue was first observed with **SummertimeSaga 0.20.16 (PC version)** running on RenDroid with the Ren'Py 7.3.5 runtime.

### Trigger Code (from game's `scripts.rpa` → `game/scripts/core/io.rpy`)

```python
# game/scripts/core/io.rpy — defines store.io module
class ReadableFile(object):
    def __init__(self, fn):
        self._raw = renpy.file(fn)   # returns Python 2.7 built-in file object
        self.closed = False

    def readinto(self, b):
        data = self.read(len(b))
        b[:len(data)] = data
        return len(data)

    def __getattr__(self, name):      # proxies flush/tell/read/seek to _raw
        return getattr(self._raw, name)

def open(fn, encoding=None):
    rf = ReadableFile(fn)
    br = io.BufferedReader(rf)
    if encoding:
        return io.TextIOWrapper(br, encoding=encoding)
    return br
```

```python
# game/scripts/core/changelog.rpy
init python in changelog hide:
    from store.io import open
    with open('changelog.txt', encoding='utf8') as f:   # ← __exit__ triggers close → flush → EBADF
        data = f.read()
```

### On-Device Test Results

```
--- Test A: plain file flush then close ---
read OK: 10
flush before close...
FAIL: [Errno 9] Bad file descriptor          # Even plain file(fn,"rb").flush() fails!

--- Test B: renpy.file flush then close ---
read OK: 10
flush()...
FAIL: IOError [Errno 9] Bad file descriptor   # Same for renpy.file()

--- Test D: ReadableFile with own flush() ---  # Fix: add no-op flush()
read OK: 81920 chars
tw.close()...
RF2.flush() called (no-op)
RF2.close() called
tw.close() OK!                                 # Works!
```

## Fix

Add a `ReadOnlyFile` wrapper in `renpy/loader.py` that provides a safe no-op `flush()` and proxies all other attributes to the underlying file object. Wrap all file objects returned by `load_core()`.

```python
class ReadOnlyFile(object):
    """
    Wraps a read-only file object to make flush() safe.

    On Android with Python 2.7, calling file.flush() on a read-only file
    descriptor raises IOError ([Errno 9] Bad file descriptor). This wrapper
    provides a no-op flush(), preventing errors when the file is used with
    io.BufferedReader or io.TextIOWrapper whose close() calls flush().
    """

    def __init__(self, f):
        object.__setattr__(self, '_f', f)

    def flush(self):
        return

    def __enter__(self):
        return self

    def __exit__(self, _type, value, tb):
        self.close()
        return False

    def __iter__(self):
        return iter(object.__getattribute__(self, '_f'))

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, '_f'), name)
```

### Affected Runtimes

- **7.3.5** (Python 2.7) — confirmed affected
- Other Python 2.7 runtimes (7.4.x, 7.5.x, 7.6.x) — likely affected
- Python 3 runtimes (8.x) — **not affected** (Python 3's `open()` returns `io.BufferedReader` natively, and its `flush()` does not call C `fflush()` on read-only streams)
