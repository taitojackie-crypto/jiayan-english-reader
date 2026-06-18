import logging
import re
from typing import Dict, List

logger = logging.getLogger(__name__)


class VocabularyBuilder:
    COMMON_STOPWORDS = frozenset({
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "must", "shall", "can", "need", "dare", "ought",
        "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
        "as", "into", "through", "during", "before", "after", "above", "below",
        "between", "under", "and", "but", "or", "yet", "so", "if", "because",
        "although", "though", "while", "where", "when", "that", "which", "who",
        "whom", "whose", "what", "this", "these", "those", "i", "you", "he",
        "she", "it", "we", "they", "me", "him", "her", "us", "them", "my",
        "your", "his", "its", "our", "their", "mine", "yours", "hers", "ours",
        "theirs", "myself", "yourself", "himself", "herself", "itself", "ourselves",
        "yourselves", "themselves", "here", "there", "everywhere", "anywhere",
        "somewhere", "nowhere", "all", "each", "every", "both", "few", "more",
        "most", "other", "some", "such", "no", "not", "only", "own", "same",
        "than", "too", "very", "just", "now", "then", "once", "again", "also",
        "any", "how", "why", "where", "who", "what", "which", "this", "that",
        "these", "those", "am", "s", "t", "don", "doesn", "didn", "won",
        "wouldn", "couldn", "shouldn", "isn", "aren", "wasn", "weren", "haven",
        "hasn", "hadn", "ll", "re", "ve", "d", "m", "o", "y", "ma", "mightn",
        "mustn", "needn", "shan", "shouldn",
    })

    def extract(self, text: str, top_n: int = 20) -> List[Dict[str, object]]:
        if top_n <= 0:
            return []

        tokens = re.findall(r"[a-zA-Z]+(?:'[a-zA-Z]+)?", text)
        counts: Dict[str, int] = {}
        for token in tokens:
            word = token.lower()
            if not self._is_valid_word(word):
                continue
            counts[word] = counts.get(word, 0) + 1

        sorted_words = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        selected = sorted_words[:top_n]
        if not selected:
            return []

        return [
            {
                "word": word,
                "count": count,
                "level": self._guess_level(word),
            }
            for word, count in selected
        ]

    def _is_valid_word(self, word: str) -> bool:
        if word in self.COMMON_STOPWORDS:
            return False
        if len(word) < 3 or len(word) > 20:
            return False
        if word.endswith("'s") and word[:-2] in self.COMMON_STOPWORDS:
            return False
        return True

    @staticmethod
    def _guess_level(word: str) -> str:
        length = len(word)
        if length <= 4:
            return "easy"
        if length <= 6:
            return "medium"
        return "hard"

    def pick_quiz_words(self, text: str, count: int = 5) -> List[str]:
        if count <= 0:
            return []
        tokens = re.findall(r"[a-zA-Z]+(?:'[a-zA-Z]+)?", text)
        counts: Dict[str, int] = {}
        for token in tokens:
            word = token.lower()
            if not self._is_valid_word(word):
                continue
            counts[word] = counts.get(word, 0) + 1
        sorted_words = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return [word for word, _ in sorted_words[:count]]
