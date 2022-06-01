#  Copyright (c) 2015-2018 Cisco Systems, Inc.
#
#  Permission is hereby granted, free of charge, to any person obtaining a copy
#  of this software and associated documentation files (the "Software"), to
#  deal in the Software without restriction, including without limitation the
#  rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
#  sell copies of the Software, and to permit persons to whom the Software is
#  furnished to do so, subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included in
#  all copies or substantial portions of the Software.
#
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
#  FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#  DEALINGS IN THE SOFTWARE.

import collections
import os
import re

import pytest

from molecule import config, util
from molecule.provisioner import ansible, ansible_playbooks
from molecule.test.unit.conftest import os_split


@pytest.fixture
def _patched_ansible_playbook(mocker):
    m = mocker.patch("molecule.provisioner.ansible_playbook.AnsiblePlaybook")
    m.return_value.execute.return_value = b"patched-ansible-playbook-stdout"

    return m


@pytest.fixture
def _patched_write_inventory(mocker):
    return mocker.patch("molecule.provisioner.ansible.Ansible._write_inventory")


@pytest.fixture
def _patched_remove_vars(mocker):
    return mocker.patch("molecule.provisioner.ansible.Ansible._remove_vars")


@pytest.fixture
def _patched_link_or_update_vars(mocker):
    return mocker.patch("molecule.provisioner.ansible.Ansible._link_or_update_vars")


@pytest.fixture
def _provisioner_section_data():
    return {
        "provisioner": {
            "name": "ansible",
            "config_options": {"defaults": {"foo": "bar"}},
            "connection_options": {"foo": "bar"},
            "options": {"foo": "bar", "become": True, "v": True},
            "env": {
                "FOO": "bar",
                "ANSIBLE_ROLES_PATH": "foo/bar",
                "ANSIBLE_LIBRARY": "foo/bar",
                "ANSIBLE_FILTER_PLUGINS": "foo/bar",
            },
            "inventory": {
                "hosts": {
                    "all": {
                        "hosts": {"extra-host-01": {}},
                        "children": {"extra-group": {"hosts": ["extra-host-01"]}},
                    }
                },
                "host_vars": {
                    "instance-1": [{"foo": "bar"}],
                    "localhost": [{"foo": "baz"}],
                },
                "group_vars": {
                    "example_group1": [{"foo": "bar"}],
                    "example_group2": [{"foo": "bar"}],
                },
            },
        }
    }


@pytest.fixture
def _instance(_provisioner_section_data, config_instance):
    return ansible.Ansible(config_instance)


def test_config_private_member(_instance):
    assert isinstance(_instance._config, config.Config)


def test_default_config_options_property(_instance):
    x = {
        "defaults": {
            "ansible_managed": "Ansible managed: Do NOT edit this file manually!",
            "display_failed_stderr": True,
            "forks": 50,
            "host_key_checking": False,
            # https://docs.ansible.com/ansible/devel/reference_appendices/interpreter_discovery.html
            "interpreter_python": "auto_silent",
            "nocows": 1,
            "retry_files_enabled": False,
        },
        "ssh_connection": {
            "control_path": "%(directory)s/%%h-%%p-%%r",
            "scp_if_ssh": True,
        },
    }

    assert x == _instance.default_config_options


def test_default_options_property(_instance):
    assert {"skip-tags": "molecule-notest,notest"} == _instance.default_options


def test_default_env_property(_instance):
    x = _instance._config.provisioner.config_file

    assert x == _instance.default_env["ANSIBLE_CONFIG"]
    assert "MOLECULE_FILE" in _instance.default_env
    assert "MOLECULE_INVENTORY_FILE" in _instance.default_env
    assert "MOLECULE_SCENARIO_DIRECTORY" in _instance.default_env
    assert "MOLECULE_INSTANCE_CONFIG" in _instance.default_env
    assert "ANSIBLE_CONFIG" in _instance.env
    assert "ANSIBLE_ROLES_PATH" in _instance.env
    assert "ANSIBLE_LIBRARY" in _instance.env
    assert "ANSIBLE_FILTER_PLUGINS" in _instance.env


def test_name_property(_instance):
    assert "ansible" == _instance.name


