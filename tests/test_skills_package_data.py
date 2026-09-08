"""Installed-resource coverage for default agent skills."""

from importlib import resources

from astrid.skills import default_pack_ids
from astrid.skills import state


def test_default_hivemind_skill_is_a_package_resource() -> None:
    root = resources.files("astrid")
    skill = root.joinpath("packs", "hivemind", "skill", "SKILL.md")
    manifest = root.joinpath("packs", "hivemind", "pack.yaml")
    assert skill.is_file()
    assert manifest.is_file()


def test_hivemind_is_not_hardcoded_as_a_default_skill() -> None:
    assert "_core" in default_pack_ids()
    # The package resource remains available for compatibility, but the
    # default skill set is source-provisioned rather than inferred from the
    # bundled Hivemind copy.
    assert "hivemind" not in default_pack_ids()


def test_default_uninstall_is_a_durable_opt_out_until_reinstall() -> None:
    data = state.load()
    state.record_install(data, "claude", "hivemind", target="/tmp/hivemind", mechanism="symlink")
    state.record_uninstall(data, "claude", "hivemind", default=True)
    assert data["disabled_defaults"]["claude"] == ["hivemind"]
    state.record_install(data, "claude", "hivemind", target="/tmp/hivemind", mechanism="symlink")
    assert data["disabled_defaults"]["claude"] == []
