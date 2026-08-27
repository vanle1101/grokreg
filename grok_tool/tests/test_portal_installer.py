import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import portal


class PortalInstallerTest(unittest.TestCase):
    def test_windows_installer_configures_real_zcode_reasoning_levels(self):
        script = portal.generate_codex_ps_script("sk-" + "a" * 40, "thinking")

        self.assertIn("Update-ZCodeConfig", script)
        self.assertIn("providerOptionsByLevel", script)
        self.assertIn("reasoningEffort = 'low'", script)
        self.assertIn("reasoningEffort = 'medium'", script)
        self.assertIn("reasoningEffort = 'high'", script)
        self.assertIn("defaultLevel = $defaultEffort", script)
        self.assertIn("output = 32768", script)

    def test_windows_installer_uses_selected_default_effort(self):
        expected = {"fast": "low", "smart": "medium", "thinking": "high"}
        for mode, effort in expected.items():
            with self.subTest(mode=mode):
                script = portal.generate_codex_ps_script("sk-" + "a" * 40, mode)
                self.assertIn(f'$defaultEffort = "{effort}"', script)


if __name__ == "__main__":
    unittest.main()