@pytest.mark.parametrize(
    "config_instance", ["_provisioner_section_data"], indirect=True
)
def test_config_options_property(_instance):
    x = {
        "defaults": {
            "ansible_managed": "Ansible managed: Do NOT edit this file manually!",
            "display_failed_stderr": True,
            "foo": "bar",
            "forks": 50,
            "host_key_checking": False,
            "interpreter_python": "auto_silent",
            "nocows": 1,
            "retry_files_enabled": False,
        },
        "ssh_connection": {
            "control_path": "%(directory)s/%%h-%%p-%%r",
            "scp_if_ssh": True,
        },
    }

    assert x == _instance.config_options


@pytest.mark.parametrize(
    "config_instance", ["_provisioner_section_data"], indirect=True
)
def test_options_property(_instance):
    x = {"become": True, "foo": "bar", "v": True, "skip-tags": "molecule-notest,notest"}

    assert x == _instance.options


def test_options_property_does_not_merge(_instance):
    for action in ["create", "destroy"]:
        _instance._config.action = action

        assert {"skip-tags": "molecule-notest,notest"} == _instance.options


def test_options_property_handles_cli_args(_instance):
    _instance._config.args = {"debug": True}
    x = {
        "vvv": True,
        "become": True,
        "diff": True,
        "skip-tags": "molecule-notest,notest",
    }

    assert x == _instance.options


@pytest.mark.parametrize(
    "config_instance", ["_provisioner_section_data"], indirect=True
)
def test_env_property(_instance):
    x = _instance._config.provisioner.config_file

    assert x == _instance.env["ANSIBLE_CONFIG"]
    assert "bar" == _instance.env["FOO"]


@pytest.mark.parametrize(
    "config_instance", ["_provisioner_section_data"], indirect=True
)
def test_env_appends_env_property(_instance):
    os.environ["ANSIBLE_ROLES_PATH"] = ""

    expected = [
        util.abs_path(os.path.join(_instance._config.runtime.cache_dir, "roles")),
        util.abs_path(
            os.path.join(_instance._config.scenario.ephemeral_directory, "roles")
        ),
        util.abs_path(
            os.path.join(_instance._config.project_directory, os.path.pardir)
        ),
        util.abs_path(os.path.join(os.path.expanduser("~"), ".ansible", "roles")),
        "/usr/share/ansible/roles",
        "/etc/ansible/roles",
        util.abs_path(os.path.join(_instance._config.scenario.directory, "foo", "bar")),
    ]

    # molecule could decide to add extra paths, so we only want to check
    # that those that we need are kept inside the list with exact order

    roles_path_list = _instance.env["ANSIBLE_ROLES_PATH"].split(":")

    assert roles_path_list == expected

    x = _instance._get_modules_directories()
    x.append(
        util.abs_path(os.path.join(_instance._config.scenario.directory, "foo", "bar"))
    )
    assert x == _instance.env["ANSIBLE_LIBRARY"].split(":")

    x = [
        _instance._get_filter_plugin_directory(),
        util.abs_path(
            os.path.join(
                _instance._config.scenario.ephemeral_directory, "plugins", "filter"
            )
        ),
        util.abs_path(
            os.path.join(_instance._config.project_directory, "plugins", "filter")
        ),
        util.abs_path(
            os.path.join(os.path.expanduser("~"), ".ansible", "plugins", "filter")
        ),
        "/usr/share/ansible/plugins/filter",
        util.abs_path(os.path.join(_instance._config.scenario.directory, "foo", "bar")),
    ]
    assert x == _instance.env["ANSIBLE_FILTER_PLUGINS"].split(":")


@pytest.mark.parametrize(
    "config_instance", ["_provisioner_section_data"], indirect=True
)
def test_env_appends_env_property_with_os_env(_instance):
    os.environ["ANSIBLE_ROLES_PATH"] = "/foo/bar:/foo/baz"

    expected = [
        util.abs_path(os.path.join(_instance._config.runtime.cache_dir, "roles")),
        util.abs_path(
            os.path.join(_instance._config.scenario.ephemeral_directory, "roles")
        ),
        util.abs_path(
            os.path.join(_instance._config.project_directory, os.path.pardir)
        ),
        util.abs_path(os.path.join(os.path.expanduser("~"), ".ansible", "roles")),
        "/usr/share/ansible/roles",
        "/etc/ansible/roles",
        "/foo/bar",
        "/foo/baz",
        util.abs_path(os.path.join(_instance._config.scenario.directory, "foo", "bar")),
    ]

    # molecule could decide to add extra paths, so we only want to check
    # that those that we need are kept inside the list

    roles_path_list = _instance.env["ANSIBLE_ROLES_PATH"].split(":")

    assert roles_path_list == expected


