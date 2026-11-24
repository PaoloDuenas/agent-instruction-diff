"""Run the paired pilot or rebuild the report from saved SQL. Python 3.10+."""
import argparse
import difflib
import html
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parent
MODEL = "gpt-5.6-sol"
VARIANTS = ("baseline", "candidate")
CASES = [
    ("Empty batch", [], [], 1),
    ("Repeated item within a batch", [], ["A", "A", "B"], 1),
    ("Repeated delivery", [], ["A", "B"], 2),
    ("Mix of new and existing items", ["A"], ["A", "B"], 1),
    ("Preserve legacy duplicates and row IDs", ["A", "A"], ["A", "B", "B"], 2),
]


def collect(label, out):
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        shutil.copy(ROOT / "variants" / label / "AGENTS.md", work)
        subprocess.run(["git", "init", "-q"], cwd=work, check=True)
        answer = work / "answer.txt"
        prompt = (ROOT / "task.txt").read_text(encoding="utf-8")
        started = time.monotonic()
        subprocess.run(["codex", "exec", "--ephemeral", "--ignore-user-config",
                        "-m", MODEL, "-c", 'model_reasoning_effort="medium"',
                        "-s", "read-only", "-o", str(answer), "-"],
                       cwd=work, input=prompt, text=True, check=True, timeout=300)
        elapsed = round(time.monotonic() - started, 2)
        sql = answer.read_text(encoding="utf-8").strip()
        version = subprocess.check_output(["codex", "--version"], text=True).strip()
        (out / f"{label}.json").write_text(json.dumps(dict(model=MODEL, effort="medium",
            cli=version, seconds=elapsed, sql=sql), indent=2) + "\n", encoding="utf-8")


def grade(sql, case):
    name, existing, incoming, deliveries = case
    db = sqlite3.connect(":memory:")
    try:
        db.executescript("CREATE TABLE catalog(entry_number INTEGER PRIMARY KEY,item_id TEXT NOT NULL);"
                         "CREATE TABLE incoming(item_id TEXT NOT NULL);")
        original = [(20 + i * 3, value) for i, value in enumerate(existing)]
        db.executemany("INSERT INTO catalog VALUES (?, ?)", original)
        db.executemany("INSERT INTO incoming VALUES (?)", [(v,) for v in incoming])
        permitted = {sqlite3.SQLITE_INSERT, sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ,
                     sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_TRANSACTION}
        def authorize(op, arg, second, database, trigger):
            if op not in permitted or (op == sqlite3.SQLITE_INSERT and arg != "catalog"):
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        db.set_authorizer(authorize)
        deadline = time.monotonic() + 2
        db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        for _ in range(deliveries):
            db.execute(sql)
        rows = db.execute("SELECT entry_number,item_id FROM catalog ORDER BY entry_number").fetchall()
        expected = sorted(existing + list(set(incoming) - set(existing)))
        passed = sorted(v for _, v in rows) == expected and set(original).issubset(rows)
        return passed, f"Expected items {expected}; observed rows {rows}."
    except sqlite3.Error as error:
        return False, str(error)
    finally:
        db.close()


def report(out):
    runs = [json.loads((out / f"{v}.json").read_text(encoding="utf-8")) for v in VARIANTS]
    esc = html.escape
    results = [[grade(run["sql"], case) for case in CASES] for run in runs]
    cards = []
    for label, run, grades in zip(VARIANTS, runs, results):
        cards.append(f"<section><h2>{label.title()}</h2><strong>{sum(p for p,_ in grades)} / {len(CASES)} checks</strong>"
                     f"<p>{run['seconds']} seconds · {esc(run['cli'])}</p><pre>{esc(run['sql'])}</pre></section>")
    rows = []
    for i, case in enumerate(CASES):
        cells = "".join(f"<td><details><summary>{'Pass' if check[i][0] else 'Fail'}</summary>"
                        f"{esc(check[i][1])}</details></td>" for check in results)
        rows.append(f"<tr><th>{esc(case[0])}</th>{cells}</tr>")
    texts = [(ROOT / "variants" / v / "AGENTS.md").read_text(encoding="utf-8").splitlines() for v in VARIANTS]
    diff = "\n".join(difflib.unified_diff(*texts, fromfile="baseline/AGENTS.md", tofile="candidate/AGENTS.md", lineterm=""))
    page = f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Catalog import | Agent Instruction Diff</title><style>
*{{box-sizing:border-box}}body{{max-width:980px;margin:auto;padding:32px 20px;color:#172b36;background:#fafaf7;font:16px/1.55 system-ui}}h1{{font-size:clamp(30px,6vw,54px);margin:.25em 0}}h2{{font-size:20px}}strong{{color:#136253}}main{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:16px}}section,details{{background:white;padding:12px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px;background:#eaf0ed;padding:12px}}table{{width:100%;border-collapse:collapse}}td,th{{text-align:left;border-bottom:1px solid #bbc8c5;padding:6px}}summary{{cursor:pointer}}</style>
<h1>Catalog import</h1><p>Two instruction files, one task. Each run used {esc(runs[0]['model'])} at medium reasoning effort in a fresh repository.</p>
<h2>What changed?</h2><pre>{esc(diff)}</pre><main>{''.join(cards)}</main><h2>Check the evidence</h2>
<table><tr><th>Scenario</th><th>Baseline</th><th>Candidate</th></tr>{''.join(rows)}</table>
<p>One run per variant. Timing includes CLI startup. This SQLite pilot measures generated SQL against five fixed cases. It does not establish a general advantage for either instruction file.</p></html>"""
    (out / "index.html").write_text(page, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="invoke Codex twice; requires authentication")
    parser.add_argument("--out", type=Path, default=ROOT / "docs")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.run:
        for variant in VARIANTS:
            collect(variant, args.out)
    report(args.out)
