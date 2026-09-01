from types import SimpleNamespace
from typing import Any, Self

import av
import pytest

from src.services.audio import validation
from src.services.audio.errors import SpeechProblem


def test_video_mime_type_is_rejected_before_decode() -> None:
    with pytest.raises(SpeechProblem) as error:
        validation.validate_audio(b"\x1aE\xdf\xa3synthetic", "video/webm", 120)
    assert error.value.status == 415


def test_container_with_non_audio_stream_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeContainer:
        def __init__(self) -> None:
            self.streams = [
                SimpleNamespace(type="audio"),
                SimpleNamespace(type="video"),
            ]

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    def fake_open(*args: object, **kwargs: object) -> Any:
        return FakeContainer()

    monkeypatch.setattr(av, "open", fake_open)
    with pytest.raises(SpeechProblem) as error:
        validation._decoded_duration(b"synthetic", 120)
    assert error.value.status == 422
