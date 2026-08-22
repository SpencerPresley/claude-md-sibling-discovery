"""Adapt Claude Code's LSP initialization request for Pyrefly."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import threading
from copy import deepcopy
from typing import Any, BinaryIO

HEADER_TERMINATOR = b"\r\n\r\n"
PYREFLY_COMMAND = (
    "uvx",
    "pyrefly@1.2.0",
    "lsp",
    "--indexing-mode",
    "lazy-blocking",
)


def read_message(stream: BinaryIO) -> dict[str, Any] | None:
    """Read one content-length-framed LSP message.

    Args:
        stream: Binary input stream carrying LSP messages.

    Returns:
        The decoded message, or `None` when the stream ends before a header.

    Raises:
        ValueError: If the header omits a valid `Content-Length`.
        EOFError: If the stream ends inside a message body.
    """
    header = bytearray()
    while not header.endswith(HEADER_TERMINATOR):
        byte = stream.read(1)
        if not byte:
            if not header:
                return None
            raise EOFError("LSP stream ended inside a message header")
        header.extend(byte)

    content_length = None
    for line in bytes(header).decode("ascii").split("\r\n"):
        name, separator, value = line.partition(":")
        if separator and name.lower() == "content-length":
            content_length = int(value.strip())
            break
    if content_length is None:
        raise ValueError("LSP message has no Content-Length header")

    body = stream.read(content_length)
    if len(body) != content_length:
        raise EOFError("LSP stream ended inside a message body")
    return json.loads(body)


def write_message(stream: BinaryIO, message: dict[str, Any]) -> None:
    """Write one content-length-framed LSP message.

    Args:
        stream: Binary output stream carrying LSP messages.
        message: JSON-RPC message to encode.
    """
    body = json.dumps(message, separators=(",", ":")).encode()
    stream.write(f"Content-Length: {len(body)}\r\n\r\n".encode())
    stream.write(body)
    stream.flush()


def rewrite_initialize_message(message: dict[str, Any]) -> dict[str, Any]:
    """Tell Pyrefly to use the workspace folders Claude already supplies.

    Claude sends `workspaceFolders` in the initialize parameters while
    advertising that workspace folders are unsupported. Pyrefly ignores the
    supplied folders in that combination, so workspace-wide operations omit
    files outside the nearest Pyrefly project configuration.

    Args:
        message: Decoded JSON-RPC message from Claude Code.

    Returns:
        A copy with workspace-folder support enabled for `initialize` requests.
    """
    rewritten = deepcopy(message)
    if rewritten.get("method") != "initialize":
        return rewritten

    params = rewritten.setdefault("params", {})
    capabilities = params.setdefault("capabilities", {})
    workspace = capabilities.setdefault("workspace", {})
    workspace["workspaceFolders"] = True
    return rewritten


def forward_client_stream(source: BinaryIO, destination: BinaryIO) -> None:
    """Rewrite the initialize request, then forward later traffic unchanged.

    Args:
        source: Claude Code's binary LSP output stream.
        destination: Pyrefly's binary LSP input stream.
    """
    while message := read_message(source):
        write_message(destination, rewrite_initialize_message(message))
        if message.get("method") == "initialize":
            forward_raw_stream(source, destination)
            return


def forward_raw_stream(source: BinaryIO, destination: BinaryIO) -> None:
    """Forward available bytes without waiting to fill a buffered read.

    Args:
        source: Buffered binary input stream.
        destination: Binary output stream.
    """
    read_available = getattr(source, "read1", source.read)
    while chunk := read_available(shutil.COPY_BUFSIZE):
        destination.write(chunk)
        destination.flush()


def forward_server_stream(source: BinaryIO, destination: BinaryIO) -> None:
    """Forward Pyrefly's response stream to Claude Code unchanged.

    Args:
        source: Pyrefly's binary LSP output stream.
        destination: Claude Code's binary LSP input stream.
    """
    forward_raw_stream(source, destination)


def main() -> int:
    """Run Pyrefly behind the initialization adapter.

    Returns:
        Pyrefly's process exit code.
    """
    process = subprocess.Popen(
        PYREFLY_COMMAND,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    if process.stdin is None or process.stdout is None:
        process.kill()
        raise RuntimeError("Pyrefly subprocess has no stdio pipes")

    response_thread = threading.Thread(
        target=forward_server_stream,
        args=(process.stdout, sys.stdout.buffer),
        name="pyrefly-lsp-responses",
    )
    response_thread.start()
    try:
        forward_client_stream(sys.stdin.buffer, process.stdin)
    finally:
        process.stdin.close()
        return_code = process.wait()
        response_thread.join()
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
