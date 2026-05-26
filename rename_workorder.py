#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Workorder image auto-renamer (cross-platform: Windows / macOS / Linux)

Uses Claude's vision API to extract structured fields from photographed
7-Eleven repair workorders (handwritten Traditional Chinese) and renames
each image file accordingly. Successful files are moved to a `done/`
subfolder; failures land in `error/`.

╔════════════════════════════════════════════════════════════════════╗
║ Filename pattern:                                                  ║
║   {mmdd} 7-11{store}({fault} {repair_items}){repair_no}.jpg        ║
║                                                                    ║
║ Note: space (not hyphen) between mmdd and 7-11.                    ║
╚════════════════════════════════════════════════════════════════════╝

Examples:
  0407 7-11Tonghua(NoCup)91430773.jpg
  0403 7-11Shuilongyin(MidWBNotHot 32mm1 Solenoid1)91431308.jpg
  0423 7-11Kaili(NoWater CopperJoint3)91434951.jpg

Run:
  Double-click the file                       → folder picker dialog
  python rename_workorder.py                  → folder picker dialog
  python rename_workorder.py --folder PATH    → specify folder
  python rename_workorder.py --dry-run        → preview without moving

API key setup (pick one):
  ▸ Windows  (run once in Command Prompt; open a new shell to take effect):
        setx ANTHROPIC_API_KEY "sk-ant-your-key"
  ▸ macOS / Linux:
        export ANTHROPIC_API_KEY=sk-ant-your-key          # temporary
        echo 'ANTHROPIC_API_KEY=sk-ant-your-key' > ~/.workorder_rename.conf
        chmod 600 ~/.workorder_rename.conf                # persistent

Dependencies:
  Pure Python standard library (incl. tkinter). No `pip install` needed.
  Python 3.7+ (built-in on Windows 10/11).

Behaviour:
  • Scans the chosen folder, sending each image to Claude vision.
  • On success: renames + moves to `done/` subfolder.
  • On failure (API error, JSON parse error, missing required field):
    moves the original to `error/` for manual inspection.
  • Duplicate filenames get auto-suffixed `-2`, `-3`, ...
  • All runs append to `rename_log.txt` in the source folder.
"""

import os
import sys
import json
import base64
import re
import shutil
import pathlib
import logging
import argparse
import urllib.request
import urllib.error

# UTF-8 console output on Windows
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# ─────────────────── Config ───────────────────
API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-4-5-20251001"      # cheap, fast, vision-capable
SUPPORTED_EXT = {".jpg", ".jpeg", ".png"}
SUBFOLDER_DONE = "done"
SUBFOLDER_ERROR = "error"
LOG_FILE_NAME = "rename_log.txt"
API_TIMEOUT_SEC = 90

EXTRACTION_PROMPT = """這是一張 7-11 工程服務單。請從圖中辨識以下欄位，
只回傳一個 JSON 物件，不要任何前綴後綴、markdown 標記或解釋文字。

{
  "stamp_date": "右下角門市店章上的民國年.月.日，例如 \\"115.4.07\\"。完全看不到才傳 null。",
  "store_name": "「門市名稱」欄位的手寫文字，例如 \\"同華\\"、\\"水龍吟\\"、\\"長業\\"、\\"開立\\"。請仔細辨識手寫中文，去除空白。",
  "fault_call": "「故障叫修」欄位的內容，例如 \\"不出菜\\"、\\"中WB不熱\\"、\\"味淡\\"、\\"不出水\\"、\\"單杯\\"。中英文混合都原字保留。",
  "repair_items": [
    {"name": "修護內容欄位每一列的「料件中文名稱」（取手寫的中文，例 \\"32mm\\"、\\"電磁閥\\"、\\"銅插頭\\"），不要取像 \\"EVER-103743-LC\\" 這種代碼編號",
     "qty":  "該列「數量」欄位的數字字串"}
  ],
  "repair_no": "右上角紅色「維修號碼」欄位的數字字串（通常 8 位），例如 \\"91430773\\""
}

