"""Tests for telling the speakers of a debate apart by their voice.

No voice of anyone is in here. The audio of the room is made up: every
sample is the number of who is speaking at that moment, and the speaker
model is replaced by one that counts those numbers. What is tested is
everything around the model: which lines are listened to, what is learned
from where, what is decided, what is kept and above all what is not.

The whole thing runs against a real database, with the made-up debates and
the fake Mattermost of the timeline tests.
"""

from __future__ import annotations

import dataclasses
import logging
import os
import re
import uuid
from datetime import datetime, timedelta

import numpy as np
import pytest
from sqlalchemy import select, update

from bouwmeester.core.config import get_settings
from bouwmeester.models.debat_sessie import (
    TIJDLIJN_AFGELAST,
    TIJDLIJN_AFGELOPEN,
    TIJDLIJN_LOOPT,
    DebatOndertitel,
    DebatSpreekbeurt,
)
from bouwmeester.services import debat_audio as audio
from bouwmeester.services import debat_stem as stem
from bouwmeester.services import debat_stemmen_service as svc
from bouwmeester.services import debat_tijdlijn_service as tijdlijn
from bouwmeester.services.debat_stemmen_service import (
    AFTER,
    BEFORE,
    Budget,
    DebatStemmen,
    Line,
    Turn,
    candidates,
    clips,
    nearest,
)
from bouwmeester.services.debat_tijdlijn_service import DebatTijdlijnService
from tests.test_debat_tijdlijn import START, Feed, _debat, _sessie
from tests.test_debat_transcript import (
    Mattermost,
    Subtitles,
    _cue,
    _minutes,
    _play,
    _stream,
)

AUDIO = "https://audio.tweedekamer.nl/zaal/audio/prog_index.m3u8"
CDN = "https://cdn.vos360.video/zaal"
# The audio stream runs about this far behind the room.
AUDIO_BEHIND = timedelta(seconds=30)
SEGMENT = audio.SEGMENT_TICKS
SAMPLES = round(audio.SEGMENT_SECONDS * audio.SAMPLE_RATE)
TICKS_PER_SAMPLE = audio.TICKS_PER_SECOND // audio.SAMPLE_RATE
# The segments are on a grid that started well before the debate.
GRID = audio.datetime_to_ticks(START) - 1000 * SEGMENT


@pytest.fixture(autouse=True)
def _no_voices_left_over():
    stem.VOICES.clear()
    yield
    stem.VOICES.clear()


def _at(seconds: float) -> datetime:
    return START + timedelta(seconds=seconds)


def _unit(*values: float) -> np.ndarray:
    vector = np.array(values, dtype=np.float32)
    return vector / np.linalg.norm(vector)


class Embedder:
    """Stands in for the speaker model: counts who is in the samples.

    A sample is the number of who is speaking, so the vector says how much
    of the piece is whose. Two pieces of the same person point the same
    way, exactly as with a real voice.
    """

    def __init__(self) -> None:
        self.heard: list[float] = []
        self.error: Exception | None = None

    def embed(self, samples: np.ndarray) -> np.ndarray | None:
        if self.error is not None:
            raise self.error
        self.heard.append(len(samples) / audio.SAMPLE_RATE)
        counts = np.bincount(np.rint(samples).astype(int), minlength=8)[1:8]
        if not counts.any():
            return None
        return (counts / np.linalg.norm(counts)).astype(np.float32)


class Sound:
    """The audio of the room: who is really speaking at every moment.

    `speaking` is (seconds after the start, number of the person), oldest
    first. Served the way the real server does: a playlist of the last
    five segments, older ones by name, nothing that has not been broadcast.
    """

    def __init__(self, monkeypatch, feed: Feed, speaking: list[tuple[float, int]]):
        self.feed = feed
        self.starts = np.array([audio.datetime_to_ticks(_at(s)) for s, _ in speaking])
        self.who = np.array([who for _, who in speaking], dtype=np.float32)
        self.embedder: Embedder | None = Embedder()
        self.down = False
        # The server has nothing from before this moment.
        self.kept_from: datetime | None = None
        self.playlists = 0
        self.misses = 0
        self.segments: list[int] = []
        # Every stretch that was asked for, and the ones that were there.
        self.asked: list[tuple[datetime, datetime]] = []
        self.got: list[tuple[datetime, datetime]] = []
        # And the moment of the round each of those was heard in.
        self.when: list[datetime] = []
        self.rounds: dict[datetime, float] = {}

        async def fetch_playlist(client, url):
            self.playlists += 1
            if self.down:
                raise audio.AudioError("down")
            last = (self._edge() - GRID) // SEGMENT - 1
            return audio.Playlist(
                init_url="init.m4i",
                segments=tuple(
                    audio.Segment(
                        GRID + n * SEGMENT, f"{CDN}/Segment-{GRID + n * SEGMENT}.m4a"
                    )
                    for n in range(last - 4, last + 1)
                ),
            )

        async def get(client, url):
            ticks = int(re.search(r"Segment-(\d+)\.m4a", url).group(1))
            if (ticks - GRID) % SEGMENT or ticks + SEGMENT > self._edge():
                return _Response(404)
            if self.kept_from and ticks < audio.datetime_to_ticks(self.kept_from):
                self.misses += 1
                return _Response(404)
            self.segments.append(ticks)
            return _Response(200, self._samples(ticks).tobytes())

        async def fetch_bytes(client, url):
            return b"init"

        def decode(init, segments):
            return np.frombuffer(b"".join(segments), dtype=np.float32)

        real = audio.Reach.samples

        async def samples(reach, start, end):
            self.asked.append((start, end))
            before = sum(self.embedder.heard) if self.embedder else 0.0
            self.rounds.setdefault(self.feed.now, before)
            heard = await real(reach, start, end)
            if heard is not None:
                self.got.append((start, end))
                self.when.append(self.feed.now)
            return heard

        monkeypatch.setattr(audio, "fetch_playlist", fetch_playlist)
        monkeypatch.setattr(audio, "_get", get)
        monkeypatch.setattr(audio, "fetch_bytes", fetch_bytes)
        monkeypatch.setattr(audio, "decode", decode)
        monkeypatch.setattr(audio.Reach, "samples", samples)
        monkeypatch.setattr(stem, "load", lambda path: self.embedder)

    def _edge(self) -> int:
        return audio.datetime_to_ticks(self.feed.now - AUDIO_BEHIND)

    def _samples(self, ticks: int) -> np.ndarray:
        moments = ticks + np.arange(SAMPLES) * TICKS_PER_SAMPLE
        index = np.searchsorted(self.starts, moments, side="right") - 1
        return np.where(index >= 0, self.who[index.clip(0)], 0).astype(np.float32)

    def lines_heard(self) -> list[int]:
        """The second every single line that was listened to starts."""
        return [
            round((start + svc.LINE_PAD - START).total_seconds())
            for start, end in self.got
            if end - start < svc.CLIP_MIN
        ]

    def clips_heard(self) -> list[tuple[float, float]]:
        """The pieces a voice was learned from, in seconds."""
        return [
            ((start - START).total_seconds(), (end - START).total_seconds())
            for start, end in self.got
            if end - start >= svc.CLIP_MIN
        ]


class _Response:
    def __init__(self, status: int, content: bytes = b"") -> None:
        self.status_code = status
        self.content = content


def _with_audio(debat):
    return dataclasses.replace(_stream(debat), audio_url=AUDIO)


def _lines(first: int, last: int, step: int = 4, length: float = 3.0):
    """A line every few seconds, named after the second it starts."""
    return [_cue(s, f"r{s}.", length) for s in range(first, last + 1, step)]


def _said(message: str) -> list[str]:
    """The lines under a message, as the names they were given."""
    parts = message.split("\n", 1)
    return parts[1].split() if len(parts) == 2 else []


async def _where(db_session, sessie) -> dict[str, tuple]:
    """Per line: (kind of event, who, seconds, how assigned, done)."""
    rows = await db_session.execute(
        select(
            DebatOndertitel.tekst,
            DebatSpreekbeurt.event_type,
            DebatSpreekbeurt.object_id,
            DebatSpreekbeurt.event_start,
            DebatOndertitel.toewijzing,
            DebatOndertitel.stem_klaar,
        )
        .join(DebatSpreekbeurt, DebatSpreekbeurt.id == DebatOndertitel.spreekbeurt_id)
        .where(DebatOndertitel.sessie_id == sessie.id)
    )
    return {
        text: (kind, who, round((start - START).total_seconds()), how, done)
        for text, kind, who, start, how, done in rows.all()
    }


# A speaker, an interruption and the answer. The events are off the way
# they are in a real debate: the interruption is entered 8 seconds before
# the interrupter says a word, the answer 10 seconds after it began.
EVENTS = (("speaker", 1, "a"), ("interrupter", 3, "b"), ("speaker", 4, "a"))
SPEAKING = [(60, 1), (188, 2), (230, 1)]


