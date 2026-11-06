#!/usr/bin/env python3
"""audiobook 数据备份核心逻辑（P0）

一般由 scripts/backup.sh 调用，不直接手写参数：

    python3 scripts/backup_run.py \
        --data /volume1/docker/audiobook-data \
        --backup /volume1/docker/audiobook-backup \
        --exclude-dirs cache,log,.backup-tmp \
        --exclude-patterns '*.tmp,*.part,*.partial,*.swp' \
        --keep-daily 7 --keep-weekly 4 --keep-monthly 6

设计要点：
* 数据库走 SQLite 官方在线备份 API（sqlite3.Connection.backup），
  站点运行中也能拿到一致快照；只有容器已停止时才允许回退为文件冷拷贝。
* 书库/音频走「硬链接快照」：每份快照都是完整的目录树，未变化文件与
  上一份共享 inode，因此既省空间，又能直接整目录恢复（等价 rsync --link-dest）。
* 只依赖 Python 3.8+ 标准库，NAS 上不需要装 rsync / sqlite3 命令行。
* 任何一步失败都不会删除上一份可用快照；失败的快照目录会被清理掉。
"""

import argparse
import fnmatch
import hashlib
import json
import os
import shutil
import sqlite3
import stat
import sys
import time
from datetime import datetime

TS_FMT = "%Y%m%d-%H%M%S"
GB = 1024 ** 3

# 需要在线备份的数据库（相对 data 目录）
DATABASES = [
    ("books/calibre-webserver.db", "webserver.db"),
    ("books/library/metadata.db", "calibre-metadata.db"),
]


class BackupError(Exception):
    pass


def log(msg):
    print("[backup] " + msg, flush=True)


def parse_ts(name):
    return datetime.strptime(name, TS_FMT)


def valid_ts(name):
    try:
        parse_ts(name)
        return True
    except ValueError:
        return False


