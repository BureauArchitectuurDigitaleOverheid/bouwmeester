"""The status line under the message of a turn at speaking.

The message of a turn has two writers. The transcription makes the text
grow while someone speaks, and the marking of questions appends where they
stand. A `PUT /posts/{id}` replaces the whole message, so each writer has to
keep what the other wrote. This module is the convention both follow.

A message is:

    <body>

    ---
    <status block>

The body is the head of the turn and its transcript. The status block is
everything after the last line that is exactly `---`, and it is optional.
Mattermost shows the `---` as a thin rule.

For the writer of the body:

    nieuw = met_body(huidig_bericht, nieuwe_body)

keeps the status block that is there. Never build the message by hand, and
never put a line that is exactly `---` in the body (`voeg_samen` escapes one
that slips in).

For the writer of the status block:

    nieuw = met_status(huidig_bericht, statusregel(...))

keeps the body. The status block is not parsed back: it is derived from the
database every time (`statusregel`), so a block that was lost is restored by
the next write.

Pure functions, no I/O.
"""

from __future__ import annotations

from collections.abc import Sequence

from bouwmeester.models.debat_markering import (
    SOORT_MOTIE,
    SOORT_VRAAG,
    STATUS_ANTWOORD_KLAAR,
    STATUS_BEANTWOORD,
    STATUS_OPEN,
    STATUS_TOEGEWEZEN,
    STATUS_VERVALT,
    STATUS_VERWORPEN,
)

SCHEIDING = "---"

ICOON_VRAAG = "❓"
ICOON_MOTIE = "📜"

# (singular, plural) per soort, in the order the lines are shown. A soort
# that is not in here is not shown.
_SOORT_LABEL: dict[str, tuple[str, str]] = {
    SOORT_VRAAG: ("vraag", "vragen"),
    SOORT_MOTIE: ("motie", "moties"),
}
_SOORT_ICOON: dict[str, str] = {
    SOORT_VRAAG: ICOON_VRAAG,
    SOORT_MOTIE: ICOON_MOTIE,
}
# One word per status, in the order they are shown.
_STATUS_LABEL: dict[str, str] = {
    STATUS_OPEN: "open",
    STATUS_TOEGEWEZEN: "opgepakt",
    STATUS_ANTWOORD_KLAAR: "antwoord klaar",
    STATUS_BEANTWOORD: "beantwoord",
    STATUS_VERVALT: "hoeft geen antwoord",
}
# The words of a status that differ for a soort. A motie is not answered:
# it gets an oordeel.
_STATUS_LABEL_PER_SOORT: dict[str, dict[str, str]] = {
    SOORT_MOTIE: {
        STATUS_ANTWOORD_KLAAR: "oordeel klaar",
        STATUS_BEANTWOORD: "oordeel gegeven",
        STATUS_VERVALT: "hoeft geen oordeel",
    },
}


def splits(bericht: str) -> tuple[str, str]:
    """A message as (body, status block). No status block is an empty string."""
    regels = (bericht or "").split("\n")
    for i in range(len(regels) - 1, -1, -1):
        if regels[i].strip() == SCHEIDING:
            body = "\n".join(regels[:i]).rstrip()
            status = "\n".join(regels[i + 1 :]).strip()
            return body, status
    return (bericht or "").rstrip(), ""


def voeg_samen(body: str, status: str) -> str:
    """A message from a body and a status block."""
    # A bare `---` in the body would be read as the separator next time.
    veilig = "\n".join(
        "\\---" if regel.strip() == SCHEIDING else regel
        for regel in (body or "").rstrip().split("\n")
    )
    status = (status or "").strip()
    if not status:
        return veilig
    return f"{veilig}\n\n{SCHEIDING}\n{status}"


def met_status(bericht: str, status: str) -> str:
    """The same message with another status block; the body is kept."""
    body, _ = splits(bericht)
    return voeg_samen(body, status)


def met_body(bericht: str, body: str) -> str:
    """The same message with another body; the status block is kept."""
    _, status = splits(bericht)
    return voeg_samen(body, status)


def statusregel(markeringen: Sequence[tuple[str, str]]) -> str:
    """The status block for the markeringen of one turn.

    Each item is (soort, status). One line per soort:

        ❓ 1 vraag · open
        ❓ 3 vragen · open
        ❓ 3 vragen · 2 open · 1 beantwoord
        📜 1 motie · open

    Short, because it stands under every message with a question in it. A
    block in the channel that still has the longer words of before is
    written anew the next time its message is.

    A rejected markering does not count. Nothing to show is an empty string.
    """
    regels: list[str] = []
    for soort, (enkel, meer) in _SOORT_LABEL.items():
        statussen = [
            status
            for s, status in markeringen
            if s == soort and status != STATUS_VERWORPEN
        ]
        if not statussen:
            continue
        woorden = {**_STATUS_LABEL, **_STATUS_LABEL_PER_SOORT.get(soort, {})}
        aantal = len(statussen)
        kop = f"{aantal} {enkel if aantal == 1 else meer}"
        per_status = [
            (status, statussen.count(status))
            for status in _STATUS_LABEL
            if status in statussen
        ]
        if len(per_status) == 1:
            stand = woorden[per_status[0][0]]
        else:
            stand = " · ".join(f"{n} {woorden[status]}" for status, n in per_status)
        regel = f"{_SOORT_ICOON[soort]} {kop}"
        regels.append(f"{regel} · {stand}" if stand else regel)
    return "\n".join(regels)
