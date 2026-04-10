"""
Tests for restore_inputs_from_localstorage.

Regression: Monte Carlo and Sensitivity pages used to only check
st.session_state.inputs and stop with "set a template" on direct
navigation / page reload. They never looked in localStorage. The helper
under test lets any page rehydrate session state from the saved
scenario so users can deep-link into sub-pages without bouncing through
the Planner page first.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parent
sys.path.insert(0, str(REPO_ROOT / "retirement-sim"))
sys.path.insert(0, str(APP_ROOT))


class FakeSessionState(dict):
    """Mimic the attribute-style access Streamlit's session_state supports."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as e:
            raise AttributeError(name) from e

    def __setattr__(self, name, value):
        self[name] = value


class RestoreInputsTests(unittest.TestCase):
    def setUp(self):
        self.fake_state = FakeSessionState()
        # Patch st.session_state inside the helper module so the helper
        # reads/writes our fake dict instead of Streamlit's real state.
        self.state_patch = patch(
            "helpers.local_storage.st.session_state", self.fake_state
        )
        self.state_patch.start()

    def tearDown(self):
        self.state_patch.stop()

    def test_restores_when_session_empty_and_localstorage_has_scenario(self):
        from helpers.local_storage import restore_inputs_from_localstorage

        payload = {
            "name": "Saved scenario",
            "current_age": 42,
            "inputs": {"in_SalaryAnnual": 95000, "in_RetirementTarget": 1_500_000},
        }
        with patch(
            "helpers.local_storage.load_from_localstorage", return_value=payload
        ):
            restored = restore_inputs_from_localstorage()

        self.assertTrue(restored)
        self.assertEqual(self.fake_state["inputs"]["in_SalaryAnnual"], 95000)
        self.assertEqual(self.fake_state["current_age"], 42)
        self.assertEqual(self.fake_state["scenario_name"], "Saved scenario")

    def test_noop_when_inputs_already_in_session(self):
        from helpers.local_storage import restore_inputs_from_localstorage

        self.fake_state["inputs"] = {"in_SalaryAnnual": 1}
        self.fake_state["current_age"] = 30
        with patch(
            "helpers.local_storage.load_from_localstorage"
        ) as mock_load:
            restored = restore_inputs_from_localstorage()

        self.assertFalse(restored)
        mock_load.assert_not_called()
        self.assertEqual(self.fake_state["inputs"], {"in_SalaryAnnual": 1})

    def test_returns_false_when_localstorage_empty(self):
        from helpers.local_storage import restore_inputs_from_localstorage

        with patch(
            "helpers.local_storage.load_from_localstorage", return_value=None
        ):
            restored = restore_inputs_from_localstorage()

        self.assertFalse(restored)
        self.assertNotIn("inputs", self.fake_state)

    def test_returns_false_when_payload_has_no_inputs(self):
        from helpers.local_storage import restore_inputs_from_localstorage

        with patch(
            "helpers.local_storage.load_from_localstorage",
            return_value={"name": "broken", "current_age": 30},
        ):
            restored = restore_inputs_from_localstorage()

        self.assertFalse(restored)
        self.assertNotIn("inputs", self.fake_state)

    def test_defaults_current_age_when_missing(self):
        from helpers.local_storage import restore_inputs_from_localstorage

        with patch(
            "helpers.local_storage.load_from_localstorage",
            return_value={"inputs": {"in_SalaryAnnual": 80000}},
        ):
            restored = restore_inputs_from_localstorage()

        self.assertTrue(restored)
        self.assertEqual(self.fake_state["current_age"], 35)
        self.assertEqual(self.fake_state["scenario_name"], "My scenario")


if __name__ == "__main__":
    unittest.main()
