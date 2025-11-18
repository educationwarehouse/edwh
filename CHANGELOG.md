# Changelog

<!--next-version-placeholder-->

## v1.7.0 (2025-11-18)

### Feature

* Make `ew fmt` show unused imports and fix `--ioptimize` to remove these ([`36676cd`](https://github.com/educationwarehouse/edwh/commit/36676cd6e74f9ee5c56dbb413acaccca6a030df3))

## v1.6.3 (2025-11-14)

### Fix

* **set_env_value:** Allow setting value to None to remove the env key ([`82284ca`](https://github.com/educationwarehouse/edwh/commit/82284ca8104d1319a13e463528a7e41f849277b8))

## v1.6.2 (2025-11-10)

### Fix

* **build:** Don't prompt user when state of development indicates development; include 'pull' in confirmation prompt ([`5f85e70`](https://github.com/educationwarehouse/edwh/commit/5f85e707e92872b6cd66e98e3865a6a17577749d))

## v1.6.1 (2025-11-10)

### Fix

* Merge `dc build` into `dc up --build` to speed it up; include `dc pull` in `ew build` ([`5af381d`](https://github.com/educationwarehouse/edwh/commit/5af381dfcd9c8044cb1821ffb43fe550601f7df3))

## v1.6.0 (2025-11-07)

### Feature

* **up:** Deal with paused containers (unpause+stop incl deps) and always build before up since cache is fast anyway ([`9612823`](https://github.com/educationwarehouse/edwh/commit/96128234900a29c808ef481bf62d9109e65256f3))

### Fix

* Only require hatch when using publish with `--hatch` ([`e9e6f05`](https://github.com/educationwarehouse/edwh/commit/e9e6f05f3028b3973d0ce29f99aa618edc8fe6ae))

## v1.5.0 (2025-11-01)

### Feature

* Switch from hatch to uv for build and publish ([`0a0b2bc`](https://github.com/educationwarehouse/edwh/commit/0a0b2bcbd353c90c4cbd7fbeed534e96a2f26501))

## v1.4.3 (2025-10-30)

### Fix

* Export get_hosts_for_service again ([`175a979`](https://github.com/educationwarehouse/edwh/commit/175a979c0a4866022b5058c26a0d7266d33194b5))

## v1.4.2 (2025-10-28)

### Fix

* Add terminal hyperlink support and improve compose file discovery ([`69fef80`](https://github.com/educationwarehouse/edwh/commit/69fef8032ef544231decbde6eb269fa8c3f268c6))

## v1.4.1 (2025-10-21)

### Fix

* Add 'git' as official plugin ([`f4cfc44`](https://github.com/educationwarehouse/edwh/commit/f4cfc4413446e778d8e351ce44f7b7af69da974c))

## v1.4.0 (2025-10-14)

### Feature

* **psa:** Add a column indicating the project's health (ok, unhealthy, paused, mixed) ([`2151db2`](https://github.com/educationwarehouse/edwh/commit/2151db23916eafc1a6d51cd5975d65198ce659c4))

## v1.3.0 (2025-10-10)

### Feature

* `edwh sudo` command to store sudo in os keyring ([`9b1448f`](https://github.com/educationwarehouse/edwh/commit/9b1448f6322b15193840649d1d6159cb9cbe963a))

## v1.2.1 (2025-10-10)



## v1.2.0 (2025-10-06)

### Fix

* Improvement in 'health --wait' so its more accurate ([`535c768`](https://github.com/educationwarehouse/edwh/commit/535c76836e3cda30813fdeca8774ebc0b8b5933c))

### Documentation

* Update to coding-guidelines.md ([`4932e8a`](https://github.com/educationwarehouse/edwh/commit/4932e8afd4eef96f63ae00c7a263173695ff9f5c))
* Add coding guidelines ([`ac7224a`](https://github.com/educationwarehouse/edwh/commit/ac7224ac4f0c2889aab67b9068aaa9ef9d5c3d04))

## v1.1.0 (2025-08-28)

### Feature

* `start_logs` supports extra args ([`330c9bf`](https://github.com/educationwarehouse/edwh/commit/330c9bff353ebfbacd758cf9c5c4dd121317350c))

## v1.0.6 (2025-08-05)

### Fix

* Replace hardcoded database names with discovered container names ([`c6f8513`](https://github.com/educationwarehouse/edwh/commit/c6f8513464fad77b3de289b45a4dbc33369925f6))

## v1.0.5 (2025-07-11)

### Fix

* Re-introduce `run_fmt` function ([`dd90a83`](https://github.com/educationwarehouse/edwh/commit/dd90a83404fd0d0c3e56c6446f46c5292b67368d))

## v1.0.4 (2025-07-10)

### Fix

* Replace .exists with `exists_nonempty` which also checks the file actually has some bytes of content ([`9317ae6`](https://github.com/educationwarehouse/edwh/commit/9317ae638dc7e3e69a36d4cd6818a62b794e01b9))
* Reorder checks in read_dotenv and remove redundant code ([`fe1af27`](https://github.com/educationwarehouse/edwh/commit/fe1af27fa47287f1e15c4aa56dd7019a360e6d8d))

## v1.0.3 (2025-07-08)

### Fix

* Mark dependency as '>=' instead of '>' ([`81f618b`](https://github.com/educationwarehouse/edwh/commit/81f618b06a1a8f5656e52b6c96e9153f3fc15ef5))

## v1.0.2 (2025-07-08)

### Fix

* Also bump `ewok` even if no new `edwh` version was released ([`67e14e8`](https://github.com/educationwarehouse/edwh/commit/67e14e874a5e5c9eea8d09d04e942bded48705e9))

## v1.0.1 (2025-07-04)

### Fix

* Bump `ruff` version ([`fe734df`](https://github.com/educationwarehouse/edwh/commit/fe734df3104aea04ce2755d3ee5844ce16223582))

## v1.0.0 (2025-07-04)

### Feature

* Rewrote `logs` function so it doesn't require sudo file access anymore ([`5dc74d3`](https://github.com/educationwarehouse/edwh/commit/5dc74d33bf7874f7d21af83944cf279209077586))
* Ported a lot of cli-framework functionality to `ewok` ([`7f993e0`](https://github.com/educationwarehouse/edwh/commit/7f993e0d4fb6ac69ebd07fe33531255033cb71c5))

### Fix

* Improved ctrl-c and docker restart handling ([`4525b57`](https://github.com/educationwarehouse/edwh/commit/4525b57823a704357c1decfc1caeba4430902f17))
* **monkeypatch_invoke:** Add exception for `fabric` and `invoke` internals and show warning once per file ([`0ffb53a`](https://github.com/educationwarehouse/edwh/commit/0ffb53a005c91070597c20802e235d8ec0b90912))
* Monkeypatch invoke to show warning if invoke.task is used instead of edwh.task or ewok.task ([`e6f60ff`](https://github.com/educationwarehouse/edwh/commit/e6f60ff99819c3ea3d3390f1e728ded16883b3f8))
* It seems t.get_args doesn't work on a literal that uses the `type` keyword ([`9384310`](https://github.com/educationwarehouse/edwh/commit/9384310f4f43aafb8e3fb28d9b19e7ee3f4d2cf1))
* Improved typing ([`ca5b16c`](https://github.com/educationwarehouse/edwh/commit/ca5b16cae9f66206b726ee77f0141ee30694dc0c))
* Bump minimum supported Python version to 3.12; change `logs` from `threading` to `concurrent.futures` for higher-level api ([`271504d`](https://github.com/educationwarehouse/edwh/commit/271504d3604bde63a090a21f30b6c76b55ec4e5f))
* **logs:** A bit more useful return type for `follow_logs` ([`55294be`](https://github.com/educationwarehouse/edwh/commit/55294bec9cc23943b8f05a7f4dcbba0124bbe3ee))
* Show error if `get_task` is called with old signature ([`dd76f22`](https://github.com/educationwarehouse/edwh/commit/dd76f223c00142e1ea2b6036e3b6110b9587d820))
* **logs:** Don't crash if container_id is empty (for some reason) ([`488612d`](https://github.com/educationwarehouse/edwh/commit/488612d81a8032e2eb0073fe0476c284967e2025))

## v0.60.0 (2025-06-23)

### Feature

* `restart` command do force restart within a container by killing pid 1 ([`79286dc`](https://github.com/educationwarehouse/edwh/commit/79286dcc3bbffcd9176e6a2424f802b7a9286d2e))

## v0.59.1 (2025-06-19)

### Fix

* **fmt:** Improve handling of file arguments in run_fmt method ([`c76de0d`](https://github.com/educationwarehouse/edwh/commit/c76de0d0aa33861e81db36d3183f4fdea2d694ea))

## v0.59.0 (2025-06-19)

### Feature

* Add `ew-fmt` script which runs `ew fmt` without importing other namespaces (faster + less interference) ([`8900826`](https://github.com/educationwarehouse/edwh/commit/8900826dd193586e3f6d4fdd241b59a3194e4bd9))
* **cli:** Add CLI flags to selectively disable task imports ([`449e834`](https://github.com/educationwarehouse/edwh/commit/449e8349965190a5c2e7ff3d4dad3154d590eb5a))

## v0.58.1 (2025-06-19)

### Fix

* Allow `--file` as alias for `--directory` and start on `--ioptimize` (but ruff --fix F401 doesn't work right now) ([`f6aede8`](https://github.com/educationwarehouse/edwh/commit/f6aede82d2dc0420eb9180d06add3af557b4b21d))

## v0.58.0 (2025-06-19)

### Feature

* **publish:** First git pull (+ check for unstaged changes) to prevent annoying tag conflicts ([`9f4ead0`](https://github.com/educationwarehouse/edwh/commit/9f4ead00773da14745e50ac37691ab3cb96679c3))

### Fix

* **build:** Look for any .in files, not just ones named requirements.in (useful in whitelabel) ([`df9b2a5`](https://github.com/educationwarehouse/edwh/commit/df9b2a507aa06a38f2faddda1674ba58f03cb91f))

## v0.57.3 (2025-05-02)

### Fix

* Bump version of `ruff` ([`4f25a6f`](https://github.com/educationwarehouse/edwh/commit/4f25a6f7849193c766e4b5c9896ade62dcf471f6))

## v0.57.2 (2025-04-18)

### Fix

* Bump `ruff` patch version ([`7b3c1a6`](https://github.com/educationwarehouse/edwh/commit/7b3c1a60b22547a4d903bdf8eff801799ae2aecb))

## v0.57.1 (2025-04-04)

### Fix

* Print('$ edwh ...') line only after actually printing a log line ([`02bc5ae`](https://github.com/educationwarehouse/edwh/commit/02bc5aea96c59ddbf25d5bd82cf960e32fb28821))

## v0.57.0 (2025-04-03)

### Feature

* **up:** Use `edwh up --wait -s <service>` to wait for service(s) to be healthy ([`cad79ea`](https://github.com/educationwarehouse/edwh/commit/cad79ea8bbe31792a9504d5382a34399a73a1cdf))

## v0.56.11 (2025-04-03)

### Fix

* Pin dependencies at major level to prevent breaking changes leaking through (e.g. termcolor v3) ([`5602de4`](https://github.com/educationwarehouse/edwh/commit/5602de4d213068a3fa6a60703dc6cc1b16d847db))

## v0.56.10 (2025-03-21)

### Fix

* Allow `1`/`t`/`y` as boolish values (e.g. for `include_celeries_in_minimal`) ([`61d1857`](https://github.com/educationwarehouse/edwh/commit/61d1857dd32c85dc813c860bf32cdb1324fe9388))

## v0.56.9 (2025-03-17)

### Fix

* Improved `help` parsing (for custom flags) + try to load help from docstring if not explicitly available ([`94430b7`](https://github.com/educationwarehouse/edwh/commit/94430b7fac4e2dc79d65b72ea78c5e8cd876958b))


## v0.56.8 (2025-03-14)

### Fix

* Bump ruff to 0.10 ([`d262f65`](https://github.com/educationwarehouse/edwh/commit/d262f65894a3a57139d3ddede3af5aa85c2300fa))


## v0.56.7 (2025-03-13)

### Fix

* If old-school task is used (instead of improved_task) - hookable does not exist. Conservatively set hookable to False in that case, preventing unexpected cascading ([`6ebd509`](https://github.com/educationwarehouse/edwh/commit/6ebd5096e9c14269b0f229f8492ce5dc0e5bf43a))

## v0.56.6 (2025-03-13)

### Fix

* Remove debug return in `setup` and use `@task()` with parens for better typing support. ([`5a51d2c`](https://github.com/educationwarehouse/edwh/commit/5a51d2cf49f7f77de40ad5979533a8022546b978))
* Allow subtasks to define `hookable=False` and prevent being cascaded from core ([`7824e12`](https://github.com/educationwarehouse/edwh/commit/7824e1236119472bd090290aaa445be69357ab2e))
* Make `ctx['result']` work with fabric (`.get` is a file operation instead of a dict get in fabric) ([`1f5a11f`](https://github.com/educationwarehouse/edwh/commit/1f5a11f74676f79e1f2e1db4c70a2a31c144b3b6))

## v0.56.5 (2025-03-07)

### Fix

* Warn on subtask failure instead of crashing ([`91ad82d`](https://github.com/educationwarehouse/edwh/commit/91ad82d2f7c7b615626133f964d13937a8182e6c))

## v0.56.4 (2025-03-07)

### Fix

* Make `up` return the requested services for use by local `up` ([`de2198d`](https://github.com/educationwarehouse/edwh/commit/de2198dbc89c4aa215340f023ff641494ce461c3))

## v0.56.3 (2025-03-07)

### Fix

* Allow cherry-picking argument names in cascading hookable tasks; provide return value data via `context['result']` ([`e6257b1`](https://github.com/educationwarehouse/edwh/commit/e6257b18c5d224025494152484f49dca5a179fd2))

### Documentation

* Explained `improved_task` ([`0a7c679`](https://github.com/educationwarehouse/edwh/commit/0a7c679986a546e6ef673e998f5f59f44eaaf49c))

## v0.56.2 (2025-03-07)

### Fix

* Undo commit removing arguments since cascading functions can now simply choose to ignore them ([`73b03c6`](https://github.com/educationwarehouse/edwh/commit/73b03c61ff0360bd8d6af861d97a84829522f415))
* Cascading tasks can choose to inherit the hookable arguments or ignore them. `inspect` is used to determine whether the arguments should be passed or not. ([`4823300`](https://github.com/educationwarehouse/edwh/commit/48233003f88f5c709fe84c7ef9d827d4b59fd6d7))
* Remove old unused arguments to `setup` (so local setup doesn't need to have that in their signature) ([`fec8587`](https://github.com/educationwarehouse/edwh/commit/fec8587d327b27526ef47a4c003f3ec230456c18))

## v0.56.1 (2025-03-07)

### Fix

* Specify `devdb` as official plugin ([`ecd6467`](https://github.com/educationwarehouse/edwh/commit/ecd64672bf4b3d24c5f798b19f0fc4e379d529c8))

## v0.56.0 (2025-03-07)

### Feature

* Add `hookable` to more tasks (stop, down, version, clean) ([`0603a1e`](https://github.com/educationwarehouse/edwh/commit/0603a1ec8a2d5a619ae1cc6492f91dc2a2e03670))
* Add `hookable: bool` option to `@task`, which makes the existing logic in `up` and `setup` for local tasks: ([`35d33ad`](https://github.com/educationwarehouse/edwh/commit/35d33ad7b948e2fa2ad676f924599deab62f5a53))

## v0.55.0 (2025-03-06)

### Feature

* `check_env` default now accepts a callback function for lazy evaluation ([`562e098`](https://github.com/educationwarehouse/edwh/commit/562e0986217ffd18d8697097c36745c12af685fc))

## v0.54.1 (2025-03-03)

### Fix

* **self-update:** Make `-f` and `--fresh` an alias for `--no-cache` ([`7fd6971`](https://github.com/educationwarehouse/edwh/commit/7fd6971215657938846439219079fec46fde48bf))

## v0.54.0 (2025-03-03)

### Fix

* **inspect:** Allow both a container id OR a human name to be passed to `inspect-health` ([`11629ec`](https://github.com/educationwarehouse/edwh/commit/11629ecb00fb9bfe527f9ec259aa39859a652075))
* `healths` deals with multiple container replica's now. ([`3817884`](https://github.com/educationwarehouse/edwh/commit/38178841ea0af34ef510b2c92bcc04d961a267e4))
* **health:** Add extra level for stopped so it doesn't count as DEGRADED (because it's different) ([`4530573`](https://github.com/educationwarehouse/edwh/commit/45305732af6cd335aa06ef76ad39496195d42352))

## v0.53.8 (2025-03-03)

### Fix

* --short now doesn't return None, instead it will check most things to run individual so it can work alongside with --ports ([`2dd8aba`](https://github.com/educationwarehouse/edwh/commit/2dd8aba4c5381e720f411bc821428156235d4aa1))

### Fix

* Use compose bake if available for better performance ([`6640f75`](https://github.com/educationwarehouse/edwh/commit/6640f751700e15b95401d32194a2173069a4d36c))

## v0.53.7 (2025-02-27)

### Fix

* Refactor structure to export more helper functions ([`b661ff4`](https://github.com/educationwarehouse/edwh/commit/b661ff4f49461e3878ed726b4bae62661e4f0f29))

## v0.53.6 (2025-02-21)

### Fix

* Ensure uvenv and python-semantic-release<8 is installed when doing `plugin.release` ([`153e613`](https://github.com/educationwarehouse/edwh/commit/153e6131ed35053421dd7679d3941e72b0d0a45c))

## v0.53.5 (2025-02-20)

### Fix

* Pin ruff to specific version, so its updates are linked to edwh updates, ensuring self-update also updates ruff ([`603d4b4`](https://github.com/educationwarehouse/edwh/commit/603d4b4c51da60d7839adef634e7b7ffda06d013))

## v0.53.4 (2025-02-06)

### Fix

* `edwh plugin.remove all` ([`c59c1f1`](https://github.com/educationwarehouse/edwh/commit/c59c1f166cf1720310931094b1590343f7bcd82b))

## v0.53.3 (2025-02-04)

### Fix

* **fmt:** Use `find_ruff_bin` instead of expecting ruff to be in PATH ([`9eefdf4`](https://github.com/educationwarehouse/edwh/commit/9eefdf406810c933be543d263f3ad053beb84353))

## v0.53.2 (2025-01-13)

### Fix

* **health:** When wait is done, print empty line to cleanup print traces ([`e8098ae`](https://github.com/educationwarehouse/edwh/commit/e8098ae14643e7144666be1a40ecbdbb94242e00))

## v0.53.1 (2025-01-09)

### Fix

* Differentiate between exited with exit code 0 (degraded/yellow) or higher (red/critical) ([`bcdb7d7`](https://github.com/educationwarehouse/edwh/commit/bcdb7d7f44d093319a8d7c196d71e16e882c4863))

## v0.53.0 (2025-01-09)



## v0.53.0-beta.1 (2025-01-07)

### Feature

* **health:** Add optional 'health' section to .toml (as a default for `edwh health`) ([`b6e676d`](https://github.com/educationwarehouse/edwh/commit/b6e676da2b0cb185348b988fc4ad90afb01b9842))
* Add `--wait` to `edwh health` to wait for containers to be done starting (up/dead) ([`37d4938`](https://github.com/educationwarehouse/edwh/commit/37d4938650aabfc57dcd9f9e4c2773ff0fea138e))
* Colored printing on `edwh health`, include failing reason by default (hide with `-q`) ([`6120e03`](https://github.com/educationwarehouse/edwh/commit/6120e03cb730bdc295989ae2cac010c3b9dc13de))
* **health:** Load docker health statuses ([`a64b5b3`](https://github.com/educationwarehouse/edwh/commit/a64b5b3fd8e249ebc8094fd2331c29ce17433294))
* Started on `edwh health` command which works with docker (compose) health checks ([`20d041b`](https://github.com/educationwarehouse/edwh/commit/20d041ba18daacf3e90f67bddee29f16ca54a510))

### Fix

* Improved unicode output in `inspect-health` ([`b55a46d`](https://github.com/educationwarehouse/edwh/commit/b55a46d205b97b41df655bdb1dc337b5f5d8177b))
* **health:** Don't crash if all containers are down ([`9626819`](https://github.com/educationwarehouse/edwh/commit/9626819258b12660152a925f9f427db602808f53))
* Call `inspect()` with `docker compose ps -aq` to prevent issues when docker containers stop in between invoke commands ([`0c93d27`](https://github.com/educationwarehouse/edwh/commit/0c93d27a3cb15b6828ec4b9f9e080d4e62942a96))
* **health:** Simplify and increase performance by doing 1 docker inspect on multiple containers instead of multiple separate inspects ([`4b93430`](https://github.com/educationwarehouse/edwh/commit/4b934307a8431c07e8520d210840a01703203491))
* Skip health status if it is None (e.g. when container is removed during check) ([`2db3fa7`](https://github.com/educationwarehouse/edwh/commit/2db3fa7b8aea6c9b7d346576bec9addc2ce4a6bd))
* Report containers as dead if they're missing; + pty on ew up for nicer rendering ([`915a5a1`](https://github.com/educationwarehouse/edwh/commit/915a5a17d57d729f1faa4f0d2615f523b1b84f5e))
* Don't force list for `flags`, also support e.g. tuple ([`39c0caa`](https://github.com/educationwarehouse/edwh/commit/39c0caadbd863797efdca84bcb68fac6c58dd8e9))

## v0.52.2 (2024-11-29)

### Fix

* Add `__main__.py` so the program can be run via `python -m edwh`, which is needed to make the pycharm debugger work properly ([`eb2e981`](https://github.com/educationwarehouse/edwh/commit/eb2e98156412cfb92c6cca08b363cab35d564b80))

## v0.52.1 (2024-11-28)

### Fix

* **fmt:** Show stderr on `ew fmt` errors ([`408ea6c`](https://github.com/educationwarehouse/edwh/commit/408ea6c9fc660c3cdcf884fa3bcdeecd401b4158))

## v0.52.0 (2024-11-28)

### Feature

* Allow passing `--select <code>` and `--fix` to lint/ruff ([`97a0ece`](https://github.com/educationwarehouse/edwh/commit/97a0ece194cd05cdd2ee93e57ef25cfa41893f07))
* Add `edwh lint` subcommand, also based on `ruff` ([`76a468f`](https://github.com/educationwarehouse/edwh/commit/76a468fa6d707e94ffd6a089ac17c3761a9fd00e))
* Replace `su6[black,isort` with `ruff` for `edwh fmt` ([`ff89c28`](https://github.com/educationwarehouse/edwh/commit/ff89c2878833ed4ccdb4fd18b0689b93c718a4e2))

### Fix

* Replaced old `ansi` prints with `termcolor` ([`6d44fec`](https://github.com/educationwarehouse/edwh/commit/6d44fecd5795f3ac9178c00f6b2abeebd9bfd835))
* Change `No 'edwh' packages found. That can't be right` into a yellow print instead of an exception, so the script still continues instead of showing a traceback ([`40d5d66`](https://github.com/educationwarehouse/edwh/commit/40d5d66c83f228fc1453d46ee8111afcbf4bd44d))
* Path.glob yields paths instead of strings ([`a98dacc`](https://github.com/educationwarehouse/edwh/commit/a98daccbfca0383e650dd996da19c7e6e0ebb441))
* Add `psa` alias for `ps-all` ([`e2ff06d`](https://github.com/educationwarehouse/edwh/commit/e2ff06d8ed3bffedcdae64b479f6d1d8455f021b))
* Yarl was replaced with yayarl in the dependencies but not in the plugin.py code ([`73ce7f5`](https://github.com/educationwarehouse/edwh/commit/73ce7f51a2d34855f21292a21b9ae62a99368e2a))
* Improved output for `ew fmt/ew lint` ([`d7f9523`](https://github.com/educationwarehouse/edwh/commit/d7f9523ebd79cce3502fb4199cf6f23e16320552))

## v0.51.3 (2024-11-22)

### Fix

* Still run local tasks.py:setup if docker-compose.yml is missing ([`dbf6748`](https://github.com/educationwarehouse/edwh/commit/dbf6748e53691fa99d646d761c9ba9222a95fcd5))
* (Y/n) -> [Yn] for consistency ([`e288263`](https://github.com/educationwarehouse/edwh/commit/e288263bd387c9346737cb3eaad1a18c46f2de43))

## v0.51.2 (2024-11-18)

### Fix

* Don't crash when accepting default if allowed_values is set ([`305d521`](https://github.com/educationwarehouse/edwh/commit/305d5215de8ea952fb6efd2e1a708ffc5e81944a))

## v0.51.1 (2024-11-18)

### Fix

* Rename new `check_env` options to be more clear ([`df95292`](https://github.com/educationwarehouse/edwh/commit/df952920558a1de9a415511b65bf550132a6030c))

## v0.51.0 (2024-11-15)

### Feature

* Added valid_input to check_env ([`c44783b`](https://github.com/educationwarehouse/edwh/commit/c44783bb1381a10c77662d7328c564fe0597e988))
* Added use_default to check_env ([`e9718d2`](https://github.com/educationwarehouse/edwh/commit/e9718d2a91554c7b6d89fcb3256fd767363fc67b))

### Fix

* Allow custom local dependencies in ~/.config/edwh ([`c2ff06e`](https://github.com/educationwarehouse/edwh/commit/c2ff06e040faca2d9605f36f47a8869827a861cb))

## v0.50.0 (2024-11-14)

### Feature

* Allow setting `--dice` for `edwh generate-password` ([`05ce574`](https://github.com/educationwarehouse/edwh/commit/05ce574d8b3abcecc6985dc9ba1f870e1c672431))

### Fix

* Add missing dependency; document what each depenency does ([`3287767`](https://github.com/educationwarehouse/edwh/commit/3287767d7c6a8f1260523d540baf566327f388df))
* If state_of_development is empty, show a warning instead of error ([`066d0fc`](https://github.com/educationwarehouse/edwh/commit/066d0fc3d035a5337f65b353013a3a448f773949))

## v0.49.1 (2024-11-12)

### Fix

* **sleep:** '1' ended immediately, so added 'flush' to print instantly instead of waiting for buffer and added 'sleeping 0 seconds' for sanity ([`dfd0a96`](https://github.com/educationwarehouse/edwh/commit/dfd0a96fb7a02981ff4054988719cbd91737ec7a))

## v0.49.0 (2024-11-07)

### Feature

* Add `ew ps-all` to show all active docker projects. Used as a fallback for `ew ps` when you're not in a docker compose project ([`9461193`](https://github.com/educationwarehouse/edwh/commit/9461193e47fcf8c88d15dbc11d4ec85652e89913))

## v0.48.2 (2024-10-28)

### Fix

* Allow `-f/--force` for `migrate` to remove existing flags ([`3a07740`](https://github.com/educationwarehouse/edwh/commit/3a07740ed3257f6a83dbab4e704995666452e2ab))

## v0.48.1 (2024-10-10)

### Fix

* Doing ctrl-c during sudo will not bypass it anymore ✨ ([`6f66529`](https://github.com/educationwarehouse/edwh/commit/6f66529b89cc1b1385133f57fb79c5a1a35af663))

## v0.48.0 (2024-10-08)

### Feature

* Added migrations task, so you could get the 'migrate --list' command in edwh. ([`b8d0bb7`](https://github.com/educationwarehouse/edwh/commit/b8d0bb70b1cee0f9fc9f36b399771aec5355e1ba))

### Fix

* Removed the 'migrate --list' file, because it served no purpose ([`f7bcf97`](https://github.com/educationwarehouse/edwh/commit/f7bcf978d4a9b0249cae1ce48e660ba36f8f78f3))
* Removed migrations printing it's content a second time. ([`7d1f15a`](https://github.com/educationwarehouse/edwh/commit/7d1f15ab0caaf7ff64e35963a1dcf92d6fe356c3))

## v0.47.0 (2024-09-20)

### Feature

* `ew fmt` to format code prettily ([`e15258d`](https://github.com/educationwarehouse/edwh/commit/e15258de4ee7b682d1603db49170c07ea1a8dddf))

### Fix

* **logs:** Wait 100ms if no new log data was found, to preserve cpu ([`064b409`](https://github.com/educationwarehouse/edwh/commit/064b409fdef0fc59f9954574609600c16d850fff))
* Pass -f to self-update as --no-cache ([`7ba6b41`](https://github.com/educationwarehouse/edwh/commit/7ba6b4180f8ca6fba8de3e3dc1f17775c152c387))

## v0.46.7 (2024-09-17)

### Fix

* Allow -f for plugin.update to run with cleaned cache (-> more chance for updating) ([`bc67a5d`](https://github.com/educationwarehouse/edwh/commit/bc67a5d00e020308427d3449cf5fc7d54639e197))

## v0.46.6 (2024-09-17)

### Fix

* Ew sleep functie heeft nu een afteller in de terminal ([`70af754`](https://github.com/educationwarehouse/edwh/commit/70af754cd8a58cb6a5e73669b3f4e545a3751f1c))

## v0.46.5 (2024-09-13)

### Fix

* Don't crash on tail if missing file ([`f07d62c`](https://github.com/educationwarehouse/edwh/commit/f07d62ce801b074c6a5f11e466647892a03788a2))

## v0.46.4 (2024-09-13)

### Fix

* Exit on sudo failure because why bother continuing ([`b14c4ab`](https://github.com/educationwarehouse/edwh/commit/b14c4ab43b610cdca813ce6f49f90ff50c46c7a7))

## v0.46.3 (2024-09-12)

### Fix

* If docker log isn't valid json for some reason, just continue instead of crashing ([`8ddfdca`](https://github.com/educationwarehouse/edwh/commit/8ddfdca2f3e064f49c2a63c28ba18d021e5ee43a))

## v0.46.2 (2024-08-23)

### Fix

* `ew discover` broke again ([`0451ed8`](https://github.com/educationwarehouse/edwh/commit/0451ed8e5056b8a6fc84bc788322fe2b44767c66))

## v0.46.1 (2024-08-09)

### Fix

* If container goes down (ew down, not stop or restart) -> stop watching logs (because nothing new will appear) ([`e398498`](https://github.com/educationwarehouse/edwh/commit/e3984988e72fac399d53c8fa57c33d6f303703ba))

## v0.46.0 (2024-08-09)

### Feature

* Improved personal task loading, add add_alias helper function ([`d61d6ba`](https://github.com/educationwarehouse/edwh/commit/d61d6ba8895ffc4d8adff1ac14100338dc64fcde))

### Documentation

* Explained all the ways commands can be added to edwh ([`57282ec`](https://github.com/educationwarehouse/edwh/commit/57282ec8d821014a335536a4629bc60dfe3c3823))

## v0.46.0-beta.1 (2024-08-08)

### Feature

* Allow defining personal tasks in ~/.config/edwh. Removed `sul` because it was a personal task ([`4a65638`](https://github.com/educationwarehouse/edwh/commit/4a6563850ad952392c96fe76e8625f9c31f7d5db))

## v0.45.1 (2024-07-30)

### Fix

* **wipe:** Don't crash on unnamed mounts, just skip those ([`3812245`](https://github.com/educationwarehouse/edwh/commit/381224547bb9717b259918a009d38ed046827766))

## v0.45.0 (2024-07-26)

### Feature

* Allow `-s db` to up/log/... all db services ([`0299010`](https://github.com/educationwarehouse/edwh/commit/029901080009271d57ca46f132594ae2cb247ee6))

## v0.44.3 (2024-07-26)

### Fix

* **setup:** Allow selecting no database containers ([`4f002ee`](https://github.com/educationwarehouse/edwh/commit/4f002eeb3789d2730c1d5be7a3e6fb5dd7f72fe9))

## v0.44.2 (2024-07-26)

### Fix

* Make `ew discover` work again ([`122a8d1`](https://github.com/educationwarehouse/edwh/commit/122a8d19626c89c54e7855c369d2ba6fe12d2134))

## v0.44.1 (2024-07-25)

### Fix

* Shut up annoying cryptography deprecation warning (from paramiko) ([`1fa94db`](https://github.com/educationwarehouse/edwh/commit/1fa94dbe265e92a5a58cd6fb3e0ca076068f8a70))

## v0.44.0 (2024-07-23)

### Feature

* Add `ew sleep <n: int>` ([`40bffbf`](https://github.com/educationwarehouse/edwh/commit/40bffbfb8554f3100179ff8d82b52273c5e4554a))

## v0.43.10 (2024-07-18)

### Fix

* Also include typing_extensions in 3.12 ([`4390446`](https://github.com/educationwarehouse/edwh/commit/4390446f37e8d5fabc2be72c26c4085b97984c84))

## v0.43.9 (2024-07-16)

### Fix

* Don't auto-up after wipe-db, use `edwh wipe-db migrate up` instead ([`7adce33`](https://github.com/educationwarehouse/edwh/commit/7adce33fb00b3bee1b42e85fd63942ca559d2f42))

### Documentation

* Added comment explaining exit behavior for log ([`c0eb10e`](https://github.com/educationwarehouse/edwh/commit/c0eb10e2e0ef0a16b30a1c104e8eb0022dcd5021))

### Performance

* Use tuple instead of list for unmutable iterator ([`82feabb`](https://github.com/educationwarehouse/edwh/commit/82feabb5f70b6f8bb934d967353753af4b2b979f))

## v0.43.8 (2024-07-16)

### Fix

* `ew logs` now also works for containers that are shut down (e.g. migrate) ([`794141e`](https://github.com/educationwarehouse/edwh/commit/794141e2f345d2a77cad9b75f27b57d1d91e64bb))

## v0.43.7 (2024-07-15)

### Fix

* Show more readable error if trying to log shut down services ([`c02ef97`](https://github.com/educationwarehouse/edwh/commit/c02ef97fdc3689f7740c86c2543ba62fbe8227e1))

## v0.43.6 (2024-07-12)

### Fix

* `edwh plugin.add True` -> not_all_installed should be optional str instead of bool ([`ae85912`](https://github.com/educationwarehouse/edwh/commit/ae85912d46f642cfb3477c622c99c9aed4e3facb))

## v0.43.5 (2024-07-12)

### Fix

* **setup:** Reload config after setup to prevent 'missing key' error immediately after asking for that exact key ([`8cdc16e`](https://github.com/educationwarehouse/edwh/commit/8cdc16e3f42883b979cf66370b222e3c90ff6e3b))

## v0.43.4 (2024-07-12)

### Fix

* **sul:** Construct command for c.sudo instead of elevate which runs everything as root ([`c57c87a`](https://github.com/educationwarehouse/edwh/commit/c57c87a93ab762fd0724840c6976b0d0c2cdca35))

## v0.43.3 (2024-07-12)

### Fix

* `service` as tuple broke single -s!!! ([`39c766d`](https://github.com/educationwarehouse/edwh/commit/39c766dcdb26f4a5d1d144bb79ddfcefaaad5c8e))

## v0.43.2 (2024-07-12)

### Fix

* A single `-s` should NOT  be splitted into characters!!! ([`281bfc5`](https://github.com/educationwarehouse/edwh/commit/281bfc509a3e97f2ae7f3e4f0c8ab9528ef669d3))

## v0.43.1 (2024-07-12)

### Fix

* Improved typing (mypy) ([`41a2395`](https://github.com/educationwarehouse/edwh/commit/41a239547b6a828f638681fe36f3081f68a39d1e))

## v0.43.0 (2024-07-12)

### Feature

* Fabric_read and fabric_write helpers to work with remote files ([`9b9893d`](https://github.com/educationwarehouse/edwh/commit/9b9893dc1f235378081faf5c69f54aee724ff4d3))
* Added `edwh sul` shortcut command ([`bf29e86`](https://github.com/educationwarehouse/edwh/commit/bf29e86efb9ea97f17c1cc98f2cc08e987fe84fd))
* Allow choosing services as 'db', so wipe-db knows which volumes to purge ([`f92d285`](https://github.com/educationwarehouse/edwh/commit/f92d28506d5bbba71b98d4b0052aa027c3e03b8c))
* **log:** Show current command ([`1e5308c`](https://github.com/educationwarehouse/edwh/commit/1e5308c30d6aad986b1e8f655bd5234c6744c8e9))
* Included 'improved logging' functionality in the regular 'logs' subcommand, changed naming of options ([`528edab`](https://github.com/educationwarehouse/edwh/commit/528edab307061974ce2f41f15a195c48bcc1f7b8))
* Added filtering to improved log ([`101032b`](https://github.com/educationwarehouse/edwh/commit/101032be40d06b105318bcc2c75466405c807492))
* In progress on improved logging ([`3f85f27`](https://github.com/educationwarehouse/edwh/commit/3f85f276d331277156f2b324c556f2fb2f54d29a))
* Copied omgeving wipe-db ([#1971](https://github.com/educationwarehouse/edwh/issues/1971)) ([`506bad9`](https://github.com/educationwarehouse/edwh/commit/506bad92e0cfd3fabde932a34463d51d2bbb4f08))

### Fix

* Remove deprecated extendable_fab which broke named args ([`3c337c0`](https://github.com/educationwarehouse/edwh/commit/3c337c0fed143a46506bfd1b5168ed65c23f2338))
* **files:** Make fabric_ file functions also work locally (incl throw and parents options) ([`5d0e655`](https://github.com/educationwarehouse/edwh/commit/5d0e65529611e0359915a3715c1cd21cb5411374))
* **files:** Make fabric_ file functions also work locally ([`372693a`](https://github.com/educationwarehouse/edwh/commit/372693acda0ae2aa6e922abed9f3cd19a8ebe9f8))
* **fab.file:** Improved remote file handing ([`807ca1f`](https://github.com/educationwarehouse/edwh/commit/807ca1fd204297311869d7277e148693391d3628))
* **log:** Since and default services (-> from 'log' section in toml) ([`54c064e`](https://github.com/educationwarehouse/edwh/commit/54c064e8186e64c0cff524dfc19d9683aa0646ba))
* **log:** Id and service mapping was incorrect ([`d2d9a9d`](https://github.com/educationwarehouse/edwh/commit/d2d9a9dc2344f6715e1ad04b2f559fb8e715dd09))
* Improved --since ([`76a1ab6`](https://github.com/educationwarehouse/edwh/commit/76a1ab649c740f0c82ccc7ff50567dbcad502537))
* Since+filter improvements for logging ([`3a33bf7`](https://github.com/educationwarehouse/edwh/commit/3a33bf74c0839ec32cae241b9ee75e1c4c86b201))
* **ps:** Actually show full command when using -f + add -a/---all like `dc ps -a` ([`68b5459`](https://github.com/educationwarehouse/edwh/commit/68b5459f8ef654972e47fc0c087b17fd71c938cd))
* **up:** Service is a list[str], not a single one ([`88abd66`](https://github.com/educationwarehouse/edwh/commit/88abd66945c107e7ae1f69dc096181e325cd329e))
* Better type hints, split string into args ([`ebfaddc`](https://github.com/educationwarehouse/edwh/commit/ebfaddce24d1cd30851a5350c8b4fb95d377112c))

### Documentation

* Replace uvx with uvenv ([`b36fc96`](https://github.com/educationwarehouse/edwh/commit/b36fc96ceb7671154b08fbd83965d4e19a7df4a6))

## v0.42.3 (2024-06-20)

### Fix

* Improved wipe-db (don't crash on missing pg-stats, faster start with `dc create` instead of `start + stop`) ([`b03043c`](https://github.com/educationwarehouse/edwh/commit/b03043cd54af4108069d9fe2e0135593439b5c88))

## v0.42.2 (2024-06-20)

### Fix

* Expose 'get_hosts_for_service' via edwh.tasks again ([`1733a08`](https://github.com/educationwarehouse/edwh/commit/1733a08fe6f4648ed9132ce34364d0286e112469))

## v0.42.1 (2024-06-20)

### Fix

* `ew ew` subcommand that does nothing, for improved command chaining #2352 ([`d8e163d`](https://github.com/educationwarehouse/edwh/commit/d8e163d05b9f29fa6d0f2d5f289ba5f0b286815f))

## v0.42.0 (2024-06-20)

### Feature

* More robust wipe-db functionality ([`3222344`](https://github.com/educationwarehouse/edwh/commit/322234467a3bead2e428e0176b25ff5df48b4e5f))
* Copied omgeving wipe-db ([#1971](https://github.com/educationwarehouse/edwh/issues/1971)) ([`d261d3f`](https://github.com/educationwarehouse/edwh/commit/d261d3fc3136b152ae21f439645c5a4be8a3422a))

### Fix

* Improved `ew build` by setting it to pty -> nice docker build in colors ([`70b9123`](https://github.com/educationwarehouse/edwh/commit/70b912309b0cdac6bfb5ba74861361770124fe03))
* **up:** Service is a list[str], not a single one ([`e5e9cee`](https://github.com/educationwarehouse/edwh/commit/e5e9ceee4e9d3cfc347392f3dbf3423134aac0fe))
* Better type hints, split string into args ([`e96b94c`](https://github.com/educationwarehouse/edwh/commit/e96b94c9952d660d569025c436824407ed82a2be))

## v0.41.4 (2024-05-31)

### Fix

* `ew logs` should look at the log section of config, not minimal ([`3f10042`](https://github.com/educationwarehouse/edwh/commit/3f10042fe77192084880c9f25af575cc00f1bc6d))

## v0.41.3 (2024-05-06)

### Fix

* Require plumbum ([`ad6599b`](https://github.com/educationwarehouse/edwh/commit/ad6599be64e9acb1fe144a3848e9049c08725d68))

## v0.41.2 (2024-04-15)

### Fix

* **self-update:** Allow --no-cache ([`a51271a`](https://github.com/educationwarehouse/edwh/commit/a51271ab8146d0a0b23a98d432a05c78c2656a90))

## v0.41.1 (2024-04-15)

### Fix

* **config:** Write celeries=False if no celery services available ([`40993fe`](https://github.com/educationwarehouse/edwh/commit/40993fec34ee0512a77676623569e0be754c629a))

## v0.41.0 (2024-04-12)
### Feature
* Add json output option for settings ([`defb609`](https://github.com/educationwarehouse/edwh/commit/defb6092b0ba6473d9a9d1a189810f7df4de5daa))

### Documentation
* Added more info to `plugin.add` ([`9205cee`](https://github.com/educationwarehouse/edwh/commit/9205ceebbad871005682f362bfc9198bc2095398))

## v0.40.6 (2024-04-12)

### Fix

* **plugins:** Pypi changed quotes from ' to " for extras ([`50a6b11`](https://github.com/educationwarehouse/edwh/commit/50a6b115c549e3f09ac9182facf46674de0a8f8f))
* Work in progress on `ew build` (depends on state-of-development flag to be implemented) ([`db54ef9`](https://github.com/educationwarehouse/edwh/commit/db54ef9e7047671de4f71d32f801c9b093e18a86))

## v0.40.5 (2024-04-12)

### Fix

* Make change-config more user-friendly ([`c451f81`](https://github.com/educationwarehouse/edwh/commit/c451f819dfdb55e38b16f6236cab69eb22442483))

## v0.40.4 (2024-04-12)

### Fix

* Make require_sudo return a bool ([`b33e1ac`](https://github.com/educationwarehouse/edwh/commit/b33e1ac7711e84acc6b82f14ba32aeaa5628c322))
* Add 'change-config' subcommand to change the values in .toml ([`a3f64b1`](https://github.com/educationwarehouse/edwh/commit/a3f64b1a4d64540cf0dad6b4582c34a77e6bf0b4))

## v0.40.3 (2024-03-19)
### Fix
* Automatically set 'services' to 'discover' if not set ([`6b29542`](https://github.com/educationwarehouse/edwh/commit/6b295421f6a9a29322c97fe10923890c698198ed))

## v0.40.2 (2024-03-19)
### Fix
* Don't crash on services without celery (-> include_celeries_in_minimal missing) ([`c727837`](https://github.com/educationwarehouse/edwh/commit/c727837ab792ea88368b55e69fc0eabfa246baa6))

## v0.40.1 (2024-03-15)
### Fix
* Replace raw uv bin with python -m uv because that will use the right environment ([`dc2e9f6`](https://github.com/educationwarehouse/edwh/commit/dc2e9f65bc595446a89a10fd05fb36fe2a8d1f8a))

## v0.40.0 (2024-03-15)
### Feature
* **#2043:** Use `uv` in self-update and plugin.add for blazingly fast performance :rocket: ([`6adb1d3`](https://github.com/educationwarehouse/edwh/commit/6adb1d38b666e9b51106c1b92418b9894f3ba991))

## v0.39.2 (2024-03-15)
### Fix
* **check_env:** Set default of `toml_path` to None so you don't get a warning when not explicitly stating toml_path ([`775957b`](https://github.com/educationwarehouse/edwh/commit/775957b198fd911a428d116bd50bd2c506b97473))

## v0.39.1 (2024-03-15)
### Fix
* Introduce 'warn_once' so `Deprecated: toml_path (.toml is not used by check_env anymore.)` doesn't get spammed anymore ([`098b330`](https://github.com/educationwarehouse/edwh/commit/098b330f458795596818d14fae16f4eb43c51bc5))

## v0.39.0 (2024-03-15)
### Fix
* Don't crash on `ew ps` if no dc-file (there already is a warning beforehand); + docs ([`ecb9d02`](https://github.com/educationwarehouse/edwh/commit/ecb9d026401323e61a4af062d8d605045605fdab))

## v0.39.0-beta.2 (2024-03-12)
### Feature
* Functionality to clean w2p sessions (to speed up permisisons setup) ([`cc89b7f`](https://github.com/educationwarehouse/edwh/commit/cc89b7f00ade1c7ab8bea6dd740d19184278081a))

## v0.39.0-beta.1 (2024-03-12)
### Feature
* Add --verbose to setup to find out which permissions are so slow ([`dca6437`](https://github.com/educationwarehouse/edwh/commit/dca6437e604cb75445b8408c1dd2f53659f01d65))
* Implement default.toml, rename config.toml to .toml, allow aliases like "-s celeries" ([`498ef2b`](https://github.com/educationwarehouse/edwh/commit/498ef2b3eef70a96723fbce6a85f4700e13e0dbe))
* `ew version` now includes Python version ([`bf0d64e`](https://github.com/educationwarehouse/edwh/commit/bf0d64ec8aa3b4457289413fda02fbb1662ca1cf))

### Fix
* Better colored prints instead of warnings, don't crash on editable local/git install ([`e496a37`](https://github.com/educationwarehouse/edwh/commit/e496a3718444c527eb1afcf0876b34503c8fdb61))
* Strip / from services ([#1972](https://github.com/educationwarehouse/edwh/issues/1972)) ([`be476fd`](https://github.com/educationwarehouse/edwh/commit/be476fdfac034c91ff9ce5eb2910da427dc755a5))
* Improved 'setup': no 'discovery', don't query for celeries when no celeries were found ([`0147530`](https://github.com/educationwarehouse/edwh/commit/0147530c9c1d96fbeab887487076f672232fc35e))

## v0.38.3 (2024-02-19)


## v0.38.2 (2024-02-19)


## v0.38.1 (2024-02-19)
### Fix
* Added missing dependency (click) that was only installed for dev before ([`b2dae24`](https://github.com/educationwarehouse/edwh/commit/b2dae24d29e06b134aa71e96aeb7d6a19534183e))

### Documentation
* Added newline to docstring ([`9589bb0`](https://github.com/educationwarehouse/edwh/commit/9589bb05ae046cc921b73864618407a548e44cc3))

## v0.38.0 (2024-02-02)
### Feature
* **interactive-select:** Added a variant with a radio select instead of checkboxes ([`e33826b`](https://github.com/educationwarehouse/edwh/commit/e33826bc0bb27d9d18596f6785a13ecd10524a09))
* **checkboxes:** Options can now be a dict of value: label and you can add a list of pre-selected values via `selected=` ([`60001a9`](https://github.com/educationwarehouse/edwh/commit/60001a9428c37168190312d6bac034f08a27e44a))

## v0.37.1 (2024-01-29)
### Fix
* **process_env_file:** If .env file is missing, don't crash but simply return an empty dict ([`6a79a24`](https://github.com/educationwarehouse/edwh/commit/6a79a24e17d04d9141a6c7ee2b285a6e078a2dc0))

## v0.37.0 (2024-01-23)
### Feature
* **setup:** `require_sudo` and `interactive_selected_checkbox_values` functionality ([`404dd64`](https://github.com/educationwarehouse/edwh/commit/404dd643272206ed4ff4e51c4abc060e9ed0865b))

## v0.36.5 (2024-01-23)
### Fix
* **dc:** Dc_config now always returns a dict (possibly empty) instead of maybe None ([`3e0a7ab`](https://github.com/educationwarehouse/edwh/commit/3e0a7ab3c249393d2b28ad09c0df59c43c6e3e93))

## v0.36.4 (2024-01-23)
### Fix
* **dotenv:** Make `read_dotenv` work even with an invalid dc.yml ([`86aeee4`](https://github.com/educationwarehouse/edwh/commit/86aeee49bdb15d7da678e60e55f0f5df7c8fdde3))

## v0.36.3 (2024-01-23)
### Fix
* **discover:** Add humanize as regular dependency instead of extra ([`a0d49df`](https://github.com/educationwarehouse/edwh/commit/a0d49df2271dc20ef283c0574d154a8558ceaa1e))

## v0.36.2 (2024-01-18)
### Fix
* **help:** Include namespace in command example (pip.compile instead of compile) ([`de4a4b2`](https://github.com/educationwarehouse/edwh/commit/de4a4b29b03f8ba33649c6dea78f3587b9bc0e8c))
* --help BEFORE the subcommand because otherwise it doesn't always work ([`6546876`](https://github.com/educationwarehouse/edwh/commit/654687661b65bb977c7ad275b3647211b1423e7b))

### Documentation
* **changelog:** Merge prerelease and actual release changelogs ([`3ebb8c3`](https://github.com/educationwarehouse/edwh/commit/3ebb8c341f88018e7c4b61b4aec7a0776b40d14a))

## v0.36.1 (2024-01-18)
### Fix
* **help:** Deal with missing help docstring in plugin/namespace ([`b5e139f`](https://github.com/educationwarehouse/edwh/commit/b5e139f8bd98fff49186a122ddd3b3f1f959ad1a))
* **plugin:** Deal with unreleased plugins ([`a2cc4d5`](https://github.com/educationwarehouse/edwh/commit/a2cc4d5def1b0c141ddcc53ed707b6617900591d))

## v0.36.0 (2024-01-18)
### Feature
* Added `edwh[uptime]` extra and `edwh[server-plugins]` (because some plugins don't have to be installed on our servers, slowing them down) ([`57385b0`](https://github.com/educationwarehouse/edwh/commit/57385b01849d6dab929cefdb0140f689de0169fa))
* Added `edwh help` command to show help information about whole plugins/namespaces (instead of just --help for everything or one command) ([`f870f37`](https://github.com/educationwarehouse/edwh/commit/f870f374c478f8409ae4debd810e294ed0963840))

### Fix
* Don't show None if no global module docstring, just print an empty string instead ([`6081872`](https://github.com/educationwarehouse/edwh/commit/6081872d02863a2e0c47804414316ee1d4f7996e))

## v0.35.0 (2024-01-08)
### Feature
* `ew up` now also looks for local `up` tasks + shows related config ([`725db25`](https://github.com/educationwarehouse/edwh/commit/725db259fdf838724f4f1184d4c942e6e17d94fa))

### Fix
* Pass list of services to local `up` ([`65e8c11`](https://github.com/educationwarehouse/edwh/commit/65e8c119e0e056f30c246f65ba4e676751ebf341))
* Invoke 2.1 requires fabic 3.1+, not 3.0 ([`8c47abd`](https://github.com/educationwarehouse/edwh/commit/8c47abde702ac2165eb2b708e39246f3d2e832d4))
* Bump invoke so it should work with 3.12 ([`ba9421d`](https://github.com/educationwarehouse/edwh/commit/ba9421d6ad6fd023f871b0a341f53e40b287218e))

## v0.34.1 (2023-12-15)
### Fix
* Only one newline between env vars; require humanize since its imported in edwh ([`328e546`](https://github.com/educationwarehouse/edwh/commit/328e54666e00aef1b0da1308f120cf48c23db628))

## v0.34.0 (2023-12-15)
### Feature
* Added --as-json to ew discover ([`23e8e98`](https://github.com/educationwarehouse/edwh/commit/23e8e987a0f06de063f2ef1203e3b352d0a11f84))

## v0.33.2 (2023-11-06)
### Fix
* **plugin:** Don't crash if no new version to publish, but warn ([`6ccc166`](https://github.com/educationwarehouse/edwh/commit/6ccc16698569b5dbf75984ecae2b464f550b8866))

## v0.33.1 (2023-11-06)
### Fix
* **plugin:** Unless you say --yes, `release` now asks you to confirm a new publication ([`324886c`](https://github.com/educationwarehouse/edwh/commit/324886cbc40e2e31d97e6283993fee945a533676))
* **build:** Slightly improved UX for `ew build` + use get_task instead of import ([`53befa9`](https://github.com/educationwarehouse/edwh/commit/53befa9d7bd3ea42698c3d2416a9e30c789f24d8))

### Documentation
* Added more info about plugins ([`286d843`](https://github.com/educationwarehouse/edwh/commit/286d843425c859ab1290924299dff03bf1aa3ec0))
* Merge prerelease versions into actual release changes ([`3568750`](https://github.com/educationwarehouse/edwh/commit/3568750842e3bba8e05d6aaf1583cfddfb1372df))

## v0.33.0 (2023-11-06)
### Feature
* **plugin:** Ew plugin.publish alias for plugin.release ([`0d7ead7`](https://github.com/educationwarehouse/edwh/commit/0d7ead72edcced7b3a4965835d963644362bc48b))
* ew logs now accepts --errors and --ycecream to filter on y| and e| prefix ([`7209f89`](https://github.com/educationwarehouse/edwh/commit/7209f8970106e2415c5243d91aa87f7e440113cb))
* **self-update:** Allow --prerelease to update to beta versions ([`54fe3bf`](https://github.com/educationwarehouse/edwh/commit/54fe3bf5fde0104833df1bda743af28423a6d124))

## v0.32.0 (2023-11-03)
### Feature
*  `plugin.release` command ([`d00cd9b`](https://github.com/educationwarehouse/edwh/commit/d00cd9b7a0f50bdb9f559e9c3a501e202a327b4e))

### Fix
* `ew plugin.release` now properly prints the package name and new version! ([`50159b7`](https://github.com/educationwarehouse/edwh/commit/50159b7c41fdcf8432b31d89bcb82f8eef6113fe))

## v0.31.0 (2023-11-03)
### Feature
* Get_task en task_for_namespace functies om makkelijk andere tasks uit te kunnen voeren (ipv zelf met imports lopen klooien) ([`0faeda5`](https://github.com/educationwarehouse/edwh/commit/0faeda55eb6274965e2f68bbc9100d36ef571e43))

## v0.30.2 (2023-11-03)
### Fix
* **setup:** Don't crash if missing local tasks.py ([`0f80851`](https://github.com/educationwarehouse/edwh/commit/0f808516e4e826bd7b92aecb474397b1959f5925))

## v0.30.1 (2023-10-31)
### Documentation
* **pyproject:** Added whitelabel plugin as extra's ([`b4d493d`](https://github.com/educationwarehouse/edwh/commit/b4d493dca510dd38a8dd48cbfd02c32d68114708))

## v0.30.0 (2023-10-31)
### Feature
* Local tasks in the format `namespace.tasks.py` are now also loaded ([`3e0fdd8`](https://github.com/educationwarehouse/edwh/commit/3e0fdd8b87e4c4416c40116feb2457c37f15ec3c))

## v0.29.6 (2023-10-27)
### Fix
* Remove add_global_flag pt2 ([`b8e7648`](https://github.com/educationwarehouse/edwh/commit/b8e764891c9938c9a8f399597b5bd3ebae6f6c86))

## v0.29.5 (2023-10-27)
### Fix
* Removed add_global_flag because it breaks normal flags ([`f1fcda6`](https://github.com/educationwarehouse/edwh/commit/f1fcda6a1c8b13ff360b10bbc24e0f455692e129))

## v0.29.4 (2023-10-24)
### Fix
* **setup:** Hopefully no more infinite loop when calling `ew setup` in a newly installed omgeving ([`aa64c1c`](https://github.com/educationwarehouse/edwh/commit/aa64c1c5ec49fdc574b4ed46b17e88136a99ad2a))

### Documentation
* **changelog:** Prerelease changes onder patch release gezet ([`006358f`](https://github.com/educationwarehouse/edwh/commit/006358fd6964a4a4f0ee0965e5c54f82ab6f5bed))

## v0.29.3 (2023-10-05)
### Fix
* **dc:** Replace yaml.load(docker-compose.yml) with `docker compose config` to properly handle includes ([`8311aa4`](https://github.com/educationwarehouse/edwh/commit/8311aa4dd0c0085c122911bcf53c8cbc4deba40c))

### Documentation
* **changelog:** Remove prerelease changes and merge them to 0.29.2 ([`fef301e`](https://github.com/educationwarehouse/edwh/commit/fef301e6c94774fcab67dbc07e7e611589b9f3c6))

## v0.27.3-beta.1 (2023-10-05)
### Fix
* **dc:** Replace yaml.load(docker-compose.yml) with `docker compose config` to properly handle includes ([`8311aa4`](https://github.com/educationwarehouse/edwh/commit/8311aa4dd0c0085c122911bcf53c8cbc4deba40c))

## v0.29.2 (2023-10-03)

### Fix
* **ps:** Don't show all columns from docker compose ps ([`1d2bb19`](https://github.com/educationwarehouse/edwh/commit/1d2bb19b4357c6330e19f62a8a375064fcc72f06))

## v0.29.1 (2023-10-03)
### Fix
* 'hide' on ctx.run because we print the result afterwards; --short option to show less info ([`ae7dcf6`](https://github.com/educationwarehouse/edwh/commit/ae7dcf69e8086744ffef959c4502b74bfca0443e))

## v0.29.0 (2023-10-03)
### Feature
* Ew_self_update as a command to update self-update twice. ([`f280e82`](https://github.com/educationwarehouse/edwh/commit/f280e82328e1373e601fc2e653dff60a19555538))

## v0.28.2 (2023-10-03)
### Fix
* Newer black! & DOCKER_COMPOSE variable used. ([`64152db`](https://github.com/educationwarehouse/edwh/commit/64152db642dad9ec852c06e08dcf481fa102bf31))

## v0.28.1 (2023-10-03)
### Fix
* Fixed ctx.run for local usage ([`9d1612a`](https://github.com/educationwarehouse/edwh/commit/9d1612a877bf559287b544be0ff8ba6e82925c22))

## v0.28.0 (2023-10-03)
### Feature
* Discover added to iterate different hosts and find the services, mapped hostnames, ports, exposed ports and disk usage. ([`c6a91c7`](https://github.com/educationwarehouse/edwh/commit/c6a91c76ea6c49641f7f07dc19866077a91c0df3))

## v0.27.2 (2023-09-27)
### Fix
* Exclude all directories starting with venv ([`35859be`](https://github.com/educationwarehouse/edwh/commit/35859be1c3b9dc63d4484be187e902aa3899827b))

## v0.27.2-beta.1 (2023-09-27)
### Fix
* If loading dc.yml fails, still try local tasks (because that might fix it) ([`251fa53`](https://github.com/educationwarehouse/edwh/commit/251fa5333e96f7d24c72ee9a0a9ccfd464f341c3))

## v0.27.1 (2023-09-26)
### Fix
* **types:** Minor changes (py.typed file + some annotations) to make type checkers a bit happier (-> work better as a library) ([`b6adf30`](https://github.com/educationwarehouse/edwh/commit/b6adf300cf11412cd5df0fe4f844d532e516611f))

## v0.27.0 (2023-09-21)
### Feature
* `docker compose ls` support, using `ew ls` or `ew ls -q` ([`1a3f73e`](https://github.com/educationwarehouse/edwh/commit/1a3f73e80ee1767579fc19c801f5e38411953871))

### Fix
* Removed an unused argument to `ew ls` ([`8d447c5`](https://github.com/educationwarehouse/edwh/commit/8d447c5ff7e5bf207ee815df1eb858d4daffed43))

## v0.26.0 (2023-09-21)
### Feature
* Work with `docker compose` by default ([`4da67a8`](https://github.com/educationwarehouse/edwh/commit/4da67a8f19312fa15e70ca0737318220b25d1bd3))

## v0.25.2 (2023-09-20)
### Fix
* Removing test print statement. ([`d9864ec`](https://github.com/educationwarehouse/edwh/commit/d9864ecee06e212e258a28a2b2e40ed6374965dd))

## v0.25.1 (2023-09-20)
### Fix
* Handle crashing plugins nicely. ([`47f7db1`](https://github.com/educationwarehouse/edwh/commit/47f7db1dcf6c88ba804d2f676be603a867065191))

## v0.25.0 (2023-09-20)
### Feature
* Next_value can handle more keys instead of just one. ([`5e9fe72`](https://github.com/educationwarehouse/edwh/commit/5e9fe72556c464420181186af92c8b25bfa29346))

## v0.25.0-beta.1 (2023-09-19)
### Feature
* [eod] in progress logging to check why it's so slow sometimes ([`1b2945e`](https://github.com/educationwarehouse/edwh/commit/1b2945e50a4fe14f8383ab4893ae15b4baad21d5))

## v0.24.0 (2023-09-14)
### Feature
* **core:** Allow --new-docker-compose to use `docker compose` instead of `docker-compose`. ([`8f6f39b`](https://github.com/educationwarehouse/edwh/commit/8f6f39bec0cbe6d986584b436b6ba0d5fe804675))
* **core:** `add_global_flag` functionality to add a flag to inv/fab core opts. ([`4e18491`](https://github.com/educationwarehouse/edwh/commit/4e18491fba85cccfc68f2beac3533695308735bb))

### Fix
* **dc:** Core flag -o also enables old docker-compose ([`4294002`](https://github.com/educationwarehouse/edwh/commit/4294002f2a308e7e31172249d6e45bc1e8e4463e))

## v0.23.1 (2023-09-07)
### Fix
* **edwh:** No crash if missing config toml or docker-compose file, but warn instead ([`3044854`](https://github.com/educationwarehouse/edwh/commit/3044854ea46843e2135e2f7404bc2526660f4269))

## v0.23.0 (2023-09-06)
### Feature
* **settings:** Added fuzzy matching when no results: 'redesh' or 'redahs' will match REDASH_SECRET ([`6f94062`](https://github.com/educationwarehouse/edwh/commit/6f94062ba942208b3220c9d52404694f4bace988))

## v0.22.3 (2023-08-08)
### Fix
* **permissions:** Set_permissions now also works on an empty directory thanks to `xargs --no-run-if-empty` ([`7482ad4`](https://github.com/educationwarehouse/edwh/commit/7482ad47305cced764daba43694558be520bcc1a))

## v0.22.2 (2023-08-08)
### Fix
* **env:** TomlConfig is now a 'singleton' based on fname (toml file name) and dotenv_path instead of only one instance. ([`bef13f8`](https://github.com/educationwarehouse/edwh/commit/bef13f8013ac6ddfbe0386f4ab89d2cd29721cee))

## v0.22.1 (2023-08-08)
### Fix
* **env:** Also create missing parent directory of custom .env path ([`d77b78c`](https://github.com/educationwarehouse/edwh/commit/d77b78ce2c442dd09b5f9465649fef0bd4eb9fad))

### Documentation
* **changelog:** Translate changelog to English ([`2cf7a2d`](https://github.com/educationwarehouse/edwh/commit/2cf7a2df2abdca85912fe57575cbfb25f2a13692))

## v0.22.0 (2023-08-08)
### Feature
* **env:** Moved password generator to helpers; added 'suffix' (to be used instead of incorrect 'postfix') and 'path'/'toml_path' to check_env ([`f121d02`](https://github.com/educationwarehouse/edwh/commit/f121d02a3f0f212e155e2b6ec4e0a88b94d00356))

### Fix
* `check_env` now also creates the default .env if it does not exist yet. ([`253e93c`](https://github.com/educationwarehouse/edwh/commit/253e93c60a672be71f5ec280855c9f2c3be9e0f4))
* **env:** TomlConfig now also handles an alternative .env path well. ([`82601c7`](https://github.com/educationwarehouse/edwh/commit/82601c7cebe63d9e0023ee1df88a6a7a5e7e74bf))

### Documentation
* Manually update changelog to remove beta release ([`baae20b`](https://github.com/educationwarehouse/edwh/commit/baae20bf8077dace6af6bf20fdd237c94cddece0))

## v0.21.0 (2023-08-01)
### Feature
* **logs:** Extra --all option (alias for -s "*") ([`475ce58`](https://github.com/educationwarehouse/edwh/commit/475ce58509205a9a1f823fec0e93b848eb161a2a))

### Fix
* Actually look at [services.log] in config.toml when running `ew log` without providing a service name ([`fc04d6a`](https://github.com/educationwarehouse/edwh/commit/fc04d6a07bd45625f03d2936e4e98dceb100396b))

## v0.20.1 (2023-07-11)
### Fix
* Changed `print(colored(` to `cprint(` ([`92b34a2`](https://github.com/educationwarehouse/edwh/commit/92b34a2505b094c76bf0a8011e9cbcf04feb12d9))

## v0.20.0 (2023-07-11)
### Feature
* Allow multiple plugins (separated with ',') in plugin.add, plugin.update and plugin.remove ([`69ce19c`](https://github.com/educationwarehouse/edwh/commit/69ce19c1838265e578f0ef7f68156bd6eb0515f3))

## v0.19.5 (2023-06-19)
### Documentation
* **plugin:** Add `files` plugin as an option ([`0b343dc`](https://github.com/educationwarehouse/edwh/commit/0b343dc9c8096a09bbb069cdcc9c73b8af1866b9))

## v0.19.4 (2023-06-19)
### Fix
* **deps:** Missing python-dateutil dependency ([`63ff229`](https://github.com/educationwarehouse/edwh/commit/63ff2298743f4bc981ae5b9b9e6969512f7d535c))

## v0.19.3 (2023-06-16)
### Fix
* Made the message for minimal services a bit clearer in setup and made it so that the celeries aren't listed in the selection of services. ([`31be024`](https://github.com/educationwarehouse/edwh/commit/31be024ab2dc3bb440f0e06db1c75480cb2571dd))

## v0.19.2 (2023-06-14)
### Fix
* For service discovery the setup will no longer use docker-compose (as that may result in cyclic dependencies of the docker-compose depending on settings in the .env file). It will simply find the `services` key from the `docker-compose.yaml` ([`97146e8`](https://github.com/educationwarehouse/edwh/commit/97146e8657d219d2d94ff4bd5bb4a520369e1107))

## v0.19.1 (2023-06-13)
### Fix

* **changelog:** Shortcut: ew plugins --changelog = ew plugin.changelog --new ([`b4e1c52`](https://github.com/educationwarehouse/edwh/commit/b4e1c52be66ab2f38f88f0e3bd7e8a40f25a37e1))

## v0.19.0 (2023-06-13)
### Feature

* **changelog:** Working --new flag ([`d921c9a`](https://github.com/educationwarehouse/edwh/commit/d921c9a54505b787dab9db7900bdb066856ac09a))
* **changelog:** WIP to allow showing plugin changelogs ([`efa634c`](https://github.com/educationwarehouse/edwh/commit/efa634c86d3c19f61f603c7a7a36896b82bee015))

## v0.18.5 (2023-06-06)
### Fix
* **plugin:** Uninstall <plugin> doesn't prompt anymore ([`627894e`](https://github.com/educationwarehouse/edwh/commit/627894e0159123836d9f293fc8f5f1ce57e638f6))

## v0.18.4 (2023-05-31)


## v0.18.3 (2023-05-31)
### Fix
* Follow now works again with `ew logs` ([`3d43fbe`](https://github.com/educationwarehouse/edwh/commit/3d43fbe0dfe8bdbbc84e59d96d6d09751ca6732d))

## v0.18.2 (2023-05-31)
### Fix
* Added sshfs to pyproject.toml so it can be installed using edwh.self-update and can be listen in the plugin ([`2b99fcd`](https://github.com/educationwarehouse/edwh/commit/2b99fcdb5bc2407b5e7daec015e1d71e682155ab))

## v0.18.1 (2023-05-23)
### Fix
* `--sort` now disables `--follow` instead of warning. ([`09c6ca1`](https://github.com/educationwarehouse/edwh/commit/09c6ca1cd7e24d6a16f4ba3a5803f8e7e97f3f3a))

## v0.18.0 (2023-05-23)
### Feature
* Allow `edwh logs --sort` to sort on timestamp. ([`bfc18b7`](https://github.com/educationwarehouse/edwh/commit/bfc18b75e5e8470d0b533d70d209b9704c25024d))

## v0.18.0-beta.2 (2023-05-23)
### Fix
* **plugin:** Allow updating 'edwh' via plugin.update ([`a27adaa`](https://github.com/educationwarehouse/edwh/commit/a27adaa762b6060ff5d34fb2251d52300ee1c3dc))

## v0.18.0-beta.1 (2023-05-23)
### Feature
* Added upgrade feature taiga#1385 ([`72b85e2`](https://github.com/educationwarehouse/edwh/commit/72b85e27f22d30160a25609fb62ce7446444cf03))

### Fix
* **setup:** Docker-compose config --services depends on .env, so run local_setup on crash ([`542a6db`](https://github.com/educationwarehouse/edwh/commit/542a6db385220dfc91fc96052a28b5642c368b44))

### Documentation
* Added sshfs docs to README.md ([`1cdf1e4`](https://github.com/educationwarehouse/edwh/commit/1cdf1e49a9f788b27545fe2a5538cd93d8bcbf66))

## v0.17.2 (2023-05-19)


## v0.17.1 (2023-05-19)
### Fix
* **local:** Warn instead of crash if local tasks.py is incorrect (raises importerror) ([`614ced6`](https://github.com/educationwarehouse/edwh/commit/614ced6fb46ae158968d40c5b8ffd23a55264442))

## v0.17.0 (2023-05-19)
### Fix
* Renamed removed edwh-demo-tasks-plugin to existing (new) edwh-demo-plugin ([`cc4b2e8`](https://github.com/educationwarehouse/edwh/commit/cc4b2e8970aaf33adc2c2097de6514835dd61b77))

## v0.16.1 (2023-05-19)
### Fix
* Added sshkey info to readme.md ([`1a9ff59`](https://github.com/educationwarehouse/edwh/commit/1a9ff59f925b3d863355886265528e79d6b223fe))

## v0.16.0 (2023-05-19)
### Feature
* Added edwh-sshkey-plugin to pyproject.toml ([`afdb0e9`](https://github.com/educationwarehouse/edwh/commit/afdb0e9ab51103cd19a5c8ac0d43fa27506b903d))

## v0.15.2 (2023-05-11)
### Fix
* **plugins:** Swapped latest and custom version, docs for upgrade arguments ([`350aacc`](https://github.com/educationwarehouse/edwh/commit/350aacc592162e2420d9c07a03e0b7f9be6ad91a))

## v0.15.1 (2023-05-11)
### Fix
* Fix grammar in case of 1 out of date plugin (are -> is) ([`009f531`](https://github.com/educationwarehouse/edwh/commit/009f53125acd84a9fc5cb4cedfbc9d3ee2fbba36))

## v0.15.0 (2023-05-11)
### Feature
* **plugin:** Aliases for add/remove and allow --version for upgrade ([`e3f63ef`](https://github.com/educationwarehouse/edwh/commit/e3f63efdfc2250e2e8cf2eb40ad272caa5d88265))
* **plugins:** Add 'plugin' namespace (as internal extra) to manage installed plugins ([`7270273`](https://github.com/educationwarehouse/edwh/commit/72702736de9b3defe82f984400793d4f3aad4249))

### Documentation
* **plugin:** Add explaination about plugin.add when running plugins and not all are present ([`c0ecebd`](https://github.com/educationwarehouse/edwh/commit/c0ecebdc4743a076253cf2e2d9aee11d8b592e0a))
* **changelog:** Manual editing to remove prerelease commits ([`002e798`](https://github.com/educationwarehouse/edwh/commit/002e7984c8283645c6a2adebd47250948d03e50a))

### Performance
* **plugins:**  used threading to speed up package metadata collection and split meta tasks to own file ([`cbc8a6d`](https://github.com/educationwarehouse/edwh/commit/cbc8a6df9a52bdfd67254174e76576ec38a3c017))

## v0.14.0 (2023-05-08)
### Feature
* **plugins:** New command `edwh plugins` to show installed and available plugins ([`669d923`](https://github.com/educationwarehouse/edwh/commit/669d9236cc143ea2e0df0d26b9ce9d4123ee119c))

## v0.13.0 (2023-05-08)
### Feature
* Added self-update and self-update-pipx to manage plugin updates ([`2fa61ff`](https://github.com/educationwarehouse/edwh/commit/2fa61ff71277ec063564404e77ec2378f8f81fb6))

## v0.12.2 (2023-05-08)
### Documentation
* **locust:** Added edwh-locust-plugin as plugin extra ([`c33dd33`](https://github.com/educationwarehouse/edwh/commit/c33dd33c1547fd303af931075c2172b5516c6840))

## v0.12.1 (2023-05-08)
### Documentation
* **b2:** Added b2 as possible plugin ([`7cd7378`](https://github.com/educationwarehouse/edwh/commit/7cd73789c47b93ed3cc1caa77b97a945be20dda4))

## v0.12.0 (2023-05-08)
### Feature
* Split helpers to own file and imported functions in __init__, so `edwh` can be used better as a Python lib ([`e6b540e`](https://github.com/educationwarehouse/edwh/commit/e6b540e2ddbfc9fe21a5d5dc61202dd3f7a195ee))

## v0.11.0 (2023-05-04)
### Feature
* **env:** Get_env_value added + warn instead of crash if opengraph code is missing from local ([`992ab97`](https://github.com/educationwarehouse/edwh/commit/992ab9743d2ecb094022d3c813d7296a270a804c))

## v0.10.2 (2023-05-04)


## v0.10.1 (2023-05-04)



## v0.10.0 (2023-05-04)
### Feature
* `next_value` and `set_permissions` transfered from other repositories tasks.py ([`7bcb749`](https://github.com/educationwarehouse/edwh/commit/7bcb7491b728b00ce3846c62806d31bf1e49352c))
* **ew:** `ew completions` to generate bash script ([`c1c6a1f`](https://github.com/educationwarehouse/edwh/commit/c1c6a1f6a0d753cd6b6b67f6a5591583a1f63f19))
* **ew:** `ew completions` to generate bash script ([`c1c6a1f`](https://github.com/educationwarehouse/edwh/commit/c1c6a1f6a0d753cd6b6b67f6a5591583a1f63f19))
### Fix
* **dep:** Invoke 2.1 does not work well with some of our plugins ([`bb5d450`](https://github.com/educationwarehouse/edwh/commit/bb5d450252a8329968b24c251f8f50a873f3b3f3))

## v0.9.1 (2023-04-25)
### Fix
* **toml:** Tomlkit instead of tomllib for 3.11+ + refactoring ([`8de80f0`](https://github.com/educationwarehouse/edwh/commit/8de80f017f98dc9f632bb13966305a3716fa74af))
* **deps:** Invoke 2.0 works with python 3.11 ([`bbd2d69`](https://github.com/educationwarehouse/edwh/commit/bbd2d691ebe79eeb8b89b9e853fc0b40ba85cf10))

## v0.9.0 (2023-04-24)
### Feature
* -n will remove the config file so that you can reconfigure it. NOTE IT WILL REMOVE THE EXISTING CONFIG.TOML ([`33a8f5c`](https://github.com/educationwarehouse/edwh/commit/33a8f5ca59f9227233996828fc4c36da764cfb12))
* -n will remove the config file so that you can reconfigure it. NOTE IT WILL REMOVE THE EXISTING CONFIG.TOML ([`9e2dc42`](https://github.com/educationwarehouse/edwh/commit/9e2dc4236827de74291a69fdfcb352ccca0a2fe0))
* Fixed color coding ([`4e1c7ca`](https://github.com/educationwarehouse/edwh/commit/4e1c7ca16907fe7e1adc8b3ba468b7147b01e1fe))

### Fix
* Celeries will only be included in minimal when include_celeries_in_minimal == "true". ([`b12b997`](https://github.com/educationwarehouse/edwh/commit/b12b99764f317d47c35d8a9a8a1cba15cf595200))
* When a key is not found en config.toml it will run edwh setup ([`742902a`](https://github.com/educationwarehouse/edwh/commit/742902ad42c5c26a73d3791aef948912be618ab2))
* Wrong indexing of services ([`1e8a601`](https://github.com/educationwarehouse/edwh/commit/1e8a6012549fbd9eabde265e58fd5d76a31928cc))
* Color codes and type ([`8d0674c`](https://github.com/educationwarehouse/edwh/commit/8d0674caed03c561b2c38e15654b5eb135144a17))

## v0.8.0 (2023-04-21)


## v0.7.1 (2023-04-21)
### Fix
* Copy/paste error ([`197975f`](https://github.com/educationwarehouse/edwh/commit/197975f23ab6598289cb4dd2131bdeed7dec2918))

## v0.7.0 (2023-04-21)
### Feature
* `apply_dotenv_vars_to_yaml_templates` added for traefik. ([`cc65abe`](https://github.com/educationwarehouse/edwh/commit/cc65abe300de0457f0ab464dcfa84cf2c3c981b5))

## v0.6.6 (2023-04-21)


## v0.6.5 (2023-04-20)
### Fix
* Semver testing + demo plugin re-included ([`3e96848`](https://github.com/educationwarehouse/edwh/commit/3e968480ab67596a961a219bb3f7b900fbe7fa1f))
* `exec_setup_in_other_task` has changed a little to search further up parent folders, until a `tasks.py` is found. ([`1675d8b`](https://github.com/educationwarehouse/edwh/commit/1675d8b0b83f238839f0d76013e09e412ea01598))

## v0.6.4 (2023-04-18)
### Fix
* **dev:** Remove demo plugin from [plugins] extra ([`582dc89`](https://github.com/educationwarehouse/edwh/commit/582dc89ce4f81b6ccb6cb99517e73fa996dfd764))

## v0.6.3 (2023-04-18)
### Fix
* **project:** Update dependency versions for invoke 2.0 so py3.11+ works again ([`cd406be`](https://github.com/educationwarehouse/edwh/commit/cd406be2adab4c7a04fbd15cde5229d672cf7892))

## v0.6.2 (2023-04-17)
### Documentation
* **readme:** Added Server Provisioning plugin in overview of plugins ([`1c20334`](https://github.com/educationwarehouse/edwh/commit/1c203342a7d688750bfb55fc784fa181c05e84e8))

## v0.6.1 (2023-04-17)


## v0.6.0 (2023-04-17)
### Feature
* **core:** Replaced invoke with fabric for possibly more plugin functionality ([`85838ea`](https://github.com/educationwarehouse/edwh/commit/85838ea3b4cd2a50dc6e8a90e3955d9d82778b0f))

### Fix
* **project:** Remove theoretical support for Python versions below 3.10 since that has never worked ([`2f567e2`](https://github.com/educationwarehouse/edwh/commit/2f567e2404a3c10019b9bc8efd39c2ed4248bca3))
* **dependencies:** Importilb is only a package for python 2, not needed as dependency for py 3 ([`f5e0745`](https://github.com/educationwarehouse/edwh/commit/f5e0745f143d09cd6a9cfc4b5884d8f11faa2e35))

## v0.5.0 (2023-04-17)


## v0.4.5 (2023-04-11)
### Documentation
* **changelog:** Manual fix changelog for missing versions pt2 ([`488982d`](https://github.com/educationwarehouse/edwh/commit/488982d604266d1b54adfc02782fd876f8c9c6b5))
* **changelog:** Manual fix changelog for missing versions ([`fba6cc2`](https://github.com/educationwarehouse/edwh/commit/fba6cc200576cf700faf867cb79efab6f3f13f71))

## v0.4.4 (2023-04-11)
### Feature
* **edwh:** Include bundler-plugin in `edwh[plugins]` as well ([`df4424d`](https://github.com/educationwarehouse/edwh/commit/df4424d37c225c3e6c89010a3186fc225d13e354))

## 0.4.3 (2023-04-11)
### Feature
* allow bundle(r) extra and alias for pip-compile extra. ([`82079ec`](https://github.com/educationwarehouse/edwh/commit/82079ec3e59c4c8789098c37666dbf22f1d3d30e))

## 0.4.2 (2023-04-11)
### Feature
* allow installing edwh-pipcompile-plugin as `edwh[pip]`. ([`2ebf9a6`](https://github.com/educationwarehouse/edwh/commit/2ebf9a627846114a725880e1fd074579f063fa3b))

## 0.4.1 (2023-04-11)
### Fix
* added python-semantic-release as dev dependency. ([`60d6b1c`](https://github.com/educationwarehouse/edwh/commit/60d6b1c8f5d39004e7eede2a3ce473810a214a6d))

## 0.4.0 (2023-04-11)
### Feat
*  allow pip install `edwh[multipass,restic]`. ([`2c43c47`](https://github.com/educationwarehouse/edwh/commit/2c43c477857db1157c4df90cd7bd43744aa5e9a8))

## v0.3.2 (2023-04-10)
### Fix
* Diceware was included as a dependency, but used as a pipx installed application. ([`2f6bc9f`](https://github.com/educationwarehouse/edwh/commit/2f6bc9f7c7aabafbab0b857d84905be13d3973f0))

## v0.3.1 (2023-04-10)
### Fix
* Missing changelog entry ([`4fe91e4`](https://github.com/educationwarehouse/edwh/commit/4fe91e400a8b64197b7a1c7df55777c13787b2d7))

## v0.3.1 (2023-04-10)
### Feature
* Added and upgraded: settings, up, ps, logs, stop, down, build, rebuild, docs, search_adjacent_setting, generate_password, settings, volumes and helpers. ([`9f80e25`](https://github.com/educationwarehouse/edwh/commit/9f80e25953a37a333ce4a0b73e355864d6c26fb1))

## v0.2.1 (2023-04-07)
### Fix
* **pyproject.toml:** Use `hatch run publish` to use python-semantic-release to patch the changelog and versioning. ([`639dbff`](https://github.com/educationwarehouse/edwh/commit/639dbff3a67d8dd273863551780a69b4934debbf))

## v0.2.0 (2023-04-07)
### Feature
* Removed old redundant demo methods and added `zen` ([`f5be9c6`](https://github.com/educationwarehouse/edwh/commit/f5be9c65c7ef249d73c56b1d49c8e61023d46991))

## v0.1.8 (2023-04-07)
### Fix
* Removed CHANGELOG.txt and reduced semantic-versioning responsibilities ([`e9e26d9`](https://github.com/educationwarehouse/edwh/commit/e9e26d994ae64fd5c04c58b8888524debb4a83c7))
