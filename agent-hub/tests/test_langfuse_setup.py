"""Offline tests: no test contacts a real Langfuse or creates remote resources."""

import base64
from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import shlex
import stat
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "langfuse_setup.py"
SPEC = importlib.util.spec_from_file_location("langfuse_setup", SCRIPT)
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)


class LangfuseSetupTests(unittest.TestCase):
    def setUp(self):
        self.env = {
            "LANGFUSE_BASE_URL": "https://observability.example.test/",
            "LANGFUSE_PUBLIC_KEY": "pk-lf-test-public",
            "LANGFUSE_SECRET_KEY": "sk-lf-TEST-SECRET",
            "LANGFUSE_PROJECT_ID": "project-123",
        }
        self.values = setup.configuration(self.env)

    def response(self, payload=None, status=200):
        response = Mock(status=status)
        response.read.return_value = json.dumps(payload or {"data": [{"id": "project-123"}]}).encode()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        opener = Mock()
        opener.open.return_value = response
        return opener

    def test_verification_uses_only_read_only_project_endpoint(self):
        opener = self.response()
        self.assertEqual(setup.verify_project(self.values, opener), "project-123")
        request = opener.open.call_args.args[0]
        self.assertEqual(request.method, "GET")
        self.assertIsNone(request.data)
        self.assertEqual(request.full_url, "https://observability.example.test/api/public/projects")
        basic = request.get_header("Authorization").split(" ")[1]
        self.assertEqual(base64.b64decode(basic).decode(), "pk-lf-test-public:sk-lf-TEST-SECRET")
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 15)

    def test_discovery_without_expected_project_id(self):
        self.values["LANGFUSE_PROJECT_ID"] = ""
        self.assertEqual(setup.verify_project(self.values, self.response()), "project-123")

    def test_wrong_or_non_project_scoped_credentials_fail(self):
        for payload in ({"data": [{"id": "wrong"}]}, {"data": []}, {"data": [{"id": "one"}, {"id": "two"}]}, {"data": [{"id": "bad\nID"}]}):
            with self.subTest(payload=payload), self.assertRaises(setup.SetupError):
                setup.verify_project(self.values, self.response(payload))

    def test_refuses_insecure_or_credential_bearing_origins(self):
        for url in ("http://external.example", "https://user:password@example.test", "https://@example.test", "https://example.test/api", "https://example.test?token=secret", "https://example.test#secret", "https://example.test:bad", "https://example.test\n"):
            with self.subTest(url=url), self.assertRaises(setup.SetupError):
                setup.configuration({**self.env, "LANGFUSE_BASE_URL": url})
        for url in ("http://localhost:8080", "http://127.0.0.1:8080", "http://[::1]:8080"):
            self.assertEqual(setup.configuration({**self.env, "LANGFUSE_BASE_URL": url})["LANGFUSE_BASE_URL"], url)

    def test_missing_or_multiline_secrets_fail_before_network(self):
        for key, value in (("LANGFUSE_SECRET_KEY", ""), ("LANGFUSE_SECRET_KEY", "secret\nINJECT=bad"), ("LANGFUSE_PUBLIC_KEY", "user:password")):
            with self.subTest(key=key, value=value), self.assertRaises(setup.SetupError):
                setup.configuration({**self.env, key: value})

    def test_refuses_every_redirect(self):
        with self.assertRaisesRegex(setup.SetupError, "redirected"):
            setup.NoRedirects().redirect_request(None, None, 302, "Found", {}, "https://other.example")

    def test_http_and_transport_errors_never_echo_server_content_or_credentials(self):
        errors = [HTTPError("https://example.test", 401, "sk-lf-TEST-SECRET", {}, io.BytesIO(b"sk-lf-TEST-SECRET")), URLError("sk-lf-TEST-SECRET")]
        for error in errors:
            opener = Mock()
            opener.open.side_effect = error
            with self.assertRaises(setup.SetupError) as caught:
                setup.verify_project(self.values, opener)
            self.assertNotIn("sk-lf-TEST-SECRET", str(caught.exception))

    def test_invalid_and_oversize_payload_fail_safely(self):
        for payload in (b"not json", b"\xff", b"x" * 1_048_577):
            opener = self.response()
            opener.open.return_value.read.return_value = payload
            with self.assertRaises(setup.SetupError):
                setup.verify_project(self.values, opener)

    def test_private_file_is_exclusive_mode_0600_and_shell_roundtrips(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "agent.env"
            values = {**self.values, "LANGFUSE_SECRET_KEY": "sk-lf-quote'$value"}
            setup.write_private_env(path, values, "project-123")
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            parsed = dict(item.split("=", 1) for item in shlex.split(path.read_text(), comments=True))
            self.assertEqual(parsed, values)
            original = path.read_bytes()
            with self.assertRaisesRegex(setup.SetupError, "overwrite"):
                setup.write_private_env(path, self.values, "project-123")
            self.assertEqual(path.read_bytes(), original)

    def test_rejects_repository_paths_and_links_into_repositories(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            repo = root / "repo"
            repo.mkdir()
            (repo / ".git").write_text("gitdir: elsewhere")  # Also protects worktrees.
            (root / "link").symlink_to(repo, target_is_directory=True)
            for path in (repo / "new.env", root / "link" / "new.env"):
                with self.assertRaisesRegex(setup.SetupError, "Git checkout"):
                    setup.write_private_env(path, self.values, "project-123")
            self.assertFalse((repo / "new.env").exists())

    def test_rejects_existing_or_dangling_destination_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "agent.env"
            path.symlink_to(Path(folder) / "missing")
            with self.assertRaisesRegex(setup.SetupError, "overwrite"):
                setup.write_private_env(path, self.values, "project-123")
            self.assertFalse((Path(folder) / "missing").exists())

    def test_cli_default_is_read_only_and_does_not_display_keys(self):
        output = io.StringIO()
        with patch.dict(setup.os.environ, self.env, clear=True), patch.object(setup, "verify_project", return_value="project-123"), patch.object(setup, "write_private_env") as writer, redirect_stdout(output):
            self.assertEqual(setup.main([]), 0)
            writer.assert_not_called()
        self.assertIn("Read-only", output.getvalue())
        self.assertNotIn(self.env["LANGFUSE_SECRET_KEY"], output.getvalue())
        self.assertNotIn(self.env["LANGFUSE_PUBLIC_KEY"], output.getvalue())

    def test_failed_verification_does_not_write_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "new.env"
            with patch.dict(setup.os.environ, self.env, clear=True), patch.object(setup, "verify_project", side_effect=setup.SetupError("Credentials rejected.")), redirect_stderr(io.StringIO()):
                self.assertEqual(setup.main(["--write-env", str(path)]), 1)
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
