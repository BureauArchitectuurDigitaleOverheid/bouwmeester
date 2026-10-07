# debat_eval

Measures how well the application marks what happens in a debate, on real
debates with the real model, and shows what a change to the prompt or to the
checks in the code gains or costs.

Today the code marks three kinds: a `vraag` put to the bewindspersoon, a
`motie` that a member announces or reads out, and a `toezegging` of the
bewindspersoon. Two more kinds are named in `models/debat_markering.py`. The
gold format, the codebook and the scoring cover all five, so a kind that gets
built can be measured from its first prompt.

Nothing in this directory is used by the application. `VOORSTEL.md` (Dutch)
holds the proposal that came out of the first measurement; "What was built
from the proposal" and "Toezeggingen" below say what became of it and what
it measured.

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
| `variants.py` | Where a prompt variant to try goes, and the production checks for scoring a run from before they existed |
| `stats.py` | Counts of a gold set: items per kind, per hour, hard negatives |

Tests: `backend/tests/test_debat_eval.py`. The fixture
`backend/tests/fixtures/debat_markeringen_synthetisch.json` is a made-up debate
of 37 turns in the gold format that covers every kind and every hard negative
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
baseline. The variants of the first measurement are in `prompts.py` now, so
only `productie` is left; a new wording to try is one line in
`PROMPT_VARIANTS`.

A gold file of a debate on an initiatiefnota or initiatiefwet can name the
initiatiefnemers the way the TK API does, in
`debat.initiatiefnemer_namen` (`[{"naam": "A.B. Voorbeeld", "fractie": "X"}]`).
Without it the harness runs as production does for a debate the API lists
nobody for.

### Providers

| `--provider` | What it is | Needs |
|---|---|---|
| `claude_cli` (default) | `ClaudeCliLLMService`: one `claude -p` process per call | The `claude` binary, logged in. No key: without `CLAUDE_CODE_OAUTH_TOKEN` it uses the login of the local CLI |
| `configured` | Whatever `get_llm_service` picks, as in production | `ANTHROPIC_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN` or the VLAM settings, in the environment or the config table |
| `oracle` | Answers with the gold questions of the turn, and for a turn of the bewindspersoon with its gold toezeggingen | Nothing. Shows what the code alone loses |

The first measurement used `claude_cli` with the default `LLM_MODEL`
(`claude-haiku-4-5-20251001`). Check which model production is configured with
before reading the numbers as production numbers.

### What a run costs

The service skips the chairman, turns under five words and interruptions of
a member that name no bewindspersoon. On the first gold set (328 turns, 5.8
hours of speech) that left 135 turns of members for the model, 136 calls with
one retry. With four debates in parallel the run took 7 minutes through the
CLI. Run it in the background and read the progress lines; each turn prints
one.

A turn of the bewindspersoon is read for toezeggingen, with a prompt of its
own, in windows of about 4,000 characters, a call each, and only the windows
in which the words of a commitment stand somewhere
(`debat_toezegging.may_hold_commitment`). The set has 38 such turns in two
debates: a median of 640 characters, a ninth decile of 5,214, a longest of
11,248; 5 are over 4,000 and none over 12,000. That is 27 calls a run on top
of the 135 for the turns of members: 4.6 more per hour of speech over the
whole set, against 3.6 when an answer was one call whatever its length. A
call for a window took 4.2 to 7.1 seconds (14 calls on one debate).

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

## What was built from the proposal

The first three steps of `VOORSTEL.md` are in production code: the two
paragraphs in the prompt, the checks on the quote in `lees_antwoord`
(`debat_vraag_vorm.has_question_form`, `debat_motie.is_motion_text`), the
names of the initiatiefnemers where the TK API gives them, and the motie as a
kind of its own (`debat_motie.find_moties`, by rule, without a model).

### One debate was kept apart

The proposal warned that the question-form check was tuned on the whole gold
set. So the rules were made on three of the four debates (the two
commissiedebatten with a bewindspersoon and the fragment) and the fourth, the
plenary one, was left unread until the last run was in. One caveat: the word
lists the check started from were written with all four debates in view, so
the debate that was kept apart is less unseen for the questions than it is
for the moties.

