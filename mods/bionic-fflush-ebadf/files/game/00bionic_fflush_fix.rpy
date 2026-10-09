# Bionic fflush EBADF Fix
#
# Android's Bionic libc returns EBADF when fflush() is called on a read-only
# file descriptor.  Python 2.7's file.flush() triggers this, which causes
# IOError when io.BufferedReader / io.TextIOWrapper close (they always flush
# before close).
#
# This monkey-patches renpy.loader.load() to wrap every returned file object
# with ReadOnlyFile, whose flush() is a safe no-op.
#
# Affected: Ren'Py 7.x (Python 2.7) on Android.
# See BUG.md for full root-cause analysis.

init -1500 python hide:

    class ReadOnlyFile(object):
        """
        Wraps a read-only file object so that flush() is a safe no-op.
        Proxies everything else to the underlying file unchanged.
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

    import renpy.loader

    _orig_load = renpy.loader.load

    def _patched_load(name, tl=True):
        rv = _orig_load(name, tl)
        return ReadOnlyFile(rv)

    renpy.loader.load = _patched_load
