# debat_eval

Measures how well the application marks what happens in a debate, on real
debates with the real model, and shows what a change to the prompt or to the
checks in the code gains or costs.

Today the code marks one kind: a `vraag` put to the bewindspersoon. Four more
kinds are named in `models/debat_markering.py`. The gold format, the codebook
and the scoring cover all five, so a kind that gets built can be measured from
its first prompt.

Nothing in this directory is used by the application. `VOORSTEL.md` (Dutch)
holds the proposal that came out of the first measurement.

## What is where

| File | What it does |
|---|---|
| `build_turns.py` | Recording of a debate (subtitle lines and Debat Direct events) to a gold file without labels |
| `apply_labels.py` | Short label lines to `items` and `negatieven` in a gold file |
| `gold.py` | The gold format and its validation |
| `harness.py` | Runs `DebatVraagService` over the turns of a gold file |
| `run.py` | Command line around the harness; writes a run file and prints the report |
| `report.py` | Scores a saved run again, without a model or a database |
| `scoring.py` | Matching, counting, the report and the comparison of two runs |
| `variants.py` | Prompt variants and code checks to try, applied from outside production code |
| `stats.py` | Counts of a gold set: items per kind, per hour, hard negatives |

Tests: `backend/tests/test_debat_eval.py`. The fixture
`backend/tests/fixtures/debat_markeringen_synthetisch.json` is a made-up debate
of 30 turns in the gold format that covers every kind and every hard negative
of the codebook. It is meant for prompt tests with a fake model.

## The gold set is not in this repository

The repository is public. A gold file built from a recording holds the names
of the speakers and what they said, so it stays on the machine of whoever
labelled it. The harness takes gold files by path. Do not copy turns, quotes
or debate ids from a gold file into a test, a fixture or a commit message.
Counts are fine.

## Running it

All commands from `backend/`. The harness writes to the database (a sessie
per debate, removed afterwards), so it refuses any database whose name does
not end in `_eval`.

```bash
export DATABASE_URL=postgresql+asyncpg://bouwmeester:bouwmeester@localhost:5433/bouwmeester_eval
export DEV_NO_AUTH=1 PYTHONPATH=scripts
uv run alembic upgrade head            # once, after creating the database

# Baseline with the production prompt
uv run python -m debat_eval.run $GOLD/gold-*.json --label baseline --out $GOLD/run-baseline.json

# After a prompt change: run again and compare
uv run python -m debat_eval.run $GOLD/gold-*.json --label na-wijziging \
    --out $GOLD/run-na.json --compare $GOLD/run-baseline.json

# Score a saved run again (changed gold file, or a code check), no model needed
uv run python -m debat_eval.report $GOLD/run-baseline.json --check vraagvorm
uv run python -m debat_eval.stats $GOLD/gold-*.json
```

`--prompt-variant` sends the production prompt through one of the rewrites in
`variants.py` before it reaches the model. That is how a wording change is
measured without editing `prompts.py`. Once a change is in `prompts.py`, run
with the default variant `productie` and `--compare` against the saved
baseline.

### Providers

| `--provider` | What it is | Needs |
|---|---|---|
| `claude_cli` (default) | `ClaudeCliLLMService`: one `claude -p` process per call | The `claude` binary, logged in. No key: without `CLAUDE_CODE_OAUTH_TOKEN` it uses the login of the local CLI |
| `configured` | Whatever `get_llm_service` picks, as in production | `ANTHROPIC_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN` or the VLAM settings, in the environment or the config table |
| `oracle` | Answers with the gold questions of the turn | Nothing. Shows what the code alone loses |

The first measurement used `claude_cli` with the default `LLM_MODEL`
(`claude-haiku-4-5-20251001`). Check which model production is configured with
before reading the numbers as production numbers.

### What a run costs

The service skips the chairman, the bewindspersoon, turns under five words and
interruptions of a member that name no bewindspersoon. On the first gold set
(328 turns, 5.8 hours of speech) that left 135 turns for the model, 136 calls
with one retry. With four debates in parallel the run took 7 minutes through
the CLI. Run it in the background and read the progress lines; each
turn prints one.

## How a run is scored

A marking and a gold item match when they are in the same turn and the words
they share, in the same order and in runs of at least three words, cover at
least half of the shorter quote. One sentence more or less does not matter;
two different questions that both say "de minister" do not match.

Per kind:

- A gold item is required unless it is marked `onzeker` or `herhaling`. An
  optional item that is found is fine, one that is not found is not a miss.
- A marking is right when it matches a gold item of its kind. Two markings on
  one gold item are both right.
- A `vraag` marking on a gold `verzoek_om_brief` is left out of the count.
  Such a request is put to the bewindspersoon and the current prompt treats it
  as a question.
- Every other marking is a false positive, named after the hard negative it
  matches, the other kind it matches (`soort:motie`), or `ongelabeld`.

Precision is right / (right + false positives). Recall is required found /
required. A miss says why: the turn was skipped by the code, the model did not
give it, or the model gave it and a check dropped it.

Read every `ongelabeld` false positive after a run and label it: as a negative
if the model was wrong, as an item if the labeller missed it. Then score again
with `report.py`. In the first measurement 28 of 53 false positives were
unlabelled at first; all 28 turned out to be statements.

## Making a gold file

```bash
uv run python -m debat_eval.build_turns --debate-id <id> --vtt-dir <dir> \
    --cache <dir> --out <turns.json>
# read every turn, write labels.txt (format: see apply_labels.py)
uv run python -m debat_eval.apply_labels <turns.json> <labels.txt> <gold.json>
```

