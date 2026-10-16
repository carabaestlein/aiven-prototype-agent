#!/usr/bin/env python3
"""Verify existing Langfuse project keys; optionally prepare a private shell env file.

No resources are created and no traces are sent. Uses only Python's standard library.
"""

from __future__ import annotations

import argparse
import base64
import ipaddress
import json
import os
from pathlib import Path
import re
import shlex
import sys
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class SetupError(Exception):
    """Safe, credential-free error suitable for display."""


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward Basic credentials to a redirected host, including HTTPS.
        raise SetupError("Langfuse redirected the request; configure its final web origin.")


def configuration(env: Mapping[str, str]) -> dict[str, str]:
    keys = ("LANGFUSE_BASE_URL", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")
    values = {key: env.get(key, "") for key in keys}
    for key, value in values.items():
        if not value or not value.isascii() or any(ord(c) < 33 or ord(c) == 127 for c in value):
            raise SetupError(f"Set {key} in the environment to a non-empty value without whitespace.")
    if ":" in values["LANGFUSE_PUBLIC_KEY"]:
        raise SetupError("LANGFUSE_PUBLIC_KEY must not contain a colon.")
    try:
        parsed = urlsplit(values["LANGFUSE_BASE_URL"])
        parsed.port  # Validate a supplied port before making a request.
        host = parsed.hostname
        loopback = host == "localhost"
        if host and not loopback:
            try:
                loopback = ipaddress.ip_address(host).is_loopback
            except ValueError:
                pass
        valid_transport = parsed.scheme == "https" or (parsed.scheme == "http" and loopback)
        valid_origin = host and parsed.username is None and parsed.password is None and not parsed.query and not parsed.fragment and parsed.path in ("", "/")
        if not (valid_transport and valid_origin):
            raise ValueError()
    except ValueError:
        raise SetupError("LANGFUSE_BASE_URL must be an HTTPS origin (HTTP is allowed only on loopback).") from None
    values["LANGFUSE_BASE_URL"] = values["LANGFUSE_BASE_URL"].rstrip("/")
    expected_project = env.get("LANGFUSE_PROJECT_ID", "")
    if expected_project and not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", expected_project):
        raise SetupError("LANGFUSE_PROJECT_ID must contain 1–200 letters, numbers, underscores or hyphens.")
    values["LANGFUSE_PROJECT_ID"] = expected_project
    return values


def verify_project(values: Mapping[str, str], opener=None) -> str:
    """Read the project associated with the credentials and check an optional expected ID."""
    credentials = f"{values['LANGFUSE_PUBLIC_KEY']}:{values['LANGFUSE_SECRET_KEY']}"
    authorization = base64.b64encode(credentials.encode("ascii")).decode("ascii")
    request = Request(
        values["LANGFUSE_BASE_URL"] + "/api/public/projects",
        method="GET",
        headers={"Authorization": "Basic " + authorization, "Accept": "application/json"},
    )
    client = opener if opener is not None else build_opener(NoRedirects())
    try:
        with client.open(request, timeout=15) as response:
            if response.status != 200:
                raise SetupError("Langfuse did not return a successful project response.")
            payload = response.read(1_048_577)
    except HTTPError as error:
        if error.code in (401, 403):
            raise SetupError("Langfuse rejected the project credentials or their permissions.") from None
        raise SetupError(f"Langfuse returned HTTP {error.code}; check the web service and API path.") from None
    except (URLError, TimeoutError, OSError):
        raise SetupError("Could not reach Langfuse securely; check its URL, certificate and connectivity.") from None
    if len(payload) > 1_048_576:
        raise SetupError("Langfuse returned an unexpectedly large project response.")
    try:
        projects = json.loads(payload)["data"]
        if not isinstance(projects, list) or len(projects) != 1:
            raise ValueError()
        project_id = projects[0]["id"]
        if not isinstance(project_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", project_id):
            raise ValueError()
    except (KeyError, TypeError, ValueError, UnicodeDecodeError):
        raise SetupError("Expected exactly one project from a project-scoped Langfuse key pair.") from None
    expected = values.get("LANGFUSE_PROJECT_ID")
    if expected and project_id != expected:
        raise SetupError("The key pair belongs to a different LANGFUSE_PROJECT_ID; no file was written.")
    return project_id


def validate_output_path(path: Path) -> Path:
    # Resolve parents to detect symlinks into a checkout; retain the final name so
    # O_EXCL below also rejects an existing (including dangling) destination link.
    try:
        parent = path.expanduser().absolute().parent.resolve(strict=True)
    except OSError:
        raise SetupError("The output directory must already exist outside a Git checkout.") from None
    if not parent.is_dir():
        raise SetupError("The output directory must already exist outside a Git checkout.")
    if any((ancestor / ".git").exists() for ancestor in (parent, *parent.parents)):
        raise SetupError("Refusing to write credentials inside a Git checkout; choose a private directory outside repositories.")
    destination = parent / path.name
    if destination.exists() or destination.is_symlink():
        raise SetupError("Refusing to overwrite an existing output file.")
    return destination


def write_private_env(path: Path, values: Mapping[str, str], project_id: str) -> None:
    destination = validate_output_path(path)
    selected = {key: values[key] for key in ("LANGFUSE_BASE_URL", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")}
    selected["LANGFUSE_PROJECT_ID"] = project_id
    content = "# Private shell environment; never commit or paste into task logs.\n"
    content += "".join(f"{key}={shlex.quote(value)}\n" for key, value in selected.items())
    try:
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise SetupError("Refusing to overwrite an existing output file.") from None
    except OSError:
        raise SetupError("Could not create the private environment file.") from None
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            os.fchmod(output.fileno(), 0o600)
            output.write(content)
    except OSError:
        destination.unlink(missing_ok=True)
        raise SetupError("Could not finish writing the private environment file.") from None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-env", type=Path, help="after successful verification, create a new mode-0600 shell env file outside Git checkouts")
    args = parser.parse_args(argv)
    try:
        values = configuration(os.environ)
        if args.write_env is not None:
            validate_output_path(args.write_env)
        project_id = verify_project(values)
        if args.write_env is not None:
            write_private_env(args.write_env, values, project_id)
        print("Verified Langfuse project credentials.")
        print(f"LANGFUSE_PROJECT_ID={project_id}")
        if args.write_env is not None:
            print("Created a private environment file with owner-only permissions.")
        else:
            print("Read-only check completed; no resources, traces or files were created.")
        return 0
    except SetupError as error:
        print(f"Langfuse setup: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
