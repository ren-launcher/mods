# Mods

A source and distribution repository for Ren’Py mods. Each mod declares its version and usage in a README, stores its game-root overlay in `files/`, and is distributed as a ZIP inside an OCI artifact.

## Installation and removal

Close the game, import and enable the mod ZIP through your launcher, then start the game. Close the game before updating, disabling, or removing a mod.

For manual installation, back up any files the ZIP will replace, then extract it into the game root containing `game/`. To uninstall, remove files added by the mod and their generated `.rpyc` files, and restore replaced originals. Removing a mod does not undo changes already saved to game saves or persistent data.

## Development

See [Development](DEVELOPMENT.md) for tooling and publishing, and [Distribution design](docs/design.md) for the client contract.