`build_turns` uses the application's own `parse_vtt`, `place_cues`,
`parse_debate`, `fetch_sprekers` and `is_bewindspersoon`. It assigns lines to
turns by time alone, with the offset the feed gives. Production moves lines
around a change of speaker by voice afterwards; this does not. The consequence
shows in the gold set: a sentence of the bewindspersoon at the end of the turn
of the member who interrupted, and the other way around. Such items are
labelled where they stand, with a note.

The context of a debate (bewindspersonen, agenda documents) comes from Debat
Direct here and from the Tweede Kamer API in production. `stukken` holds only
the name of the debate, so the choice of a document is not exercised.

## Codebook

One rule above all: the quote is cut from the text of the turn, transcript
mistakes included, and it holds the words that make it an item of its kind.

### vraag

A question or an explicit request put to a bewindspersoon (minister,
staatssecretaris, kabinet, regering), by anyone, in a term or an interruption.

- Counts with an addressee in the question ("Kan de minister ..."), before it
  ("dan heb ik vragen aan de minister", and what follows), or after it ("Graag
  een reactie van de minister").
- A question without an addressee in a member's own term counts when only the
  bewindspersoon answers in that debate. With initiatiefnemers at the table it
  does not (negative `algemeen`), unless it carries on from a question to the
  bewindspersoon.
- Questions that follow each other on one subject are one item. A new subject
  is a new item.
- An indirect question counts: "Ik ben benieuwd hoe de minister daartegen
  aankijkt", "Ik hoor graag van de minister of ...".
- An interruption of the bewindspersoon counts without an addressee.
- An initiatiefnemer who passes a question on to the minister counts, as
  `onzeker` when it is said in passing.
- "Vragen wij het kabinet om aandacht voor ..." asks for an action and not for
  an answer. Labelled `vraag`, `onzeker`. Three of these in the first set.
- A question the member asks again is a `vraag` with `herhaling`.

### toezegging

A bewindspersoon commits to something the Kamer can hold them to: a letter, a
date, coming back to it in writing or in a named report, looking into it,
taking it up with someone.

- "Dat zeg ik toe", "Ik kom daar vóór de begrotingsbehandeling schriftelijk op
  terug", "Ik neem dat mee in het halfjaarbericht".
- An effort without anything to deliver ("ik ga kijken of dat lukt", "ik wil
  mijn uiterste best doen") is `onzeker`.
- The same commitment said again, made more precise, or read out by the
  chairman at the end is `herhaling`.
- Not a toezegging: coming back to it later in the same answer
  (`later_in_debat`), work that is going on (`lopend_beleid`), what another
  minister promised (`toezegging_van_ander`), a member recalling a promise
  (`toezegging_aangehaald`), the oordeel on a motion.

### verzoek_om_brief

A member asks the bewindspersoon for something on paper: a letter, an
overview, a report, or "de Kamer informeren" with a moment or a form ("vóór de
begrotingsbehandeling", "per brief").

- "Kan de minister ons daarover informeren?" without a moment or a form is a
  `vraag`: it can be answered on the spot.
- "In kaart brengen" without asking for the result is a `vraag`.
- A suggestion about when or how to report back is `onzeker`.
- "En de Kamer daarover te informeren" in the text of a motion belongs to the
  motie.

### motie

A motion is announced ("ik zal daar een motie over indienen") or read out. For
a motion that is read out the quote is the dictum, from "verzoekt de regering"
to "gaat over tot de orde van de dag".

- "Ik overweeg een motie" is `onzeker`.
- An announcement right before reading the motion out is `herhaling`.
- "Dan scheelt mij dat een motie" is the negative `geen_motie`.

### feitelijke_claim

Kept narrow: a statement with a concrete figure or a date about the world or
about policy, that a ministry would want to check. By a member or by a
bewindspersoon.

- "Sinds 1 januari 2025 geldt ...", "Elk jaar worden ruim 480.000 ...".
- `onzeker`: a checkable fact without a figure or date, a figure quoted from
  literature, the date of a motion, an anecdote, the figure of a proposal.
- Not labelled: figures inside a question, a motion or a toezegging, dates of
  the debate itself, round rhetorical numbers.

This kind is the noisiest. One member's term can hold six figures, and which of
them a ministry cares about is a judgement the labeller cannot make from the
transcript. A second labeller would likely disagree on a third of them.

### Hard negatives

| Type | What it is |
|---|---|
| `retorisch` | A question nobody is meant to answer, or one the speaker answers |
| `aan_kamerlid` | A question to another member, also when it names the minister |
| `aan_initiatiefnemers` | A question to the initiatiefnemers, also with "zij" or "u", also when it names the kabinet |
| `over_kabinet` | A statement about the kabinet or a bewindspersoon, to whoever |
| `stelling` | A statement a question can be made of: "Niemand kan mij vertellen waar ...", "De grote vraag is of ...", a plea, a wish |
| `aangehaald` | A question from earlier, retold or repeated in order to answer it |
| `oproep` | A call without a question: "Het kabinet moet ...", "Ik hoop dat de minister ..." |
| `algemeen` | A question without an addressee where others answer too |
| `orde` | About the order of the meeting |

The examples above are made up; they are the ones in the fixture.

## Limits of the first gold set

- One labeller, no second reading. 39 of 266 items are marked `onzeker`.
- Four debates of two days, 5.8 hours of speech; one of the four is a fragment
  of a quarter of an hour. The recordings have holes: the second term of one
  debate and part of the answer of the bewindspersoon in another are missing.
- The 28 `stelling` negatives that were added after the baseline run were found
  because the model marked them. Statements the model did not mark are not all
  labelled, so the count of that type says little about how often it occurs.
- The check `vraagvorm` in `variants.py` was tuned on this set. Its numbers on
  this set are an upper bound.
