# RenDroid Mods

Community mods for RenDroid.

## How Mods Work

RenDroid uses **file overlay** — files from a mod ZIP are copied on top of the game directory, replacing or adding game files (`.rpy`, `.rpyc`, images, audio, etc.). Original files are automatically backed up and can be restored when the mod is disabled.

## How to Package a Mod

### ZIP Structure

A mod ZIP should mirror the game directory layout:

```txt
my-mod.zip
├── game/
│   ├── scripts.rpy
│   └── images/
│       └── bg.png
└── renpy/             # optional
    └── ...
```

- Do **not** wrap files in a top-level directory (e.g. `my-mod-v1/game/...`). The ZIP root should directly contain `game/`, `renpy/`, etc.

### Build

```bash
cd my-mod
zip -r ../my-mod.zip . -x '*.md' -x 'VERSION'
```

Or use the provided Makefile (see below).

## Building All Mods

Each mod directory contains a `VERSION` file. The Makefile auto-discovers them and builds versioned ZIPs into `dist/`.

```bash
make          # build all mods → dist/
make clean    # remove dist/
```
