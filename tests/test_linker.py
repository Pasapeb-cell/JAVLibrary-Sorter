import os

from javsorter.organize.linker import SymlinkCapability, create_symlink, probe_symlink_capability


def test_probe_symlink_capability_reports_a_known_state(tmp_path):
    # This dev environment may or may not have symlink privileges
    # (Windows Developer Mode / admin) -- both are legitimate outcomes.
    assert probe_symlink_capability(tmp_path) in (SymlinkCapability.OK, SymlinkCapability.DENIED)


def test_create_symlink_success_or_documented_permission_failure(tmp_path):
    target = tmp_path / "target.mp4"
    target.write_bytes(b"")
    link_path = tmp_path / "Category" / "value" / "target.mp4"

    result = create_symlink(target, link_path)

    if result.success:
        assert link_path.is_symlink()
        assert link_path.resolve() == target.resolve()
    else:
        # Never silently fall back to a hardlink/copy -- the failure must
        # be reported as a permission error, and nothing left on disk.
        assert result.is_permission_error is True
        assert not link_path.exists()


def test_create_symlink_reports_permission_error_flag(tmp_path, monkeypatch):
    target = tmp_path / "target.mp4"
    target.write_bytes(b"")
    link_path = tmp_path / "link.mp4"

    def _raise_permission_denied(*args, **kwargs):
        error = OSError("A required privilege is not held by the client")
        error.winerror = 1314
        raise error

    monkeypatch.setattr(os, "symlink", _raise_permission_denied)

    result = create_symlink(target, link_path)

    assert result.success is False
    assert result.is_permission_error is True


def test_create_symlink_other_os_error_is_not_flagged_as_permission(tmp_path, monkeypatch):
    target = tmp_path / "target.mp4"
    target.write_bytes(b"")
    link_path = tmp_path / "link.mp4"

    def _raise_other_error(*args, **kwargs):
        error = OSError("Disk full")
        error.winerror = 112
        raise error

    monkeypatch.setattr(os, "symlink", _raise_other_error)

    result = create_symlink(target, link_path)

    assert result.success is False
    assert result.is_permission_error is False
