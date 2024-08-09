# edwh

[![PyPI - Version](https://img.shields.io/pypi/v/edwh.svg)](https://pypi.org/project/edwh)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/edwh.svg)](https://pypi.org/project/edwh)

-----

**Table of Contents**

- [Installation](#installation)
- [Usage](#usage)
- [Plugins](#plugins)
- [License](#license)
- [Changelog](#changelog)

## Installation

```console
pipx install edwh
# or: uvenv install edwh

# or with all plugins:
pipx install[plugins]
# or with specific plugins: 
pipx install[multipass,restic]

# managing plugins later:
edwh plugins
edwh plugin.add multipass
edwh plugin.remove multipass
```

## Usage

```console
# to see all available commands:
ew # or `edwh`
# to see help about a specific namespace:
ew help <namespace> # e.g. `ew help plugin`
# to see help about a specific command:
ew help <command> # e.g. `ew help plugin.list` 
```

## Task Load Order

Commands are loaded in the following order:

1. **EDWH Package**:
    - Loaded into the global namespace and its own namespaces (like `ew plugins.`).

2. **Plugins**:
    - Loaded into their own namespaces (like `ew mp.`).

3. **Current Directory**:
    - Loaded into the `local.` namespace. If it doesn't exist, it traverses up the directory tree 
    - (e.g., `../tasks.py`, `../../tasks.py`).

4. **Other Local Tasks**:
    - Other local tasks with their own namespace are loaded (e.g., `namespace.tasks.py`) and can be invoked
      with `edwh namespace.command`.

5. **Personal Global Tasks**:
    - Personal global tasks (e.g., `~/.config/edwh/tasks.py`) are also loaded into the **global** namespace, useful for
      shortcuts, custom aliases, etc. (+ `add_alias`).

6. **Personal Namespaced Tasks**:
    - Personal tasks with their own namespace (e.g., `~/.config/edwh/namespace.tasks.py`). Similar to a plugin, but for
      personal use.

## Plugins

### Multipass

- pip name: [`edwh-multipass-plugin`](https://pypi.org/project/edwh-multipass-plugin/)
- github: [`educationwarehouse/edwh-multipass-plugin`](https://github.com/educationwarehouse/edwh-multipass-plugin)
- plugin name: `edwh[multipass]`
- subcommand namespace: `mp`

### Restic

- pip name: [`edwh-restic-plugin`](https://pypi.org/project/edwh-restic-plugin/)
- github: [`educationwarehouse/edwh-restic-plugin`](https://github.com/educationwarehouse/edwh-restic-plugin)
- plugin name: `edwh[restic]`
- subcommand namespace: `restic`

### Pip Compile

- pip name: [`edwh-pipcompile-plugin`](https://pypi.org/project/edwh-pipcompile-plugin/)
- github: [`educationwarehouse/edwh-pipcompile-plugin`](https://github.com/educationwarehouse/edwh-pipcompile-plugin)
- plugin name: `edwh[pip]`
- subcommand namespace: `pip`

### Bundler

- pip name: [`edwh-bundler-plugin`](https://pypi.org/project/edwh-bundler-plugin/)
- github: [`educationwarehouse/edwh-bundler-plugin`](https://github.com/educationwarehouse/edwh-bundler-plugin)
- plugin name: `edwh[bundler]`
- subcommand namespace: `bundle`

### Server Provisioning

- pip name: [`edwh-server-provisioning-plugin`](https://pypi.org/project/edwh-server-provisioning-plugin/)
- github: [`educationwarehouse/server_provisioning`](https://github.com/educationwarehouse/server_provisioning)
- plugin name: `edwh[server-provisioning]`
- subcommand namespace: `remote`

### b2

- pip name: [`edwh-b2-plugin`](https://pypi.org/project/edwh-b2-plugin/)
- github: [`educationwarehouse/edwh-b2-plugin`](https://github.com/educationwarehouse/edwh-b2-plugin)
- plugin name: `edwh[b2]`
- subcommand namespace: `b2`

### Locust

- pip name: [`edwh-locust-plugin`](https://pypi.org/project/edwh-locust-plugin/)
- github: [`educationwarehouse/edwh-locust-plugin`](https://github.com/educationwarehouse/edwh-locust-plugin)
- plugin name: `edwh[locust]`
- subcommand namespace: `locust`

### sshkey

- pip name: [`edwh-sshkey-plugin`](https://pypi.org/project/edwh-sshkey-plugin)
- github: [`educationwarehouse/edwh-sshkey-plugin`](https://github.com/educationwarehouse/edwh-sshkey-plugin)
- plugin name `edwh[sshkey]`
- subcommand namespace `sshkey`

### sshfs

- pip name: [`edwh-sshfs-plugin`](https://pypi.org/project/edwh-sshfs-plugin)
- github: [`educationwarehouse/edwh-sshfs-plugin`](https://github.com/educationwarehouse/edwh-sshfs-plugin)
- plugin name `edwh[sshfs]`
- subcommand namespace `sshfs`

### files

- pip name: [`edwh-files-plugin`](https://pypi.org/project/edwh-files-plugin)
- github: [`educationwarehouse/edwh-files-plugin`](https://github.com/educationwarehouse/edwh-files-plugin)
- plugin name `edwh[files]`
- subcommand namespace `file`

### whitelabel

- pip name: [`edwh-whitelabel-plugin`](https://pypi.org/project/edwh-whitelabel-plugin)
- github: [`educationwarehouse/edwh-whitelabel-plugin`](https://github.com/educationwarehouse/edwh-whitelabel-plugin)
- plugin name `edwh[whitelabel]`
- subcommand namespace `wl`

## License

`edwh` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.

## Changelog

[See CHANGELOG.md](CHANGELOG.md)