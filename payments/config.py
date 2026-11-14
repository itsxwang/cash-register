"""Config loader for Cash Register.

`config.yaml` is parsed with a tiny, dependency-free YAML-subset parser that
supports exactly what the project needs:

- nested maps via 2-space indentation
- `key: value` scalars: quoted strings, plain strings, ints, floats, booleans
- inline lists: [a, b, c]
- `#` comments (full-line and trailing, quote-aware)
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = REPO_ROOT / "config.yaml"


class ConfigError(ValueError):
    pass


def _strip_comment(line: str) -> str:
    out = []
    quote = None
    for ch in line:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
        else:
            if ch in ("'", '"'):
                quote = ch
                out.append(ch)
            elif ch == "#":
                break
            else:
                out.append(ch)
    return "".join(out).rstrip()


def _parse_scalar(text: str):
    t = text.strip()
    if not t:
        return ""
    if (t[0] == t[-1] == "'" or t[0] == t[-1] == '"') and len(t) >= 2:
        return t[1:-1]
    if t.startswith("[") and t.endswith("]"):
        inner = t[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(part) for part in inner.split(",")]
    low = t.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low in ("null", "~"):
        return None
    try:
        return int(t)
    except ValueError:
        pass
    try:
        return float(t)
    except ValueError:
        pass
    return t


def parse_config(text: str) -> dict:
    root: dict = {}
    stack = [(-1, root)]
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = _strip_comment(raw)
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        if "\t" in line[: indent + 1]:
            raise ConfigError(f"line {lineno}: tabs are not allowed for indentation")
        while stack and indent <= stack[-1][0]:
            stack.pop()
        if not stack:
            raise ConfigError(f"line {lineno}: bad indentation")
        parent = stack[-1][1]
        stripped = line.strip()
        if ":" not in stripped:
            raise ConfigError(f"line {lineno}: expected 'key: value'")
        key, _, val = stripped.partition(":")
        key = key.strip()
        if not key:
            raise ConfigError(f"line {lineno}: empty key")
        if val.strip() == "":
            child: dict = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _parse_scalar(val)
    return root


def _find_config() -> Path:
    env = os.environ.get("CASHREGISTER_CONFIG")
    if env:
        return Path(env).expanduser().resolve()
    cwd = Path.cwd() / "config.yaml"
    if cwd.is_file():
        return cwd.resolve()
    return DEFAULT_CONFIG_PATH


def load_config(path: str | os.PathLike | None = None) -> dict:
    p = Path(path).resolve() if path else _find_config()
    if not p.is_file():
        raise ConfigError(f"config not found: {p}")
    with open(p, "r", encoding="utf-8") as fh:
        cfg = parse_config(fh.read())
    cfg["_path"] = str(p)
    return cfg


def get_path(cfg: dict, dotted: str, default=None):
    """cfg lookup like 'addresses.eth'."""
    node = cfg
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node
