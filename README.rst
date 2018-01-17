==========
Aggravator
==========

.. image:: https://travis-ci.org/petercb/aggravator.svg?branch=master
    :target: https://travis-ci.org/petercb/aggravator

.. image:: https://coveralls.io/repos/github/petercb/aggravator/badge.svg?branch=master
    :target: https://coveralls.io/github/petercb/aggravator?branch=master

Dynamic inventory script for Ansible that aggregates information from other sources

Installing
----------

.. code:: sh

  virtualenv aggravator
  source aggravator/bin/activate
  pip install aggravator


Executing
---------

.. code:: sh

  ansible-playbook -i aggravator/bin/inventory site.yml


How does it work
----------------

It will aggregate other config sources (YAML or JSON format) into a single
config stream.

The sources can be files or urls (to either file or webservices that produce
YAML or JSON) and the key path to merge them under can be specified.

Why does it exist
-----------------

We wanted to maintain our Ansible inventory in GIT as YAML files, and not in
the INI like format that Ansible generally supports for flat file inventory.

Additionally we had some legacy config management systems that contained some
information about our systems that we wanted exported to Ansible so we didn't
have to maintain them in multiple places.

So a script that could take YAML files and render them in a JSON format that
Ansible would ingest was needed, as was one that could aggregate many files
and streams.

Config format
-------------

Example (etc/config.yaml):

.. code:: yaml

  ---
  environments:
    test:
      include:
        - path: inventory/test.yaml
        - path: vars/global.yaml
          key: all/vars
        - path: secrets/test.yaml
          key: all/vars

By default the inventory script will look for the root config file as follows:

- `../etc/config.yaml` (relative to the `inventory` file)
- `/etc/aggravator/config.yaml`
- `/usr/local/etc/aggravator/config.yaml`

If it can't find it in one of those locations, you will need to use the `--uri`
option to specify it (or set the `INVENTORY_URI` env var)

It will parse it for a list of environments (test, prod, qa, etc) and for a
list of includes. The `include` section should be a list of dictionaries with
the following keys:

path
  The path to the data to be ingested, this can be one of:
  - absolute file path
  - relative file path (relative to the root config.yaml)
  - url to a file or service that emits a supported format

key
  The key where the data should be merged into, if none is specified it is
  imported into the root of the data structure.

format
  The data type of the stream to ingest (ie. `yaml` or `json`) if not specified
  then the script will attempt to guess it from the file extension

*Order* is important as items lower in the list will take precedence over ones
specified earlier in the list.

Merging
-------

Dictionaries will be merged, and lists will be replaced. So if a property at
the same level in two source streams of the same name are dictionaries their
contents will be merged. If they are lists, the later one will replace the
earlier.

If the data type of two properties at the same level are different the later
one will overwrite the earlier.

Environment Variables
---------------------

Setting the following environment variables can influence how the script
executes when it is called by Ansible.

`INVENTORY_ENV`
  Specify the environment name to merge inventory for as defined under the
  'environments' section in the root config.
  The environment name can also be guessed from the executable name, so if you
  create a symlink from `prod` to the `inventory` bin, it will assume the env
  you want to execute for is called `prod`, unless you override that.

`INVENTORY_URI`
  Location to the root config, if not in one of the standard locations

`VAULT_PASSWORD_FILE`
  Location of the vault password file if not in the default location of
  `~/.vault_pass.txt`, can be set to `/dev/null` to disable decryption of
  secrets.


Usage
-----

`inventory [OPTIONS]`

  Ansible file based dynamic inventory script

Options:

--env TEXT                  specify the platform name to pull inventory for
--uri TEXT                  specify the URI to query for inventory config
                            file, supports file:// and http(s)://  [default:
                            /home/peterb-l/git/petercb/aggravator/venv/etc/config.yaml]
--vault-password-file PATH  vault password file, if set to /dev/null secret
                            decryption will be disabled  [default: ~/.vault_pass.txt]
--list                      Print inventory information as a JSON object
--host TEXT                 Retrieve host variables (not implemented)
--createlinks DIRECTORY     Create symlinks in DIRECTORY to the script for
                            each platform name retrieved
--show                      Output a list of upstream environments
--help                      Show this message and exit.

