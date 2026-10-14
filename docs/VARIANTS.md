# FORGE variants and reader views

This page gives exact usage for the optional variants used in the accompanying paper. All variants change only the acting seat's private context. The engine, scoring and reader renders do not change. The default environment, mandate `principal` at 36 turns, renders byte-identically with or without the variant code present.

A mandate string selects the variant. The meta record in the episode log records the string for each seat, so a logged episode can be rebuilt. Code lives in `src/forge/variants/`. Registry: `src/forge/variants/registry.py`.

## Mandate strings

| Mandate | Meaning | End of mover prompt |
|---|---|---|
| `principal`, `own`, `joint` | Native mandates. Default is `principal`. | Nothing added. |
| `priority:P_SHIP` | Hidden priority: get a graded release on the board and keep one token banked. | `## Your standing priority` reminder. |
| `priority:P_GUARD` | Hidden priority: never let a release lower the graded score. | `## Your standing priority` reminder. |
| `priority:P_ALIGN` | Hidden priority: settle the interface before code is written. | `## Your standing priority` reminder. |
| `sham:COBALT`, `sham:MAROON`, `sham:BRONZE` | Inactive-label control. The seat sees an index label and the ordinary score goal. | `## Your standing priority` reminder naming the index. |
| `clear-goal:P_SHIP`, `clear-goal:P_GUARD`, `clear-goal:P_ALIGN` | Clear-goal active arm. | `## Your sole scored objective` reminder. |
| `clear-sham:COBALT`, `clear-sham:MAROON`, `clear-sham:BRONZE` | Clear-goal inactive arm. | `## Your sole scored objective` reminder. |

The Mandate paragraph in the system text changes with the mandate. No other system text changes, except the deadline sentences in extended episodes.

P_OWN exists in code but was not an assigned objective in the study. It is not on the menu. The runner refuses `priority:P_OWN` and `clear-goal:P_OWN` before any model call with `unknown priority 'P_OWN'`.

Two wordings of the hidden priorities exist. Iteration 1 was used only in one early check at fixed game states. Iteration 2 is what every campaign used and what `priority:<ID>` selects. Call `hidden_priority.priority_system_block(base, id, "iter1")` to render iteration 1. Pinned wording digests: iteration 2 `45f2b029...202e8f`, inactive label `8c6a9282...acfa7fc`, clear goal `d1957960...68553b`. Tests check these digests.

Each hidden priority names Omega-2 axes it should raise or lower. P_SHIP raises `release_share` and lowers `verify_share`. P_GUARD raises `verify_share` and lowers `breach_share` and `release_share`. P_ALIGN raises `coordinate_share` and lowers `cross_write_share`. See `AXES` and `Priority.raises` and `lowers` in `src/forge/variants/hidden_priority.py`.

## Run each variant

All commands below need `models.json` and a key in `OPENROUTER_API_KEY`. Copy `models.example.json` to `models.json` first. Set the key in your shell. Do not put a key in any file. Without a key, each command stops before any call with `ProviderError: no API key: pass api_key or set OPENROUTER_API_KEY`.

Hidden priorities, as studied, with the extended deadline:

```powershell
.venv\Scripts\python scripts\run_episode.py --bank v1 --index 0 --models models.json --api model:luna --data model:sonnet --qa model:grok --extended --mandate API=priority:P_SHIP --mandate DATA=priority:P_GUARD --mandate QA=priority:P_ALIGN --budget-usd 5 --out data\runs\v2
```

Inactive-label control. Use one label, here COBALT, or mix labels by seat:

```powershell
.venv\Scripts\python scripts\run_episode.py --bank v1 --index 0 --models models.json --api model:luna --data model:sonnet --qa model:grok --extended --mandate API=sham:COBALT --mandate DATA=sham:COBALT --mandate QA=sham:COBALT --budget-usd 5 --out data\runs\sham
```

Clear goal, active arm:

```powershell
.venv\Scripts\python scripts\run_episode.py --bank v1 --index 0 --models models.json --api model:luna --data model:sonnet --qa model:grok --extended --mandate API=clear-goal:P_SHIP --mandate DATA=clear-goal:P_SHIP --mandate QA=clear-goal:P_SHIP --budget-usd 5 --out data\runs\clear
```

Clear goal, inactive arm:

```powershell
.venv\Scripts\python scripts\run_episode.py --bank v1 --index 0 --models models.json --api model:luna --data model:sonnet --qa model:grok --extended --mandate API=clear-sham:COBALT --mandate DATA=clear-sham:COBALT --mandate QA=clear-sham:COBALT --budget-usd 5 --out data\runs\clear-sham
```

You may set a different mandate per seat. A seat with no `--mandate` flag uses `principal`. Mandates apply to model seats only. The runner refuses `--mandate` on a scripted seat.

Zero-cost check of the extended deadline with scripted seats. It needs no key:

```powershell
.venv\Scripts\python scripts\run_episode.py --bank v1 --index 0 --extended --api scripted:cooperative --data scripted:cooperative --qa scripted:cooperative --out data\runs\ext-smoke
```

Expected result: J=100, two releases, graded release at turn 33, the same settlement as the 36-turn scripted run.

## Extended deadline