注意：
- repair_items 是陣列。修護內容完全空白時請傳空陣列 []
- 多列料件請分別建立物件
- stamp_date / store_name / fault_call / repair_no 都要盡力辨識（必要欄位）
- 只回傳合法 JSON，無其他文字
"""


# ─────────────────── API key ───────────────────
def load_api_key():
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key.strip()
    config = pathlib.Path.home() / ".workorder_rename.conf"
    if config.exists():
        for line in config.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("ANTHROPIC_API_KEY"):
                _, _, val = line.partition("=")
                return val.strip().strip('"').strip("'")
    raise RuntimeError(
        "ANTHROPIC_API_KEY not found. Set the environment variable, or "
        "create ~/.workorder_rename.conf with:\n  ANTHROPIC_API_KEY=sk-ant-..."
    )


# ─────────────────── Folder picker ───────────────────
def pick_folder_interactive():
    """Show a folder picker dialog; fall back to stdin if no GUI."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askdirectory(title="Select workorder image folder")
        try:
            root.destroy()
        except Exception:
            pass
        if path:
            p = pathlib.Path(path)
            if p.is_dir():
                return p
            print(f"Not a directory: {p}")
    except Exception as e:
        print(f"GUI picker unavailable ({e}); falling back to text input.")

    while True:
        s = input('\nEnter workorder folder path (empty to cancel):\n> ').strip().strip('"').strip("'")
        if not s:
            print("Cancelled.")
            sys.exit(0)
        p = pathlib.Path(s).expanduser()
        if p.is_dir():
            return p
        print(f"Folder not found: {p}, please try again.")


# ─────────────────── Claude vision call ───────────────────
def call_claude_vision(image_path, api_key):
    ext = pathlib.Path(image_path).suffix.lower()
    media_type = "image/png" if ext == ".png" else "image/jpeg"
    with open(image_path, "rb") as fp:
        b64 = base64.standard_b64encode(fp.read()).decode("ascii")

    payload = {
        "model": MODEL,
        "max_tokens": 1024,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image",
                 "source": {"type": "base64", "media_type": media_type, "data": b64}},
                {"type": "text", "text": EXTRACTION_PROMPT},
            ],
        }],
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=API_TIMEOUT_SEC) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"API HTTP {e.code}: {err_body[:400]}")

    text = body["content"][0]["text"].strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


# ─────────────────── Filename builder ───────────────────
def roc_to_mmdd(stamp_date):
    """'115.4.07' / '115. 4. 7' -> '0407'. Returns None on failure."""
    if not stamp_date:
        return None
    m = re.search(r"\d{2,3}\s*[.\-/]\s*(\d{1,2})\s*[.\-/]\s*(\d{1,2})", str(stamp_date))
    if not m:
        return None
    mm, dd = int(m.group(1)), int(m.group(2))
    if not (1 <= mm <= 12 and 1 <= dd <= 31):
        return None
    return f"{mm:02d}{dd:02d}"


def sanitize(s):
    """Strip filesystem-illegal characters and all whitespace."""
    if s is None:
        return ""
    s = str(s)
    s = re.sub(r'[\\/:*?"<>|\r\n\t]+', "", s)
    s = re.sub(r"\s+", "", s)
    return s.strip()


def clean_qty(v):
    """'1' / 1 / 'null' / None / '' -> '1' or ''."""
    if v is None:
        return ""
    s = str(v).strip()
    if s.lower() in {"", "null", "none", "n/a", "-"}:
        return ""
    return sanitize(s)


def build_filename(fields):
    """
    Compose filename from extracted fields.
    Pattern: {mmdd} 7-11{store}({fault} {item}{qty}...){repair_no}.jpg
    """
    mmdd = roc_to_mmdd(fields.get("stamp_date"))
    store = sanitize(fields.get("store_name"))
    fault = sanitize(fields.get("fault_call"))
    repair_no = sanitize(fields.get("repair_no"))
    items = fields.get("repair_items") or []

    missing = []
    if not mmdd: missing.append("stamp_date")
    if not store: missing.append("store_name")
    if not fault: missing.append("fault_call")
    if not repair_no: missing.append("repair_no")
    if missing:
        raise ValueError(f"Missing required fields {missing}; extracted={fields}")

    # repair items: each row "{name}{qty}", rows joined by single space
    parts = []
    for it in items:
        if not isinstance(it, dict):
            continue
        name = sanitize(it.get("name"))
        qty = clean_qty(it.get("qty"))
        if name:
            parts.append(f"{name}{qty}")

    inner = f"{fault} {' '.join(parts)}".strip() if parts else fault
    return f"{mmdd} 7-11{store}({inner}){repair_no}.jpg"


