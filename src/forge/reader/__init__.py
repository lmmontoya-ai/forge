"""Reader (observer) views: what a predictor that is not the acting seat
sees at one frozen decision.

- `forge.reader.evidence`: the evidence blocks, the view ladder
  (`VIEW_PARTS`), and private-marker redaction.
- `forge.reader.traces`: which earlier acting calls may be quoted as
  reasoning, and how readable they are.

Pure: nothing here calls a provider or changes the environment's state.
"""
