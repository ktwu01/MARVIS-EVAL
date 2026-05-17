from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from mavis_eval.adapters import mavis_runner as mr


CASE_FIXTURE = {
    "case_id": "demo_case",
    "title": "Demo",
    "user_instruction": "Do a thing.",
    "allowed_tools": ["file_read", "file_write"],
    "forbidden_tools": ["email_send"],
    "forbidden_actions": ["Send anything"],
    "initial_state": {"input_files": ["input/notes.md", "recordings/"]},
    "input_assets": [
        {"type": "markdown", "path": "input/notes.md"},
        {"type": "directory", "path": "recordings"},
    ],
    "evaluation": {"final_artifact_paths": ["output/answer.md"]},
}


class BuildPromptTest(unittest.TestCase):
    def test_prompt_contains_paths_and_constraints(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "demo_case"
            mr.prepare_run_dir(Path(tmp), "demo_case")
            prompt = mr.build_prompt(CASE_FIXTURE, run_dir, extra_suffix="EXTRA")
        self.assertIn("Do a thing.", prompt)
        self.assertIn(str((run_dir / "output").resolve()), prompt)
        self.assertIn("output/answer.md", prompt)
        self.assertIn("email_send", prompt)
        self.assertIn("file_read", prompt)
        self.assertIn("Send anything", prompt)
        self.assertIn("EXTRA", prompt)
        self.assertIn("input/notes.md", prompt)
        self.assertIn(str((run_dir / "input" / "notes.md").resolve()), prompt)


class PrepareAndStageTest(unittest.TestCase):
    def test_prepare_creates_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = mr.prepare_run_dir(Path(tmp), "demo_case")
            self.assertTrue((run_dir / "output").is_dir())
            self.assertTrue((run_dir / "state").is_dir())

    def test_stage_without_fixtures_creates_declared_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = mr.prepare_run_dir(Path(tmp), "demo_case")
            mr.stage_fixtures(CASE_FIXTURE, run_dir, fixtures_root=None)
            self.assertTrue((run_dir / "recordings").is_dir())

    def test_stage_sweeps_unlisted_fixture_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            run_dir = mr.prepare_run_dir(tmp_path / "runs", "demo_case")
            fixtures_root = tmp_path / "fixtures"
            (fixtures_root / "demo_case" / "extra").mkdir(parents=True)
            (fixtures_root / "demo_case" / "extra" / "unlisted.txt").write_text("x", encoding="utf-8")
            # case fixture has no "extra/unlisted.txt" listed in input_assets
            staged = mr.stage_fixtures(CASE_FIXTURE, run_dir, fixtures_root=fixtures_root)
            self.assertIn("extra/unlisted.txt", staged)
            self.assertEqual((run_dir / "extra" / "unlisted.txt").read_text(), "x")

    def test_stage_with_fixtures_copies_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            run_dir = mr.prepare_run_dir(tmp_path / "runs", "demo_case")
            fixtures_root = tmp_path / "fixtures"
            (fixtures_root / "demo_case" / "input").mkdir(parents=True)
            (fixtures_root / "demo_case" / "input" / "notes.md").write_text("hello", encoding="utf-8")
            (fixtures_root / "demo_case" / "recordings").mkdir()
            (fixtures_root / "demo_case" / "recordings" / "a.wav").write_bytes(b"\x00")
            staged = mr.stage_fixtures(CASE_FIXTURE, run_dir, fixtures_root=fixtures_root)
            self.assertIn("input/notes.md", staged)
            self.assertIn("recordings", staged)
            self.assertEqual((run_dir / "input" / "notes.md").read_text(), "hello")
            self.assertTrue((run_dir / "recordings" / "a.wav").is_file())


class TrajectoryNormalizeTest(unittest.TestCase):
    def test_skips_thinking_and_user_messages(self):
        messages = [
            {"role": "user", "msg_content": "hi"},
            {
                "role": "assistant",
                "timestamp": 1700000000000,
                "thinking_content": "SECRET REASONING — must be excluded",
                "tool_calls": [
                    {
                        "tool_name": "read",
                        "tool_call_id": "tc1",
                        "tool_call_args": json.dumps({"filePath": "/x"}),
                        "tool_call_result_data": "ok",
                    }
                ],
            },
            {
                "role": "assistant",
                "timestamp": 1700000001000,
                "tool_calls": [
                    {
                        "tool_name": "write",
                        "tool_call_id": "tc2",
                        "tool_call_args": "{not json",  # malformed; should not raise
                        "tool_call_result_data": "wrote",
                    }
                ],
            },
            {"role": "assistant", "tool_calls": []},
        ]
        steps = mr.normalize_trajectory(messages, session_id="sess_x")
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0]["step"], 1)
        self.assertEqual(steps[0]["tool"], "read")
        self.assertEqual(steps[0]["args"], {"filePath": "/x"})
        self.assertEqual(steps[0]["source_session"], "sess_x")
        self.assertEqual(steps[1]["tool"], "write")
        self.assertEqual(steps[1]["args"], {"raw": "{not json"})
        serialized = json.dumps(steps)
        self.assertNotIn("SECRET REASONING", serialized)
        self.assertNotIn("thinking_content", serialized)


class ParseLastJsonTest(unittest.TestCase):
    def test_handles_header_line_before_json(self):
        out = 'Root session created: mvs_abc\n{"sessionId": "mvs_abc", "agentName": "mavis"}\n'
        parsed = mr._parse_last_json(out)
        self.assertEqual(parsed["sessionId"], "mvs_abc")

    def test_pure_json(self):
        out = '{"messages": []}'
        parsed = mr._parse_last_json(out)
        self.assertEqual(parsed, {"messages": []})

    def test_raises_on_empty(self):
        with self.assertRaises(RuntimeError):
            mr._parse_last_json("")

    def test_raises_when_no_json(self):
        with self.assertRaises(RuntimeError):
            mr._parse_last_json("no json here")


class WriteTrajectoryTest(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            steps = [
                {"step": 1, "tool": "read", "args": {"a": 1}, "observation": "o"},
                {"step": 2, "tool": "write", "args": {}, "observation": "ok"},
            ]
            path = mr.write_trajectory(steps, run_dir)
            lines = path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual(json.loads(lines[0])["tool"], "read")


if __name__ == "__main__":
    unittest.main()