@pytest.mark.parametrize(
    "config_instance", ["_provisioner_section_data"], indirect=True
)
def test_host_vars_property(_instance):
    x = {"instance-1": [{"foo": "bar"}], "localhost": [{"foo": "baz"}]}

    assert x == _instance.host_vars


@pytest.mark.parametrize(
    "config_instance", ["_provisioner_section_data"], indirect=True
)
def test_group_vars_property(_instance):
    x = {"example_group1": [{"foo": "bar"}], "example_group2": [{"foo": "bar"}]}

    assert x == _instance.group_vars


@pytest.mark.parametrize(
    "config_instance", ["_provisioner_section_data"], indirect=True
)
def test_hosts_property(_instance):
    hosts = {
        "all": {
            "hosts": {"extra-host-01": {}},
            "children": {"extra-group": {"hosts": ["extra-host-01"]}},
        }
    }

    assert hosts == _instance.hosts


def test_links_property(_instance):
    assert {} == _instance.links


def test_inventory_directory_property(_instance):
    x = os.path.join(_instance._config.scenario.ephemeral_directory, "inventory")
    assert x == _instance.inventory_directory


def test_inventory_file_property(_instance):
    x = os.path.join(
        _instance._config.scenario.inventory_directory, "ansible_inventory.yml"
    )

    assert x == _instance.inventory_file


def test_config_file_property(_instance):
    x = os.path.join(_instance._config.scenario.ephemeral_directory, "ansible.cfg")

    assert x == _instance.config_file


def test_playbooks_property(_instance):
    assert isinstance(_instance.playbooks, ansible_playbooks.AnsiblePlaybooks)


def test_directory_property(_instance):
    result = _instance.directory
    parts = os_split(result)

    assert ("molecule", "provisioner", "ansible") == parts[-3:]


def test_playbooks_cleaned_property_is_optional(_instance):
    assert _instance.playbooks.cleanup is None


def test_playbooks_converge_property(_instance):
    x = os.path.join(_instance._config.scenario.directory, "converge.yml")

    assert x == _instance.playbooks.converge


def test_playbooks_side_effect_property(_instance):
    assert _instance.playbooks.side_effect is None


def test_check(_instance, mocker, _patched_ansible_playbook):
    _instance.check()

    _patched_ansible_playbook.assert_called_once_with(
        _instance._config.provisioner.playbooks.converge, _instance._config, False
    )
    _patched_ansible_playbook.return_value.add_cli_arg.assert_called_once_with(
        "check", True
    )
    _patched_ansible_playbook.return_value.execute.assert_called_once_with()


def test_converge(_instance, mocker, _patched_ansible_playbook):
    result = _instance.converge()

    _patched_ansible_playbook.assert_called_once_with(
        _instance._config.provisioner.playbooks.converge, _instance._config, False
    )
    # NOTE(retr0h): This is not the true return type.  This is a mock return
    #               which didn't go through str.decode().
    assert result == b"patched-ansible-playbook-stdout"

    _patched_ansible_playbook.return_value.execute.assert_called_once_with()


def test_converge_with_playbook(_instance, mocker, _patched_ansible_playbook):
    result = _instance.converge("playbook")

    _patched_ansible_playbook.assert_called_once_with(
        "playbook", _instance._config, False
    )
    # NOTE(retr0h): This is not the true return type.  This is a mock return
    #               which didn't go through str.decode().
    assert result == b"patched-ansible-playbook-stdout"

    _patched_ansible_playbook.return_value.execute.assert_called_once_with()


def test_cleanup(_instance, mocker, _patched_ansible_playbook):
    _instance.cleanup()

    _patched_ansible_playbook.assert_called_once_with(
        _instance._config.provisioner.playbooks.cleanup, _instance._config, False
    )
    _patched_ansible_playbook.return_value.execute.assert_called_once_with()


