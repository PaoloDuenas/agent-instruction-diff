# Agent Instruction Diff

What changes when you edit AGENTS.md? Run the same task with two instruction files, then inspect the generated SQL and the rows each answer produced.

**[Open the pilot report](https://paoloduenas.github.io/agent-instruction-diff/)** · [Task](task.txt) · [Baseline instructions](variants/baseline/AGENTS.md) · [Candidate instructions](variants/candidate/AGENTS.md)

## Catalog import pilot

The baseline passed 2 of 5 checks. Its INSERT OR IGNORE statement relied on a uniqueness constraint that the catalog did not have. The candidate passed all five with an explicit existence check. The candidate instructions mention repeated deliveries and legacy duplicates, so the experiment measures the value of those hints on this task. One sample per condition cannot establish a repeatable effect.

The scenario adapts [round two of Agent Harness Lab](https://github.com/PaoloDuenas/agent-harness-lab/tree/51023b10fc00c02c9cba298e080918a2c47a1544). This edition uses SQLite to make replay possible with the Python standard library. Checks cover sequential imports, including an existing catalog with duplicate IDs. Concurrent writers are outside this pilot.

## Reproduce

With Python 3.10 or later, run the checks against both saved answers and rebuild the standalone HTML:

    python compare.py

To collect two fresh answers, install Git and an authenticated Codex CLI with access to the model listed in compare.py. From this directory run:

    python compare.py --run --out my-run

Open my-run/index.html. Each CLI invocation starts a fresh temporary repository containing one AGENTS.md and receives the same task. Each answer is executed against a fresh in-memory database for every case. The timer covers CLI startup through completion; local machine and provider variability affect it. The model generates a statement; the external grader executes it after the run.