Model `claude-haiku-4-5-20251001` through `claude_cli`, three runs each, 135
calls a run. The mean, and the lowest and highest run. "After" is the first
version that was built; "after the review" is what is in the code now, with
the rules for moties narrowed and the question-form check widened (see
below).

| Questions | Marked | Wrong | Precision | Recall |
|---|---|---|---|---|
| Three debates the rules were made on, before | 133 to 145 | 32 to 43 | 73% (70 to 76) | 95% (93 to 96) |
| The same, after | 116 to 117 | 13 to 16 | 87% (86 to 89) | 93% (91 to 94) |
| The same, after the review | 111 to 116 | 11 to 13 | 89% (88 to 90) | 91% (90 to 94) |
| The debate kept apart, before | 41 to 49 | 12 to 19 | 65% (60 to 70) | 93% (93 to 93) |
| The same, after | 35 to 36 | 6 to 9 | 79% (75 to 82) | 90% (86 to 93) |
| The same, after the review | 34 to 42 | 6 to 10 | 80% (76 to 82) | 91% (90 to 93) |
| All four, before | 182 to 191 | 51 to 55 | 71% (70 to 72) | 95% (93 to 96) |
| All four, after | 152 | 19 to 24 | 85% (84 to 87) | 92% (90 to 93) |
| All four, after the review | 145 to 153 | 17 to 23 | 87% (85 to 88) | 91% (90 to 93) |

What that says:

- The debate that was kept apart gains as many points of precision as the
  other three (about 15), from a lower start to a lower end.
- The review widened the question-form check for questions without a
  question mark: a preposition in front of the question word, indirect
  questions, requests for a reaction or a toezegging, a condition or a
  vocative first, a verb with a subject that is nobody at the table. That
  cost no precision that three runs can show: 87% after it against 85%
  before it on all four, inside the spread of either. Applied to the stored
  answers of the three runs before, the wider check lets one more wrong
  marking through in one run of three, and keeps one more sure question in
  two.
- What the check still costs. In the debate kept apart it dropped one
  question the labeller was sure of in every run, the same one: a demand
  worded as a wish, without the word order or the words of a request, and
  with the request for a reaction in the next sentence, which the model left
  out of its quote. Reading the sentence after the quote would catch it.
  That was tried on the three debates, gained about one right marking and
  one wrong one per run, and was left out. In the three debates the rules
  were made on it dropped a quote of a sure question in two runs of three:
  the tail of a question whose first words the model had cut off. One of
  those shapes ("met me eens dat") was added to the rule after these runs.
- The rest of the lost recall is not the form check. Of the 134 questions the
  runs before found 128, 127 and 125, the runs after the review 122, 121 and
  125. Per run 1 to 3 more were named by the model with a quote that is not
  in the turn; the others the model did not name. That is the model finding
  a little less with the new paragraphs, or chance: three runs do not tell
  those apart.
- The checks alone, applied to the answers of the three runs before, without
  asking the model again: 83% precision (81 to 85) at 94% recall on all four.
- Wrong markings left, summed over the three runs after the review, all four
  debates: 20 statements, 9 questions to nobody in the debate with
  initiatiefnemers, 7 not labelled yet, 6 calls, 6 retold, 5 rhetorical, 3 to
  the initiatiefnemers, 2 to another member, 1 about the cabinet. Before: 65
  statements, 24 times the text of a motie, 6 about the cabinet.
- The names of the initiatiefnemers: one debate has them. In the turns of the
  initiatiefnemers the checks left 4 or 5 markings per run, of which 0 to 2
  were right; asking that the quote names the bewindspersoon takes 1 to 3 of
  the wrong ones away and none of the right ones. Too little to say more
  than that it does no harm.
- The debate kept apart was read after the first three runs, to see what was
  lost in it. The rules of the review were written from made-up sentences
  and checked on the other three debates, but it is no longer unseen.

| Moties | Gold, sure | Found | Gold, unsure or repeated | Found | Marked | Wrong |
|---|---|---|---|---|---|---|
| Three debates the rule was made on | 10 | 10 | 2 | 2 | 12 | 0 |
| The debate kept apart | 1 | 1 | 1 | 0 | 1 | 0 |

