"""Translation workflow:  uv run python tools/translations.py update | compile | check

update   extract the texts from the sources into src/gelcam/translations/gelcam_<lang>.ts (existing
         translations are kept; new texts are added as "unfinished", vanished ones are dropped)
compile  .ts -> .qm (what the application loads; the .qm files are not committed)
check    every text translated, the {placeholders} of source and translation identical

English is the source language. To add a language, add its code to LANGUAGES, run
`update --lang <code>` and translate the new .ts file.
"""

from __future__ import annotations

import argparse
import html
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "gelcam"
TRANSLATIONS = SRC / "translations"
LANGUAGES = ("cs",)

_PLACEHOLDER = re.compile(r"\{[^{}]*\}")


def _tool(name: str) -> str:
    exe = Path(sys.executable).parent / (name + (".exe" if sys.platform == "win32" else ""))
    return str(exe) if exe.exists() else name


def ts_path(lang: str) -> Path:
    return TRANSLATIONS / f"gelcam_{lang}.ts"


def update(lang: str) -> int:
    sources = sorted(str(p) for p in SRC.rglob("*.py"))
    return subprocess.call([_tool("pyside6-lupdate"), *sources, "-ts", str(ts_path(lang)), "-no-obsolete"])


def compile_all(langs: tuple[str, ...] = LANGUAGES) -> list[Path]:
    """Compile every .ts to .qm next to it; returns the .qm paths."""
    out = []
    for lang in langs:
        qm = TRANSLATIONS / f"gelcam_{lang}.qm"
        if subprocess.call([_tool("pyside6-lrelease"), str(ts_path(lang)), "-qm", str(qm)]) != 0:
            raise RuntimeError(f"lrelease failed for {lang}")
        out.append(qm)
    return out


def read_ts(path: Path) -> list[tuple[str, str, str, bool]]:
    """(context, source, translation, unfinished) for every message in a .ts file."""
    text = path.read_text(encoding="utf-8")
    messages = []
    for ctx, body in re.findall(r"<context>\s*<name>(.*?)</name>(.*?)</context>", text, re.S):
        for block in re.findall(r"<message.*?</message>", body, re.S):
            src = html.unescape(re.search(r"<source>(.*?)</source>", block, re.S).group(1))
            tr = re.search(r"<translation([^>]*)>(.*?)</translation>", block, re.S)
            messages.append((ctx, src, html.unescape(tr.group(2)), "unfinished" in tr.group(1)))
    return messages


def problems(path: Path) -> list[str]:
    """Human-readable list of problems of one .ts file (empty = fine)."""
    found = []
    for ctx, src, tr, unfinished in read_ts(path):
        if unfinished or not tr.strip():
            found.append(f"untranslated [{ctx}] {src[:70]!r}")
        elif sorted(_PLACEHOLDER.findall(src)) != sorted(_PLACEHOLDER.findall(tr)):
            found.append(f"placeholders differ [{ctx}] {src[:50]!r} -> {tr[:50]!r}")
    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["update", "compile", "check"])
    ap.add_argument("--lang", default=None, help="language code (default: all known languages)")
    args = ap.parse_args()
    langs = (args.lang,) if args.lang else LANGUAGES
    if args.command == "update":
        return max(update(lang) for lang in langs)
    if args.command == "compile":
        for qm in compile_all(langs):
            print("compiled", qm.relative_to(ROOT))
        return 0
    bad = 0
    for lang in langs:
        issues = problems(ts_path(lang))
        print(f"{lang}: {len(read_ts(ts_path(lang)))} texts, {len(issues)} problem(s)")
        for line in issues:
            print("  ", line)
        bad += len(issues)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
