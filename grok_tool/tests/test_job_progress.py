from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from grokreg.core import style_log
from web_console.job_manager import Job
from web_console.plugins.grok import GrokToolPlugin


class JobProgressTest(unittest.TestCase):
    def test_progress_marker_updates_snapshot_without_polluting_logs(self):
        job = Job(
            id="progress-test",
            tool_id="grok",
            params={"count": 100},
            status="running",
        )

        job.append_log("@@JOB_PROGRESS completed=2 total=100 ok=1 failed=1")

        snapshot = job.snapshot()
        self.assertEqual(
            snapshot["progress"],
            {
                "completed": 2,
                "total": 100,
                "ok": 1,
                "failed": 1,
                "percent": 2,
                "continuous": False,
            },
        )
        self.assertEqual(snapshot["logs"], [])

    def test_clearing_visible_logs_keeps_batch_progress(self):
        job = Job(id="progress-test", tool_id="grok", params={"count": 10})
        job.append_log("visible")
        job.append_log("@@JOB_PROGRESS completed=3 total=10 ok=2 failed=1")

        self.assertEqual(job.clear_logs(), 1)
        self.assertEqual(job.snapshot()["progress"]["completed"], 3)

    def test_progress_emitter_contract(self):
        with patch.dict("os.environ", {"GROK_WEB_CONSOLE": "1"}), patch.object(
            style_log, "_out"
        ) as output:
            style_log.progress(4, 100, 3)
        output.assert_called_once_with(
            "@@JOB_PROGRESS completed=4 total=100 ok=3 failed=1"
        )

    def test_grok_web_command_accepts_one_hundred_accounts(self):
        plugin = GrokToolPlugin()
        field = next(field for field in plugin.meta.fields if field.key == "count")
        self.assertEqual(field.max, 2000)

        with patch.object(plugin, "_py", return_value=Path(sys.executable)):
            command = plugin.build_command(
                {"mail": "0", "count": 100, "backend": "github"}, Path.cwd()
            )
        self.assertEqual(command[command.index("--count") + 1], "100")


if __name__ == "__main__":
    unittest.main()
