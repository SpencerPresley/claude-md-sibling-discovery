"""Tests for the Pyrefly LSP protocol adapter."""

from __future__ import annotations

import importlib.util
import io
import json
import unittest
from pathlib import Path
from types import ModuleType

ADAPTER_PATH = (
    Path(__file__).parents[1] / "plugins" / "pyrefly-lsp" / "server" / "pyrefly_lsp.py"
)
PLUGIN_MANIFEST_PATH = ADAPTER_PATH.parents[1] / ".claude-plugin" / "plugin.json"


def load_adapter() -> ModuleType:
    """Load the adapter module from the plugin bundle."""
    if not ADAPTER_PATH.exists():
        raise AssertionError(f"adapter is missing: {ADAPTER_PATH}")
    spec = importlib.util.spec_from_file_location("pyrefly_lsp_adapter", ADAPTER_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load adapter: {ADAPTER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RewriteInitializeMessageTest(unittest.TestCase):
    """Verify the one protocol field Claude and Pyrefly disagree on."""

    def test_advertises_the_workspace_folder_claude_already_sends(self) -> None:
        """Enable workspace folders without changing the supplied folder list."""
        adapter = load_adapter()
        message = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "capabilities": {
                    "workspace": {"configuration": False, "workspaceFolders": False}
                },
                "workspaceFolders": [
                    {"uri": "file:///repo", "name": "repo"},
                ],
            },
        }

        rewritten = adapter.rewrite_initialize_message(message)

        self.assertTrue(
            rewritten["params"]["capabilities"]["workspace"]["workspaceFolders"]
        )
        self.assertEqual(
            rewritten["params"]["workspaceFolders"],
            [{"uri": "file:///repo", "name": "repo"}],
        )
        self.assertFalse(
            rewritten["params"]["capabilities"]["workspace"]["configuration"]
        )

    def test_rewrites_initialize_after_earlier_notifications(self) -> None:
        """Adapt initialization after `$/setTrace`, then pass traffic through."""
        adapter = load_adapter()
        initialize = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "capabilities": {"workspace": {"workspaceFolders": False}},
                "workspaceFolders": [{"uri": "file:///repo", "name": "repo"}],
            },
        }
        initialized = {"jsonrpc": "2.0", "method": "initialized", "params": {}}
        set_trace = {
            "jsonrpc": "2.0",
            "method": "$/setTrace",
            "params": {"value": "verbose"},
        }
        initialized_frame = frame(initialized)
        source = TrackingBytesIO(
            frame(set_trace) + frame(initialize) + initialized_frame
        )
        destination = io.BytesIO()

        if not hasattr(adapter, "forward_client_stream"):
            self.fail("adapter does not forward the client stream")
        adapter.forward_client_stream(source, destination)

        destination.seek(0)
        self.assertEqual(adapter.read_message(destination), set_trace)
        rewritten = adapter.read_message(destination)
        self.assertTrue(
            rewritten["params"]["capabilities"]["workspace"]["workspaceFolders"]
        )
        self.assertEqual(destination.read(), initialized_frame)
        self.assertGreater(source.read1_calls, 0)

    def test_launches_pyrefly_with_deterministic_indexing(self) -> None:
        """Use the pinned server in blocking mode so the first answer is complete."""
        adapter = load_adapter()

        self.assertTrue(hasattr(adapter, "PYREFLY_COMMAND"))
        self.assertEqual(
            adapter.PYREFLY_COMMAND,
            (
                "uvx",
                "pyrefly@1.2.0",
                "lsp",
                "--indexing-mode",
                "lazy-blocking",
            ),
        )

    def test_plugin_manifest_starts_the_adapter_without_project_sync(self) -> None:
        """Run the bundled adapter without mutating the target project's environment."""
        manifest = json.loads(PLUGIN_MANIFEST_PATH.read_text())
        server = manifest["lspServers"]["pyrefly"]

        self.assertEqual(server["command"], "uv")
        self.assertEqual(
            server["args"],
            [
                "run",
                "--no-project",
                "--quiet",
                "${CLAUDE_PLUGIN_ROOT}/server/pyrefly_lsp.py",
            ],
        )


def frame(message: dict[str, object]) -> bytes:
    """Encode one JSON-RPC message with LSP content-length framing."""
    body = json.dumps(message, separators=(",", ":")).encode()
    return f"Content-Length: {len(body)}\r\n\r\n".encode() + body


class TrackingBytesIO(io.BytesIO):
    """Record whether forwarding uses the non-greedy buffered-read API."""

    def __init__(self, initial_bytes: bytes) -> None:
        """Initialize the stream with framed LSP traffic."""
        super().__init__(initial_bytes)
        self.read1_calls = 0

    def read1(self, size: int = -1) -> bytes:
        """Read available bytes while recording use of `read1`."""
        self.read1_calls += 1
        return super().read1(size)


if __name__ == "__main__":
    unittest.main()
