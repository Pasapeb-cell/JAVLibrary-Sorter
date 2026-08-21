from javsorter.organize.journal import RunJournal, latest_journal, undo


def _make_file(path, content=b"video"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_journal_roundtrip(tmp_path):
    journal = RunJournal(library_root=str(tmp_path / "Library"))
    journal.record_move(tmp_path / "a.mp4", tmp_path / "Library" / "ABC-123" / "ABC-123.mp4")
    journal.record_created_file(tmp_path / "Library" / "ABC-123" / "ABC-123.nfo")
    journal.record_created_link(tmp_path / "Library" / "Actress" / "X" / "ABC-123.mp4")

    saved = journal.save(tmp_path / "runs")
    loaded = RunJournal.load(saved)

    assert len(loaded.entries) == 3
    assert loaded.library_root == journal.library_root


def test_journal_ignores_a_move_that_did_not_move(tmp_path):
    journal = RunJournal()
    same = tmp_path / "ABC-123.mp4"

    journal.record_move(same, same)

    assert journal.is_empty()


def test_undo_restores_moved_file(tmp_path):
    source = _make_file(tmp_path / "source" / "messy@ABC-123.mp4")
    destination = tmp_path / "Library" / "ABC-123" / "ABC-123.mp4"
    destination.parent.mkdir(parents=True)
    source.replace(destination)

    journal = RunJournal(library_root=str(tmp_path / "Library"))
    journal.record_move(source, destination)

    report = undo(journal)

    assert report.files_restored == 1
    assert source.exists()
    assert not destination.exists()


def test_undo_deletes_generated_files(tmp_path):
    nfo = _make_file(tmp_path / "Library" / "ABC-123" / "ABC-123.nfo", b"<movie/>")
    journal = RunJournal(library_root=str(tmp_path / "Library"))
    journal.record_created_file(nfo)

    report = undo(journal)

    assert report.files_removed == 1
    assert not nfo.exists()


def test_undo_leaves_a_preexisting_file_alone(tmp_path):
    """A file that already existed is never recorded as created, so undo
    must not delete it -- we could not restore its old contents.
    """
    existing = _make_file(tmp_path / "Library" / "ABC-123" / "ABC-123.nfo", b"mine")
    journal = RunJournal(library_root=str(tmp_path / "Library"))
    # Deliberately not recorded.

    undo(journal)

    assert existing.exists()
    assert existing.read_bytes() == b"mine"


def test_undo_will_not_clobber_something_at_the_original_location(tmp_path):
    source = _make_file(tmp_path / "source" / "ABC-123.mp4", b"new file here now")
    destination = _make_file(tmp_path / "Library" / "ABC-123" / "ABC-123.mp4", b"moved one")

    journal = RunJournal(library_root=str(tmp_path / "Library"))
    journal.record_move(source, destination)

    report = undo(journal)

    assert report.files_restored == 0
    assert report.failures
    assert source.read_bytes() == b"new file here now"
    assert destination.exists()


def test_undo_removes_symlinks_without_touching_their_targets(tmp_path):
    import os

    target = _make_file(tmp_path / "Library" / "ABC-123" / "ABC-123.mp4")
    link = tmp_path / "Library" / "Actress" / "Someone" / "ABC-123.mp4"
    link.parent.mkdir(parents=True)
    try:
        os.symlink(target, link)
    except OSError:
        import pytest

        pytest.skip("symlink creation not permitted in this environment")

    journal = RunJournal(library_root=str(tmp_path / "Library"))
    journal.record_created_link(link)

    report = undo(journal)

    assert report.links_removed == 1
    assert not link.exists()
    assert target.exists()


def test_undo_prunes_emptied_directories(tmp_path):
    library = tmp_path / "Library"
    source = tmp_path / "source" / "ABC-123.mp4"
    source.parent.mkdir(parents=True)
    destination = _make_file(library / "ABC-123" / "ABC-123.mp4")

    journal = RunJournal(library_root=str(library))
    journal.record_move(source, destination)

    undo(journal)

    assert not library.exists()


def test_latest_journal_picks_the_newest(tmp_path):
    runs = tmp_path / "runs"
    RunJournal(started_at="2026-01-01T10-00-00").save(runs)
    newest = RunJournal(started_at="2026-06-01T10-00-00").save(runs)

    assert latest_journal(runs) == newest


def test_latest_journal_when_none_exist(tmp_path):
    assert latest_journal(tmp_path / "nope") is None
