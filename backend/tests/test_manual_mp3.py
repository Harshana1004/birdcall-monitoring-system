"""
MP3 uploads for manual analysis: decoded once to original.wav.

    cd backend
    python -m pytest tests/test_manual_mp3.py -v
"""

import numpy as np
import pytest
import soundfile as sf
from fastapi import UploadFile

from src.api.analysis import _validate_upload_filename
from src.core.exceptions import InvalidAudioFileError
from src.services.manual_analysis import ManualAnalysisService

RATE = 44100


def tone(seconds: float = 2.0, channels: int = 2) -> np.ndarray:
    t = np.arange(int(seconds * RATE)) / RATE
    mono = 0.4 * np.sin(2 * np.pi * 3000 * t)
    return np.column_stack([mono] * channels)


def test_mp3_is_decoded_to_wav(tmp_path):
    source = tmp_path / "call.mp3"
    sf.write(source, tone(), RATE, format="MP3")

    original = tmp_path / "original.wav"
    ManualAnalysisService._store_original(source, original)

    info = sf.info(original)
    assert info.format == "WAV" and info.subtype == "PCM_16"
    assert info.samplerate == RATE and info.channels == 2
    # MP3 adds encoder padding, so allow a little extra length.
    assert 2.0 <= info.duration < 2.2

    audio, _ = sf.read(original)
    assert 0.3 < np.abs(audio).max() < 0.5


def test_wav_is_copied_unchanged(tmp_path):
    source = tmp_path / "call.wav"
    sf.write(source, tone(1.0, 1), RATE, subtype="FLOAT")

    original = tmp_path / "original.wav"
    ManualAnalysisService._store_original(source, original)

    assert original.read_bytes() == source.read_bytes()


def test_broken_mp3_is_rejected(tmp_path):
    source = tmp_path / "broken.mp3"
    source.write_bytes(b"this is not audio" * 100)

    original = tmp_path / "original.wav"
    with pytest.raises(InvalidAudioFileError):
        ManualAnalysisService._store_original(source, original)
    assert not original.exists()


@pytest.mark.parametrize("name", ["a.wav", "B.MP3", "c.mp3"])
def test_accepted_extensions(name):
    assert _validate_upload_filename(UploadFile(file=None, filename=name)) == name


@pytest.mark.parametrize("name", ["a.flac", "b.m4a", "noextension"])
def test_rejected_extensions(name):
    with pytest.raises(InvalidAudioFileError):
        _validate_upload_filename(UploadFile(file=None, filename=name))
