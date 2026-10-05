"""Tell the speakers of one debate apart by their voice.

Debat Direct says who has the floor, but its moments are seconds off. The
subtitles say what is said and exactly when. The audio decides whose voice
a line is: a speaker model turns a few seconds of sound into a vector, and
two vectors of the same voice point the same way.

Measured on 5 October 2026 with the model this is written for (WeSpeaker
ResNet34-LM, trained on VoxCeleb2), on a recorded debate with five
speakers: 400 lines of about two seconds, each well inside a turn so that
it is known whose it is, against the voices as they are learned here.

* The voice of who spoke scored 0.52 at the lowest, 0.61 for 99 in 100
  lines, 0.78 in the middle.
* The voice of someone else scored 0.20 in the middle, but 0.48 for 1 in
  20 and 0.61 at the highest: two people can sound alike.
* The right voice beat the best wrong one by 0.18 for 99 in 100 lines.

A voice of a person who is named is biometric data. So:

* A voice is used for one thing: to tell the speakers of one debate apart.
  It is never compared with a voice of another debate.
* It exists only in the memory of the worker (`VOICES`), learned from the
  debate itself and thrown away when the debate is over, when it drops out
  of what the timeline follows, and when it has not been used for a while.
  It is not in the database, not in a file and not in a log. After a
  restart the voices are learned again from the audio the server still has.
* What is kept is which turn a line belongs to. That says nothing about a
  voice.
"""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np

from bouwmeester.services.debat_audio import SAMPLE_RATE

logger = logging.getLogger(__name__)

# With every candidate's voice known, a line is somebody's when their
# voice scores at least this and beats the others by `MARGIN`. On its own
# this number is passed by a wrong voice now and then; the margin is what
# decides. Of the 400 lines, 399 went to the right person, none to a wrong
# one and one was left undecided.
MATCH = 0.45
MARGIN = 0.15
# With a candidate whose voice is not known yet there is nothing to beat,
# so the bar is where a wrong voice was never measured: above 0.61.
MATCH_ALONE = 0.62
# And a line is clearly not somebody's when their voice scores at most
# this: the right voice was never measured under 0.52.
MISMATCH = 0.30
# Less sound than this says too little about a voice.
MIN_SECONDS = 1.0
# How long the voices of a debate are kept without being used. A debate
# that is suspended for longer learns them again afterwards.
MAX_IDLE = timedelta(minutes=20)

_FBANK_BINS = 80


class Embedder:
    """The speaker model: sound in, a vector of length one out."""

    def __init__(self, path: str) -> None:
        # Imported here: without these libraries the timeline has to keep
        # running, only the voices fall away.
        import kaldi_native_fbank as knf
        import onnxruntime as ort

        options = ort.SessionOptions()
        # One thread. The runtime would otherwise take every core of the
        # machine, not of the container, for a job that is in no hurry.
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        self._session = ort.InferenceSession(
            path, sess_options=options, providers=["CPUExecutionProvider"]
        )
        self._input = self._session.get_inputs()[0].name
        self._knf = knf

    def embed(self, samples: np.ndarray) -> np.ndarray | None:
        """The voice in these samples (16 kHz mono, between -1 and 1).

        ``None`` for too little sound. Blocking, about a tenth of a second
        for a line: call it through `asyncio.to_thread`.
        """
        if len(samples) < MIN_SECONDS * SAMPLE_RATE:
            return None
        options = self._knf.FbankOptions()
        options.frame_opts.dither = 0.0
        options.frame_opts.samp_freq = SAMPLE_RATE
        options.mel_opts.num_bins = _FBANK_BINS
        fbank = self._knf.OnlineFbank(options)
        # The model was trained on features of 16-bit samples.
        fbank.accept_waveform(SAMPLE_RATE, (samples * 32768).tolist())
        fbank.input_finished()
        features = np.stack([fbank.get_frame(i) for i in range(fbank.num_frames_ready)])
        features = features - features.mean(axis=0)
        out = self._session.run(None, {self._input: features[None].astype(np.float32)})[
            0
        ][0]
        norm = float(np.linalg.norm(out))
        if not np.isfinite(norm) or norm == 0.0:
            return None
        return out / norm


# What the model takes: 70 MB loaded and up to 170 MB while it works
# (measured), with room to spare for the audio of a round.
MEMORY_NEEDED = 400 * 2**20
_CGROUP = (
    ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory.current"),
    (
        "/sys/fs/cgroup/memory/memory.limit_in_bytes",
        "/sys/fs/cgroup/memory/memory.usage_in_bytes",
    ),
)


def memory_left(paths=_CGROUP) -> int | None:  # type: ignore[no-untyped-def]
    """How many bytes the container may still use, or ``None`` if unlimited.

    Read from the cgroup, which is what kills a container. Not being able
    to tell counts as unlimited: on a laptop there is no such file.
    """
    for limit_path, usage_path in paths:
        try:
            with open(limit_path) as f:
                limit = f.read().strip()
            with open(usage_path) as f:
                usage = int(f.read().strip())
        except (OSError, ValueError):
            continue
        if not limit.isdigit() or int(limit) >= 2**60:
            return None
        return int(limit) - usage
    return None


# Per path: the model, or None when it could not be loaded. Looked at once
# per process, so a missing model is one line in the log and not one per
# round.
_loaded: dict[str, Embedder | None] = {}