class TestChoose:
    def test_the_voice_that_matches_and_beats_the_other(self):
        assert stem.choose({"a": 0.8, "b": 0.2}, []) == "a"

    def test_not_when_the_other_is_close(self):
        assert stem.choose({"a": 0.60, "b": 0.50}, []) is None

    def test_exactly_the_margin_is_enough(self):
        assert stem.choose({"a": 0.65, "b": 0.50}, []) == "a"

    def test_not_when_nobody_matches(self):
        assert stem.choose({"a": 0.44, "b": 0.10}, []) is None

    def test_exactly_the_bar_matches(self):
        assert stem.choose({"a": stem.MATCH, "b": 0.10}, []) == "a"

    def test_one_voice_and_nobody_else_only_has_to_match(self):
        assert stem.choose({"a": 0.5}, []) == "a"

    def test_with_someone_unknown_it_takes_a_stronger_match(self):
        """Two people can sound alike: 0.5 is reached by a wrong voice."""
        assert stem.choose({"a": 0.5}, ["b"]) is None
        assert stem.choose({"a": stem.MATCH_ALONE}, ["b"]) == "a"

    def test_with_someone_unknown_the_margin_is_not_what_decides(self):
        assert stem.choose({"a": 0.70, "c": 0.65}, ["b"]) == "a"

    def test_clearly_not_the_known_voice_is_the_one_that_is_left(self):
        assert stem.choose({"a": 0.1}, ["b"]) == "b"
        assert stem.choose({"a": stem.MISMATCH}, ["b"]) == "b"

    def test_not_clearly_anything_is_left_open(self):
        assert stem.choose({"a": 0.4}, ["b"]) is None

    def test_two_unknown_voices_cannot_be_told_apart(self):
        assert stem.choose({"a": 0.1}, ["b", "c"]) is None

    def test_the_best_of_the_known_voices_counts(self):
        assert stem.choose({"a": 0.1, "c": 0.4}, ["b"]) is None

    def test_no_known_voice_no_answer(self):
        assert stem.choose({}, ["b"]) is None

    def test_a_tie_does_not_depend_on_the_order(self):
        assert stem.choose({"b": 0.7, "a": 0.7}, ["c"]) == "a"
        assert stem.choose({"a": 0.7, "b": 0.7}, ["c"]) == "a"


class TestVoice:
    def test_a_voice_is_the_mean_of_what_was_heard(self):
        held = stem.SessieVoices(used=START)
        held.learn("a", _unit(1, 0), _at(10))
        held.learn("a", _unit(0, 1), _at(20))

        voice = held.voices["a"]

        assert voice.count == 2
        assert voice.clips == {_at(10), _at(20)}
        assert voice.score(_unit(1, 1)) == pytest.approx(1.0)
        assert voice.score(_unit(1, 0)) == pytest.approx(0.7071, abs=1e-4)

    def test_a_piece_heard_more_often_weighs_more(self):
        held = stem.SessieVoices(used=START)
        for second in (10, 20, 30):
            held.learn("a", _unit(1, 0), _at(second))
        held.learn("a", _unit(0, 1), _at(40))

        assert held.voices["a"].score(_unit(1, 0)) == pytest.approx(0.9487, abs=1e-4)

    def test_learning_does_not_change_what_was_handed_in(self):
        first = _unit(1, 0)
        held = stem.SessieVoices(used=START)
        held.learn("a", first, _at(10))
        held.learn("a", _unit(0, 1), _at(20))

        assert first.tolist() == [1.0, 0.0]


class TestCache:
    def test_voices_are_per_debate(self):
        """There is no way to ask for a voice across debates."""
        cache = stem.VoiceCache()
        one, other = uuid.uuid4(), uuid.uuid4()
        cache.of(one, START).learn("a", _unit(1, 0), START)

        assert "a" in cache.of(one, START).voices
        assert cache.of(other, START).voices == {}
        assert cache.peek(uuid.uuid4()) is None

    def test_looking_does_not_count_as_using(self):
        cache = stem.VoiceCache()
        sessie = uuid.uuid4()
        cache.of(sessie, START)

        assert cache.peek(sessie).used == START
        cache.of(sessie, _at(60))
        assert cache.peek(sessie).used == _at(60)

    def test_forgetting_one_debate_leaves_the_others(self):
        cache = stem.VoiceCache()
        one, other = uuid.uuid4(), uuid.uuid4()
        cache.of(one, START)
        cache.of(other, START)

        cache.forget(one)
        cache.forget(uuid.uuid4())

        assert one not in cache
        assert other in cache
        assert len(cache) == 1

    def test_only_what_is_followed_is_kept(self):
        cache = stem.VoiceCache()
        one, other = uuid.uuid4(), uuid.uuid4()
        cache.of(one, START)
        cache.of(other, START)

        cache.keep_only([other])

        assert one not in cache
        assert other in cache

    def test_what_is_not_used_for_a_while_is_forgotten(self):
        cache = stem.VoiceCache()
        idle, used = uuid.uuid4(), uuid.uuid4()
        cache.of(idle, START)
        cache.of(used, START + timedelta(minutes=5))

        cache.expire(START + stem.MAX_IDLE + timedelta(seconds=1))

        assert idle not in cache
        assert used in cache

    def test_exactly_as_long_as_allowed_is_still_kept(self):
        cache = stem.VoiceCache()
        sessie = uuid.uuid4()
        cache.of(sessie, START)

        cache.expire(START + stem.MAX_IDLE)

        assert sessie in cache

    def test_everything_can_be_thrown_away(self):
        cache = stem.VoiceCache()
        cache.of(uuid.uuid4(), START)

        cache.clear()

        assert len(cache) == 0


class TestLoad:
    def test_without_the_file_there_is_no_model_and_one_line_says_so(
        self, caplog, monkeypatch
    ):
        monkeypatch.setattr(stem, "_loaded", {})

        with caplog.at_level(logging.INFO, logger=stem.logger.name):
            assert stem.load("/nergens/model.onnx") is None
            assert stem.load("/nergens/model.onnx") is None

        assert caplog.text.count("Geen sprekermodel op /nergens/model.onnx") == 1

    def test_no_path_no_model(self, monkeypatch):
        monkeypatch.setattr(stem, "_loaded", {})

        assert stem.load("") is None

    def test_a_file_that_is_not_a_model_does_not_stop_anything(
        self, tmp_path, caplog, monkeypatch
    ):
        monkeypatch.setattr(stem, "_loaded", {})
        broken = tmp_path / "model.onnx"
        broken.write_bytes(b"not a model")

        with caplog.at_level(logging.WARNING, logger=stem.logger.name):
            assert stem.load(str(broken)) is None

        assert "niet te laden" in caplog.text

    def test_the_model_is_read_once(self, monkeypatch, tmp_path):
        monkeypatch.setattr(stem, "_loaded", {})
        made: list[str] = []
        monkeypatch.setattr(stem, "Embedder", lambda path: made.append(path) or "model")
        there = tmp_path / "model.onnx"
        there.write_bytes(b"x")

        assert stem.load(str(there)) == "model"
        assert stem.load(str(there)) == "model"
        assert made == [str(there)]


def _harmonics(base: float, seconds: float, seed: int) -> np.ndarray:
    """A made-up sound with a pitch and overtones. Nobody's voice."""
    moments = np.arange(int(seconds * audio.SAMPLE_RATE)) / audio.SAMPLE_RATE
    rng = np.random.default_rng(seed)
    wave = sum(
        np.sin(2 * np.pi * base * k * moments + rng.uniform(0, 6)) / k
        for k in range(1, 12)
    )
    wave = wave + 0.05 * rng.standard_normal(len(moments))
    return (0.2 * wave / np.abs(wave).max()).astype(np.float32)