def test_destroy(_instance, mocker, _patched_ansible_playbook):
    _instance.destroy()

    _patched_ansible_playbook.assert_called_once_with(
        _instance._config.provisioner.playbooks.destroy, _instance._config, False
    )
    _patched_ansible_playbook.return_value.execute.assert_called_once_with()


def test_side_effect(_instance, mocker, _patched_ansible_playbook):
    _instance.side_effect()

    _patched_ansible_playbook.assert_called_once_with(
        _instance._config.provisioner.playbooks.side_effect, _instance._config, False
    )
    _patched_ansible_playbook.return_value.execute.assert_called_once_with()


def test_create(_instance, mocker, _patched_ansible_playbook):
    _instance.create()

    _patched_ansible_playbook.assert_called_once_with(
        _instance._config.provisioner.playbooks.create, _instance._config, False
    )
    _patched_ansible_playbook.return_value.execute.assert_called_once_with()


def test_prepare(_instance, mocker, _patched_ansible_playbook):
    _instance.prepare()

    _patched_ansible_playbook.assert_called_once_with(
        _instance._config.provisioner.playbooks.prepare, _instance._config, False
    )
    _patched_ansible_playbook.return_value.execute.assert_called_once_with()


def test_syntax(_instance, mocker, _patched_ansible_playbook):
    _instance.syntax()

    _patched_ansible_playbook.assert_called_once_with(
        _instance._config.provisioner.playbooks.converge, _instance._config, False
    )
    _patched_ansible_playbook.return_value.add_cli_arg.assert_called_once_with(
        "syntax-check", True
    )
    _patched_ansible_playbook.return_value.execute.assert_called_once_with()


def test_verify(_instance, mocker, _patched_ansible_playbook):
    _instance.verify()

    if _instance._config.provisioner.playbooks.verify:
        _patched_ansible_playbook.assert_called_once_with(
            _instance._config.provisioner.playbooks.verify, _instance._config
        )
        _patched_ansible_playbook.return_value.execute.assert_called_once_with()


def test_write_config(temp_dir, _instance):
    _instance.write_config()

    assert os.path.isfile(_instance.config_file)


def test_manage_inventory(
    _instance,
    _patched_write_inventory,
    _patched_remove_vars,
    patched_add_or_update_vars,
    _patched_link_or_update_vars,
):
    _instance.manage_inventory()

    _patched_write_inventory.assert_called_once_with()
    _patched_remove_vars.assert_called_once_with()
    patched_add_or_update_vars.assert_called_once_with()
    assert not _patched_link_or_update_vars.called


def test_manage_inventory_with_links(
    _instance,
    _patched_write_inventory,
    _patched_remove_vars,
    patched_add_or_update_vars,
    _patched_link_or_update_vars,
):
    c = _instance._config.config
    c["provisioner"]["inventory"]["links"] = {"foo": "bar"}
    _instance.manage_inventory()

    _patched_write_inventory.assert_called_once_with()
    _patched_remove_vars.assert_called_once_with()
    assert not patched_add_or_update_vars.called
    _patched_link_or_update_vars.assert_called_once_with()


@pytest.mark.parametrize(
    "config_instance", ["_provisioner_section_data"], indirect=True
)
def test_add_or_update_vars(_instance):
    inventory_dir = _instance._config.scenario.inventory_directory

    host_vars_directory = os.path.join(inventory_dir, "host_vars")
    host_vars = os.path.join(host_vars_directory, "instance-1")

    _instance._add_or_update_vars()

    assert os.path.isdir(host_vars_directory)
    assert os.path.isfile(host_vars)

    host_vars_localhost = os.path.join(host_vars_directory, "localhost")
    assert os.path.isfile(host_vars_localhost)

    group_vars_directory = os.path.join(inventory_dir, "group_vars")
    group_vars_1 = os.path.join(group_vars_directory, "example_group1")
    group_vars_2 = os.path.join(group_vars_directory, "example_group2")

    assert os.path.isdir(group_vars_directory)
    assert os.path.isfile(group_vars_1)
    assert os.path.isfile(group_vars_2)

    hosts = os.path.join(inventory_dir, "hosts")
    assert os.path.isfile(hosts)
    assert util.safe_load_file(hosts) == _instance.hosts


