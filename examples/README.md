# Examples

- `config.single-drive.json`: the minimal configuration the installer writes for a single-drive setup.
- `config.ssd-hdd.json`: index on an SSD, archive and old documents on a second drive, an adopted Obsidian vault
  with its own folder names, and the Claude Code integration.

Any key you leave out takes its default (see [docs/CONFIGURATION.md](../docs/CONFIGURATION.md)). Replace `<you>`
with your Windows user name, or let the installer write the file for you.

## Example vault

The fictional demo vault (the persona Alex Morgan: a garden-planner app, half-marathon training, learning Spanish)
ships inside the package. Create a copy anywhere with:

```
personalos init --vault <empty folder> --demo
```

Every demo note has `demo: true` in its frontmatter.
