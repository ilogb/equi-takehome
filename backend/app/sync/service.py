"""Folder selection and change polling.

The decisions are pure (`decide_change`, `walk_folder`, `apply_changes`, `sync_step`) and
work against any DocumentSource with in-memory sets; `select_folder`, `initial_sync` and
`poll_changes` are the thin database layer around them.

Q24: a file already known is never re-queued (edits in place are ignored) and removals,
trashing and moves out are ignored. A11: every folder below the chosen one is watched.
"""

import enum
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.jobs.queue import enqueue
from app.models import FileStatus, Fund, FundAlias, SourceFile, User, WatchedFolder
from app.pipeline.detect import kind_for
from app.sources.base import DocumentSource, PageTokenExpired, ReconnectRequired, RemoteChange, RemoteFile, SourceError

log = logging.getLogger("sync")

# Called with a newly seen file and its path relative to the chosen folder.
# Returns True if it was queued for processing, False if stored as unsupported.
AddFile = Callable[[RemoteFile, str], bool]


class Action(enum.Enum):
    enqueue_new = "enqueue_new"
    add_folder = "add_folder"
    remove_folder = "remove_folder"
    ignore_known = "ignore_known"
    ignore_removed = "ignore_removed"
    ignore_outside = "ignore_outside"


@dataclass
class SyncResult:
    queued: int = 0
    ignored: int = 0


@dataclass
class FolderSnapshot:
    folder: RemoteFile
    page_token: str
    folder_ids: set[str]
    files: list[tuple[RemoteFile, str]]


def decide_change(
    change: RemoteChange, folder_ids: set[str], known_file_ids: set[str], root_id: str | None = None
) -> Action:
    """What one Drive change means for the watched tree (`folder_ids` includes the root).

    A watched folder (other than the root) that is removed, trashed or moved out of the tree
    leaves the set, so files dropped into it later are not picked up. Its existing file rows
    stay (Q24).
    """
    f = change.file
    gone = change.removed or f is None or f.trashed
    if change.file_id in folder_ids and change.file_id != root_id:
        if gone or not folder_ids.intersection(f.parents):
            return Action.remove_folder
        return Action.ignore_known
    if gone:
        return Action.ignore_removed
    if change.file_id in known_file_ids or change.file_id in folder_ids:
        return Action.ignore_known
    if not folder_ids.intersection(f.parents):
        return Action.ignore_outside
    return Action.add_folder if f.is_folder else Action.enqueue_new


def _join(prefix: str, name: str) -> str:
    return f"{prefix}/{name}" if prefix else name


def walk_folder(
    source: DocumentSource, root_id: str, prefix: str = ""
) -> tuple[set[str], list[tuple[RemoteFile, str]]]:
    """Every folder id below (and including) `root_id`, and every file with its relative path.

    Drive's files.list returns direct children only, so each subfolder is listed in turn.
    """
    folder_ids: set[str] = set()
    files: list[tuple[RemoteFile, str]] = []
    stack = [(root_id, prefix)]
    while stack:
        fid, path = stack.pop()
        if fid in folder_ids:  # a folder can have several parents; never list it twice
            continue
        folder_ids.add(fid)
        for child in sorted(source.list_children(fid), key=lambda c: c.name):
            if child.is_folder:
                stack.append((child.id, _join(path, child.name)))
            else:
                files.append((child, _join(path, child.name)))
    return folder_ids, files


def snapshot_folder(source: DocumentSource, folder_id: str) -> FolderSnapshot:
    """Read a folder for selection. The change token is taken BEFORE listing, so a file
    added while the tree is walked shows up in the first poll instead of being lost."""
    folder = source.get_folder(folder_id)
    if not folder.is_folder or folder.trashed:
        raise ValueError("not a folder")
    token = source.start_page_token()
    folder_ids, files = walk_folder(source, folder_id)
    return FolderSnapshot(folder=folder, page_token=token, folder_ids=folder_ids, files=files)


def _add_unseen(files: list[tuple[RemoteFile, str]], known: set[str], add_file: AddFile, result: SyncResult) -> None:
    for remote, path in files:
        if remote.id in known:
            continue
        known.add(remote.id)
        if add_file(remote, path):
            result.queued += 1
        else:
            result.ignored += 1