@pytest.mark.parametrize(
    "config_instance", ["_provisioner_section_data"], indirect=True
)
def test_add_or_update_vars_without_host_vars(_instance):
    c = _instance._config.config
    c["provisioner"]["inventory"]["host_vars"] = {}
    inventory_dir = _instance._config.scenario.inventory_directory

    host_vars_directory = os.path.join(inventory_dir, "host_vars")
    host_vars = os.path.join(host_vars_directory, "instance-1")

    _instance._add_or_update_vars()

    assert not os.path.isdir(host_vars_directory)
    assert not os.path.isfile(host_vars)

    host_vars_localhost = os.path.join(host_vars_directory, "localhost")
    assert not os.path.isfile(host_vars_localhost)

    group_vars_directory = os.path.join(inventory_dir, "group_vars")
    group_vars_1 = os.path.join(group_vars_directory, "example_group1")
    group_vars_2 = os.path.join(group_vars_directory, "example_group2")

    assert os.path.isdir(group_vars_directory)
    assert os.path.isfile(group_vars_1)
    assert os.path.isfile(group_vars_2)

    hosts = os.path.join(inventory_dir, "hosts")
    assert os.path.isfile(hosts)
    assert util.safe_load_file(hosts) == _instance.hosts


def test_add_or_update_vars_does_not_create_vars(_instance):
    c = _instance._config.config
    c["provisioner"]["inventory"]["hosts"] = {}
    c["provisioner"]["inventory"]["host_vars"] = {}
    c["provisioner"]["inventory"]["group_vars"] = {}
    inventory_dir = _instance._config.scenario.inventory_directory

    hosts = os.path.join(inventory_dir, "hosts")
    host_vars_directory = os.path.join(inventory_dir, "host_vars")
    group_vars_directory = os.path.join(inventory_dir, "group_vars")

    _instance._add_or_update_vars()

    assert not os.path.isdir(host_vars_directory)
    assert not os.path.isdir(group_vars_directory)
    assert not os.path.isfile(hosts)


@pytest.mark.parametrize(
    "config_instance", ["_provisioner_section_data"], indirect=True
)
def test_remove_vars(_instance):
    inventory_dir = _instance._config.scenario.inventory_directory

    hosts = os.path.join(inventory_dir, "hosts")
    host_vars_directory = os.path.join(inventory_dir, "host_vars")
    host_vars = os.path.join(host_vars_directory, "instance-1")

    _instance._add_or_update_vars()
    assert os.path.isfile(hosts)
    assert os.path.isdir(host_vars_directory)
    assert os.path.isfile(host_vars)

    host_vars_localhost = os.path.join(host_vars_directory, "localhost")
    assert os.path.isfile(host_vars_localhost)

    group_vars_directory = os.path.join(inventory_dir, "group_vars")
    group_vars_1 = os.path.join(group_vars_directory, "example_group1")
    group_vars_2 = os.path.join(group_vars_directory, "example_group2")

    assert os.path.isdir(group_vars_directory)
    assert os.path.isfile(group_vars_1)
    assert os.path.isfile(group_vars_2)

    _instance._remove_vars()

    assert not os.path.isfile(hosts)
    assert not os.path.isdir(host_vars_directory)
    assert not os.path.isdir(group_vars_directory)


def test_remove_vars_symlinks(_instance):
    inventory_dir = _instance._config.scenario.inventory_directory

    source_group_vars = os.path.join(inventory_dir, os.path.pardir, "group_vars")
    target_group_vars = os.path.join(inventory_dir, "group_vars")
    os.mkdir(source_group_vars)
    os.symlink(source_group_vars, target_group_vars)

    _instance._remove_vars()

    assert not os.path.lexists(target_group_vars)