def load(path: str) -> Embedder | None:
    """The speaker model at `path`, or ``None`` when there is none to use."""
    if path not in _loaded:
        _loaded[path] = _load(path)
    return _loaded[path]


def _load(path: str) -> Embedder | None:
    if not path or not os.path.isfile(path):
        logger.info(
            "Geen sprekermodel op %s: regels blijven op tijd bij een spreker", path
        )
        return None
    free = memory_left()
    if free is not None and free < MEMORY_NEEDED:
        # The API runs in the same container as the worker. A container
        # that is killed for its memory takes both down, and a line under
        # the wrong speaker is not worth that.
        logger.warning(
            "Te weinig geheugen voor het sprekermodel (%d MB vrij, %d MB nodig): "
            "regels blijven op tijd bij een spreker",
            free // 2**20,
            MEMORY_NEEDED // 2**20,
        )
        return None
    try:
        embedder = Embedder(path)
    except Exception as exc:
        logger.warning(
            "Sprekermodel op %s niet te laden (%s): regels blijven op tijd "
            "bij een spreker",
            path,
            type(exc).__name__,
        )
        return None
    logger.info(
        "Sprekermodel geladen van %s (%s vrij)",
        path,
        "geen limiet" if free is None else f"{free // 2**20} MB",
    )
    return embedder


def choose(scores: Mapping[str, float], unknown: Collection[str]) -> str | None:
    """Whose line it is, or ``None`` when the voices do not say clearly.

    `scores` is how much the line sounds like every candidate whose voice
    is known; `unknown` are the candidates whose voice is not. With all
    voices known a line goes to the one that matches and beats the others.
    With one still unknown it takes a stronger match, and a line that
    clearly is none of the known voices goes to the one candidate that is
    left, when there is exactly one.
    """
    if not scores:
        return None
    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    best, top = ranked[0]
    if unknown:
        if top >= MATCH_ALONE:
            return best
        if top <= MISMATCH and len(unknown) == 1:
            return next(iter(unknown))
        return None
    if top >= MATCH and (len(ranked) == 1 or top - ranked[1][1] >= MARGIN):
        return best
    return None


@dataclass
class Voice:
    """The voice of one person in one debate: the mean of what was heard."""

    total: np.ndarray
    count: int = 1
    # The moments the pieces it was learned from begin, so that no piece
    # is counted twice.
    clips: set[datetime] = field(default_factory=set)

    def add(self, vector: np.ndarray) -> None:
        self.total = self.total + vector
        self.count += 1

    def score(self, vector: np.ndarray) -> float:
        """How much a piece of sound is this voice: 1 the same, 0 unrelated."""
        return float(vector @ self.total / np.linalg.norm(self.total))


@dataclass
class SessieVoices:
    """What the worker remembers of the voices of one debate."""

    used: datetime
    voices: dict[str, Voice] = field(default_factory=dict)
    # The vector of a line that could not be decided yet, so that it is
    # not computed again on every round while a voice is still unknown.
    lines: dict[uuid.UUID, np.ndarray] = field(default_factory=dict)
    # Names of audio segments that exist, per playlist. Names, not audio.
    segments: dict[str, set[int]] = field(default_factory=dict)
    # Pieces a voice could have been learned from whose audio is gone or
    # says nothing, by the moment they begin: not asked for again.
    gone: set[datetime] = field(default_factory=set)
    # After the audio could not be read: not before this moment again.
    retry_at: datetime | None = None

    def learn(self, person: str, vector: np.ndarray, clip: datetime) -> None:
        voice = self.voices.get(person)
        if voice is None:
            self.voices[person] = Voice(total=vector.copy(), clips={clip})
        else:
            voice.add(vector)
            voice.clips.add(clip)


class VoiceCache:
    """The voices of the debates that are running, per debate.

    Lives in the process and nowhere else. Every read names a sessie:
    there is no way to ask for a voice across debates.
    """

    def __init__(self) -> None:
        self._sessies: dict[uuid.UUID, SessieVoices] = {}

    def of(self, sessie_id: uuid.UUID, now: datetime) -> SessieVoices:
        """The voices of one debate, counted as used at `now`."""
        held = self._sessies.get(sessie_id)
        if held is None:
            held = self._sessies[sessie_id] = SessieVoices(used=now)
        held.used = now
        return held

    def peek(self, sessie_id: uuid.UUID) -> SessieVoices | None:
        """The voices of one debate if there are any, without using them."""
        return self._sessies.get(sessie_id)

    def forget(self, sessie_id: uuid.UUID) -> None:
        self._sessies.pop(sessie_id, None)

    def keep_only(self, sessie_ids: Collection[uuid.UUID]) -> None:
        """Forget every debate the timeline does not follow any more."""
        for sessie_id in list(self._sessies):
            if sessie_id not in sessie_ids:
                del self._sessies[sessie_id]

    def expire(self, now: datetime) -> None:
        """Forget what has not been used for `MAX_IDLE`."""
        for sessie_id, held in list(self._sessies.items()):
            if now - held.used > MAX_IDLE:
                del self._sessies[sessie_id]

    def clear(self) -> None:
        self._sessies.clear()

    def __contains__(self, sessie_id: object) -> bool:
        return sessie_id in self._sessies

    def __len__(self) -> int:
        return len(self._sessies)


# The one place voices are. Two workers that run at the same time, as
# during a deploy, each have their own and learn the same voices from the
# same audio.
VOICES = VoiceCache()