def find_unique_name(target_dir, base_name):
    target = target_dir / base_name
    if not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix
    n = 2
    while True:
        candidate = target_dir / f"{stem}-{n}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def already_renamed(name):
    """Return True if filename already matches the renamed pattern."""
    return bool(re.match(r"^\d{4} 7-11.+\(.+\)\d+(-\d+)?\.jpg$", name))


# ─────────────────── Main pipeline ───────────────────
def process_one(file_path, api_key, logger, dry_run=False):
    file_path = pathlib.Path(file_path)
    if not file_path.is_file():
        logger.warning(f"File not found: {file_path}")
        return False, "missing"
    if file_path.suffix.lower() not in SUPPORTED_EXT:
        logger.info(f"Unsupported image type: {file_path.name}")
        return False, "skip"
    if file_path.parent.name in {SUBFOLDER_DONE, SUBFOLDER_ERROR}:
        return False, "skip"
    if already_renamed(file_path.name):
        logger.info(f"Already named correctly, skipping: {file_path.name}")
        return False, "skip"

    parent = file_path.parent
    done_dir = parent / SUBFOLDER_DONE
    error_dir = parent / SUBFOLDER_ERROR
    if not dry_run:
        done_dir.mkdir(exist_ok=True)
        error_dir.mkdir(exist_ok=True)

    try:
        fields = call_claude_vision(str(file_path), api_key)
        logger.info(f"Extracted [{file_path.name}]: {json.dumps(fields, ensure_ascii=False)}")
        new_name = build_filename(fields)
        target = find_unique_name(done_dir, new_name)
        if dry_run:
            logger.info(f"[DRY-RUN] {file_path.name} → {target.name}")
            return True, "ok"
        shutil.move(str(file_path), str(target))
        logger.info(f"OK: {file_path.name} → {target.name}")
        return True, "ok"
    except Exception as e:
        logger.error(f"FAIL [{file_path.name}]: {e}")
        if dry_run:
            return False, "fail"
        try:
            err_target = find_unique_name(error_dir, file_path.name)
            shutil.move(str(file_path), str(err_target))
            logger.info(f"Moved to error/: {err_target.name}")
        except Exception as move_err:
            logger.error(f"Failed to move to error/: {move_err}")
        return False, "fail"


def setup_logging(log_dir):
    log_path = pathlib.Path(log_dir) / LOG_FILE_NAME
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger = logging.getLogger("workorder")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


def main():
    parser = argparse.ArgumentParser(description="7-Eleven workorder image auto-renamer")
    parser.add_argument("--folder", help="Workorder folder (omit to launch folder picker)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without moving files")
    args = parser.parse_args()

    print("=" * 60)
    print("  7-Eleven workorder image auto-renamer")
    print("=" * 60)

    if args.folder:
        folder = pathlib.Path(args.folder).expanduser()
        if not folder.is_dir():
            print(f"\nFolder not found: {folder}", file=sys.stderr)
            sys.exit(1)
    else:
        folder = pick_folder_interactive()

    print(f"\nFolder: {folder}")

    try:
        api_key = load_api_key()
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)

    logger = setup_logging(folder)

    files = [f for f in sorted(folder.iterdir())
             if f.is_file()
             and f.suffix.lower() in SUPPORTED_EXT
             and not already_renamed(f.name)]

    if not files:
        print("\nNothing to do (no .jpg/.jpeg/.png in folder, or all already renamed).")
        return

    print(f"Found {len(files)} file(s) to process. Starting...\n")
    logger.info(f"=== Start processing {len(files)} files (dry_run={args.dry_run}) ===")

    ok = fail = 0
    for i, f in enumerate(files, 1):
        print(f"[{i}/{len(files)}] {f.name}")
        success, _ = process_one(f, api_key, logger, dry_run=args.dry_run)
        if success:
            ok += 1
        else:
            fail += 1

    logger.info(f"=== Done: {ok} ok / {fail} fail ===")
    print(f"\nDone: {ok} ok / {fail} fail")
    print(f"  ✓ Renamed files:    {folder / SUBFOLDER_DONE}")
    print(f"  ✗ Failed files:     {folder / SUBFOLDER_ERROR}")
    print(f"  📝 Log:             {folder / LOG_FILE_NAME}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        # On Windows double-click, keep the console open
        if os.name == "nt":
            try:
                input("\nPress Enter to close...")
            except EOFError:
                pass