def test_link_vars(_instance):
    c = _instance._config.config
    c["provisioner"]["inventory"]["links"] = {
        "hosts": "../hosts",
        "group_vars": "../group_vars",
        "host_vars": "../host_vars",
    }
    inventory_dir = _instance._config.scenario.inventory_directory
    scenario_dir = _instance._config.scenario.directory
    source_hosts = os.path.join(scenario_dir, os.path.pardir, "hosts")
    target_hosts = os.path.join(inventory_dir, "hosts")
    source_group_vars = os.path.join(scenario_dir, os.path.pardir, "group_vars")
    target_group_vars = os.path.join(inventory_dir, "group_vars")
    source_host_vars = os.path.join(scenario_dir, os.path.pardir, "host_vars")
    target_host_vars = os.path.join(inventory_dir, "host_vars")

    open(source_hosts, "w").close()  # pylint: disable=consider-using-with
    os.mkdir(source_group_vars)
    os.mkdir(source_host_vars)

    _instance._link_or_update_vars()

    assert os.path.lexists(target_hosts)
    assert os.path.lexists(target_group_vars)
    assert os.path.lexists(target_host_vars)


def test_link_vars_raises_when_source_not_found(_instance, patched_logger_critical):
    c = _instance._config.config
    c["provisioner"]["inventory"]["links"] = {"foo": "../bar"}

    with pytest.raises(SystemExit) as e:
        _instance._link_or_update_vars()

    assert 1 == e.value.code

    source = os.path.join(_instance._config.scenario.directory, os.path.pardir, "bar")
    msg = f"The source path '{source}' does not exist."
    patched_logger_critical.assert_called_once_with(msg)


def test_verify_inventory(_instance):
    _instance._verify_inventory()


def test_verify_inventory_raises_when_missing_hosts(
    temp_dir, patched_logger_critical, _instance
):
    _instance._config.config["platforms"] = []
    with pytest.raises(SystemExit) as e:
        _instance._verify_inventory()

    assert 1 == e.value.code

    msg = "Instances missing from the 'platform' section of molecule.yml."
    patched_logger_critical.assert_called_once_with(msg)


def test_vivify(_instance):
    d = _instance._vivify()
    d["bar"]["baz"] = "qux"

    assert "qux" == str(d["bar"]["baz"])


def test_default_to_regular(_instance):
    d = collections.defaultdict()
    assert isinstance(d, collections.defaultdict)

    d = _instance._default_to_regular(d)
    assert isinstance(d, dict)


def test_get_plugin_directory(_instance):
    result = _instance._get_plugin_directory()
    parts = os_split(result)

    assert ("molecule", "provisioner", "ansible", "plugins") == parts[-4:]


def test_get_modules_directories_default(_instance, monkeypatch):
    monkeypatch.delenv("ANSIBLE_LIBRARY", raising=False)

    paths = _instance._get_modules_directories()

    assert len(paths) == 5
    assert re.search(r"molecule/provisioner/ansible/plugins/modules$", paths[0])
    assert re.search(r"\.cache/molecule/[^/]+/default/library$", paths[1])
    assert re.search(r"/library$", paths[2])
    assert re.search(r"\.ansible/plugins/modules$", paths[3])
    assert re.search(r"/usr/share/ansible/plugins/modules$", paths[4])


def test_get_modules_directories_single_ansible_library(_instance, monkeypatch):
    monkeypatch.setenv("ANSIBLE_LIBRARY", "/abs/path/lib")

    paths = _instance._get_modules_directories()

    assert len(paths) == 6
    assert paths[0] == "/abs/path/lib"


def test_get_modules_directories_multi_ansible_library(_instance, monkeypatch):
    monkeypatch.setenv("ANSIBLE_LIBRARY", "relpath/lib:/abs/path/lib")

    paths = _instance._get_modules_directories()

    assert len(paths) == 7
    assert paths[0].endswith("relpath/lib")
    assert paths[1] == "/abs/path/lib"


def test_get_filter_plugin_directory(_instance):
    result = _instance._get_filter_plugin_directory()
    parts = os_split(result)
    x = ("molecule", "provisioner", "ansible", "plugins", "filter")

    assert x == parts[-5:]


def test_absolute_path_for(_instance):
    env = {"foo": "foo:bar"}
    x = ":".join(
        [
            os.path.join(_instance._config.scenario.directory, "foo"),
            os.path.join(_instance._config.scenario.directory, "bar"),
        ]
    )

    assert x == _instance._absolute_path_for(env, "foo")


def test_absolute_path_for_raises_with_missing_key(_instance):
    env = {"foo": "foo:bar"}

    with pytest.raises(KeyError):
        _instance._absolute_path_for(env, "invalid")