The same in every run, before and after the review: the rule asks no model.
Of the 11, 9 were read out and 2 announced. The one that was not found is a
motie a member said to be considering, in a clause that leaves its subject
out; the codebook calls that unsure. One debate with one announcement is not
a test of the rule for announcements: that rule is narrow on purpose and will
miss other wordings. No dictum was marked as a question in any run after,
against 6 to 9 per run before.

The gold set does not show what the review found, because nobody in these
four debates says "aan de orde van de dag" next to a question or tells what
an earlier motie "verzoekt" in a turn with another part of the formula. So
the rule now takes a part of the formula only in the shape it has in a motie
("overwegende dat", not "aan de orde van de dag", not "de motie verzoekt"),
and only close to the other parts: at most 600 characters between two parts
in front of the dictum and 900 from the dictum to the close, against 404 and
619 at most in the 9 moties that were read out. A dictum with "motie" in the
five words in front of it is told about and is no motie; none of the 9 has
that. Those cases are tested on made-up sentences only.

### What is still open

- The oordeel of the bewindspersoon on a motie is not read from the debate.
  A motie stays "open" until someone ticks it off.
- A motie that is announced in the first term and read out in the second is
  marked twice. The table has `DebatMarkeringVermelding` for that; nothing
  writes it for a motie yet.
- The first line of a motie is the start of its dictum as the transcript has
  it. A summary by the model would read better and cost a call per motie.
- Whether the TK API lists the initiatiefnemers before a debate begins is not
  known. Meetings that are planned carry none; 20 of 33 that were held do.
- A dictum whose opening and considerans fell in the turn before and whose
  close was not heard is a dictum alone, and is not marked: the rule reads
  one turn and cannot tell it from someone talking about a motie. Reading
  it would take the end of the turn before.
- A turn of which only moties are stored counts as not read by the model, so
  that a model that was away loses no questions. Read a second time, such a
  turn costs one more call; the worker reads a turn once.
- In a turn of an initiatiefnemer a question counts when its quote names the
  bewindspersoon by title, misheard titles included. "Kan hij dat toezeggen"
  with nothing but "hij" is dropped there.

## Toezeggingen

Step 4 of the proposal. A turn of the bewindspersoon, which the code used to
skip, is read for toezeggingen and for nothing else.

### What is code and what is the model

| | Who decides |
|---|---|
| Which turns are read, and in which order: those of members first, then at most two windows of answers per round | Code (`debat_vraag_worker`) |
| How an answer is cut: windows of about 4,000 characters that end where a sentence ends and begin two sentences back, and how far a turn was read | Code (`answer_window`, `antwoord_gelezen_tot`) |
| Whether a window goes to the model: the words of a commitment stand in what is new in it | Code (`next_window`, `may_hold_commitment`) |
| Which sentences the model is pointed at | Code (`commitment_passages`) |
| Whether a sentence commits to anything, the summary, the moment that was named, which earlier toezegging it repeats, which open question it answers | Model |
| The quote stands literally in the turn | Code (`locate_citaat`) |
| The quote has the form of a commitment. Dropped: a refusal anywhere in the clause, "daar kom ik zo op terug" and the second term, coming back without a moment or anything to deliver, what was promised before, a question told back | Code (`has_commitment_form`) |
| The moment is shown only when its words stand in the quote, one after the other | Code (`deadline_is_said`) |
| A repeat is one only when it shares two words of substance with the toezegging it points at; otherwise it is new | Code (`shares_a_subject`) |
| The question it is linked to is open, was asked before the answer, was put to this bewindspersoon, and shares two words of substance with the toezegging | Code (`_vragen_aan`, `shares_a_subject`) |
| The same toezegging seen by two windows is stored once | Code (`_nog_niet_opgeslagen`) |
| Who it was promised to: whoever asked the linked question, or the member who interrupted right before a toezegging at the start of the answer, unless the meeting was suspended in between; otherwise nobody | Code (`_aan_wie`) |

