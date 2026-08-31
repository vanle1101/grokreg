from __future__ import annotations

from dataclasses import dataclass
import unittest
from unittest import mock

from grokreg.captcha import turnstile_solver_client as client_module
from grokreg.captcha.turnstile_solver_client import (
    ExternalTurnstileSolver,
    TurnstileSolveError,
    probe_solver,
)
from services import solver_manager


@dataclass
class FakeResponse:
    payload: dict
    status_code: int = 200

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self.payload


class SequenceSession:
    def __init__(self, responses: list[FakeResponse]):
        self.responses = list(responses)
        self.urls: list[str] = []
        self.trust_env = True

    def get(self, url: str, **_kwargs) -> FakeResponse:
        self.urls.append(url)
        return self.responses.pop(0)


class TurnstileSolverTests(unittest.TestCase):
    def test_local_solver_surfaces_http_200_error_without_polling_to_timeout(self):
        session = SequenceSession([
            FakeResponse({"errorId": 0, "taskId": "task-1"}),
            FakeResponse({
                "errorId": 1,
                "status": "failed",
                "errorCode": "ERROR_CAPTCHA_UNSOLVABLE",
                "errorDescription": "Workers could not solve the Captcha",
            }),
        ])
        solver = ExternalTurnstileSolver(timeout=90)
        solver._http = session

        with mock.patch.object(client_module.time, "sleep", return_value=None):
            with self.assertRaisesRegex(TurnstileSolveError, "ERROR_CAPTCHA_UNSOLVABLE"):
                solver._solve_local("https://example.test", "site-key")

        self.assertEqual(len(session.urls), 2)
        self.assertIn("timeout=90", session.urls[0])

    def test_local_solver_rejects_create_error_even_when_http_status_is_200(self):
        solver = ExternalTurnstileSolver(timeout=45)
        solver._http = SequenceSession([
            FakeResponse({
                "errorId": 1,
                "errorCode": "ERROR_BAD_REQUEST",
                "errorDescription": "invalid site key",
            })
        ])

        with self.assertRaisesRegex(TurnstileSolveError, "ERROR_BAD_REQUEST"):
            solver._solve_local("https://example.test", "site-key")

    def test_probe_solver_requires_healthy_browser_capacity(self):
        unhealthy = SequenceSession([
            FakeResponse({"ok": True, "threads": 0, "available": 0})
        ])
        with mock.patch.object(client_module.requests, "Session", return_value=unhealthy):
            result = probe_solver("http://127.0.0.1:5072")

        self.assertFalse(result["online"])
        self.assertEqual(result["threads"], 0)

    def test_solver_manager_uses_nested_thread_setting(self):
        settings = solver_manager.settings_from_config({"turnstile": {"threads": 4}})
        self.assertEqual(settings["turnstile_threads"], 4)

        session = SequenceSession([
            FakeResponse({"ok": True, "threads": 4, "available": 0})
        ])
        with mock.patch.object(solver_manager.requests, "Session", return_value=session):
            self.assertTrue(solver_manager.is_running("http://127.0.0.1:5072"))


if __name__ == "__main__":
    unittest.main()
