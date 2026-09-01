"""Azure Speech-to-Text capability for the office chatbot."""

from src.services.audio.azure_client import AzureSpeechClient
from src.services.audio.config import SpeechSettings
from src.services.audio.limits import AdmissionController, RedisAdmissionController
from src.services.audio.models import SpeechCaller
from src.services.audio.service import AudioTranscription, AudioTranscriptionService

__all__ = [
    "AdmissionController",
    "AudioTranscription",
    "AudioTranscriptionService",
    "AzureSpeechClient",
    "RedisAdmissionController",
    "SpeechCaller",
    "SpeechSettings",
]
