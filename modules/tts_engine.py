import hashlib
import os
import threading
from pathlib import Path
from typing import List, Optional

import numpy as np
import soundfile as sf

from kokoro import KPipeline


class TTSEngine:
    DEFAULT_VOICE = "af_heart"
    DEFAULT_LANG = "a"
    SAMPLE_RATE = 24000
    VOICES = [
        # American English - Female
        "af_heart", "af_bella",
        # American English - Male
        "am_adam", "am_echo",
    ]

    def __init__(
        self,
        voice: Optional[str] = None,
        lang_code: Optional[str] = None,
        output_dir: str = "data/audio",
    ):
        self.voice = voice or os.environ.get("TTS_VOICE") or self.DEFAULT_VOICE
        self.lang_code = lang_code or os.environ.get("TTS_LANG") or self.DEFAULT_LANG
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._pipeline: Optional[KPipeline] = None
        self._lock = threading.Lock()

    @classmethod
    def list_voices(cls) -> List[str]:
        return cls.VOICES

    def _get_pipeline(self) -> KPipeline:
        if self._pipeline is None:
            with self._lock:
                if self._pipeline is None:
                    self._pipeline = KPipeline(lang_code=self.lang_code, model=True)
        return self._pipeline

    def _normalize_voice(self, voice: str) -> str:
        if voice in self.VOICES:
            return voice
        return self.DEFAULT_VOICE

    def speak(self, text: str, filename: Optional[str] = None, voice: Optional[str] = None, speed: Optional[float] = None) -> str:
        text = text.strip()
        if not text:
            raise ValueError("TTS text cannot be empty")

        selected_voice = voice or self.voice
        selected_speed = speed if speed is not None else 1.0

        if filename is None:
            filename = f"{hashlib.md5((text + selected_voice + str(selected_speed)).encode('utf-8')).hexdigest()}.wav"

        output_path = self.output_dir / filename
        if output_path.exists():
            return str(output_path)

        self._save(text, output_path, selected_voice, selected_speed)
        return str(output_path)

    def _save(self, text: str, output_path: Path, voice: Optional[str] = None, speed: float = 1.0) -> None:
        pipeline = self._get_pipeline()
        selected_voice = self._normalize_voice(voice or self.voice)
        audio_chunks = [
            result.audio
            for result in pipeline(text, voice=selected_voice, speed=speed)
            if result.audio is not None
        ]

        if not audio_chunks:
            raise RuntimeError("Kokoro produced no audio")

        audio = np.concatenate(audio_chunks)
        sf.write(str(output_path), audio, self.SAMPLE_RATE)
