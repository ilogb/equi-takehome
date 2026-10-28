"""Sync decisions over FakeDriveSource with in-memory state (no database)."""

from app.sources.base import RemoteChange
from app.sync.service import (
    Action,
    apply_changes,
    decide_change,
    snapshot_folder,
    sync_step,
    walk_folder,
)
from tests.fakes import FakeDriveSource, file, folder

PNG = "image/png"


def tree() -> FakeDriveSource:
    return FakeDriveSource(
        items=[
            folder("root", "Equi Finance Docs"),
            folder("docs", "docs", "root"),
            folder("real", "real", "docs"),
            folder("synth", "synthetic", "docs"),
            file("f1", "man-ahl.pdf", "real"),
            file("f2", "alderbank.csv", "synth", mime="text/csv"),
            file("f3", "top.pdf", "root"),
            file("img", "logo.png", "real", mime=PNG),
            folder("other", "Somewhere else"),
            file("x1", "elsewhere.pdf", "other"),
        ]
    )


class Recorder:
    """Collects files the orchestration would upsert; known ids are ignored like the DB upsert."""

    def __init__(self):
        self.added: dict[str, str] = {}

    def __call__(self, remote, path: str) -> bool:
        self.added[remote.id] = path
        return remote.mime_type != PNG  # unsupported files are stored but not queued


# --- walk ----------------------------------------------------------------------


def test_walk_includes_subfolders_with_paths():
    folders, files = walk_folder(tree(), "root")
    assert folders == {"root", "docs", "real", "synth"}
    paths = {f.id: p for f, p in files}
    assert paths == {
        "f1": "docs/real/man-ahl.pdf",
        "f2": "docs/synthetic/alderbank.csv",
        "f3": "top.pdf",
        "img": "docs/real/logo.png",
    }
    assert "x1" not in paths


def test_token_saved_before_listing():
    src = tree()
    snap = snapshot_folder(src, "root")
    assert snap.page_token == "100"
    assert snap.folder.name == "Equi Finance Docs"
    assert src.calls.index("start_page_token") < src.calls.index("list_children")
    assert {f.id for f, _ in snap.files} == {"f1", "f2", "f3", "img"}
    assert snap.folder_ids == {"root", "docs", "real", "synth"}


# --- decide_change ---------------------------------------------------------------


def ch(item=None, removed_id=None) -> RemoteChange:
    if removed_id:
        return RemoteChange(file_id=removed_id, removed=True, file=None)
    return RemoteChange(file_id=item.id, removed=False, file=item)


def test_decide_new_file_in_set_is_enqueued():
    assert decide_change(ch(file("n", "n.pdf", "real")), {"root", "real"}, set()) is Action.enqueue_new


def test_decide_new_folder_in_set_is_added():
    assert decide_change(ch(folder("sub", "sub", "root")), {"root"}, set()) is Action.add_folder


def test_decide_known_file_is_ignored_edit():
    assert decide_change(ch(file("f1", "renamed.pdf", "real")), {"real"}, {"f1"}) is Action.ignore_known


def test_decide_known_folder_is_ignored():
    assert decide_change(ch(folder("real", "real2", "docs")), {"docs", "real"}, set()) is Action.ignore_known


def test_decide_removed_and_trashed_ignored():
    assert decide_change(ch(removed_id="f1"), {"real"}, {"f1"}) is Action.ignore_removed
    trashed = file("n", "n.pdf", "real", trashed=True)
    assert decide_change(ch(trashed), {"real"}, set()) is Action.ignore_removed
    trashed_folder = folder("sub", "sub", "root")
    trashed_folder = type(trashed_folder)(**{**trashed_folder.__dict__, "trashed": True})
    assert decide_change(ch(trashed_folder), {"root"}, set()) is Action.ignore_removed


def test_decide_outside_ignored():
    assert decide_change(ch(file("x2", "x.pdf", "other")), {"root"}, set()) is Action.ignore_outside
    assert decide_change(ch(folder("o2", "o2", "other")), {"root"}, set()) is Action.ignore_outside


def test_decide_sequence_file_in_subfolder_created_after_selection():
    """Review Focus 1: the folder change grows the set, so the next file change is enqueued."""
    folders, known = {"root"}, set()
    changes = [ch(folder("new", "2026", "root")), ch(file("nf", "q3.pdf", "new"))]
    actions = []
    for c in changes:
        a = decide_change(c, folders, known)
        actions.append(a)
        if a is Action.add_folder:
            folders.add(c.file_id)
        elif a is Action.enqueue_new:
            known.add(c.file_id)
    assert actions == [Action.add_folder, Action.enqueue_new]


# --- apply_changes (poll orchestration, no DB) -------------------------------------


def selected():
    src = tree()
    folders, files = walk_folder(src, "root")
    return src, folders, {f.id for f, _ in files}


def test_poll_picks_up_file_in_new_subfolder():
    src, folders, known = selected()
    src.push_change(folder("new", "2026", "real"))
    src.push_change(file("nf", "q3.pdf", "new"))
    changes, _ = src.list_changes("100")
    rec = Recorder()
    result = apply_changes(src, "root", changes, folders, known, rec)
    assert rec.added == {"nf": "docs/real/2026/q3.pdf"}
    assert result.queued == 1
    assert "new" in folders and "nf" in known


def test_poll_picks_up_files_in_folder_moved_in():
    """A folder moved in with files already inside produces only the folder change."""
    src, folders, known = selected()
    src.items["moved"] = folder("moved", "Archive", "other")
    src.items["m1"] = file("m1", "old.pdf", "moved")
    src.push_change(folder("moved", "Archive", "root"))  # now parented under root
    changes, _ = src.list_changes("100")
    rec = Recorder()
    result = apply_changes(src, "root", changes, folders, known, rec)
    assert rec.added == {"m1": "Archive/old.pdf"}
    assert result.queued == 1
    assert "moved" in folders


