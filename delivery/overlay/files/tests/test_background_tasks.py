"""后台任务可读错误与重试提示的回归。"""

from webserver.services.background_service import BackgroundTask, humanize_error


def test_humanize_error_is_single_line_and_bounded():
    raw = "Traceback:\n  line1\n  line2\n" + "x" * 400
    msg = humanize_error(raw)
    assert "\n" not in msg
    assert len(msg) <= 300


def test_humanize_error_maps_common_failures():
    assert "数据库忙" in humanize_error("sqlite3.OperationalError: database is locked")
    assert "磁盘空间不足" in humanize_error("OSError: No space left on device")
    assert "没有权限" in humanize_error("PermissionError: [Errno 13] Permission denied")


def test_failed_scan_task_exposes_retry_action():
    task = BackgroundTask(BackgroundTask.SERVICE_TYPE_SCAN, "scan")
    task.status = BackgroundTask.STATUS_FAILED
    action = task.to_dict()["retry_action"]
    assert action["api"] == "/api/admin/import/run"
    assert action["body"] == {"filelist": {"filter": "invalid"}}


def test_failed_audio_task_points_to_conversion_api():
    task = BackgroundTask(BackgroundTask.SERVICE_TYPE_AUDIO, "book", book_id=42)
    task.status = BackgroundTask.STATUS_FAILED
    assert task.to_dict()["retry_action"]["api"] == "/api/audio/42/conversion"


def test_running_or_completed_task_has_no_retry_action():
    task = BackgroundTask(BackgroundTask.SERVICE_TYPE_SCAN, "scan")
    assert task.to_dict()["can_retry"] is False
    task.status = BackgroundTask.STATUS_COMPLETED
    assert task.to_dict()["retry_action"] is None
