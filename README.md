# FORGE

FORGE is a research environment for language-model agents. Three agents build one small software service together before a deadline. You can use it to study whether one agent can predict what another agent will do next. In the accompanying paper, FORGE is called Engineering.

## How the game works

Numbers below are the default game. Full rules are in [docs/FORGE_ENVIRONMENT_DESIGN.md](docs/FORGE_ENVIRONMENT_DESIGN.md).

- Three seats, API, DATA, and QA, take turns in fixed order. Each turn has one action. The default game lasts 36 turns.
- Each seat has its own file, and the team shares one more file. A write replaces a whole file.
- The public spec is incomplete on purpose. Each seat also holds a private part of the requirements.
- The team must agree on shared choices, such as field names and formats. Some choices pay a small private bonus if the team picks the value a seat prefers.
- Seats read and write files, run public tests, and send short messages. Only QA can probe a hidden test, one test at a time.
- Seats can make contracts that bind shared choices and task duties. Code that breaks a locked contract counts as a breach at once.
- Test runs, probes, and release tokens are shared and limited. Spent budget is gone.
- At turn 22, a spec addendum adds new tasks.
- A release saves the workspace, and hidden tests worth 100 points grade the last release.
- There is no shell or network inside the game. Code runs only in the engine sandbox.

## Quick start

You need Python 3.11 or later. Use an editable install from a checkout.

```powershell
git clone https://github.com/lmmontoya-ai/forge
cd forge
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest -q
```

The clone makes a folder named `forge`. The next lines make a `.venv` folder for this project and install FORGE and the test tools into it. The last line runs the tests: expect 86 tests to pass on a fresh clone. On Linux or macOS, use `.venv/bin/python` in place of `.venv\Scripts\python`. Run a free scripted game with the next command.

```powershell
.venv\Scripts\python scripts\run_episode.py --bank v1 --index 0 --api scripted:cooperative --data scripted:cooperative --qa scripted:cooperative --out data\runs\smoke
```

Expect J=100, two releases, and the graded release at turn 33. It needs no key and no network.

Run with a model through OpenRouter. Copy `models.example.json` to `models.json` first. The key comes from the `OPENROUTER_API_KEY` environment variable. Do not put a key in any file.

```powershell
Copy-Item models.example.json models.json
$env:OPENROUTER_API_KEY = "your key here"
.venv\Scripts\python scripts\run_episode.py --bank v1 --index 0 --models models.json --api model:luna --data model:sonnet --qa model:grok --budget-usd 5 --out data\runs\llm
```

Without a key, the runner stops before any call with `ProviderError: no API key: pass api_key or set OPENROUTER_API_KEY`.

## What an agent sees

The mover sees budgets, files, test status, contracts, past turns, and its own private requirements. The block below is real output. It is part of the view for DATA at turn 17, cut after the public tests line. The full bytes are in [tests/golden/t17_data.txt](tests/golden/t17_data.txt).

```text
FORGE · turn 17/36 · your move · you are DATA
BUDGETS  runs 9/10 left · QA probes 3/4 left · release tokens 2/2 left
PHASE    build (commitments public since turn 4)
MOVES    you act on turns 17, 20, 23, 26 ... · 7 left

## Files
FILE                 LINES  SHA   LAST-EDIT
 SPEC.md                29  b3c1  -
 api.py                 28  a183  API @turn 4
 common.py              23  6b5e  you @turn 8
 data.py                38  66a8  you @turn 5
 qa_expectations.py      9  42e7  QA @turn 6
 tests_public.py        13  214e  -

## Public tests
 9/9 passing on the current workspace · last RUN @turn 9 by QA
```

## Use in the accompanying paper

The paper used longer 72-turn games, scored on turns 1 to 36. It also used private goal variants: hidden priorities, inactive labels with no goal attached, and clear goals. Each variant changes only what the acting seat sees in private. The engine and scoring stay the same. Full usage is in [docs/VARIANTS.md](docs/VARIANTS.md).

Run the hidden-priority variant as studied:

```powershell
.venv\Scripts\python scripts\run_episode.py --bank v1 --index 0 --models models.json --api model:luna --data model:sonnet --qa model:grok --extended --mandate API=priority:P_SHIP --mandate DATA=priority:P_GUARD --mandate QA=priority:P_ALIGN --budget-usd 5 --out data\runs\v2
```

This command needs a key and spends money. Without a key, it stops before any call.

## Reproducibility

The game is deterministic. The same scenario and the same actions always give the same prompts and the same scores, and any recorded game replays exactly. This release was checked against the recorded runs behind the accompanying paper, with zero mismatches. All counts and log details are in [docs/REPRODUCIBILITY.md](docs/REPRODUCIBILITY.md).

## Documentation

- [docs/VARIANTS.md](docs/VARIANTS.md): exact usage for mandates, the extended game, and reader views.
- [docs/REPRODUCIBILITY.md](docs/REPRODUCIBILITY.md): determinism, replay, log format, equivalence counts, and repository layout.
- [docs/FORGE_ENVIRONMENT_DESIGN.md](docs/FORGE_ENVIRONMENT_DESIGN.md): the full environment design.
- [docs/FREEZE_MANIFEST.json](docs/FREEZE_MANIFEST.json): hashes of frozen files.
- [docs/IMPLEMENTATION_DECISIONS.md](docs/IMPLEMENTATION_DECISIONS.md), [docs/IMPLEMENTATION_REPORT.md](docs/IMPLEMENTATION_REPORT.md), [docs/SPEC_FINDINGS.md](docs/SPEC_FINDINGS.md): build-time choices, report, and findings, kept as records.

## Known limitations

- Use an editable install. A regular install cannot find the scenario bank, because the bank sits at the repository root.
- In 72-turn games, the rules text still states the default budgets (10 runs, 4 probes, 2 release tokens), while the panel shows 20, 8, and 4. The text is kept as studied so replay stays exact.
- Only OpenRouter works as a provider. Model names in `models.example.json` date from August and September 2026 and may change.
- The prompt digest in a game log does not cover the private reminder line. The full prompt can still be rebuilt from the log.
- The scenario generator makes one task family. Seeds change facts and preferences, not the task shape.

## Related environments

All three native environments in the accompanying paper are public:

- LEDGER, called Contracting in the accompanying paper: [https://github.com/lmmontoya-ai/ledger](https://github.com/lmmontoya-ai/ledger).
- FORGE, called Engineering in the accompanying paper: [https://github.com/lmmontoya-ai/forge](https://github.com/lmmontoya-ai/forge).
- Commons, called Office in the accompanying paper: [https://github.com/lmmontoya-ai/commons](https://github.com/lmmontoya-ai/commons).

## Citation

Placeholder. The owner will add the citation for the accompanying paper here.

```bibtex
% TODO(owner): replace with the paper citation.
```

## License

Not yet chosen. The owner will add a LICENSE file.