def test_poll_ignores_other_folders():
    src, folders, known = selected()
    src.push_change(file("x2", "x.pdf", "other"))
    src.push_change(folder("o2", "o2", "other"))
    changes, _ = src.list_changes("100")
    rec = Recorder()
    result = apply_changes(src, "root", changes, folders, known, rec)
    assert rec.added == {}
    assert (result.queued, result.ignored) == (0, 2)


def test_poll_ignores_edits_and_deletes():
    src, folders, known = selected()
    src.push_change(file("f1", "man-ahl-v2.pdf", "real"))  # edit in place
    src.push_change(file("f2", "alderbank.csv", "synth", mime="text/csv", trashed=True))
    src.push_change(removed_id="f3")
    changes, _ = src.list_changes("100")
    rec = Recorder()
    result = apply_changes(src, "root", changes, folders, known, rec)
    assert rec.added == {}
    assert (result.queued, result.ignored) == (0, 3)


def test_poll_unsupported_new_file_stored_not_queued():
    src, folders, known = selected()
    src.push_change(file("p2", "chart.png", "root", mime=PNG))
    changes, _ = src.list_changes("100")
    rec = Recorder()
    result = apply_changes(src, "root", changes, folders, known, rec)
    assert rec.added == {"p2": "chart.png"}
    assert (result.queued, result.ignored) == (0, 1)


def test_poll_same_new_file_twice_in_one_batch_queued_once():
    src, folders, known = selected()
    src.push_change(file("nf", "q3.pdf", "root"))
    src.push_change(file("nf", "q3-renamed.pdf", "root"))
    changes, _ = src.list_changes("100")
    rec = Recorder()
    result = apply_changes(src, "root", changes, folders, known, rec)
    assert list(rec.added) == ["nf"]
    assert (result.queued, result.ignored) == (1, 1)


def test_token_advances_non_contiguously():
    src = tree()
    _, nxt = src.list_changes("100")
    assert nxt == "103"


# --- sync_step: token handling and 410 ------------------------------------------------


def test_sync_step_takes_token_from_response():
    src, folders, known = selected()
    src.push_change(file("nf", "q3.pdf", "root"))
    token, result = sync_step(src, "root", "100", folders, known, Recorder())
    assert token == "103"
    assert result.queued == 1


def test_410_rewalks():
    src, folders, known = selected()
    src.expired_tokens.add("100")
    src.items["late"] = file("late", "late.pdf", "synth")  # appeared while the token was dead
    src.items["f1"] = file("f1", "man-ahl-edited.pdf", "real")  # known: not re-added
    src.calls.clear()
    rec = Recorder()
    token, result = sync_step(src, "root", "100", folders, known, rec)
    assert rec.added == {"late": "docs/synthetic/late.pdf"}
    assert result.queued == 1
    assert token == "100"  # fresh start token, taken before the re-walk
    assert src.calls.index("start_page_token") < src.calls.index("list_children")
    assert "late" in known


def test_select_rejects_a_file():
    import pytest

    src = tree()
    with pytest.raises(ValueError):
        snapshot_folder(src, "f1")
    assert "start_page_token" not in src.calls


def test_poll_new_file_in_existing_subfolder_gets_full_path():
    src, folders, known = selected()
    src.push_change(file("nf", "q3.csv", "synth", mime="text/csv"))
    changes, _ = src.list_changes("100")
    rec = Recorder()
    apply_changes(src, "root", changes, folders, known, rec)
    assert rec.added == {"nf": "docs/synthetic/q3.csv"}


# --- fix round 1: folders leaving the tree ------------------------------------------


def test_decide_watched_folder_leaving_tree():
    folders = {"root", "docs", "real"}
    moved_out = folder("real", "real", "other")
    assert decide_change(ch(moved_out), folders, set(), root_id="root") is Action.remove_folder
    trashed = type(moved_out)(**{**folder("real", "real", "docs").__dict__, "trashed": True})
    assert decide_change(ch(trashed), folders, set(), root_id="root") is Action.remove_folder
    assert decide_change(ch(removed_id="real"), folders, set(), root_id="root") is Action.remove_folder
    # the root itself never leaves the set
    assert decide_change(ch(folder("root", "R", "elsewhere")), folders, set(), root_id="root") is Action.ignore_known
    # moved within the tree: still watched
    assert decide_change(ch(folder("real", "real", "root")), folders, set(), root_id="root") is Action.ignore_known


def test_folder_moved_out_then_new_file_in_it_not_enqueued():
    src, folders, known = selected()
    src.push_change(folder("docs", "docs", "other"))  # docs (with real, synthetic) moved out
    src.push_change(file("nf", "late.pdf", "real"))  # new file in a folder no longer watched
    changes, _ = src.list_changes("100")
    rec = Recorder()
    result = apply_changes(src, "root", changes, folders, known, rec)
    assert rec.added == {}
    assert folders == {"root"}
    assert (result.queued, result.ignored) == (0, 2)


def test_folder_moved_out_then_back_in_is_watched_again():
    src, folders, known = selected()
    src.push_change(folder("synth", "synthetic", "other"))
    src.push_change(folder("synth", "synthetic", "root"))
    src.push_change(file("nf", "q.pdf", "synth"))
    changes, _ = src.list_changes("100")
    rec = Recorder()
    apply_changes(src, "root", changes, folders, known, rec)
    assert rec.added == {"nf": "synthetic/q.pdf"}
    assert "synth" in folders
