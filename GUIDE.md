# dupefind guide

## How a scan works

`scan(*roots, options=None, on_progress=None)` returns a `ScanReport`.
`iter_groups` takes the same arguments and streams `DuplicateGroup` objects
instead. Both read files and never change them.

1. **Walk.** Every root is used as given, even when it is a link. A root may be a
   directory (walked depth first, entries in name order) or a single file. Links
   met during the walk are skipped unless `follow_symlinks=True`. Directories are
   recognised by their real location, so nothing is walked twice.
2. **Size.** Files are grouped by byte size. A unique size cannot have a duplicate,
   so such a file is never opened.
3. **Identity.** Each same-size file is stat'ed again. Two paths that resolve to
   the same location are one entry. Two names with the same device and file id are
   hard links to one file: they are merged into one `DuplicateFile` whose
   `aliases` lists the other names, unless `hardlinks=True`. If the size or
   modification time differs from the walk, the file is reported as `changed`.
4. **Partial hash.** The first `partial_size` bytes are hashed. A file no larger
   than that is now fully hashed and is never read again.
5. **Full hash.** Files still sharing a partial digest are hashed in full. A file
   whose byte count differs from its size while it is read, or whose size or
   modification time changed by the time its group is confirmed, is dropped and
   reported as `changed`.

Groups of larger files are yielded first.

## Options

| Field | Default | Meaning |
| --- | --- | --- |
| `algorithm` | `"sha256"` | Any fixed-size `hashlib` algorithm. The digest is of the whole file. |
| `partial_size` | `4096` | Bytes hashed before any full read. Must be at least 1. |
| `min_size` | `0` | Ignore files smaller than this. |
| `max_size` | `None` | Ignore files larger than this. |
| `include_empty` | `True` | Compare zero-length files (they all form one group). |
| `include` | `()` | Globs; when given, only matching files are compared. |
| `exclude` | `()` | Globs for files and directories to skip. |
| `follow_symlinks` | `False` | Walk into symlinked directories and junctions. |
| `hardlinks` | `False` | List every hard-link name as a separate copy. |

Invalid values raise `ValueError` when the options are built (`TypeError` for a
bare string given as a pattern list).

Glob rules: a pattern without `/` matches the base name; a pattern with `/`
matches the path relative to the root it was found under, written with `/`.
Matching follows the platform case rules, so it is case-insensitive on Windows.

Empty files: fdupes compares them by default, jdupes needs `-z`, and rmlint leaves
them out. `dupefind` keeps its `0.1.0` behaviour and compares them; pass
`include_empty=False` or `min_size=1` (`--no-empty` or `--min-size 1`) before any
clean-up.

## Results

- `DuplicateGroup`: `digest`, `algorithm`, `size`, `files` (sorted by path, at
  least two), `paths`, `wasted_bytes` (size times copies minus one).
- `DuplicateFile`: `path`, `size`, `mtime_ns`, `aliases`.
- `ScanIssue`: `path`, `kind` (`permission`, `missing`, `changed`, `error`),
  `message`. The path is not part of any group.
- `ScanStats`: `files_seen`, `candidates`, `partial_hashed`, `full_hashed`,
  `bytes_read`, `groups`, `duplicate_files`, `wasted_bytes`.
- `Progress`: `stage` (`walk`, `partial`, `full`), `done`, `total`, `bytes_read`.

## Clean-up actions

`plan_actions(groups, action="delete", keep="oldest")` returns `PlannedAction`
items. One file per group survives with its aliases; every other file and every
alias of it gets an action, so a delete frees the space.

A regular file is always preferred as the survivor over a symlink (which can only
appear with `follow_symlinks`), so the real data is what is kept.

| `keep` | Survivor (ties broken by path) |
| --- | --- |
| `first` | first path in sort order |
| `oldest` | oldest modification time |
| `newest` | newest modification time |
| `shortest` | shortest path |

`apply_actions(plan, dry_run=True)` returns one `ActionResult` per item with
`status` `dry-run`, `done`, `skipped` or `failed`. Every item, in a dry run too, is
checked right before it would run:

- the target, looked at without following links, is a regular file of its own:
  a symlink, a junction or a directory found at the target path is refused, so
  with `follow_symlinks` the symlinks in a group are reported but never acted on;
- the target is writable (see read-only files below);
- the kept file exists and is a regular file;
- they are not the same file (same device and file id), so a hard link, junction
  path, symlink or other spelling of the kept file is never removed;
- both still have the planned size;
- for `hardlink`, both are on the same device;
- the two files are equal byte for byte;
- the target is not a kept file anywhere in the plan.

Then, immediately before the delete or the replace, both paths are stat'ed again
and must still show the same device, file id, size, modification time and mode as
the files that were just compared. A target replaced by another file or a link, or
a kept file removed or rewritten in between, is refused. A refusal never touches
either file, so a group always keeps at least the kept copy. The only remaining
window is the few instructions between that last stat and the system call; no
portable file API can close it, which is why the checks are repeated so late.

Read-only files: a target that is read-only (the Windows read-only attribute, or
no owner write bit or no write access on POSIX, such as mode 0444) is `skipped`
with the reason `target is read-only`, for both actions, in a dry run too, and is
left exactly as it was. Clear the flag first if you want it handled. A read-only
kept file is fine: it is only read, and a hard link to it shares its attributes.
If the operating system refuses the act itself (for example a target in a
directory you cannot write to), the result is `failed`; a delete then did not
happen, and a hard link leaves the target unchanged and removes its temporary
name.

`hardlink` links to the real file behind the kept path, creates the new link next
to the target under a temporary name, checks that it is the kept file, and moves it
over the target in one step, so the target name never goes missing.
Windows allows at most 1023 extra hard links per file; beyond that the action
fails and is reported.

Only file contents are compared. Metadata that is not part of the content, such as
permissions, owners, extended attributes or extra NTFS data streams, is not
compared and goes with a removed or replaced copy.

## JSON

`report_to_json(report, actions=None, indent=2)` and `report_to_dict` produce:

```json
{
  "schema": 1,
  "groups": [
    {"digest": "...", "algorithm": "sha256", "size": 6000, "wasted_bytes": 6000,
     "files": [{"path": "a.jpg", "mtime_ns": 0, "aliases": []}]}
  ],
  "issues": [{"path": "...", "kind": "permission", "message": "..."}],
  "stats": {"files_seen": 0, "candidates": 0, "partial_hashed": 0, "full_hashed": 0,
            "bytes_read": 0, "groups": 0, "duplicate_files": 0, "wasted_bytes": 0},
  "actions": null
}
```

`actions` is a list of `{action, target, keep, size, status, reason}` when
actions were planned. `schema` changes only if a field is removed or changes
meaning.

## Command line

```
dupefind PATH [PATH ...] [--json] [--algorithm NAME] [--partial-size N]
         [--min-size N] [--max-size N] [--no-empty] [--include GLOB]...
         [--exclude GLOB]... [--follow-symlinks] [--hardlinks]
         [--delete | --hardlink] [--keep first|oldest|newest|shortest]
         [--apply] [--empty] [-q]
```

With `--delete` or `--hardlink`, empty files are left out unless `--empty` is given
(a plain report still lists them, unless `--no-empty`).

Sizes accept `K`, `M`, `G` and `T` suffixes (powers of 1024). Text output lists
each group as `# SIZE bytes x N files, ALGORITHM:DIGEST`, its paths (aliases
indented with `=`), and a blank line. With `--delete` or `--hardlink` one line per
action follows. Skipped paths and a summary go to stderr unless `-q`. Errors exit
with status 1, as does any failed action. `python -m dupefind` works too.
