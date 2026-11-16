import re

from webserver.constants import CALIBRE_COLUMN_FOLDER

FOLDER_SEP = "."
MAX_DEPTH = 2
MAX_SEGMENT_LEN = 24
CLEAR_WORDS = ("清除", "clear")
_SEGMENT_RE = re.compile(r"^[^\W_]+$")


def normalize_segment(name):
    name = (name or "").strip()
    if not name or len(name) > MAX_SEGMENT_LEN or not _SEGMENT_RE.match(name):
        raise ValueError("invalid folder name")
    return name


def split_folder(value):
    value = (value or "").strip()
    return value.split(FOLDER_SEP) if value else []


def normalize_folder(raw):
    """Validate a folder path and return it; empty (or a clear word) means root."""
    raw = (raw or "").strip()
    if not raw or raw.lower() in CLEAR_WORDS:
        return ""
    parts = raw.split(FOLDER_SEP)
    if len(parts) > MAX_DEPTH:
        raise ValueError("folder too deep")
    return FOLDER_SEP.join(normalize_segment(p) for p in parts)


def folder_table(cache):
    """Return Calibre's in-memory table of #folder, or None if the column is missing."""
    field = cache.fields.get(CALIBRE_COLUMN_FOLDER)
    return field.table if field is not None else None


def folder_counts(cache):
    """Return {folder value: number of books directly in it}."""
    table = folder_table(cache)
    if table is None:
        return {}
    return {v: len(table.col_book_map.get(i, ())) for i, v in table.id_map.items()}


def folder_counts_for(cache, visible_ids):
    """Return {folder value: number of books directly in it} restricted to visible_ids.

    与 folder_counts 同口径（按完整路径逐本计数），但只数 visible_ids 里的书。
    用于阅读范围受限用户：左侧目录树每级的 (N) 必须按「他真正读得到的书」重算，
    否则会出现「目录显示 128 本，点进去只有 12 本」的口径漂移。
    """
    table = folder_table(cache)
    if table is None or not visible_ids:
        return {}
    # #folder 是单值列：一本书只属于一个目录值，先建 book_id → 目录值 的正向映射。
    book_to_value = {}
    for i, v in table.id_map.items():
        for bid in table.col_book_map.get(i, ()):
            book_to_value[bid] = v
    result = {}
    for bid in visible_ids:
        v = book_to_value.get(bid)
        if v:
            result[v] = result.get(v, 0) + 1
    return result


def top_level_count(counts):
    return len({split_folder(v)[0] for v, n in counts.items() if v and n > 0})


def build_tree(counts):
    """Build nested [{name, count, children}] from direct counts; count includes sub-folders."""
    root = {"children": {}}
    for value, n in counts.items():
        parts = split_folder(value)
        if not parts or n <= 0:
            continue
        node = root
        for part in parts:
            node = node["children"].setdefault(part, {"name": part, "count": 0, "children": {}})
            node["count"] += n

    def finish(children):
        return [{"name": c["name"], "count": c["count"], "children": finish(c["children"])} for _, c in sorted(children.items())]

    return finish(root["children"])


def find_children(tree, parent_parts):
    """Return the child nodes under the folder given as a list of segments."""
    nodes = tree
    for part in parent_parts:
        nodes = next((n["children"] for n in nodes if n["name"] == part), [])
    return nodes


def candidate_names(tree, parent_parts):
    """Suggest folder names for the level after parent_parts: its children, else every name used at that level."""
    nodes = find_children(tree, parent_parts)
    if not nodes:
        level_nodes = tree
        for _ in parent_parts:
            level_nodes = [c for n in level_nodes for c in n["children"]]
        nodes = level_nodes
    merged = {}
    for n in nodes:
        merged[n["name"]] = merged.get(n["name"], 0) + n["count"]
    return sorted(merged.items(), key=lambda kv: (-kv[1], kv[0]))


def plan_rename(values, path, name):
    """Return {old value: new value} for path and its sub-folders after renaming its last segment."""
    parts = path.split(FOLDER_SEP)
    new_path = FOLDER_SEP.join(parts[:-1] + [name])
    plan = {}
    for v in values:
        if v == path or v.startswith(path + FOLDER_SEP):
            plan[v] = new_path + v[len(path):]
    return plan