@pytest.mark.skipif(
    not os.path.isfile(os.environ.get("DEBAT_STEM_MODEL_PATH", "")),
    reason="the speaker model is not in the repository; set DEBAT_STEM_MODEL_PATH",
)
def test_the_real_model_on_made_up_sound(monkeypatch):
    """The one test of the model itself, on sound that is nobody's."""
    monkeypatch.setattr(stem, "_loaded", {})
    embedder = stem.load(os.environ["DEBAT_STEM_MODEL_PATH"])
    low, high = _harmonics(110.0, 3.0, 1), _harmonics(220.0, 3.0, 2)

    one, again, other = embedder.embed(low), embedder.embed(low), embedder.embed(high)

    assert one.shape == (256,)
    assert float(np.linalg.norm(one)) == pytest.approx(1.0, abs=1e-5)
    assert float(one @ again) == pytest.approx(1.0, abs=1e-5)
    assert float(one @ other) < 0.9
    assert embedder.embed(low[: audio.SAMPLE_RATE // 2]) is None


class _Session:
    """Stands in for the model: remembers what it was fed, answers `out`."""

    def __init__(self, out: list[float]) -> None:
        self.out = out
        self.fed: list[np.ndarray] = []

    def run(self, outputs, feeds):
        ((name, features),) = feeds.items()
        assert name == "feats"
        self.fed.append(features)
        return [np.array([self.out], dtype=np.float32)]


def _embedder(out: list[float]) -> tuple[stem.Embedder, _Session]:
    """The real features in front of a model that is not there."""
    import kaldi_native_fbank

    embedder = object.__new__(stem.Embedder)
    embedder._session = _Session(out)
    embedder._input = "feats"
    embedder._knf = kaldi_native_fbank
    return embedder, embedder._session


def test_the_numbers_are_the_ones_that_were_measured():
    """Each of these was chosen from a measurement, explained where it is
    set. A change is a decision, not a slip."""
    seconds = {
        "BEFORE": 14,
        "AFTER": 9,
        "EDGE_IN": 6,
        "EDGE_OUT": 14,
        "OPEN_SLACK": 20,
        "CLIP_MIN": 4,
        "CLIP_MAX": 8,
        "CLIP_GAP": 1.5,
        "SUPERSEDED": 5,
        "LINE_PAD": 0.2,
        "LINE_MIN": 1.6,
        "WAIT": 30,
        "RETRY_FOR": 600,
        "AUDIO_RETRY": 60,
        "AUDIO_KEEPS": 45 * 60,
    }
    assert {name: getattr(svc, name).total_seconds() for name in seconds} == seconds
    assert (svc.MAX_CLIPS, svc.SOUND_PER_TICK, svc.SOUND_PER_SESSIE_MIN) == (8, 48, 12)
    assert (stem.MATCH, stem.MARGIN, stem.MATCH_ALONE, stem.MISMATCH) == (
        0.45,
        0.15,
        0.62,
        0.30,
    )
    assert stem.MIN_SECONDS == 1.0
    assert stem.MAX_IDLE == timedelta(minutes=20)
    assert audio.TRUSTED_HOSTS == ("tweedekamer.nl", "vos360.video")
    assert audio.SAMPLE_RATE == 16_000


def test_the_model_runs_on_one_core_of_the_cpu(monkeypatch):
    """The runtime would otherwise take every core of the machine."""
    import onnxruntime

    made: list[tuple] = []

    class Input:
        def __init__(self, name: str) -> None:
            self.name = name

    class Session:
        def __init__(self, path, sess_options, providers):
            made.append((path, sess_options, providers))

        def get_inputs(self):
            return [Input("feats"), Input("other")]

    monkeypatch.setattr(onnxruntime, "InferenceSession", Session)

    embedder = stem.Embedder("/ergens/model.onnx")

    ((path, options, providers),) = made
    assert path == "/ergens/model.onnx"
    assert (options.intra_op_num_threads, options.inter_op_num_threads) == (1, 1)
    assert providers == ["CPUExecutionProvider"]
    assert embedder._input == "feats"


class TestEmbedder:
    def test_the_model_is_fed_what_it_was_trained_on(self):
        """80 mel bins per 10 ms, with the mean over time taken out."""
        embedder, session = _embedder([3.0, 4.0])

        embedder.embed(_harmonics(110.0, 2.0, 1))

        (features,) = session.fed
        assert features.dtype == np.float32
        # A frame of 25 ms every 10 ms, as many as fit in two seconds.
        assert features.shape == (1, 198, 80)
        assert np.abs(features[0].mean(axis=0)).max() < 1e-3
        assert features[0].std() > 0.1

    def test_the_same_sound_gives_the_same_features(self):
        """No dither: a line listened to twice is the same line."""
        embedder, session = _embedder([3.0, 4.0])
        sound = _harmonics(110.0, 2.0, 1)

        embedder.embed(sound)
        embedder.embed(sound)

        assert np.array_equal(session.fed[0], session.fed[1])

    def test_what_comes_out_has_length_one(self):
        embedder, _ = _embedder([3.0, 4.0])

        vector = embedder.embed(_harmonics(110.0, 2.0, 1))

        assert vector.tolist() == pytest.approx([0.6, 0.8])

    def test_too_little_sound_is_not_fed_to_the_model(self):
        embedder, session = _embedder([3.0, 4.0])
        almost = int(stem.MIN_SECONDS * audio.SAMPLE_RATE) - 1

        assert embedder.embed(_harmonics(110.0, 2.0, 1)[:almost]) is None
        assert session.fed == []
        assert embedder.embed(_harmonics(110.0, 2.0, 1)[: almost + 1]) is not None

    @pytest.mark.parametrize(
        "out", [[0.0, 0.0], [float("nan"), 1.0], [float("inf"), 1.0]]
    )
    def test_an_answer_that_is_not_a_direction_is_no_voice(self, out):
        embedder, _ = _embedder(out)

        assert embedder.embed(_harmonics(110.0, 2.0, 1)) is None


def _turns(*events: tuple[float, str | None]) -> list[Turn]:
    """Turns from (seconds after the start, who or None)."""
    return [
        Turn(
            uuid.uuid4(),
            _at(seconds),
            _at(events[index + 1][0]) if index + 1 < len(events) else None,
            who,
        )
        for index, (seconds, who) in enumerate(events)
    ]


class TestCandidates:
    def test_a_line_near_a_change_can_be_of_either(self):
        turns = _turns((0, "a"), (100, "b"))

        assert candidates(turns, _at(95)) == turns
        assert candidates(turns, _at(105)) == turns

    def test_a_line_far_from_any_change_is_nobodys_to_decide(self):
        turns = _turns((0, "a"), (100, "b"))

        assert candidates(turns, _at(50)) == []
        assert candidates(turns, _at(150)) == []

    def test_the_window_is_wider_before_the_event_than_after(self):
        turns = _turns((0, "a"), (100, "b"))
        before, after = BEFORE.total_seconds(), AFTER.total_seconds()

        assert candidates(turns, _at(100 - before)) == turns
        assert candidates(turns, _at(100 - before - 0.1)) == []
        assert candidates(turns, _at(100 + after)) == turns
        assert candidates(turns, _at(100 + after + 0.1)) == []

    def test_the_same_person_carrying_on_is_not_a_change(self):
        turns = _turns((0, "a"), (100, "a"))

        assert candidates(turns, _at(100)) == []

    def test_a_suspension_is_not_a_voice(self):
        turns = _turns((0, "a"), (100, None), (200, "b"))

        assert candidates(turns, _at(100)) == []
        assert candidates(turns, _at(200)) == []

    def test_a_change_after_something_that_is_not_one_still_counts(self):
        turns = _turns((0, "a"), (100, None), (200, "b"), (300, "c"))

        assert candidates(turns, _at(300)) == turns[2:]

    def test_a_change_after_someone_carrying_on_still_counts(self):
        turns = _turns((0, "a"), (100, "a"), (200, "b"))

        assert candidates(turns, _at(200)) == turns[1:]

    def test_two_changes_close_together_give_everyone_around_them(self):
        turns = _turns((0, "a"), (100, "v"), (103, "b"))

        assert candidates(turns, _at(101)) == turns

    def test_a_turn_is_a_candidate_once(self):
        turns = _turns((0, "a"), (100, "v"), (103, "b"))

        assert len(candidates(turns, _at(102))) == 3


class TestNearest:
    def test_the_turn_the_line_is_in(self):
        turns = _turns((0, "a"), (100, "b"), (200, "a"))

        assert nearest(turns, "a", _at(210)) is turns[2]
        assert nearest(turns, "a", _at(50)) is turns[0]

    def test_just_before_a_turn_is_nearer_than_a_minute_after_another(self):
        turns = _turns((0, "a"), (100, "b"), (200, "a"))

        assert nearest(turns, "a", _at(195)) is turns[2]
        assert nearest(turns, "a", _at(105)) is turns[0]

    def test_the_turn_that_is_still_going_on_has_no_end(self):
        turns = _turns((0, "a"), (100, "b"))

        assert nearest(turns, "b", _at(500)) is turns[1]
        assert turns[1].distance(_at(500)) == timedelta(0)

    def test_the_end_of_a_turn_is_not_in_it(self):
        turns = _turns((0, "a"), (100, "b"))

        assert turns[0].distance(_at(99.9)) == timedelta(0)
        assert turns[0].distance(_at(100)) == timedelta(0)
        assert turns[0].distance(_at(103)) == timedelta(seconds=3)
        assert turns[1].distance(_at(97)) == timedelta(seconds=3)

    def test_an_event_replaced_within_seconds_is_passed_over(self):
        """An interruption and a turn of the same person a second apart:
        what was said just before belongs with the turn."""
        turns = _turns((0, "v"), (100, "a"), (101, "a"))

        assert nearest(turns, "a", _at(95)) is turns[2]

    def test_two_turns_of_one_person_further_apart_are_both_real(self):
        turns = _turns(
            (0, "v"), (100, "a"), (100 + svc.SUPERSEDED.total_seconds(), "a")
        )

        assert nearest(turns, "a", _at(95)) is turns[1]

    def test_equally_far_is_the_earlier_one(self):
        turns = _turns((0, "a"), (100, "b"), (110, "a"))

        assert nearest(turns, "a", _at(105)) is turns[0]


def _line(start: float, length: float = 3.0) -> Line:
    return Line(uuid.uuid4(), _at(start), _at(start + length), None, False)


class TestClips:
    def test_lines_that_follow_each_other_are_one_piece(self):
        lines = [_line(10), _line(14)]

        assert clips(lines, _at(0), _at(100)) == [(_at(10), _at(17))]

    def test_a_piece_is_no_longer_than_the_most(self):
        lines = [_line(10), _line(14), _line(18), _line(22)]

        assert clips(lines, _at(0), _at(100)) == [
            (_at(10), _at(17)),
            (_at(18), _at(25)),
        ]

    def test_exactly_the_most_is_one_piece(self):
        most = svc.CLIP_MAX.total_seconds()
        lines = [_line(10, most / 2), _line(10 + most / 2, most / 2)]

        assert clips(lines, _at(0), _at(100)) == [(_at(10), _at(10 + most))]

    def test_a_silence_ends_a_piece(self):
        gap = svc.CLIP_GAP.total_seconds()
        lines = [_line(10, 2), _line(12 + gap, 2), _line(14.1 + 2 * gap, 5)]

        assert clips(lines, _at(0), _at(100)) == [
            (_at(10), _at(14 + gap)),
            (_at(14.1 + 2 * gap), _at(19.1 + 2 * gap)),
        ]

    def test_a_piece_that_is_too_short_is_not_learned_from(self):
        short = svc.CLIP_MIN.total_seconds() - 0.1

        assert clips([_line(10, short)], _at(0), _at(100)) == []
        assert clips([_line(10, short + 0.1)], _at(0), _at(100)) == [
            (_at(10), _at(10 + short + 0.1))
        ]

    def test_a_piece_of_exactly_the_least_counts_wherever_it_is(self):
        least = svc.CLIP_MIN.total_seconds()
        lines = [_line(10, least), _line(30, least)]

        assert clips(lines, _at(0), _at(100)) == [
            (_at(10), _at(10 + least)),
            (_at(30), _at(30 + least)),
        ]

    def test_a_short_piece_before_a_long_one_is_dropped_alone(self):
        lines = [_line(10, 2), _line(30, 5)]

        assert clips(lines, _at(0), _at(100)) == [(_at(30), _at(35))]

    def test_only_lines_wholly_inside(self):
        lines = [_line(8, 5), _line(20, 5), _line(96, 5)]

        assert clips(lines, _at(10), _at(100)) == [(_at(20), _at(25))]
        assert clips([_line(10, 5)], _at(10), _at(15)) == [(_at(10), _at(15))]

    def test_one_endless_line_is_cut(self):
        most = svc.CLIP_MAX.total_seconds()

        assert clips([_line(10, 60)], _at(0), _at(100)) == [(_at(10), _at(10 + most))]


class TestBudget:
    def test_one_debate_gets_all_of_it(self):
        budget = Budget.share(1)

        assert budget.seconds == svc.SOUND_PER_TICK
        assert budget.segments == 2 * round(svc.SOUND_PER_TICK / 3.84) + 2

    def test_debates_share(self):
        assert Budget.share(3).seconds == svc.SOUND_PER_TICK / 3

    def test_many_debates_each_still_get_something(self):
        assert Budget.share(50).seconds == svc.SOUND_PER_SESSIE_MIN

    def test_no_debates_is_not_a_division_by_zero(self):
        assert Budget.share(0).seconds == svc.SOUND_PER_TICK


@pytest.mark.asyncio
class TestVoicesDecide:
    async def test_a_line_goes_to_whose_voice_it_is(self, db_session, monkeypatch):
        """The interruption is entered too early and the answer too late.
        By the time alone the last words of the speaker are under the
        interruption, and so is the start of the answer."""
        feed = Feed(monkeypatch, parts=[_with_audio(_debat(*EVENTS))])
        Subtitles(monkeypatch, feed, _lines(62, 298))
        Sound(monkeypatch, feed, SPEAKING)
        mm = Mattermost()
        sessie = await _sessie(db_session)

        await _play(db_session, mm, feed, 6)

        speaker, interruption, answer = mm.channel[1:]
        assert _said(speaker)[-3:] == ["r178.", "r182.", "r186."]
        assert _said(interruption) == [f"r{s}." for s in range(190, 227, 4)]
        assert _said(answer)[:4] == ["r230.", "r234.", "r238.", "r242."]
        where = await _where(db_session, sessie)
        assert where["r186."] == ("speaker", "a", 60, "stem", True)
        assert where["r226."] == ("interrupter", "b", 180, "stem", True)
        assert where["r230."] == ("speaker", "a", 240, "stem", True)
        # Not near a change: nobody listened, it is where the time put it.
        assert where["r190."] == ("interrupter", "b", 180, "tijd", True)

    async def test_how_many_lines_moved_is_said_and_nothing_else(
        self, db_session, monkeypatch, caplog
    ):
        feed = Feed(monkeypatch, parts=[_with_audio(_debat(*EVENTS))])
        Subtitles(monkeypatch, feed, _lines(62, 298))
        Sound(monkeypatch, feed, SPEAKING)
        await _sessie(db_session)

        with caplog.at_level(logging.INFO, logger=svc.logger.name):
            await _play(db_session, Mattermost(), feed, 6)

        said = [r.getMessage() for r in caplog.records if r.name == svc.logger.name]
        assert said
        assert all("op stem bij een andere spreekbeurt gezet" in line for line in said)
        assert all(int(line.split()[0]) > 0 for line in said)
        # Two at the interruption, three at the answer.
        assert sum(int(line.split()[0]) for line in said) == 5

    async def test_without_the_voices_the_time_decides(
        self, db_session, monkeypatch, caplog
    ):
        feed = Feed(monkeypatch, parts=[_with_audio(_debat(*EVENTS))])
        Subtitles(monkeypatch, feed, _lines(62, 298))
        sound = Sound(monkeypatch, feed, SPEAKING)
        sound.embedder = None
        mm = Mattermost()
        sessie = await _sessie(db_session)

        with caplog.at_level(logging.WARNING):
            await _play(db_session, mm, feed, 6)

        # Not an error either: nothing is tried, so nothing fails.
        assert caplog.records == []

        speaker, interruption, answer = mm.channel[1:]
        assert _said(speaker)[-1] == "r178."
        assert _said(interruption) == [f"r{s}." for s in range(182, 239, 4)]
        assert _said(answer)[0] == "r242."
        assert sound.playlists == 0
        assert sound.asked == []
        where = await _where(db_session, sessie)
        assert {how for _, _, _, how, _ in where.values()} == {"tijd"}
        assert sessie.id not in stem.VOICES

    async def test_only_lines_near_a_change_are_listened_to(
        self, db_session, monkeypatch
    ):
        feed = Feed(monkeypatch, parts=[_with_audio(_debat(*EVENTS))])
        Subtitles(monkeypatch, feed, _lines(62, 298))
        sound = Sound(monkeypatch, feed, SPEAKING)
        mm = Mattermost()
        sessie = await _sessie(db_session)

        await _play(db_session, mm, feed, 6)

        assert set(sound.lines_heard()) == {
            *range(166, 187, 4),
            *range(226, 247, 4),
        }
        where = await _where(db_session, sessie)
        assert where["r162."] == ("speaker", "a", 60, "tijd", True)
        assert where["r250."] == ("speaker", "a", 240, "tijd", True)
        assert where["r166."] == ("speaker", "a", 60, "stem", True)

    async def test_a_line_is_listened_to_once(self, db_session, monkeypatch):
        feed = Feed(monkeypatch, parts=[_with_audio(_debat(*EVENTS))])
        Subtitles(monkeypatch, feed, _lines(62, 298))
        sound = Sound(monkeypatch, feed, SPEAKING)
        await _sessie(db_session)

        await _play(db_session, Mattermost(), feed, 6)

        heard = sound.lines_heard()
        assert len(heard) == len(set(heard)) == 12

    async def test_a_voice_is_learned_from_inside_the_turns_only(
        self, db_session, monkeypatch
    ):
        feed = Feed(monkeypatch, parts=[_with_audio(_debat(*EVENTS))])
        Subtitles(monkeypatch, feed, _lines(62, 298))
        sound = Sound(monkeypatch, feed, SPEAKING)
        sessie = await _sessie(db_session)

        await _play(db_session, Mattermost(), feed, 6)

        learned = sound.clips_heard()
        edge_in, edge_out = svc.EDGE_IN.total_seconds(), svc.EDGE_OUT.total_seconds()
        inside = [(60 + edge_in, 180 - edge_out), (180 + edge_in, 240 - edge_out)]
        inside.append((240 + edge_in, 400))
        assert learned
        assert all(
            any(lo <= start and end <= hi for lo, hi in inside)
            for start, end in learned
        )
        voices = stem.VOICES.peek(sessie.id).voices
        assert set(voices) == {"a", "b"}
        assert 1 <= voices["b"].count <= svc.MAX_CLIPS
        assert voices["a"].count == svc.MAX_CLIPS

    async def test_no_more_pieces_per_person_than_the_most(
        self, db_session, monkeypatch
    ):
        feed = Feed(monkeypatch, parts=[_with_audio(_debat(("speaker", 1, "a")))])
        Subtitles(monkeypatch, feed, _lines(62, 598))
        sound = Sound(monkeypatch, feed, [(60, 1)])
        sessie = await _sessie(db_session)

        await _play(db_session, Mattermost(), feed, 11)

        assert stem.VOICES.peek(sessie.id).voices["a"].count == svc.MAX_CLIPS
        assert len(sound.embedder.heard) == svc.MAX_CLIPS
        starts = [start for start, _ in sound.clips_heard()]
        assert len(starts) == len(set(starts)) == svc.MAX_CLIPS

    async def test_someone_too_brief_to_learn_is_told_by_who_it_is_not(
        self, db_session, monkeypatch
    ):
        """An interruption of twenty seconds has no inside to learn a
        voice from. A line that clearly is the speaker's goes to the
        speaker, one that clearly is not goes to the interrupter."""
        events = (("speaker", 1, "a"), ("interrupter", 3, "b"), ("speaker", 4, "a"))
        debat = _debat(*events)
        answer_at = START + timedelta(seconds=200)
        debat = dataclasses.replace(
            debat,
            events=(
                *debat.events[:-1],
                dataclasses.replace(debat.events[-1], start=answer_at),
            ),
        )
        feed = Feed(monkeypatch, parts=[_with_audio(debat)])
        Subtitles(monkeypatch, feed, _lines(62, 298))
        Sound(monkeypatch, feed, [(60, 1), (186, 2), (204, 1)])
        mm = Mattermost()
        sessie = await _sessie(db_session)

        await _play(db_session, mm, feed, 6)

        assert set(stem.VOICES.peek(sessie.id).voices) == {"a"}
        where = await _where(db_session, sessie)
        assert where["r182."] == ("speaker", "a", 60, "stem", True)
        assert where["r186."] == ("interrupter", "b", 180, "stem", True)
        assert where["r198."] == ("interrupter", "b", 180, "stem", True)
        assert where["r206."] == ("speaker", "a", 200, "stem", True)
        # Half one voice and half the other: not clear, so it stays where
        # the time put it, and is looked at again while that can help.
        assert where["r202."] == ("speaker", "a", 200, "tijd", False)

        await _play(db_session, mm, feed, 14, start=6.2)

        where = await _where(db_session, sessie)
        assert where["r202."] == ("speaker", "a", 200, "tijd", True)
        assert stem.VOICES.peek(sessie.id).lines == {}

    async def test_a_line_that_is_not_clear_is_not_listened_to_again(
        self, db_session, monkeypatch
    ):
        events = (("speaker", 1, "a"), ("interrupter", 3, "b"), ("speaker", 4, "a"))
        debat = _debat(*events)
        debat = dataclasses.replace(
            debat,
            events=(
                *debat.events[:-1],
                dataclasses.replace(
                    debat.events[-1], start=START + timedelta(seconds=200)
                ),
            ),
        )
        feed = Feed(monkeypatch, parts=[_with_audio(debat)])
        Subtitles(monkeypatch, feed, _lines(62, 298))
        sound = Sound(monkeypatch, feed, [(60, 1), (186, 2), (204, 1)])
        await _sessie(db_session)

        await _play(db_session, Mattermost(), feed, 9)

        assert sound.lines_heard().count(202) == 1

    async def test_both_messages_are_written_again_when_a_line_moves(
        self, db_session, monkeypatch
    ):
        feed = Feed(monkeypatch, parts=[_with_audio(_debat(*EVENTS))])
        Subtitles(monkeypatch, feed, _lines(62, 298))
        sound = Sound(monkeypatch, feed, SPEAKING)
        sound.embedder = None
        mm = Mattermost()
        await _sessie(db_session)
        await _play(db_session, mm, feed, 6)
        speaker, interruption, answer = mm.order[1:]
        assert _said(mm.messages[interruption])[0] == "r182."
        mm.updates.clear()

        sound.embedder = Embedder()
        await _play(db_session, mm, feed, 6.5, start=6.2)

        assert {post_id for post_id, _ in mm.updates} == {speaker, interruption, answer}
        assert _said(mm.messages[speaker])[-1] == "r186."
        assert _said(mm.messages[interruption])[0] == "r190."
        assert _said(mm.messages[interruption])[-1] == "r226."
        assert _said(mm.messages[answer])[0] == "r230."

    async def test_the_work_of_a_round_is_bounded_and_the_rest_carries_over(
        self, db_session, monkeypatch
    ):
        monkeypatch.setattr(svc, "SOUND_PER_TICK", 6.0)
        monkeypatch.setattr(svc, "SOUND_PER_SESSIE_MIN", 6.0)
        feed = Feed(monkeypatch, parts=[_with_audio(_debat(*EVENTS))])
        Subtitles(monkeypatch, feed, _lines(62, 298))
        sound = Sound(monkeypatch, feed, SPEAKING)
        sound.embedder = None
        mm = Mattermost()
        sessie = await _sessie(db_session)
        # Everything waits: the voices only come in after five minutes.
        await _play(db_session, mm, feed, 5.5)
        sound.embedder = Embedder()

        await _play(db_session, mm, feed, 9, start=5.6)

        before = [*sorted(sound.rounds.items()), (None, sum(sound.embedder.heard))]
        per_round = [
            later[1] - earlier[1]
            for earlier, later in zip(before, before[1:], strict=False)
        ]
        longest = svc.CLIP_MAX.total_seconds()
        assert len(per_round) > 3
        assert max(per_round) <= 6.0 + longest
        where = await _where(db_session, sessie)
        assert where["r186."] == ("speaker", "a", 60, "stem", True)
        assert where["r230."] == ("speaker", "a", 240, "stem", True)
        assert _said(mm.channel[2]) == [f"r{s}." for s in range(190, 227, 4)]

    async def test_no_more_audio_is_fetched_than_a_round_may(
        self, db_session, monkeypatch
    ):
        monkeypatch.setattr(
            Budget, "share", classmethod(lambda cls, sessies: Budget(100.0, 4))
        )
        feed = Feed(monkeypatch, parts=[_with_audio(_debat(*EVENTS))])
        Subtitles(monkeypatch, feed, _lines(62, 298))
        sound = Sound(monkeypatch, feed, SPEAKING)
        sessie = await _sessie(db_session)
        fetched: list[int] = []
        real = DebatTijdlijnService.tick

        async def tick(service, now=None):
            before = len(sound.segments)
            result = await real(service, now)
            fetched.append(len(sound.segments) - before)
            return result

        monkeypatch.setattr(DebatTijdlijnService, "tick", tick)

        await _play(db_session, Mattermost(), feed, 6)

        assert max(fetched) == 4
        where = await _where(db_session, sessie)
        assert where["r186."] == ("speaker", "a", 60, "stem", True)

    async def test_the_voices_come_back_after_a_restart(self, db_session, monkeypatch):
        """The memory of the worker is empty. What was decided stays
        decided, and the voices are learned again from the audio the
        server still has."""
        events = (*EVENTS, ("interrupter", 6, "b"))
        feed = Feed(monkeypatch, parts=[_with_audio(_debat(*events))])
        Subtitles(monkeypatch, feed, _lines(62, 418))
        sound = Sound(monkeypatch, feed, [*SPEAKING, (368, 2)])
        mm = Mattermost()
        sessie = await _sessie(db_session)
        await _play(db_session, mm, feed, 5.5)
        before = await _where(db_session, sessie)
        assert before["r186."] == ("speaker", "a", 60, "stem", True)

        stem.VOICES.clear()
        sound.got.clear()
        await _play(db_session, mm, feed, 8, start=5.6)

        after = await _where(db_session, sessie)
        assert {k: v for k, v in after.items() if k in before and before[k][4]} == {
            k: v for k, v in before.items() if v[4]
        }
        assert set(stem.VOICES.peek(sessie.id).voices) == {"a", "b"}
        # The interruption was entered eight seconds early again.
        assert after["r362."] == ("speaker", "a", 240, "stem", True)
        assert after["r366."] == ("speaker", "a", 240, "stem", True)
        assert after["r370."] == ("interrupter", "b", 360, "tijd", True)
        # Learned again also from turns that ended before the restart,
        # whose lines were all decided about long ago.
        assert any(start < 230 for start, _ in sound.clips_heard())
        # Nothing that was decided before the restart is listened to again.
        assert sound.lines_heard()
        assert all(seconds > 300 for seconds in sound.lines_heard())

    async def test_a_line_another_worker_decided_about_is_left_alone(
        self, db_session, monkeypatch
    ):
        """Two workers run at once during a deploy, each with its own
        voices. One decision per line."""
        feed = Feed(monkeypatch, parts=[_with_audio(_debat(*EVENTS))])
        Subtitles(monkeypatch, feed, _lines(62, 298))
        sound = Sound(monkeypatch, feed, SPEAKING)
        sound.embedder = None
        mm = Mattermost()
        sessie = await _sessie(db_session)
        await _play(db_session, mm, feed, 6)
        rows = {
            start: row_id
            for row_id, start in (
                await db_session.execute(
                    select(DebatSpreekbeurt.id, DebatSpreekbeurt.event_start).where(
                        DebatSpreekbeurt.sessie_id == sessie.id
                    )
                )
            ).all()
        }
        line_id, row_id = (
            await db_session.execute(
                select(DebatOndertitel.id, DebatOndertitel.spreekbeurt_id).where(
                    DebatOndertitel.sessie_id == sessie.id,
                    DebatOndertitel.tekst == "r182.",
                )
            )
        ).one()
        assert row_id == rows[_at(180)]
        stale = Line(line_id, _at(182), _at(185), row_id, False)
        worker = DebatStemmen(db_session, Embedder(), Budget.share(1))

        assert await worker._assign(stale, rows[_at(60)]) is True
        # The other worker still holds the line as it was, and decides
        # something else.
        assert await worker._assign(stale, rows[_at(240)]) is False

        where = await _where(db_session, sessie)
        assert where["r182."] == ("speaker", "a", 60, "stem", True)

    async def test_a_line_confirmed_where_it_was_is_not_a_move(
        self, db_session, monkeypatch
    ):
        feed = Feed(monkeypatch, parts=[_with_audio(_debat(*EVENTS))])
        Subtitles(monkeypatch, feed, _lines(62, 298))
        sound = Sound(monkeypatch, feed, SPEAKING)
        sound.embedder = None
        sessie = await _sessie(db_session)
        await _play(db_session, Mattermost(), feed, 6)
        line_id, row_id = (
            await db_session.execute(
                select(DebatOndertitel.id, DebatOndertitel.spreekbeurt_id).where(
                    DebatOndertitel.sessie_id == sessie.id,
                    DebatOndertitel.tekst == "r178.",
                )
            )
        ).one()
        worker = DebatStemmen(db_session, Embedder(), Budget.share(1))

        moved = await worker._assign(
            Line(line_id, _at(178), _at(181), row_id, False), row_id
        )

        assert moved is False
        where = await _where(db_session, sessie)
        assert where["r178."] == ("speaker", "a", 60, "stem", True)


@pytest.mark.asyncio
class TestLearning:
    async def test_learning_takes_a_third_of_a_round_at_most(
        self, db_session, monkeypatch
    ):
        """So that deciding is not kept waiting by one long speaker."""
        feed = Feed(monkeypatch, parts=[_with_audio(_debat(("speaker", 1, "a")))])
        Subtitles(monkeypatch, feed, _lines(62, 598))
        sound = Sound(monkeypatch, feed, [(60, 1)])
        sound.embedder = None
        await _sessie(db_session)
        # Everything waits, so there is plenty to learn from at once.
        await _play(db_session, Mattermost(), feed, 5)
        sound.embedder = Embedder()

        await _play(db_session, Mattermost(), feed, 6, start=5.2)

        per_round: dict[datetime, float] = {}
        for (start, end), moment in zip(sound.got, sound.when, strict=True):
            seconds = (end - start).total_seconds()
            per_round[moment] = per_round.get(moment, 0.0) + seconds
        # Pieces of seven seconds: the third one passes a third of 48.
        assert max(per_round.values()) == 21.0
        assert sum(per_round.values()) == 7.0 * svc.MAX_CLIPS

    async def test_a_turn_that_goes_on_is_learned_from_well_behind_now(
        self, db_session, monkeypatch
    ):
        """Whoever speaks next may have begun before their event shows."""
        from tests import test_debat_transcript as transcript_tests

        # Subtitles that come in almost at once, so that it is this rule
        # that keeps the distance and not their delay.
        monkeypatch.setattr(transcript_tests, "BEHIND", timedelta(seconds=5))
        feed = Feed(monkeypatch, parts=[_with_audio(_debat(("speaker", 1, "a")))])
        Subtitles(monkeypatch, feed, _lines(62, 298))
        sound = Sound(monkeypatch, feed, [(60, 1)])
        await _sessie(db_session)

        await _play(db_session, Mattermost(), feed, 4)

        assert sound.got
        behind = svc.OPEN_SLACK + svc.EDGE_OUT
        assert all(
            moment - end >= behind
            for (_, end), moment in zip(sound.got, sound.when, strict=True)
        )
        assert min(
            moment - end for (_, end), moment in zip(sound.got, sound.when, strict=True)
        ) < behind + timedelta(seconds=20)

    async def test_a_piece_in_which_nothing_is_heard_is_asked_for_once(
        self, db_session, monkeypatch
    ):
        feed = Feed(monkeypatch, parts=[_with_audio(_debat(("speaker", 1, "a")))])
        Subtitles(monkeypatch, feed, _lines(62, 198))
        # The speaker is silent for a while; the subtitles go on.
        sound = Sound(monkeypatch, feed, [(60, 1), (100, 0), (130, 1)])
        sessie = await _sessie(db_session)

        await _play(db_session, Mattermost(), feed, 6)

        silent = [
            start for start, end in sound.clips_heard() if 100 <= start and end <= 130
        ]
        assert silent
        assert len(silent) == len(set(silent))
        assert stem.VOICES.peek(sessie.id).voices["a"].count >= 3

    async def test_a_voice_is_learned_past_events_that_are_nobodys(
        self, db_session, monkeypatch
    ):
        """After a restart the voice of who spoke before a suspension is
        only to be had from before it."""
        events = (
            ("speaker", 1, "a"),
            ("suspended", 3, ""),
            ("continued", 4, ""),
            ("speaker", 4, "b"),
        )
        feed = Feed(monkeypatch, parts=[_with_audio(_debat(*events))])
        Subtitles(monkeypatch, feed, [*_lines(62, 170), *_lines(242, 398)])
        Sound(monkeypatch, feed, [(60, 1), (180, 0), (240, 2)])
        mm = Mattermost()
        sessie = await _sessie(db_session)
        await _play(db_session, mm, feed, 6)
        assert set(stem.VOICES.peek(sessie.id).voices) == {"a", "b"}

        stem.VOICES.clear()
        await _play(db_session, mm, feed, 7.5, start=6.2)

        assert set(stem.VOICES.peek(sessie.id).voices) == {"a", "b"}

    async def test_lines_nobody_can_decide_about_do_not_hold_up_the_rest(
        self, db_session, monkeypatch
    ):
        """Two people who each spoke too briefly to be learned: the lines
        between them wait. The change after it is decided all the same."""
        debat = _debat(
            ("speaker", 1, "c"),
            ("speaker", 1, "d"),
            ("speaker", 2, "a"),
            ("interrupter", 4, "b"),
            ("speaker", 5, "a"),
        )
        events = list(debat.events)
        events[2] = dataclasses.replace(events[2], start=_at(80))
        events[3] = dataclasses.replace(events[3], start=_at(100))
        feed = Feed(
            monkeypatch,
            parts=[_with_audio(dataclasses.replace(debat, events=tuple(events)))],
        )
        Subtitles(monkeypatch, feed, _lines(62, 358))
        Sound(monkeypatch, feed, [(60, 3), (80, 4), (100, 1), (248, 2), (290, 1)])
        sessie = await _sessie(db_session)

        await _play(db_session, Mattermost(), feed, 7)

        where = await _where(db_session, sessie)
        assert where["r70."] == ("speaker", "c", 60, "tijd", False)
        assert where["r246."] == ("speaker", "a", 100, "stem", True)
        assert where["r290."] == ("speaker", "a", 300, "stem", True)

    async def test_a_short_line_is_listened_to_with_enough_around_it(
        self, db_session, monkeypatch
    ):
        """One word says too little about a voice."""
        feed = Feed(monkeypatch, parts=[_with_audio(_debat(*EVENTS))])
        Subtitles(
            monkeypatch,
            feed,
            [*_lines(62, 160), *_lines(164, 250, length=0.5), *_lines(254, 298)],
        )
        sound = Sound(monkeypatch, feed, SPEAKING)
        await _sessie(db_session)

        await _play(db_session, Mattermost(), feed, 6)

        short = [
            (end - start).total_seconds()
            for start, end in sound.got
            if 164 <= (start - START).total_seconds() <= 250
            and end - start < svc.CLIP_MIN
        ]
        pad = svc.LINE_PAD.total_seconds()
        assert short
        assert set(short) == {svc.LINE_MIN.total_seconds() + 2 * pad}

    async def test_a_long_line_is_listened_to_whole(self, db_session, monkeypatch):
        feed = Feed(monkeypatch, parts=[_with_audio(_debat(*EVENTS))])
        Subtitles(monkeypatch, feed, _lines(62, 298))
        sound = Sound(monkeypatch, feed, SPEAKING)
        await _sessie(db_session)

        await _play(db_session, Mattermost(), feed, 6)

        pieces = {
            round((end - start).total_seconds(), 3)
            for start, end in sound.got
            if end - start < svc.CLIP_MIN
        }
        assert pieces == {3.0 + 2 * svc.LINE_PAD.total_seconds()}

    async def test_after_ten_minutes_of_silence_nothing_is_learned_any_more(
        self, db_session, monkeypatch
    ):
        feed = Feed(monkeypatch, parts=[_with_audio(_debat(("speaker", 1, "a")))])
        Subtitles(monkeypatch, feed, _lines(62, 230))
        sound = Sound(monkeypatch, feed, [(60, 1)])
        mm = Mattermost()
        sessie = await _sessie(db_session)
        await _play(db_session, mm, feed, 5)
        held = stem.VOICES.peek(sessie.id)
        used = held.used
        # As if there were still something to learn.
        held.voices.clear()
        sound.asked.clear()

        quiet = 4 + svc.RETRY_FOR.total_seconds() / 60
        await _play(db_session, mm, feed, quiet + 0.5, start=quiet)

        assert sound.asked == []
        assert stem.VOICES.peek(sessie.id).voices == {}
        assert stem.VOICES.peek(sessie.id).used < START + _minutes(quiet)
        assert stem.VOICES.peek(sessie.id).used >= used

    async def test_a_part_that_has_ended_is_not_listened_to_any_more(
        self, db_session, monkeypatch
    ):
        """Nothing is left to decide and no line will come: no audio is
        asked for, also not to learn a voice a little better."""
        events = (*EVENTS, ("debate_end", 5, ""))
        feed = Feed(monkeypatch, parts=[_with_audio(_debat(*events))])
        Subtitles(monkeypatch, feed, _lines(62, 298))
        sound = Sound(monkeypatch, feed, SPEAKING)
        mm = Mattermost()
        sessie = await _sessie(db_session)
        after = 5 + svc.AFTER_END.total_seconds() / 60
        await _play(db_session, mm, feed, after)
        where = await _where(db_session, sessie)
        assert all(done for *_, done in where.values())
        assert where["r230."] == ("speaker", "a", 240, "stem", True)
        held = stem.VOICES.peek(sessie.id)
        # As if there were still a voice to learn.
        del held.voices["b"]
        used, playlists = held.used, sound.playlists
        sound.asked.clear()

        await _play(db_session, mm, feed, after + 2, start=after + 0.2)

        assert sound.asked == []
        assert sound.playlists == playlists
        assert "b" not in stem.VOICES.peek(sessie.id).voices
        assert stem.VOICES.peek(sessie.id).used == used

    async def test_until_then_a_part_that_has_ended_is_still_learned_from(
        self, db_session, monkeypatch
    ):
        events = (*EVENTS, ("debate_end", 5, ""))
        feed = Feed(monkeypatch, parts=[_with_audio(_debat(*events))])
        Subtitles(monkeypatch, feed, _lines(62, 298))
        sound = Sound(monkeypatch, feed, SPEAKING)
        mm = Mattermost()
        sessie = await _sessie(db_session)
        after = 5 + svc.AFTER_END.total_seconds() / 60
        await _play(db_session, mm, feed, after - 0.5)
        del stem.VOICES.peek(sessie.id).voices["b"]
        sound.asked.clear()

        await _play(db_session, mm, feed, after, start=after)

        assert "b" in stem.VOICES.peek(sessie.id).voices

    async def test_a_line_that_waits_keeps_an_ended_part_listened_to(
        self, db_session, monkeypatch
    ):
        """The model came late: the lines of the last minutes are still to
        be decided about after the part has ended."""
        events = (*EVENTS, ("debate_end", 5, ""))
        feed = Feed(monkeypatch, parts=[_with_audio(_debat(*events))])
        Subtitles(monkeypatch, feed, _lines(62, 298))
        sound = Sound(monkeypatch, feed, SPEAKING)
        sound.embedder = None
        mm = Mattermost()
        sessie = await _sessie(db_session)
        after = 5 + svc.AFTER_END.total_seconds() / 60
        await _play(db_session, mm, feed, after + 0.5)
        sound.embedder = Embedder()

        await _play(db_session, mm, feed, after + 1.5, start=after + 0.6)

        where = await _where(db_session, sessie)
        assert where["r230."] == ("speaker", "a", 240, "stem", True)

    async def test_names_of_segments_are_remembered_and_old_ones_dropped(
        self, db_session, monkeypatch
    ):
        feed = Feed(monkeypatch, parts=[_with_audio(_debat(*EVENTS))])
        Subtitles(monkeypatch, feed, _lines(62, 298))
        sound = Sound(monkeypatch, feed, SPEAKING)
        sessie = await _sessie(db_session)
        await _play(db_session, Mattermost(), feed, 3)
        known = stem.VOICES.peek(sessie.id).segments[AUDIO]
        early = min(sound.segments)
        assert early in known
        # One from before what the server keeps, and one just inside it.
        now = START + _minutes(6)
        gone = audio.datetime_to_ticks(now - svc.AUDIO_KEEPS) - 1
        kept = audio.datetime_to_ticks(now - svc.AUDIO_KEEPS)
        known.update({gone, kept})

        await _play(db_session, Mattermost(), feed, 6, start=6)

        known = stem.VOICES.peek(sessie.id).segments[AUDIO]
        assert gone not in known
        assert kept in known
        assert early in known


@pytest.mark.asyncio
class TestNothingDependsOnIt:
    async def test_audio_that_cannot_be_fetched_leaves_the_time_to_decide(
        self, db_session, monkeypatch, caplog
    ):
        feed = Feed(monkeypatch, parts=[_with_audio(_debat(*EVENTS))])
        Subtitles(monkeypatch, feed, _lines(62, 298))
        sound = Sound(monkeypatch, feed, SPEAKING)
        sound.down = True
        mm = Mattermost()
        sessie = await _sessie(db_session)
        errors = 0

        with caplog.at_level(logging.WARNING):
            feed.now = START - _minutes(1)
            while feed.now <= START + _minutes(6):
                result = await DebatTijdlijnService(db_session, mm).tick(feed.now)
                errors += result.fouten
                feed.now += timedelta(seconds=10)

        assert errors == 0
        assert _said(mm.channel[2]) == [f"r{s}." for s in range(182, 239, 4)]
        where = await _where(db_session, sessie)
        assert {how for _, _, _, how, _ in where.values()} == {"tijd"}
        assert "niet te lezen (AudioError)" in caplog.text
        # Asked again after a while, not on every round: a server that is
        # down answers slowly, and the timeline waits for it.
        assert 2 <= sound.playlists <= _minutes(6) / svc.AUDIO_RETRY
        assert caplog.text.count("niet te lezen") == sound.playlists

    async def test_a_model_that_breaks_leaves_the_time_to_decide(
        self, db_session, monkeypatch, caplog
    ):
        feed = Feed(monkeypatch, parts=[_with_audio(_debat(*EVENTS))])
        Subtitles(monkeypatch, feed, _lines(62, 298))
        sound = Sound(monkeypatch, feed, SPEAKING)
        sound.embedder.error = RuntimeError("[0.12, 0.98, 0.33] is not a voice")
        mm = Mattermost()
        await _sessie(db_session)

        with caplog.at_level(logging.DEBUG):
            await _play(db_session, mm, feed, 6)

        assert _said(mm.channel[1])[-1] == "r178."
        assert _said(mm.channel[3])[0] == "r242."
        assert "niet te onderscheiden (RuntimeError)" in caplog.text
        # Whatever an error says about what was being worked on stays out
        # of the log: only what kind of error it was.
        assert "0.98" not in caplog.text

    async def test_what_was_read_is_kept_when_the_voices_fail(
        self, db_session, monkeypatch
    ):
        """A failure halfway is undone on its own: the lines that were
        read in the same round are there."""
        feed = Feed(monkeypatch, parts=[_with_audio(_debat(*EVENTS))])
        Subtitles(monkeypatch, feed, _lines(62, 298))
        Sound(monkeypatch, feed, SPEAKING)
        mm = Mattermost()
        sessie = await _sessie(db_session)
        real = DebatStemmen._decide

        async def decide(self, held, reach, turns, lines, now):
            await real(self, held, reach, turns, lines, now)
            raise RuntimeError("after deciding")

        monkeypatch.setattr(DebatStemmen, "_decide", decide)

        await _play(db_session, mm, feed, 6)

        where = await _where(db_session, sessie)
        assert len(where) == len(_lines(62, 298))
        assert {how for _, _, _, how, _ in where.values()} == {"tijd"}
        assert _said(mm.channel[2])[0] == "r182."

    async def test_switched_off_the_model_is_not_even_looked_for(
        self, db_session, monkeypatch, caplog
    ):
        feed = Feed(monkeypatch, parts=[_with_audio(_debat(*EVENTS))])
        Subtitles(monkeypatch, feed, _lines(62, 298))
        sound = Sound(monkeypatch, feed, SPEAKING)
        looked: list[str] = []
        monkeypatch.setattr(stem, "load", looked.append)
        monkeypatch.setattr(get_settings(), "DEBAT_STEMMEN_ENABLED", False)
        mm = Mattermost()
        await _sessie(db_session)

        with caplog.at_level(logging.WARNING):
            await _play(db_session, mm, feed, 6)

        assert caplog.records == []
        assert looked == []
        assert sound.asked == []
        assert _said(mm.channel[2])[0] == "r182."

    async def test_the_model_is_looked_for_where_the_setting_says(
        self, db_session, monkeypatch
    ):
        feed = Feed(monkeypatch, parts=[_with_audio(_debat(*EVENTS))])
        Subtitles(monkeypatch, feed, _lines(62, 100))
        Sound(monkeypatch, feed, SPEAKING)
        looked: set[str] = set()
        monkeypatch.setattr(stem, "load", looked.add)
        monkeypatch.setattr(get_settings(), "DEBAT_STEM_MODEL_PATH", "/ergens/m.onnx")
        await _sessie(db_session)

        await _play(db_session, Mattermost(), feed, 2)

        assert looked == {"/ergens/m.onnx"}

    async def test_a_debate_without_audio_is_not_listened_to(
        self, db_session, monkeypatch
    ):
        feed = Feed(monkeypatch, parts=[_stream(_debat(*EVENTS))])
        Subtitles(monkeypatch, feed, _lines(62, 298))
        sound = Sound(monkeypatch, feed, SPEAKING)
        mm = Mattermost()
        sessie = await _sessie(db_session)

        await _play(db_session, mm, feed, 6)

        assert sound.playlists == 0
        assert _said(mm.channel[2])[0] == "r182."
        assert sessie.id not in stem.VOICES

    async def test_audio_that_appears_later_is_picked_up(self, db_session, monkeypatch):
        feed = Feed(monkeypatch, parts=[_stream(_debat(*EVENTS))])
        Subtitles(monkeypatch, feed, _lines(62, 298))
        Sound(monkeypatch, feed, SPEAKING)
        mm = Mattermost()
        sessie = await _sessie(db_session)
        await _play(db_session, mm, feed, 2)
        assert sessie.ondertitels[feed.parts[0].id]["audio"] == ""

        feed.parts = [_with_audio(feed.parts[0])]
        await _play(db_session, mm, feed, 6, start=2.2)

        assert sessie.ondertitels[feed.parts[0].id]["audio"] == AUDIO
        assert _said(mm.channel[2])[0] == "r190."

    async def test_audio_somewhere_it_is_not_fetched_from_is_not_fetched(
        self, db_session, monkeypatch, caplog
    ):
        debat = dataclasses.replace(
            _stream(_debat(*EVENTS)), audio_url="https://evil.example/p.m3u8"
        )
        feed = Feed(monkeypatch, parts=[debat])
        Subtitles(monkeypatch, feed, _lines(62, 298))
        sound = Sound(monkeypatch, feed, SPEAKING)
        mm = Mattermost()
        sessie = await _sessie(db_session)

        with caplog.at_level(logging.WARNING):
            await _play(db_session, mm, feed, 6)

        assert sessie.ondertitels[debat.id]["audio"] == ""
        assert sound.playlists == 0
        assert sound.asked == []
        assert _said(mm.channel[2])[0] == "r182."
        assert "Stemmen" not in caplog.text
        assert "Audio" not in caplog.text


@pytest.mark.asyncio
class TestForgetting:
    """A voice is kept only while its debate runs, and only in memory."""

    async def test_voices_are_forgotten_when_the_debate_is_over(
        self, db_session, monkeypatch
    ):
        events = (("speaker", 1, "a"), ("debate_end", 4, ""))
        feed = Feed(monkeypatch, parts=[_with_audio(_debat(*events))])
        Subtitles(monkeypatch, feed, _lines(62, 230))
        Sound(monkeypatch, feed, [(60, 1)])
        mm = Mattermost()
        sessie = await _sessie(db_session)
        await _play(db_session, mm, feed, 5)
        assert "a" in stem.VOICES.peek(sessie.id).voices
        assert sessie.tijdlijn_status == TIJDLIJN_LOOPT

        over = START + _minutes(5) + tijdlijn.END_GRACE
        # Used a moment ago, so it is not the idle time that removes it.
        stem.VOICES.of(sessie.id, over)
        feed.now = over
        await DebatTijdlijnService(db_session, mm).tick(over)

        assert sessie.tijdlijn_status == TIJDLIJN_AFGELOPEN
        assert sessie.id not in stem.VOICES
        assert len(stem.VOICES) == 0

    async def test_voices_are_forgotten_when_the_debate_is_cancelled(
        self, db_session, monkeypatch
    ):
        feed = Feed(monkeypatch)
        feed.activiteit_status = "Geannuleerd"
        mm = Mattermost()
        sessie = await _sessie(db_session)
        stem.VOICES.of(sessie.id, START).learn("a", _unit(1, 0), START)

        feed.now = START
        await DebatTijdlijnService(db_session, mm).tick(START)

        assert sessie.tijdlijn_status == TIJDLIJN_AFGELAST
        assert sessie.id not in stem.VOICES

    async def test_a_debate_that_goes_on_keeps_its_voices(
        self, db_session, monkeypatch
    ):
        feed = Feed(monkeypatch, parts=[_with_audio(_debat(("speaker", 1, "a")))])
        Subtitles(monkeypatch, feed, _lines(62, 230))
        Sound(monkeypatch, feed, [(60, 1)])
        sessie = await _sessie(db_session)

        await _play(db_session, Mattermost(), feed, 5)

        assert "a" in stem.VOICES.peek(sessie.id).voices

    async def test_voices_of_a_debate_that_is_not_followed_any_more_are_forgotten(
        self, db_session, monkeypatch
    ):
        """Whatever the reason it dropped out: too old, archived, gone."""
        feed = Feed(monkeypatch)
        followed = await _sessie(db_session)
        dropped = await _sessie(db_session, tijdlijn_status=TIJDLIJN_AFGELOPEN)
        stem.VOICES.of(followed.id, START).learn("a", _unit(1, 0), START)
        stem.VOICES.of(dropped.id, START).learn("a", _unit(1, 0), START)
        stem.VOICES.of(uuid.uuid4(), START).learn("a", _unit(1, 0), START)

        feed.now = START
        await DebatTijdlijnService(db_session, Mattermost()).tick(START)

        assert followed.id in stem.VOICES
        assert len(stem.VOICES) == 1

    async def test_with_no_debate_at_all_nothing_is_kept(self, db_session, monkeypatch):
        Feed(monkeypatch)
        stem.VOICES.of(uuid.uuid4(), START).learn("a", _unit(1, 0), START)

        await DebatTijdlijnService(db_session, Mattermost()).tick(START)

        assert len(stem.VOICES) == 0

    async def test_voices_nobody_used_for_a_while_are_forgotten(
        self, db_session, monkeypatch
    ):
        """A suspension of an hour: the debate is still followed, the
        voices are not kept waiting for it."""
        events = (("speaker", 1, "a"), ("suspended", 4, ""))
        feed = Feed(monkeypatch, parts=[_with_audio(_debat(*events))])
        Subtitles(monkeypatch, feed, _lines(62, 230))
        Sound(monkeypatch, feed, [(60, 1)])
        mm = Mattermost()
        sessie = await _sessie(db_session)
        await _play(db_session, mm, feed, 5)
        assert sessie.id in stem.VOICES

        await _play(db_session, mm, feed, 40, start=5.2, step=60)

        assert sessie.tijdlijn_status == TIJDLIJN_LOOPT
        assert sessie.id not in stem.VOICES

    async def test_nothing_of_a_voice_is_in_the_database(self, db_session, monkeypatch):
        """Only which turn a line belongs to is kept, and how that was
        decided. No vector, in no column of no table of the debate."""
        feed = Feed(monkeypatch, parts=[_with_audio(_debat(*EVENTS))])
        Subtitles(monkeypatch, feed, _lines(62, 298))
        Sound(monkeypatch, feed, SPEAKING)
        sessie = await _sessie(db_session)

        await _play(db_session, Mattermost(), feed, 6)

        assert stem.VOICES.peek(sessie.id).voices
        columns = {
            column.name
            for table in (DebatOndertitel.__table__, DebatSpreekbeurt.__table__)
            for column in table.columns
        }
        assert columns == {
            "id",
            "sessie_id",
            "debat_direct_id",
            "start",
            "einde",
            "tekst",
            "spreekbeurt_id",
            "toewijzing",
            "stem_klaar",
            "created_at",
            "event_type",
            "event_start",
            "object_id",
            "post_id",
            "kop",
            "tekst_geplaatst",
            "tekst_geplaatst_hash",
            "vervolg_post_ids",
        }
        assert set(sessie.ondertitels[feed.parts[0].id]) == {
            "url",
            "offset_ms",
            "gekeken",
            "audio",
            "positie",
        }

    async def test_nothing_of_a_voice_or_of_the_audio_is_logged(
        self, db_session, monkeypatch, caplog
    ):
        feed = Feed(monkeypatch, parts=[_with_audio(_debat(*EVENTS))])
        Subtitles(monkeypatch, feed, _lines(62, 298))
        Sound(monkeypatch, feed, SPEAKING)
        await _sessie(db_session)

        with caplog.at_level(logging.DEBUG, logger="bouwmeester"):
            await _play(db_session, Mattermost(), feed, 6)

        ours = [r.getMessage() for r in caplog.records if "debat_ste" in r.name]
        # A count and the id of the debate. Not who, not what.
        assert ours
        assert all(
            re.fullmatch(
                r"\d+ regels van [0-9a-f-]{36} op stem bij een andere "
                r"spreekbeurt gezet",
                line,
            )
            for line in ours
        )
        assert "array(" not in caplog.text
        assert "float32" not in caplog.text
        # And nothing went wrong on the way: a failure is a warning.
        assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []


@pytest.mark.asyncio
class TestOldLines:
    async def test_lines_that_waited_too_long_stay_where_they_are(
        self, db_session, monkeypatch
    ):
        """Without the model every line waits. When the model is there
        later, what is too old to be listened to is not left waiting."""
        feed = Feed(monkeypatch, parts=[_with_audio(_debat(*EVENTS))])
        Subtitles(monkeypatch, feed, _lines(62, 298))
        sound = Sound(monkeypatch, feed, SPEAKING)
        sound.embedder = None
        mm = Mattermost()
        sessie = await _sessie(db_session)
        await _play(db_session, mm, feed, 6)
        where = await _where(db_session, sessie)
        assert not any(done for *_, done in where.values())

        sound.embedder = Embedder()
        # Well past what the server keeps, not only past the waiting.
        late = 6 + svc.AUDIO_KEEPS.total_seconds() / 60 + 5
        await _play(db_session, mm, feed, late + 0.5, start=late)

        where = await _where(db_session, sessie)
        assert all(done for *_, done in where.values())
        assert {how for _, _, _, how, _ in where.values()} == {"tijd"}
        assert sound.asked == []
        assert sessie.id not in stem.VOICES

    async def test_a_line_in_which_nothing_is_heard_stays_where_it_is(
        self, db_session, monkeypatch
    ):
        feed = Feed(monkeypatch, parts=[_with_audio(_debat(*EVENTS))])
        Subtitles(monkeypatch, feed, _lines(62, 298))
        # Nobody speaks between the last word of one and the first of the
        # other: the model has nothing to make a voice of.
        sound = Sound(monkeypatch, feed, [(60, 1), (181, 0), (185.5, 2), (230, 1)])
        sessie = await _sessie(db_session)

        await _play(db_session, Mattermost(), feed, 6)

        where = await _where(db_session, sessie)
        assert where["r182."] == ("interrupter", "b", 180, "tijd", True)
        assert where["r186."] == ("interrupter", "b", 180, "stem", True)
        assert sound.lines_heard().count(182) == 1

    async def test_audio_the_server_no_longer_has_is_given_up_on(
        self, db_session, monkeypatch
    ):
        feed = Feed(monkeypatch, parts=[_with_audio(_debat(*EVENTS))])
        Subtitles(monkeypatch, feed, _lines(62, 298))
        sound = Sound(monkeypatch, feed, SPEAKING)
        sound.kept_from = _at(200)
        sessie = await _sessie(db_session)

        await _play(db_session, Mattermost(), feed, 8)

        where = await _where(db_session, sessie)
        # Both voices can still be learned from what is left, but the
        # lines themselves are gone: they stay where the time put them.
        assert set(stem.VOICES.peek(sessie.id).voices) == {"a", "b"}
        assert where["r182."] == ("interrupter", "b", 180, "tijd", True)
        assert where["r230."] == ("speaker", "a", 240, "stem", True)
        # What is gone is asked for once, the line and the piece a voice
        # could have been learned from alike.
        asked = [start for start, _ in sound.asked]
        assert _at(182) - svc.LINE_PAD in asked
        assert _at(186) in asked
        assert len(asked) == len(set(asked))
        # And a round does not go looking for every one of them: a segment
        # that is not there is eleven requests.
        assert 0 < sound.misses <= 8 * 11


@pytest.mark.asyncio
class TestDirect:
    """The step on its own, for what a whole debate does not reach."""

    async def test_a_line_whose_turn_is_gone_can_still_be_given_one(
        self, db_session, monkeypatch
    ):
        feed = Feed(monkeypatch, parts=[_with_audio(_debat(*EVENTS))])
        Subtitles(monkeypatch, feed, _lines(62, 298))
        sound = Sound(monkeypatch, feed, SPEAKING)
        sound.embedder = None
        sessie = await _sessie(db_session)
        await _play(db_session, Mattermost(), feed, 6)
        line_id = (
            await db_session.execute(
                select(DebatOndertitel.id).where(
                    DebatOndertitel.sessie_id == sessie.id,
                    DebatOndertitel.tekst == "r182.",
                )
            )
        ).scalar_one()
        await db_session.execute(
            update(DebatOndertitel)
            .where(DebatOndertitel.id == line_id)
            .values(spreekbeurt_id=None)
        )
        target = (
            await db_session.execute(
                select(DebatSpreekbeurt.id).where(
                    DebatSpreekbeurt.sessie_id == sessie.id,
                    DebatSpreekbeurt.event_start == _at(60),
                )
            )
        ).scalar_one()
        worker = DebatStemmen(db_session, Embedder(), Budget.share(1))

        moved = await worker._assign(
            Line(line_id, _at(182), _at(185), None, False), target
        )

        assert moved is True
        text = (
            await db_session.execute(
                select(DebatSpreekbeurt.tekst).where(DebatSpreekbeurt.id == target)
            )
        ).scalar_one()
        assert text.split()[-2:] == ["r178.", "r182."]
