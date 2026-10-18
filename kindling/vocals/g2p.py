"""Grapheme-to-phoneme with per-language handling (Part 7).

SUPPORTED_LANGUAGES lists exactly what the reference implementation covers;
every language is tested separately. English uses letter-to-sound rules with
an exception lexicon, syllabification, stress heuristics, and elision.
Spanish uses its near-phonetic spelling plus real stress rules. Learned G2P
models plug into the Phonemizer interface later; the interface is the
contract, these are the reference implementations.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

ARPABET_VOWELS = {"IY", "IH", "EY", "EH", "AE", "AA", "AO", "OW", "UW", "UH",
                  "AH", "AY", "AW", "OY", "ER", "AX"}


class Phonemizer(ABC):
    """Contract for per-language pronunciation."""

    @property
    @abstractmethod
    def language(self) -> str:
        """BCP 47 code."""

    @property
    @abstractmethod
    def language_name(self) -> str:
        pass

    @abstractmethod
    def phonemize(self, text: str) -> List[Dict]:
        """Text to a list of syllables.

        Each syllable: {"graphemes": str, "phonemes": [str],
        "stress": 0|1|2}. Stress 1 is primary.
        """


# ---------------------------------------------------------------- English
_EN_EXCEPTIONS = {
    # word: [(graphemes, [phonemes], stress)]
    "the": [[("the", ["DH", "AH"], 0)]],
    "a": [[("a", ["AH"], 0)]],
    "of": [[("of", ["AH", "V"], 0)]],
    "to": [[("to", ["T", "UW"], 0)]],
    "and": [[("and", ["AE", "N", "D"], 0)]],
    "you": [[("you", ["Y", "UW"], 1)]],
    "i": [[("i", ["AY"], 1)]],
    "every": [[("e", ["EH"], 1)], [("very", ["V", "R", "IY"], 0)]],
    "family": [[("fa", ["F", "AE"], 1)], [("mi", ["M"], 0)], [("ly", ["L", "IY"], 0)]],
    "different": [[("di", ["D", "IH"], 1)], [("ffe", ["F"], 0)], [("rent", ["R", "AH", "N", "T"], 0)]],
    "choir": [[("choir", ["K", "W", "AY", "R"], 1)]],
    "la": [[("la", ["L", "AA"], 1)]],
}

_EN_DIGRAPHS = [
    ("dge", ["JH"]), ("tch", ["CH"]), ("igh", ["AY"]), ("eigh", ["EY"]),
    ("sh", ["SH"]), ("ch", ["CH"]), ("th", ["TH"]), ("wh", ["W"]),
    ("ph", ["F"]), ("ng", ["NG"]), ("ck", ["K"]),
    ("ee", ["IY"]), ("ea", ["IY"]), ("oo", ["UW"]), ("ai", ["EY"]),
    ("ay", ["EY"]), ("ow", ["AW"]), ("ou", ["AW"]), ("oi", ["OY"]),
    ("oy", ["OY"]), ("ie", ["IY"]), ("oa", ["OW"]), ("aw", ["AO"]),
    ("au", ["AO"]), ("ew", ["UW"]), ("ue", ["UW"]), ("ey", ["IY"]),
]

_EN_SINGLE = {
    "a": ["AE"], "b": ["B"], "c": ["K"], "d": ["D"], "e": ["EH"],
    "f": ["F"], "g": ["G"], "h": ["HH"], "i": ["IH"], "j": ["JH"],
    "k": ["K"], "l": ["L"], "m": ["M"], "n": ["N"], "o": ["AA"],
    "p": ["P"], "q": ["K"], "r": ["R"], "s": ["S"], "t": ["T"],
    "u": ["AH"], "v": ["V"], "w": ["W"], "x": ["K", "S"], "y": ["Y"],
    "z": ["Z"],
}

_EN_VOWEL_LETTERS = set("aeiouy")


def _en_word_phonemes(word: str) -> List[str]:
    """Letter-to-sound rules for one lowercase word."""
    if word in _EN_EXCEPTIONS:
        return [p for group in _EN_EXCEPTIONS[word]
                for syl in group for p in syl[1]]
    chars = word
    # silent e: VCe -> long vowel, drop the e
    silent_e = False
    if re.search(r"[aeiou][^aeiou]e$", chars) and len(chars) > 3:
        silent_e = True
        chars = chars[:-1]
    phonemes: List[str] = []
    i = 0
    while i < len(chars):
        matched = False
        for grapheme, phones in _EN_DIGRAPHS:
            if chars.startswith(grapheme, i):
                phonemes.extend(phones)
                i += len(grapheme)
                matched = True
                break
        if matched:
            continue
        ch = chars[i]
        if ch == "c" and i + 1 < len(chars) and chars[i + 1] in "eiy":
            phonemes.append("S")
        elif ch == "g" and i + 1 < len(chars) and chars[i + 1] in "eiy":
            phonemes.append("JH")
        elif ch == "a" and silent_e and i == chars.find("a"):
            phonemes.append("EY")
        elif ch == "i" and silent_e and "i" in chars:
            phonemes.append("AY")
        elif ch == "o" and silent_e and "o" in chars:
            phonemes.append("OW")
        elif ch == "u" and silent_e and "u" in chars:
            phonemes.append("UW")
        else:
            phonemes.extend(_EN_SINGLE.get(ch, []))
        i += 1
    # -ed endings
    if word.endswith("ed") and len(word) > 3:
        stem_end = word[-3]
        if stem_end in "td":
            phonemes.extend(["IH", "D"])
        elif stem_end in "pcfkssx" or word.endswith(("sh", "ch")):
            phonemes.append("T")
        else:
            phonemes.append("D")
    return phonemes


def _en_syllabify(word: str, phonemes: List[str]) -> List[Dict]:
    """Split phonemes into syllables around vowel nuclei (max-onset lite)."""
    vowel_idx = [i for i, p in enumerate(phonemes) if p in ARPABET_VOWELS]
    if not vowel_idx:
        return [{"graphemes": word, "phonemes": phonemes, "stress": 1}]
    syllables = []
    boundaries = [0]
    for v in range(1, len(vowel_idx)):
        gap = vowel_idx[v] - vowel_idx[v - 1] - 1
        cut = vowel_idx[v - 1] + 1 + max(0, gap - 1)
        boundaries.append(cut)
    boundaries.append(len(phonemes))
    for s in range(len(boundaries) - 1):
        part = phonemes[boundaries[s]:boundaries[s + 1]]
        # Elision: drop unstressed IH before R/L/N between consonants
        # ("family" -> F AE M L IY). The exception lexicon handles the
        # common words; this is the general rule.
        cleaned = []
        for j, p in enumerate(part):
            if (p == "IH" and j + 1 < len(part) and part[j + 1] in ("R", "L", "N")
                    and s > 0):
                continue
            cleaned.append(p)
        syllables.append({"graphemes": word, "phonemes": cleaned, "stress": 0})
    # Stress heuristic: first syllable primary for short words, else the
    # syllable before -tion/-ic; documented as a heuristic.
    if word.endswith(("tion", "sion")) and len(syllables) > 1:
        syllables[-2]["stress"] = 1
    elif word.endswith("ic") and len(syllables) > 1:
        syllables[-2]["stress"] = 1
    else:
        syllables[0]["stress"] = 1
    return syllables


class EnglishG2P(Phonemizer):
    @property
    def language(self) -> str:
        return "en"

    @property
    def language_name(self) -> str:
        return "English (rule-based reference)"

    def phonemize(self, text: str) -> List[Dict]:
        out = []
        for word in re.findall(r"[a-zA-Z']+", text.lower()):
            out.extend(_en_syllabify(word, _en_word_phonemes(word)))
        return out


# ---------------------------------------------------------------- Spanish
_ES_SINGLE = {
    "a": ["A"], "b": ["B"], "c": ["K"], "d": ["D"], "e": ["E"], "f": ["F"],
    "g": ["G"], "h": [], "i": ["I"], "j": ["X"], "k": ["K"], "l": ["L"],
    "m": ["M"], "n": ["N"], "o": ["O"], "p": ["P"], "q": ["K"], "r": ["R"],
    "s": ["S"], "t": ["T"], "u": ["U"], "v": ["B"], "w": ["W"], "x": ["K", "S"],
    "y": ["Y"], "z": ["S"],
}
_ES_DIGRAPHS = [("ch", ["CH"]), ("ll", ["Y"]), ("rr", ["RR"]), ("qu", ["K"]), ("gu", ["G"])]
_ES_VOWELS = set("aeiou")
_ES_DIPHTHONGS = {"ia", "ie", "io", "iu", "ua", "ue", "ui", "uo", "ai", "au",
                  "ei", "eu", "oi", "ou"}
_ACCENT_STRIP = str.maketrans("áéíóúü", "aeiouu")


def _es_syllabify(word: str) -> List[Dict]:
    plain = word.translate(_ACCENT_STRIP)
    # find vowel nuclei, keeping diphthongs together
    nuclei = []
    i = 0
    chars = list(plain)
    while i < len(chars):
        if chars[i] in _ES_VOWELS:
            pair = "".join(chars[i:i + 2])
            # accented i/u breaks the diphthong (hacia vs hacía)
            if pair in _ES_DIPHTHONGS and not (i < len(word) and word[i] in "íú"
                                               or i + 1 < len(word) and word[i + 1] in "íú"):
                nuclei.append((i, i + 2))
                i += 2
            else:
                nuclei.append((i, i + 1))
                i += 1
        else:
            i += 1
    syllables = []
    prev_end = 0
    for n_i, (ns, ne) in enumerate(nuclei):
        next_ns = nuclei[n_i + 1][0] if n_i + 1 < len(nuclei) else len(chars)
        between = next_ns - ne
        # consonants between nuclei: all but the last start the next syllable
        cut = ne + max(0, between - 1)
        syllables.append({"start": prev_end, "end": cut})
        prev_end = cut
    if prev_end < len(chars) and syllables:
        syllables[-1]["end"] = len(chars)
    # phonemes per syllable, keeping the plain-text span for stress lookup
    result = []
    for syl in syllables:
        chunk = plain[syl["start"]:syl["end"]]
        phones: List[str] = []
        j = 0
        while j < len(chunk):
            matched = False
            for grapheme, ph in _ES_DIGRAPHS:
                if chunk.startswith(grapheme, j):
                    phones.extend(ph)
                    j += len(grapheme)
                    matched = True
                    break
            if matched:
                continue
            ch = chunk[j]
            nxt = chunk[j + 1] if j + 1 < len(chunk) else ""
            if ch == "c" and nxt in "ei":
                phones.append("S")
            elif ch == "g" and nxt in "ei":
                phones.append("X")
            else:
                phones.extend(_ES_SINGLE.get(ch, []))
            j += 1
        result.append({"graphemes": chunk, "phonemes": phones, "stress": 0,
                       "_span": (syl["start"], syl["end"])})
    # stress: explicit accent, else penultimate if ends in vowel/n/s, else final
    stressed = None
    for k, ch in enumerate(word):
        if ch in "áéíóú":
            stressed = k
            break
    if stressed is not None:
        for syl in result:
            s, e = syl["_span"]
            if s <= stressed < e:
                syl["stress"] = 1
    else:
        idx = -2 if plain[-1] in "aeiouns" else -1
        if len(result) >= abs(idx):
            result[idx]["stress"] = 1
        elif result:
            result[-1]["stress"] = 1
    for syl in result:
        del syl["_span"]
    return result


class SpanishG2P(Phonemizer):
    @property
    def language(self) -> str:
        return "es"

    @property
    def language_name(self) -> str:
        return "Spanish (rule-based reference)"

    def phonemize(self, text: str) -> List[Dict]:
        out = []
        for word in re.findall(r"[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ]+", text.lower()):
            out.extend(_es_syllabify(word))
        return out


SUPPORTED_LANGUAGES: Dict[str, Phonemizer] = {
    "en": EnglishG2P(),
    "es": SpanishG2P(),
}


def phonemize(text: str, language: str = "en") -> List[Dict]:
    """Phonemize text in a supported language. Raises for the rest: no
    silent fallback, no fake pronunciation."""
    try:
        engine = SUPPORTED_LANGUAGES[language]
    except KeyError:
        raise ValueError(
            f"language {language!r} not supported. Supported: {sorted(SUPPORTED_LANGUAGES)}")
    return engine.phonemize(text)
