# Changelog

<!--next-version-placeholder-->

## v0.14.0-beta.1 (2023-05-08)
### Feature
* **plugins:** New command `edwh plugins` to show installed and available plugins ([`669d923`](https://github.com/educationwarehouse/edwh/commit/669d9236cc143ea2e0df0d26b9ce9d4123ee119c))

### Fix
* **plugins:** Works with pipx again too ([`20cd67a`](https://github.com/educationwarehouse/edwh/commit/20cd67acab29818bd328d930585d3fa53b862103))
* **plugins:** Also allow listing installed plugins ([`a0c317b`](https://github.com/educationwarehouse/edwh/commit/a0c317b9a7f3608fadd7077ac955098b2a2fab1d))

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