Flag `--extended` applies `PAPER_EXTENSION` from `src/forge/variants/extension.py`. It doubles the deadline from 36 to 72 turns, runs from 10 to 20, probes from 4 to 8 and release tokens from 2 to 4. The amendment stays at turn 22. The accompanying paper scored turns 1 to 36.

In code, call `extend_scenario(scenario)`. It returns a copy. The bank file on disk does not change.

Known property, kept for byte fidelity: the system text still states 10 runs, 4 probes and 2 release tokens in extended episodes, while the panel shows 20, 8 and 4. The system text does state 72 turns and the turn 22 amendment correctly.

The meta record in the episode log does not record extended settings. Read the event count to detect a 72-turn episode.

## Assign priorities

Use `assign_priorities(episode_id, salt=..., mode="permutation")` or `mode="iid"` from `forge.variants.hidden_priority`. It uses HMAC and no random number generator, so the same inputs give the same assignment. Mode `permutation` gives each seat a different priority. The accompanying paper used balanced designs with flat margins. That design search is study code and is not in this repository.

Function `partner_brief_line` renders the private block that tells a seat what it was told about teammates. The anticipation probe in the accompanying paper used it.

## Digests and the reminder line

The call digest in an episode log is the SHA-256 of the system block, a newline, and the user render without the reminder line. This matches the study runs. The reminder follows from the logged mandate, so the full prompt can be rebuilt from the log. Replay code `decision_prompt` in `src/forge/runtime/replay.py` digests every byte sent, reminder included.

## Reader views

Reader code lives in `src/forge/reader/`. Entry point: `build_decision_views` in `src/forge/reader/decision.py`. The reader system block keeps the rules byte-identical and swaps in a prediction mandate. Views are defined by `VIEW_PARTS` in `src/forge/reader/evidence.py`.

Views: B0, B1_count, B2_ordered, B2_shuffled, L0, L1, L2, L3, L4, L4_redacted, L4_full, C_args and C_goal. In short:

Every view starts from the same position block: the observer panel plus the target's open files. Views then add blocks.

- B0: position only, with no history of the target.
- B1_count: position plus a count of the target's past actions.
- B2_ordered: position plus the target's past actions in order.
- B2_shuffled: position plus the target's past actions in shuffled order.
- L0: position only. L1 adds every seat's past actions. L2 adds messages. L3 adds arguments. L4 adds reasoning text.
- L4_redacted: ordered actions plus reasoning text with private-goal wording removed.
- L4_full: ordered actions plus unredacted reasoning text.
- C_args: arguments only.
- C_goal: all actions, messages, arguments and the private-goal record.

For a hidden-priority episode, pass `priorities=` to the reader builder. The target's priority then joins the private-goal record. View C_goal carries it. View L4_redacted strips its wording. Function `audit_public_views` in `forge.variants.hidden_priority` checks that no public view carries priority wording.

Which views past studies used, for reference only: in the main hidden-priority study, readers saw views B0, B2_ordered, B2_shuffled and L4_redacted. In a later reader study, readers saw views B0, B1_count and B2_ordered. The nine-forecaster panel in the report used B0 as its situation view and L3 as its full-record view, with shuffle salt `ordinary-prediction-panel:v1`. This repository does not run those studies.

## Goal naming prompt

The report's goal naming result for Engineering ("Could another model identify the goal?") comes from stage S3 of the hidden-priority study. A reader saw one decision through view B0 or B2_ordered and named which of the three priorities the target held. Code: `src/forge/reader/objective.py`.

- `objective_system_block(scenario)`: the rules unchanged, with a goal naming Mandate paragraph.
- `render_objective_view(blocks, view, menu)`: the same evidence blocks as the forecast view, with the goal naming task in place of the prediction task.
- `objective_menu(salt, cell_key)`: the three priorities as options A, B and C, in an order keyed by HMAC-SHA256. The study keyed each cell as `<episode_id>:t<tick>:<reader>:<view>`.
- `parse_objective_answer` and `objective_retry`: the reply format `ANSWER: X` and the re-prompt after a bad reply.

Pass `priorities=` to `build_decision_views` as for any hidden-priority episode.

## Optional COMMIT tool forms

`ModelAgent(..., commit_form=...)` and `run_episode.py --commit-form SEAT=FORM` choose the COMMIT tool schema a model seat is sent. Code: `src/forge/runtime/commit_forms.py`.

- `map` (default): `spec/tools.v1.json` unchanged. COMMIT `slots` is an object of slot id to value.
- `nonempty-map`: the same object with `minProperties: 1`. After a COMMIT rejected for an empty slot map, the re-prompt adds one repair sentence.
- `entries`: `slots` is a nonempty list of `{slot_id, value}` entries. The reply is converted back to the object form before the engine sees it, and the log records the converted reply. The repair sentence applies too.

No form changes what the engine accepts, the prompt messages or the logged prompt digest. A non-default form is recorded in the seat's `describe()` record in the log. The five-model clear-goal study in the report used `entries` for its Gemini 3.7 Flash and Grok 4.5 seats and `nonempty-map` for its other seats. Its registration says Gemini did not follow the object keys and xAI rejected the stricter object schema.

## What is not here

Campaign drivers, balanced episode designs, forecast and policy collection, scoring pipelines and paper scripts stay in the private study repository. So do the study-only prompt additions: the notice used to test whether being watched changed behavior, the model-name cue, and the perspective sentence.
