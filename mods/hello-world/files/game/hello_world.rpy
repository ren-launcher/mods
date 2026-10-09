# Copyright (c) 2026 RenLauncher contributors. MIT.

init python:
    config.start_callbacks.append(lambda: renpy.notify("Hello World!"))
