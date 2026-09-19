"""Single-source deployment configuration contracts.

The deploy path used to carry two Caddy configurations, two writers of the same
Caddy systemd override, a second inventory reachable only through an
undocumented host variable, an unused collection install on every run, and a
recursive ownership reset of the whole application home. These tests pin the
single-source version of each.
"""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ANSIBLE = ROOT / "infrastructure" / "ansible"
PLAYBOOKS = ANSIBLE / "playbooks"
HOST_SCRIPTS = ROOT / "infrastructure" / "scripts"
SHARED_CADDYFILE = "{{ playbook_dir }}/../../caddy/Caddyfile"
FILE_MODULES = ("copy", "template", "ansible.builtin.copy", "ansible.builtin.template")
HOST_SCRIPT_REFERENCE = re.compile(
    r"(?:\{\{\s*app_home\s*\}\}|\$\{?APP_HOME\}?|/opt/cocktaildb)/scripts/"
    r"([A-Za-z0-9_.-]+)"
)


def _play(playbook):
    return yaml.safe_load((PLAYBOOKS / playbook).read_text(encoding="utf-8"))[0]


def _tasks(play):
    return (
        play.get("pre_tasks", []) + play.get("tasks", []) + play.get("post_tasks", [])
    )


def _written_files(play):
    """Every (task, module args) pair that writes a file in this play."""
    return [
        (task, task[module])
        for task in _tasks(play)
        for module in FILE_MODULES
        if module in task
    ]


def _referenced_host_scripts():
    """Script names the host itself invokes under its own scripts directory."""
    sources = (
        list(PLAYBOOKS.glob("*.yml"))
        + list((ROOT / "infrastructure" / "systemd").glob("*"))
        + list(HOST_SCRIPTS.glob("*"))
        + list((ROOT / "scripts").glob("*.sh"))
    )
    found = set()
    for path in sources:
        if path.is_file():
            found.update(
                HOST_SCRIPT_REFERENCE.findall(
                    path.read_text(encoding="utf-8", errors="replace")
                )
            )
    return found


def test_one_shared_caddy_configuration_is_deployed_by_both_playbooks():
    assert not (ANSIBLE / "files" / "Caddyfile.j2").exists(), (
        "a second Caddy configuration must not be maintained beside "
        "infrastructure/caddy/Caddyfile"
    )
    for playbook in ("deploy.yml", "deploy-caddy.yml"):
        writes = [
            args
            for _, args in _written_files(_play(playbook))
            if str(args.get("dest", "")).endswith("/Caddyfile")
        ]
        assert len(writes) == 1, f"{playbook} must publish exactly one Caddyfile"
        assert writes[0]["src"] == SHARED_CADDYFILE, (
            f"{playbook} must publish the shared Caddyfile"
        )


def test_caddy_environment_is_written_once_from_inventory():
    for playbook in ("deploy.yml", "deploy-caddy.yml"):
        play = _play(playbook)
        written = _written_files(play)
        assert not [
            args for _, args in written if "caddy.env" in str(args.get("dest", ""))
        ], f"{playbook} must not write a second Caddy environment file"

        overrides = [
            args
            for _, args in written
            if str(args.get("dest", "")).startswith(
                "/etc/systemd/system/caddy.service.d/"
            )
        ]
        assert len(overrides) == 1, (
            f"{playbook} must configure the Caddy environment exactly once"
        )
        content = overrides[0]["content"]
        assert "Environment=DOMAIN_NAME={{ domain_name }}" in content
        assert "Environment=ACME_EMAIL=admin@{{ domain_name }}" in content
        assert "EnvironmentFile" not in content
        assert "COCKTAILDB_DOMAIN" not in (PLAYBOOKS / playbook).read_text(
            encoding="utf-8"
        ), (
            f"{playbook} must take the domain from the inventory, not the ambient "
            "environment"
        )


def _file_args(play):
    """Every (task name, module args) pair for a file task in this play."""
    for task in _tasks(play):
        for module in ("file", "ansible.builtin.file"):
            args = task.get(module)
            if isinstance(args, dict):
                yield task["name"], args


def test_deploy_playbook_does_not_recursively_chown_the_application_home():
    file_args = list(_file_args(_play("deploy.yml")))
    recursive_home = [
        name
        for name, args in file_args
        if args.get("recurse") and str(args.get("path", "")).strip() == "{{ app_home }}"
    ]
    assert recursive_home == [], (
        "a deploy must not reset ownership across every release and backup"
    )
    assert [
        args
        for _, args in file_args
        if args.get("recurse") and "{{ release_root }}" in str(args.get("path", ""))
    ], "the staged release must still be owned by the application user"


def test_deploy_playbook_copies_an_explicit_host_script_set():
    copies = [
        (task, args)
        for task, args in _written_files(_play("deploy.yml"))
        if str(args.get("dest", "")).rstrip("/").endswith("{{ app_home }}/scripts")
    ]
    assert len(copies) == 1
    task, _ = copies[0]
    loop = task.get("loop")
    assert loop, "the host script set must be an explicit list, not a directory copy"
    listed = {Path(str(item)).name for item in loop}
    missing = _referenced_host_scripts() - listed
    assert not missing, f"host scripts referenced but never deployed: {sorted(missing)}"
    assert all((HOST_SCRIPTS / name).is_file() for name in listed)


def test_deploy_entry_point_installs_no_ansible_collections():
    wrapper = (ROOT / "scripts" / "deploy-ec2.sh").read_text(encoding="utf-8")
    assert "ansible-galaxy" not in wrapper, (
        "the deploy entry point must not need the Galaxy API"
    )
    assert not (ANSIBLE / "requirements.yml").exists(), (
        "no task in these playbooks uses a collection"
    )


def test_each_environment_has_one_explicit_inventory():
    assert sorted(p.name for p in (ANSIBLE / "inventory").glob("*.yml")) == [
        "dev.yml",
        "prod.yml",
    ]
    assert "inventory/hosts.yml" not in (ANSIBLE / "ansible.cfg").read_text(
        encoding="utf-8"
    ), "the deploy must not fall back to a second, ambient inventory"
