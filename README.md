# Workorder Image Renamer

[繁體中文版 README](README.zh-TW.md)

A small, real-world automation tool that uses Claude's vision API to read
handwritten convienece-store repair workorders, extract the key fields, and rename
each photo according to a strict filing convention.

What used to be a daily 30-minute chore — open photo, squint at handwriting,
type the filename — now runs in a single double-click.

## The problem

A field technician photographs paper workorders all day. Every night the
photos need to be filed under a fixed naming convention so that they can be
searched by date, store, and repair number:

```
{mmdd} convienece-store{store}({fault} {parts_used}){repair_no}.jpg
```

Example:

```
0407 convienece-storeTonghua(SingleCup)91430773.jpg
0403 convienece-storeShuilongyin(MidWBNotHot 32mm1 Solenoid1)91431308.jpg
```

The information lives in five different positions on a paper form, in mixed
Chinese handwriting + English part codes, with a date stamped in ROC
(Republic of China) calendar format.

Manual filing — one image at a time — was the bottleneck.

## How it works

1. **Scan** the source folder for `.jpg / .jpeg / .png` files.
2. **Send each image** to Claude (`claude-haiku-4-5`) with a structured JSON
   prompt instructing it to extract five fields: stamp date, store name,
   fault description, repair items + quantities, and repair number.
3. **Parse + validate** the returned JSON; convert the ROC date to MMDD;
   strip whitespace and illegal filename characters.
4. **Compose** the filename and move the image to `done/`. Duplicates get a
   `-2`, `-3`, ... suffix. Files that fail any check land in `error/` for
   manual review.
5. **Append to log** (`rename_log.txt`) so you can audit every decision the
   model made.

The entire pipeline is in one self-contained file with zero third-party
dependencies — only the Python standard library (`urllib`, `tkinter`, ...).

## Why this is interesting as a portfolio piece

- **Real shipping use case.** Used daily by a non-technical end user. Not a
  toy demo.
- **Vision LLM as OCR-plus-classifier.** The model isn't just transcribing
  text — it's locating the correct field on a form, disambiguating which red
  8-digit number is "repair number" vs. "service ticket ID", and choosing
  the handwritten part name over the printed SKU code on the same row.
- **Defensive output handling.** JSON is parsed strictly; ROC date is
  validated; required fields are checked; failures are quarantined rather
  than guessed.
- **Cross-platform, dependency-free.** Runs on Windows, macOS, and Linux
  out of the box (Python 3.7+, no `pip install`). Tkinter-based folder
  picker for non-CLI users.
- **End-user packaging.** Includes a macOS `.command` double-click
  launcher so the operator never opens a terminal.

## Quick start

### 1. Install Python

Python 3.7+ (built-in on Windows 10/11 via Microsoft Store; macOS ships
`/usr/bin/python3`).

### 2. Get an Anthropic API key

Create one at <https://console.anthropic.com/settings/keys>. It starts
with `sk-ant-`.

### 3. Set the key

```bash
# macOS / Linux — persistent
echo 'ANTHROPIC_API_KEY=sk-ant-your-key' > ~/.workorder_rename.conf
chmod 600 ~/.workorder_rename.conf
```

```cmd
:: Windows (Command Prompt) — persistent. Open a NEW cmd after running.
setx ANTHROPIC_API_KEY "sk-ant-your-key"
```

### 4. Run

```bash
# Folder picker
python rename_workorder.py

# Specific folder
python rename_workorder.py --folder "/path/to/workorders"

# Dry-run (no files moved)
python rename_workorder.py --folder "/path/to/workorders" --dry-run
```

On macOS you can also double-click `run_rename.command` instead of using
the terminal.

## Folder layout after a run

```
workorders/
├── (incoming images)        ← drop new photos here
├── done/                    ← renamed successes
├── error/                   ← failed / low-confidence images
└── rename_log.txt           ← append-only audit log
```

## Naming spec (full detail)

```
{mmdd} convienece-store{store}({fault} {item1}{qty1} {item2}{qty2}...){repair_no}.jpg
```

| Field        | Source on the form                                | Example      |
| ------------ | ------------------------------------------------- | ------------ |
| `mmdd`       | Bottom-right store stamp (ROC date → MMDD)        | 115.4.07 → `0407` |
| `store`      | "Store name" handwritten field                    | `Tonghua` (同華) |
| `fault`      | "Fault call" handwritten field                    | `SingleCup` (單杯) |
| `item{qty}`  | "Repair content" table rows, joined by spaces     | `32mm1 Solenoid1` |
| `repair_no`  | Top-right red 8-digit "repair number"             | `91430773`   |

Rules:

- Single space (not hyphen) between `{mmdd}` and `convienece-store`. Internal `convienece-store`
  keeps its hyphen.
- When the repair-content table is empty, the parentheses contain only the
  fault description.
- Multiple repair items are joined by single spaces.
- For each row, prefer the handwritten Chinese part name over the printed
  SKU code (e.g. `銅插頭` ("copper joint") not `EVER-103743-LC`).

## Cost

Using Claude Haiku 4.5 at typical 1500×1000 px workorder photos:

- ~1,500 input tokens + ~200 output tokens per image ≈ **US$0.006**
- 30 workorders/day ≈ **US$0.18** (~NT$6)
- A month ≈ **US$5.40** (~NT$180)

Failures don't waste meaningful additional API credit since most failures
are caught at JSON parsing or field-validation stage after the response
arrives.

## Known OCR pitfalls

Handwriting is hard. Confirm these manually when in doubt:

| Correct value | Frequently misread as |
| ------------- | --------------------- |
| 單杯 (single cup) | 不出菜 (no dispense) |
| 不出水 (no water) | 不出立 |
| 電磁閥 (solenoid valve) | 電池閥 |
| 長業 (store name) | 義美 / 葉美 |

Also:

- The 8-digit **repair number** is the **red** one at top-right — not the
  service-ticket ID, sequence number, or fault code on the same form.
- The **date** is the bottom-right **store stamp**, not the call-out time
  or the technician's completion timestamp.

## Repository layout

```
workorder-image-renamer/
├── README.md                ← this file (English)
├── README.zh-TW.md          ← Traditional Chinese version
├── LICENSE                  ← MIT
├── .gitignore
├── rename_workorder.py      ← main script
└── run_rename.command       ← macOS double-click launcher
```

## License

MIT — see [LICENSE](LICENSE).
