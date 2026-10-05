"""Download the speaker model into the image, and check it is the right one.

Run at build by the Dockerfile. The model is not in the repository: it is
26 MB of binary. It is pinned twice, to a revision of its repository and to
the SHA-256 of the file.

WeSpeaker ResNet34-LM (https://huggingface.co/Wespeaker/wespeaker-voxceleb-resnet34-LM),
licensed CC BY 4.0, trained on VoxCeleb2.

A download that fails does not fail the build: the application runs
without the model, and then puts every line of subtitle with a speaker by
time alone. A file that is not the pinned one does fail it. That is not an
outage but something else being served under this name.

Usage: fetch_stem_model.py <target path>
"""

import hashlib
import pathlib
import sys
import urllib.error
import urllib.request

REVISION = "f0c48c298fd835726c27956a5d617bad7115627e"
URL = (
    "https://huggingface.co/Wespeaker/wespeaker-voxceleb-resnet34-LM/resolve/"
    f"{REVISION}/voxceleb_resnet34_LM.onnx"
)
SHA256 = "7bb2f06e9df17cdf1ef14ee8a15ab08ed28e8d0ef5054ee135741560df2ec068"
TIMEOUT = 120


def fetch(url: str = URL) -> bytes | None:
    """The file, or ``None`` when it cannot be downloaded now."""
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as response:
            return response.read()
    except Exception as exc:
        # Whatever it is, also a download that breaks off halfway: this
        # must never be the reason an image cannot be built.
        print(f"Sprekermodel niet te downloaden ({exc!r}); de image komt zonder")
        return None


def main(target: pathlib.Path, data: bytes | None) -> int:
    target.parent.mkdir(parents=True, exist_ok=True)
    if data is None:
        return 0
    found = hashlib.sha256(data).hexdigest()
    if found != SHA256:
        # Not what was pinned: an error page, or another file. It is not
        # used, and the image is built without, so that a hiccup at the
        # other end cannot block a deploy.
        print(
            f"Sprekermodel heeft SHA-256 {found}, verwacht was {SHA256}; "
            "de image komt zonder"
        )
        return 0
    target.write_bytes(data)
    print(f"Sprekermodel staat op {target} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main(pathlib.Path(sys.argv[1]), fetch()))