def _folder_path(
    source: DocumentSource, folder_id: str, folder_ids: set[str], cache: dict[str, str]
) -> str:
    """Path of a watched folder relative to the root (`cache` starts as {root_id: ""}),
    resolved by walking up its parents inside the watched set."""
    names: list[tuple[str, str]] = []
    current: str | None = folder_id
    base = ""
    while current is not None:
        if current in cache:
            base = cache[current]
            break
        if any(current == fid for fid, _ in names):  # cycle guard
            break
        try:
            meta = source.get_folder(current)
        except SourceError as err:
            if err.status != 404:
                raise
            break  # folder vanished mid-poll: keep the file, with the part of the path we know
        names.append((current, meta.name))
        current = next((p for p in meta.parents if p in folder_ids), None)
    path = base
    for fid, name in reversed(names):
        path = _join(path, name)
        cache[fid] = path
    return cache.get(folder_id, path)


def apply_changes(
    source: DocumentSource,
    root_id: str,
    changes: list[RemoteChange],
    folder_ids: set[str],
    known_file_ids: set[str],
    add_file: AddFile,
) -> SyncResult:
    """Apply a batch of changes in order, growing `folder_ids` and `known_file_ids` in place.

    A folder that appears under the tree is walked at once: a folder moved in brings its
    existing files without producing a change for each of them.
    """
    result = SyncResult()
    paths: dict[str, str] = {root_id: ""}
    for change in changes:
        action = decide_change(change, folder_ids, known_file_ids, root_id)
        f = change.file
        if action is Action.add_folder:
            assert f is not None
            parent = next(p for p in f.parents if p in folder_ids)
            prefix = _join(_folder_path(source, parent, folder_ids, paths), f.name)
            paths[f.id] = prefix
            sub_folders, sub_files = walk_folder(source, f.id, prefix)
            folder_ids.update(sub_folders)
            _add_unseen(sub_files, known_file_ids, add_file, result)
        elif action is Action.remove_folder:
            # Drop it and everything under it: re-walk the folders from the root. Files found
            # by the walk are not added here; new ones arrive as their own changes.
            walked, _ = walk_folder(source, root_id)
            folder_ids.intersection_update(walked)
            paths = {k: v for k, v in paths.items() if k in folder_ids}
            result.ignored += 1
        elif action is Action.enqueue_new:
            assert f is not None
            parent = next(p for p in f.parents if p in folder_ids)
            path = _join(_folder_path(source, parent, folder_ids, paths), f.name)
            _add_unseen([(f, path)], known_file_ids, add_file, result)
        else:
            result.ignored += 1
    return result


def sync_step(
    source: DocumentSource,
    root_id: str,
    token: str,
    folder_ids: set[str],
    known_file_ids: set[str],
    add_file: AddFile,
) -> tuple[str, SyncResult]:
    """One poll. Returns the next page token, always the one Drive handed back.

    On 410 (token no longer valid) a fresh token is taken first, then the tree is re-walked
    and files not seen before are added; known files stay ignored.
    """
    try:
        changes, next_token = source.list_changes(token)
    except PageTokenExpired:
        log.warning("page token expired; re-walking folder")
        snap_token = source.start_page_token()
        walked_folders, files = walk_folder(source, root_id)
        folder_ids.clear()
        folder_ids.update(walked_folders)
        result = SyncResult()
        _add_unseen(files, known_file_ids, add_file, result)
        return snap_token, result
    return next_token, apply_changes(source, root_id, changes, folder_ids, known_file_ids, add_file)


# --- database layer ------------------------------------------------------------------------


def status_for(remote: RemoteFile) -> FileStatus:
    return FileStatus.queued if kind_for(remote.mime_type, remote.name) else FileStatus.unsupported


def _file_adder(session: Session, user: User) -> AddFile:
    def add(remote: RemoteFile, path: str) -> bool:
        status = status_for(remote)
        row = SourceFile(
            user_id=user.id,
            drive_file_id=remote.id,
            name=remote.name,
            path=path,
            mime_type=remote.mime_type,
            status=status.value,
            error="unsupported file type" if status is FileStatus.unsupported else None,
        )
        session.add(row)
        session.flush()
        if status is FileStatus.queued:
            enqueue(session, row.id)
            return True
        return False

    return add


