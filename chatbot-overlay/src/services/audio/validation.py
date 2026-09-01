import io

import av

from src.services.audio.errors import SpeechProblem
from src.services.audio.models import ValidatedAudio

_DECLARED_TYPES: dict[str, set[str]] = {
    "wav": {"audio/wav", "audio/x-wav", "audio/wave"},
    "mp3": {"audio/mpeg", "audio/mp3"},
    "ogg": {"audio/ogg", "application/ogg"},
    "webm": {"audio/webm"},
    "mp4": {"audio/mp4", "audio/x-m4a"},
}


def validate_audio(
    content: bytes, declared_type: str, max_seconds: int
) -> ValidatedAudio:
    actual_type = _sniff_container(content)
    normalized_type = declared_type.split(";", maxsplit=1)[0].strip().lower()
    if normalized_type not in _DECLARED_TYPES[actual_type]:
        raise SpeechProblem(415, "unsupported_audio", "Audio format is not supported.")

    duration_seconds = _decoded_duration(content, max_seconds)
    return ValidatedAudio(
        content=content,
        media_type=normalized_type,
        duration_milliseconds=round(duration_seconds * 1000),
    )


def _sniff_container(content: bytes) -> str:
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WAVE":
        return "wav"
    if content.startswith(b"OggS"):
        return "ogg"
    if content.startswith(b"\x1aE\xdf\xa3"):
        return "webm"
    if len(content) >= 12 and content[4:8] == b"ftyp":
        return "mp4"
    if content.startswith(b"ID3") or (
        len(content) >= 2 and content[0] == 0xFF and content[1] & 0xE0 == 0xE0
    ):
        return "mp3"
    raise SpeechProblem(415, "unsupported_audio", "Audio format is not supported.")


def _decoded_duration(content: bytes, max_seconds: int) -> float:
    try:
        with av.open(io.BytesIO(content), mode="r") as container:
            streams = [stream for stream in container.streams if stream.type == "audio"]
            if len(streams) != 1 or any(
                stream.type != "audio" for stream in container.streams
            ):
                raise _invalid_audio()
            duration = 0.0
            frames = 0
            for frame in container.decode(streams[0]):
                if not isinstance(frame, av.AudioFrame) or not frame.sample_rate:
                    continue
                duration += frame.samples / float(frame.sample_rate)
                frames += 1
                if duration > max_seconds:
                    raise SpeechProblem(
                        413, "audio_too_long", "Audio exceeds the maximum duration."
                    )
            if frames == 0 or duration <= 0:
                raise _invalid_audio()
            return duration
    except SpeechProblem:
        raise
    except Exception as exc:
        raise _invalid_audio() from exc


def _invalid_audio() -> SpeechProblem:
    return SpeechProblem(422, "invalid_audio", "Audio is empty, corrupt or unreadable.")
