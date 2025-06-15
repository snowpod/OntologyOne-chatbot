import re
import string

class GibberishDetector:

    QWERTY_ROWS = ["qwertyuiop", "asdfghjkl", "zxcvbnm"]
    SAFE_SYMBOLS = {'.', ',', '!', '?', '-', ':'}

    VALID_FILLERS = {"ah", "eh", "hmm", "huh", "mmm", "la", "lah", "leh", "lor", "meh", 
                     "oh", "ooh", "uh", "um"}

    # Define a simple whitelist for acronyms, app names, common short replies etc.
    WHITELIST = {"a", "alarie", "an", "are", "as", "ask", "any", "bot", "call", "can", 
                 "demo", "did", "do", "essey", "ev", "e.v.", "for", "go", "harper", 
                 "her", "him", "how", "hr", "http", "https", "i", "in", "irl", "is", 
                 "it", "json", "me", "no", "not", "ok", "okay", "on", "one", "ontologyone", 
                 "pics", "pls", "rdf", "sc", "siewchoo", "so", "tay", "taylor", "tia", 
                 "thanks", "this", "that", "the", "thx", "to", "ty", "tyvm", "way", 
                 "what", "when", "who", "why", "xml", "yes", "you"}

    GIBBERISH_RATIO = 0.3   # gibberish count / total word count"to", 
    SHORT_WORD_RATIO = 0.6  # short word countfgd / total word count

    def __init__(self, threshold=GIBBERISH_RATIO):
        self.threshold = threshold  # % of gibberish tokens to trigger True

    def is_gibberish(self, text):
        tokens = text.strip().split()

        #if not tokens or len(text) < 5 or re.fullmatch(r'[a-zA-Z]{10,}', text):
        if not tokens or re.fullmatch(r'[a-zA-Z]{10,}', text):
            return True

        gibberish_count = 0
        gibberish_tokens = []

        for token in tokens:
            clean_token = token.strip(string.punctuation)

            # Check if token is in the whitelist (case insensitive)
            if self._is_whitelisted(clean_token):
                continue

            if self._is_gibberish_token(clean_token):
                gibberish_count += 1
                gibberish_tokens.append(token)

        gibberish_ratio = gibberish_count / len(tokens)
        return gibberish_ratio > self.threshold

    def _is_whitelisted(self, token):
        return token.lower() in self.WHITELIST

    def _is_gibberish_token(self, token):
        # Already cleaned
        if self._is_valid_filler(token):
            return False

        # Known English word? Not gibberish.
        if self._is_known_word(token):
            return False

        # Otherwise, check for gibberish patterns
        if (
            self._is_keyboard_smash(token) or
            self._has_long_digit_sequence(token) or
            self._has_mixed_chars(token) or
            self._is_symbols_only(token)
        ):
            return True

        return True  # If not known word and failed other checks, assume gibberish

    def _is_known_word(self, token):
        try:
            from wordfreq import word_frequency
        except ImportError:
            raise RuntimeError("wordfreq is not installed or available")

        return word_frequency(token, lang="en") > 0

    def _is_keyboard_smash(self, token):
        token = token.lower()

        # Skip common words
        if len(token) <= 6 and token.isalpha():
            return False  # common words should pass

        # Exact or reversed keyboard row substrings
        if any(token in row or token[::-1] in row for row in self.QWERTY_ROWS):
            return True

        # Repeated short sequences like "asdfasdf", "qweqwe"
        for n in range(2, 5):
            if len(token) >= 2 * n:
                chunk = token[:n]
                if token == chunk * (len(token) // n):
                    return True

        # Check for high alternation of left-to-right QWERTY keys
        pattern = ''.join([c for c in token if any(c in row for row in self.QWERTY_ROWS)])
        if len(pattern) >= 6 and self._looks_like_smash_pattern(pattern):
            return True

        return False

    def _looks_like_smash_pattern(self, token):
        # Heuristic: detect fast alternation or zigzag patterns
        changes = sum(1 for i in range(1, len(token)) if token[i] != token[i-1])
        return changes / len(token) > 0.6

    def _has_long_digit_sequence(self, token):
        return bool(re.fullmatch(r'\d{5,}', token))

    def _has_mixed_chars(self, token):
        has_letter = any(c.isalpha() for c in token)
        has_digit = any(c.isdigit() for c in token)
        has_symbol = any(c in string.punctuation for c in token)
        return sum([has_letter, has_digit, has_symbol]) >= 2

    def _is_symbols_only(self, token):
        return all(c in string.punctuation for c in token) and len(token) > 2

    def _is_valid_filler(self, token):
        return token.lower() in self.VALID_FILLERS