def _known_ids(session: Session, user: User) -> set[str]:
    return set(session.scalars(select(SourceFile.drive_file_id).where(SourceFile.user_id == user.id)))


def initial_sync(session: Session, user: User, files: list[tuple[RemoteFile, str]]) -> SyncResult:
    """Upsert a row for every file below the folder; queue the supported ones."""
    result = SyncResult()
    _add_unseen(files, _known_ids(session, user), _file_adder(session, user), result)
    return result


def select_folder(session: Session, user: User, source: DocumentSource, folder_id: str) -> WatchedFolder:
    """Watch `folder_id` for `user`. Changing to a different folder deletes that user's files
    (and, by cascade, documents, rows, chunks and jobs) and funds first."""
    snap = snapshot_folder(source, folder_id)  # token first, then the walk
    watched = session.scalar(select(WatchedFolder).where(WatchedFolder.user_id == user.id).with_for_update())
    if watched is not None and watched.drive_folder_id != folder_id:
        # Cascades to documents, rows, tables, chunks and jobs; funds are per user, so go too.
        session.execute(delete(SourceFile).where(SourceFile.user_id == user.id))
        session.execute(delete(FundAlias).where(FundAlias.user_id == user.id))
        session.execute(delete(Fund).where(Fund.user_id == user.id))
    if watched is None:
        watched = WatchedFolder(user_id=user.id, drive_folder_id=folder_id, name=snap.folder.name)
        session.add(watched)
    watched.drive_folder_id = folder_id
    watched.name = snap.folder.name
    watched.page_token = snap.page_token
    watched.descendant_ids = sorted(snap.folder_ids - {folder_id})
    watched.last_error = None
    initial_sync(session, user, snap.files)
    watched.last_synced_at = datetime.now(UTC)
    session.flush()
    return watched


def poll_changes(session: Session, user: User, source: DocumentSource) -> SyncResult:
    """Pull Drive changes for the user's watched folder and queue new files below it.

    The folder row is locked so the background poller and "Sync now" never apply the same
    token twice.
    """
    watched = session.scalar(select(WatchedFolder).where(WatchedFolder.user_id == user.id).with_for_update())
    if watched is None:
        return SyncResult()
    root = watched.drive_folder_id
    folder_ids = {root, *watched.descendant_ids}
    known = _known_ids(session, user)
    token = watched.page_token or source.start_page_token()
    next_token, result = sync_step(source, root, token, folder_ids, known, _file_adder(session, user))
    watched.page_token = next_token
    watched.descendant_ids = sorted(folder_ids - {root})
    watched.last_synced_at = datetime.now(UTC)
    watched.last_error = None
    session.flush()
    return result


MakeSource = Callable[[Session, User], DocumentSource]


def poll_user(session: Session, user: User, make_source: MakeSource) -> SyncResult:
    """Poll one user and commit. On failure the work is rolled back, the error is recorded on
    the folder (and `needs_reconnect` set for a revoked grant), committed, and re-raised."""
    try:
        source = make_source(session, user)
        with session.begin_nested():
            result = poll_changes(session, user, source)
        session.commit()
        return result
    except Exception as err:
        session.rollback()
        user = session.get(User, user.id) or user
        if isinstance(err, ReconnectRequired):
            user.needs_reconnect = True
        watched = session.scalar(select(WatchedFolder).where(WatchedFolder.user_id == user.id))
        if watched is not None:
            watched.last_error = str(err) or type(err).__name__
        session.commit()
        raise


def poll_all(session: Session, make_source: MakeSource) -> None:
    """Background poll: every user with a folder, skipping users who must reconnect.
    One user's failure never stops the others."""
    users = session.scalars(
        select(User)
        .join(WatchedFolder, WatchedFolder.user_id == User.id)
        .where(User.needs_reconnect.is_(False))
        .order_by(User.id)
    ).all()
    for user in users:
        try:
            result = poll_user(session, user, make_source)
            if result.queued:
                log.info("user %s: %d file(s) queued", user.id, result.queued)
        except ReconnectRequired:
            log.warning("user %s must reconnect Google; polling paused", user.id)
        except Exception as err:
            log.warning("poll failed for user %s: %s", user.id, err)