### Which debate was kept apart, and how far that still holds

The plenary debate that was kept apart for the questions has no turn of a
bewindspersoon, so it says nothing about toezeggingen. Two debates have
answers: the notaoverleg (6 turns of the bewindspersoon, 8 toezeggingen the
labeller is sure of) and the wetgevingsoverleg (32 turns, 4 sure). The
rules, the prompt and the check on a link were made on the notaoverleg and
on made-up sentences, and measured with the wetgevingsoverleg unread
("first version" below).

After that the wetgevingsoverleg was read, and a review of the code asked
for forms that never reached the model to be let through. Two of the
wordings that were added then are the two this debate had shown to be
missing: a letter the cabinet is preparing, and an intention with a word
between "ik" and its verb. So for the version that is in the code now the
wetgevingsoverleg is no longer unseen. Its row below shows that the two are
found, not that the rules hold on a debate nobody looked at. That takes a
new debate.

### What it measured

Model `claude-haiku-4-5-20251001` through `claude_cli`, three runs each. The
mean, and the lowest and highest run. "In an answer" is how many of the sure
ones stand in a turn of the bewindspersoon; the others no run can find.

| Toezeggingen | Sure | In an answer | Found | Unsure or repeated, found | Marked | Wrong | Precision | Recall |
|---|---|---|---|---|---|---|---|---|
| Notaoverleg, first version | 8 | 6 | 4 to 5 | 1 to 2 of 7 | 5 to 7 | 0 | 100% | 54% (50 to 62) |
| The same, now | 8 | 6 | 5 | 3 of 7 | 9 | 1 | 89% | 62% |
| Wetgevingsoverleg, first version, unread then | 4 | 3 | 1 to 2 | 1 to 2 of 7 | 4 to 5 | 1 | 77% (75 to 80) | 42% (25 to 50) |
| The same, now, no longer unseen | 4 | 3 | 3 | 2 of 7 | 6 to 7 | 1 | 84% (83 to 86) | 75% |
| Both, first version | 12 | 9 | 5 to 7 | 2 to 4 of 14 | 9 to 12 | 1 | 90% (89 to 92) | 50% (42 to 58) |
| Both, now | 12 | 9 | 8 | 5 of 14 | 15 to 16 | 2 | 87% (87 to 88) | 67% |

Counted as for the questions: an unsure or repeated item that is found is
right, one that is not found is no miss. "First version" is one call per
answer and the rules before the review; "now" is windows of 4,000
characters, the rules after the review, 162 calls a run.

What that says, and what it cannot:

- Twelve sure toezeggingen is too few for a percentage to mean much: one
  toezegging more or less is 8 points of recall on both and 25 on one
  debate. What the numbers show is the shape. Nearly nine in ten of what
  is marked is a toezegging, and of the 9 that stand in an answer 8 are
  found, the same 8 in each of the three runs.
- The gain in recall has three causes that these runs do not tell apart:
  the model reads 4,000 characters instead of up to 11,000, the two
  wordings that were added, and chance. On the notaoverleg alone, where no
  wording was added for what it holds, the model found 5 of 6 in two quick
  runs with windows against 4 of 6 with one call per answer.
- Two wrong markings per run where there was one, one in each debate and
  the same two in every run. Both are the kind the first version had: what
  is being done or looked at anyway, said with "we" and a verb of doing.
  The one in the notaoverleg came in with a wording that was added after the
  review ("doen we").
- Of the 12 sure ones, 3 cannot be found by any run. Two stand in the turn
  of the member who interrupted, where the time put them; one is only in
  the list the chairman reads at the end.
- The one in an answer that is still missed, in every run, is worded as a
  wish, without a moment or anything to deliver, in the notaoverleg. It is
  said again later in the same answer with a sum of money, and that
  sentence was marked in every run: the labeller calls it a repetition, so
  it counts as right and not as found.
- Nothing the model named was dropped wrongly by the form check in these
  three runs, and no window that held a sure toezegging was passed over.

### The link to a question

The gold set does not say which question a toezegging answers, so this was
read by hand, by one reader.

