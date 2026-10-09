---
version: 0.1.2
---

# Variable Editor

Search, browse, and edit game variables, persistent data, and scalar values inside objects, dictionaries, and lists.

## Usage

Open the panel with the slider icon in the top-right corner. Search the current level, select an object to browse its contents, and use Back to return. Select a field to edit it and choose Apply to commit. Closing the dialog discards pending changes.

Game edits change the current game state; use the game’s save function to keep them. Persistent edits change data shared across saves and are saved immediately.

## Scope

The editor accesses public instance fields and existing container elements. It does not execute methods or property getters, infer game-specific meanings, or support objects with only slots. Custom engines may require installation adapters; a source overlay is not compatible with every game.
