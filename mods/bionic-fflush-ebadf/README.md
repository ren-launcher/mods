---
version: 1.0.0
---

# Bionic fflush EBADF Fix

Wraps Ren’Py loader file objects with a no-op flush method to prevent read-only file flush errors on Android with Python 2.7.

## Scope

This mod primarily targets Summertime Saga running on Android with Python 2.7. Other Python 2.7 runtimes have not been confirmed. Python 3 runtimes do not need this workaround.

## Supported games

| Game | Game release | Runtime | Verification |
| --- | --- | --- | --- |
| Summertime Saga | 0.20.16, PC version | Ren’Py 7.3.5 on Android (RenDroid) | Confirmed in the original investigation |

Other game releases and runtimes have not been verified.

## Implementation

The script patches `renpy.loader.load` during early initialization. The wrapper delegates file operations to the original object and makes `flush()` a no-op. See [the original investigation](BUG.md) for the call chain and recorded device results.