def human(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return "%.1f%s" % (n, unit) if unit != "B" else "%dB" % n
        n /= 1024.0


def sha256_file(path, buf_size=1024 * 1024):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(buf_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------
# 数据库备份
# --------------------------------------------------------------------------
def _cold_copy(src, dst):
    """容器已停止时的兜底：db / -wal / -shm 一起拷，保持一致性。"""
    for suffix in ("", "-wal", "-shm"):
        s = src + suffix
        if os.path.exists(s):
            shutil.copy2(s, dst + suffix)


def backup_one_db(src, dst, allow_cold_copy):
    info = {"source": src, "dest": dst}
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    t0 = time.time()
    try:
        src_conn = sqlite3.connect(src, timeout=60)
        try:
            src_conn.execute("PRAGMA busy_timeout=60000")
            dst_conn = sqlite3.connect(dst)
            try:
                src_conn.backup(dst_conn)
            finally:
                dst_conn.close()
        finally:
            src_conn.close()
        info["method"] = "sqlite-backup-api"
    except Exception as exc:
        if not allow_cold_copy:
            raise BackupError("在线备份失败（容器可能在写入）：%s" % exc)
        log("在线备份失败（%s），回退为文件冷拷贝（须确认容器已停止）" % exc)
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(dst + suffix):
                os.remove(dst + suffix)
        _cold_copy(src, dst)
        info["method"] = "cold-file-copy"

    # 校验副本可打开且结构完整
    conn = sqlite3.connect(dst)
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        try:
            tables = conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table'"
            ).fetchone()[0]
        except sqlite3.Error:
            tables = None
        try:
            books = conn.execute("SELECT count(*) FROM books").fetchone()[0]
        except sqlite3.Error:
            books = None
    finally:
        conn.close()

    info.update({
        "bytes": os.path.getsize(dst),
        "sha256": sha256_file(dst),
        "integrity": integrity,
        "tables": tables,
        "books": books,
        "seconds": round(time.time() - t0, 2),
        "status": "ok" if integrity == "ok" else "integrity-failed",
    })
    if integrity != "ok":
        log("!! %s 完整性校验失败: %s" % (src, integrity))
    else:
        log("数据库已备份: %s -> %s（%s，%s）"
            % (src, dst, human(info["bytes"]), info["method"]))
    return info


# --------------------------------------------------------------------------
# 文件快照（硬链接增量）
# --------------------------------------------------------------------------
def _excluded_dir(rel, exclude_dirs):
    if not exclude_dirs:
        return False
    return any(part in exclude_dirs for part in rel.split("/"))


def _excluded_file(name, patterns):
    return any(fnmatch.fnmatch(name, p) for p in patterns)


def _copy_file(src, dst, st, root_owned):
    shutil.copy2(src, dst, follow_symlinks=False)
    if root_owned:
        try:
            os.chown(dst, st.st_uid, st.st_gid, follow_symlinks=False)
        except OSError:
            pass


def latest_snapshot(root):
    if not os.path.isdir(root):
        return None
    names = sorted(n for n in os.listdir(root) if valid_ts(n))
    return os.path.join(root, names[-1]) if names else None


def snapshot_files(data_dir, dst_root, exclude_dirs, exclude_patterns):
    prev_root = latest_snapshot(os.path.dirname(dst_root))
    if os.path.exists(dst_root):
        raise BackupError("目标快照目录已存在: %s" % dst_root)

    stats = {
        "files": 0, "dirs": 0, "hardlinked": 0, "copied": 0,
        "bytes_copied": 0, "symlinks": 0, "skipped_special": 0,
        "errors": [],
        "prev": prev_root,
        "hardlink_unsupported": False,
    }
    root_owned = hasattr(os, "geteuid") and os.geteuid() == 0
    dir_modes = []

    os.makedirs(dst_root)
    stack = [""]
    t0 = time.time()
    while stack:
        rel = stack.pop()
        src_dir = os.path.join(data_dir, rel) if rel else data_dir
        dst_dir = os.path.join(dst_root, rel) if rel else dst_root
        try:
            with os.scandir(src_dir) as it:
                entries = sorted(it, key=lambda e: e.name)
        except OSError as exc:
            stats["errors"].append("%s: %s" % (src_dir, exc))
            continue

        for entry in entries:
            relpath = entry.name if not rel else rel + "/" + entry.name
            src_path = os.path.join(data_dir, relpath)
            dst_path = os.path.join(dst_root, relpath)
            try:
                st = entry.stat(follow_symlinks=False)
            except OSError as exc:
                stats["errors"].append("%s: %s" % (src_path, exc))
                continue

            if stat.S_ISDIR(st.st_mode):
                if _excluded_dir(relpath, exclude_dirs):
                    continue
                os.makedirs(dst_path, exist_ok=True)
                dir_modes.append((dst_path, st.st_mode))
                stats["dirs"] += 1
                stack.append(relpath)
                continue

            if _excluded_file(entry.name, exclude_patterns):
                continue

            if stat.S_ISLNK(st.st_mode):
                try:
                    os.symlink(os.readlink(src_path), dst_path)
                    stats["symlinks"] += 1
                except OSError as exc:
                    stats["errors"].append("%s: %s" % (src_path, exc))
                continue

            if not stat.S_ISREG(st.st_mode):
                stats["skipped_special"] += 1
                continue

            prev_path = os.path.join(prev_root, relpath) if prev_root else None
            linked = False
            if prev_path and os.path.isfile(prev_path) and not os.path.islink(prev_path):
                try:
                    pst = os.stat(prev_path, follow_symlinks=False)
                    if pst.st_size == st.st_size and pst.st_mtime_ns == st.st_mtime_ns:
                        os.link(prev_path, dst_path)
                        stats["hardlinked"] += 1
                        linked = True
                except OSError as exc:
                    # 硬链接不可用（exFAT 等）或跨设备，退回复制
                    if exc.errno in (1, 18, 95):  # EPERM / EXDEV / EOPNOTSUPP
                        stats["hardlink_unsupported"] = True

            if not linked:
                try:
                    _copy_file(src_path, dst_path, st, root_owned)
                    stats["copied"] += 1
                    stats["bytes_copied"] += st.st_size
                except OSError as exc:
                    stats["errors"].append("%s: %s" % (src_path, exc))

            stats["files"] += 1
            if stats["files"] % 2000 == 0:
                log("已处理 %d 个文件，复制 %s"
                    % (stats["files"], human(stats["bytes_copied"])))

    # 目录权限最后统一补（先建目录后建文件，只有最后设置才不会被覆盖）
    for path, mode in dir_modes:
        try:
            os.chmod(path, stat.S_IMODE(mode))
        except OSError:
            pass

    stats["seconds"] = round(time.time() - t0, 2)
    if stats["hardlink_unsupported"]:
        log("!! 备份目录不支持硬链接（可能是 exFAT/FAT），本次退化为全量复制，"
            "空间占用会显著增大")
    log("文件快照完成：%d 个文件、%d 个目录，复制 %d 个（%s），"
        "硬链接复用 %d 个，耗时 %.1fs"
        % (stats["files"], stats["dirs"], stats["copied"],
           human(stats["bytes_copied"]), stats["hardlinked"], stats["seconds"]))
    if stats["errors"]:
        log("!! 有 %d 个文件未能备份（前 10 条）：" % len(stats["errors"]))
        for err in stats["errors"][:10]:
            log("   " + err)
    return stats


# --------------------------------------------------------------------------
# 保留策略
# --------------------------------------------------------------------------
def apply_retention(root, keep_daily, keep_weekly, keep_monthly, dry_run):
    if not os.path.isdir(root):
        return []
    names = sorted((n for n in os.listdir(root) if valid_ts(n)), reverse=True)
    if not names:
        return []

    keep = {names[0]}  # 最新一份永不删除
    days, weeks, months = set(), set(), set()
    for name in names:
        dt = parse_ts(name)
        day = dt.strftime("%Y%m%d")
        week = "%04d-W%02d" % dt.isocalendar()[:2]
        month = dt.strftime("%Y%m")
        # 三层保留：一份快照只要被任一层选中，就把它的日/周/月桶都标记占用，
        # 避免同一周/月的旧快照又被另一层重复保留。
        if keep_daily and day not in days and len(days) < keep_daily:
            keep.add(name)
        elif keep_weekly and week not in weeks and len(weeks) < keep_weekly:
            keep.add(name)
        elif keep_monthly and month not in months and len(months) < keep_monthly:
            keep.add(name)
        else:
            continue
        days.add(day)
        weeks.add(week)
        months.add(month)

    deleted = [n for n in names if n not in keep]
    for name in deleted:
        path = os.path.join(root, name)
        if dry_run:
            log("[dry-run] 将删除旧快照: %s" % path)
        else:
            shutil.rmtree(path)
            log("已删除旧快照: %s" % path)
    return deleted


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def parse_args(argv):
    p = argparse.ArgumentParser(description="audiobook 数据备份（DB 在线备份 + 硬链接增量快照）")
    p.add_argument("--data", required=True, help="数据目录（容器内 /data 或宿主机绝对路径）")
    p.add_argument("--backup", required=True, help="备份根目录")
    p.add_argument("--mode", choices=("all", "db", "files"), default="all")
    p.add_argument("--exclude-dirs", default="cache,log,.backup-tmp")
    p.add_argument("--exclude-patterns", default="*.tmp,*.part,*.partial,*.swp")
    p.add_argument("--keep-daily", type=int, default=7)
    p.add_argument("--keep-weekly", type=int, default=4)
    p.add_argument("--keep-monthly", type=int, default=6)
    p.add_argument("--min-free-gb", type=float, default=5)
    p.add_argument("--no-prune", action="store_true")
    p.add_argument("--allow-cold-copy", action="store_true",
                   help="允许在在线备份失败时对 db/-wal/-shm 做冷拷贝（仅容器已停止时使用）")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--timestamp", default=None)
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    data_dir = os.path.abspath(args.data)
    backup_root = os.path.abspath(args.backup)

    if not os.path.isdir(data_dir):
        log("!! 数据目录不存在: %s" % data_dir)
        return 3
    if os.path.realpath(backup_root) == os.path.realpath(data_dir):
        log("!! 备份目录不能是数据目录本身")
        return 3
    if os.path.realpath(backup_root).startswith(os.path.realpath(data_dir) + os.sep):
        log("!! 备份目录不能位于数据目录内部（会被递归备份）")
        return 3

    ts = args.timestamp or datetime.now().strftime(TS_FMT)
    if not valid_ts(ts):
        log("!! --timestamp 必须是 %s 格式" % TS_FMT)
        return 3

    exclude_dirs = {x.strip() for x in args.exclude_dirs.split(",") if x.strip()}
    exclude_patterns = [x.strip() for x in args.exclude_patterns.split(",") if x.strip()]

    if args.dry_run:
        log("[dry-run] 数据目录: %s" % data_dir)
        log("[dry-run] 备份目录: %s" % backup_root)
        log("[dry-run] 时间戳: %s，模式: %s" % (ts, args.mode))
        log("[dry-run] 排除目录: %s" % ", ".join(sorted(exclude_dirs)))
        log("[dry-run] 排除文件: %s" % ", ".join(exclude_patterns))
        return 0

    os.makedirs(backup_root, exist_ok=True)
    free = shutil.disk_usage(backup_root).free
    if free < args.min_free_gb * GB:
        log("!! 备份盘剩余空间不足 %.1fGB（当前 %s），已中止"
            % (args.min_free_gb, human(free)))
        return 3

    summary = {
        "timestamp": ts,
        "data_dir": data_dir,
        "backup_root": backup_root,
        "exclude_dirs": sorted(exclude_dirs),
        "exclude_patterns": exclude_patterns,
        "keep_daily": args.keep_daily,
        "keep_weekly": args.keep_weekly,
        "keep_monthly": args.keep_monthly,
        "mode": args.mode,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "ok",
    }
    warnings = 0

    # 1) 数据库
    if args.mode in ("all", "db"):
        db_dir = os.path.join(backup_root, "db", ts)
        results = []
        for rel, name in DATABASES:
            src = os.path.join(data_dir, rel)
            if not os.path.isfile(src):
                log("跳过不存在的数据库: %s" % src)
                continue
            try:
                results.append(backup_one_db(
                    src, os.path.join(db_dir, name),
                    allow_cold_copy=args.allow_cold_copy))
            except Exception as exc:
                warnings += 1
                log("!! 数据库备份失败 %s: %s" % (src, exc))
                results.append({"source": src, "status": "failed", "error": str(exc)})
        if results:
            os.makedirs(db_dir, exist_ok=True)
            with open(os.path.join(db_dir, "manifest.json"), "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
        summary["databases"] = results
        if any(r.get("status") != "ok" for r in results):
            warnings += 1

    # 2) 文件快照
    if args.mode in ("all", "files"):
        dst_root = os.path.join(backup_root, "files", ts)
        try:
            stats = snapshot_files(data_dir, dst_root, exclude_dirs, exclude_patterns)
        except Exception as exc:
            log("!! 文件快照失败，已清理不完整快照: %s" % exc)
            if os.path.isdir(dst_root):
                shutil.rmtree(dst_root, ignore_errors=True)
            return 3
        summary["files"] = stats
        if stats["errors"]:
            warnings += 1

    # 3) 保留策略
    if not args.no_prune:
        summary["pruned"] = {
            "files": apply_retention(os.path.join(backup_root, "files"),
                                     args.keep_daily, args.keep_weekly,
                                     args.keep_monthly, args.dry_run),
            "db": apply_retention(os.path.join(backup_root, "db"),
                                  args.keep_daily, args.keep_weekly,
                                  args.keep_monthly, args.dry_run),
        }

    summary["status"] = "ok-with-warnings" if warnings else "ok"
    summary["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

    manifests = os.path.join(backup_root, "manifests")
    os.makedirs(manifests, exist_ok=True)
    with open(os.path.join(manifests, "backup-%s.json" % ts), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    log("备份完成，状态=%s，清单=%s"
        % (summary["status"],
           os.path.join(manifests, "backup-%s.json" % ts)))
    return 2 if warnings else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BackupError as exc:
        log("!! %s" % exc)
        sys.exit(3)
    except KeyboardInterrupt:
        log("!! 用户中断")
        sys.exit(130)