| | Named by the model | Kept by the code | Of those, the question that was answered |
|---|---|---|---|
| First version, three runs | 22 | 11 | 11 |
| Now, three runs | 25 | 10 | 7 |

Of the 3 that were kept and are not right, one is a question near it and
two link a toezegging about one part of a regulation to a question about
another part of it: they share the name of the regulation and one more
word. The check that was tightened after the review (words every debate is
about no longer count) kept all 11 of the first version when applied to
those runs again; the three wrong ones are new links of new runs.

So about one link in six is wrong over the two sets of runs together (18
of 21 right). It is shown in the reply as "bij vraag 12", where a reader
sees at once when it is off. It is not enough to tick a question off by: 3
to 4 links per run on 134 questions, and a toezegging to come back to
something in writing is the opposite of an answer. Asking for three shared
words instead of two would have dropped the three wrong ones and two of
the right ones; that was not measured in a run. Who a toezegging was
promised to follows the link or the interruption before it; that was not
checked against anything.

### How long a toezegging waits

A turn is read when it is over. In the gold set the 21 toezeggingen that
stand in an answer were said a median of 74 seconds before the end of
their turn, a ninth decile of 429 and at most 493: that long they wait
before anything can be marked, with one call per answer and with windows
alike. After the end of the turn come the margin of the worker and the
call itself, 4 to 7 seconds for a window. With windows a long answer is
read over more rounds, one or two windows a round, so its last toezegging
comes up to a round or two later than with one call.

### Questions and moties, with the answers read as well

Nothing on the path of a question or a motie changed: a turn of the
bewindspersoon was skipped for both and still is. The three runs of "now":

| Questions | Marked | Wrong | Precision | Recall |
|---|---|---|---|---|
| Three debates the rules were made on | 109 to 119 | 12 to 17 | 88% (85 to 89) | 91% (90 to 92) |
| The debate kept apart | 35 to 37 | 5 to 8 | 82% (77 to 86) | 93% |
| All four | 144 to 155 | 19 to 22 | 86% (86 to 87) | 92% (90 to 93) |

Against "after the review" above: 89% and 91%, 80% and 91%, 87% and 91%.
Within a point or two either way, with ranges that overlap; three runs of
the same code do not tell that apart from chance. The moties are the same
in every run: 11 of 11 sure ones, 13 marked, none wrong.

### What is still open

- A toezegging is marked when the turn it is in is over, minutes after it
  was said in a long answer. The windows and the read position are what
  reading during the turn needs, and it is not built: which text of a turn
  that is still going on is final (the subtitles read past it, the voices
  done with its lines) and what to do when a line moves out of a window
  that was read are a change of their own.
- The reply of a toezegging hangs under the first message of the turn, also
  when the answer is long and cut into several messages
  (`MESSAGE_LIMIT`): the messages that follow are posts of their own in the
  channel, and the status line is under the first. The time in the reply
  links to the moment the toezegging was said. Hanging it under the message
  that holds the quote goes with reading during the turn.
- The list of toezeggingen the chairman reads at the end of a commissiedebat
  is not read: a turn of the chairman is skipped, as before. The list is
  what the griffie registers, and it would confirm or correct what was
  marked. Matching a line of it to a toezegging of two hours earlier takes
  a model; the one debate with a list has three lines.
- A sentence of the bewindspersoon that the time put in the turn of the
  member who interrupted is not found: such a turn is read for questions
  and moties only. In production the voices move most of those lines before
  the turn is read; how many are left is not measured.
- A toezegging does not change where a question stands.
- The form of a toezegging (a letter, a debate, an inquiry) is not stored.
- The page with the debates that were followed counts questions only.

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
  (`toezegging_aangehaald`), a refusal (`weigering`: "dat kan ik niet
  toezeggen"), a condition that commits to nothing (`voorwaardelijk`: "als
  zij dat willen, zou ik kunnen overwegen"), the oordeel on a motion.
- A member who asks for one ("kan de minister toezeggen dat") asks a
  question, or for a letter. It is a `vraag` or a `verzoek_om_brief`.

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
- The question-form check was made on three of the four debates; see "One
  debate was kept apart" for what it does on the fourth.
