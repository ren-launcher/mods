# Example Mod — demonstrates a basic RenDroid file-overlay mod.
#
# This file is loaded early (init -999) and shows a startup notification
# to confirm the mod is active.
#
# File: game/00example_mod.rpy
# Target prefix: Game root ("") — the ZIP contains a top-level game/ directory.

init -999 python hide:
    import os

    if renpy.android:
        renpy.notify("Example Mod loaded!")
