from difflib import SequenceMatcher
from typing import List

from .vocabulary import VocabularyBuilder


class SpellingExercise:
    def __init__(self, text: str):
        self.text = text
        self.builder = VocabularyBuilder()
        self.words = self.builder.pick_quiz_words(text, count=10)

    def get_words(self) -> List[str]:
        return self.words

    def check(self, target: str, attempt: str) -> dict:
        target_clean = target.strip().lower()
        attempt_clean = attempt.strip().lower()

        if target_clean == attempt_clean:
            return {
                "correct": True,
                "target": target,
                "attempt": attempt,
                "hint": "",
                "similarity": 1.0,
            }

        similarity = SequenceMatcher(None, target_clean, attempt_clean).ratio()
        hint = self._make_hint(target)
        return {
            "correct": False,
            "target": target,
            "attempt": attempt,
            "hint": hint,
            "similarity": round(similarity, 2),
        }

    @staticmethod
    def _make_hint(word: str) -> str:
        if len(word) <= 2:
            return "_" * len(word)
        return word[0] + "_" * (len(word) - 2) + word[-1]
