"""The code must run on Python 3.10 (pyproject `requires-python`), and CI tests it there.

Python 3.12 (PEP 701) allows f-strings that reuse their own quote character
inside `{...}`, and backslashes or comments in the expression part. Those are
syntax errors on 3.10 and 3.11. A developer on 3.12 or newer would not notice
until CI fails, so this test looks for them with the tokenizer. On 3.10 and
3.11 the import of such a module fails anyway, so the test only runs on 3.12+.
"""

import io
import sys
import tokenize
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def pep701_only(source: str) -> list[tuple[int, str]]:
    """(line, problem) for each f-string feature that needs Python 3.12."""
    problems = []
    stack = []   # one entry per open f-string: [quote, depth of braces]
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type == tokenize.FSTRING_START:
            prefix_end = len(tok.string.rstrip("'\""))
            quote = tok.string[prefix_end:]
            if stack and stack[-1][1] > 0 and quote[0] == stack[-1][0][0]:
                problems.append((tok.start[0], "nested f-string reuses the outer quote"))
            stack.append([quote, 0])
        elif tok.type == tokenize.FSTRING_END:
            stack.pop()
        elif stack and tok.type == tokenize.OP and tok.string in "{}":
            stack[-1][1] += 1 if tok.string == "{" else -1
        elif stack and stack[-1][1] > 0:
            outer = stack[-1][0]
            if tok.type == tokenize.STRING:
                body_start = len(tok.string) - len(tok.string.lstrip("rRbBuU"))
                if tok.string[body_start] == outer[0]:
                    problems.append((tok.start[0], "string inside {} reuses the f-string's quote"))
                if "\\" in tok.string:
                    problems.append((tok.start[0], "backslash inside {}"))
            elif tok.type == tokenize.COMMENT:
                problems.append((tok.start[0], "comment inside {}"))
    return problems


@unittest.skipIf(sys.version_info < (3, 12), "on 3.10 and 3.11 such code fails to import anyway")
class Python310SyntaxTest(unittest.TestCase):
    def test_no_f_string_needs_python_312(self):
        files = sorted((ROOT / "src").rglob("*.py")) + sorted((ROOT / "tests").rglob("*.py"))
        found = []
        for path in files:
            for line, problem in pep701_only(path.read_text(encoding="utf-8")):
                found.append(f"{path.relative_to(ROOT)}:{line}: {problem}")
        self.assertEqual(found, [], "Python 3.10 cannot parse these")

    def test_the_check_finds_each_case(self):
        bad = {
            "x = f'{'a' if y else 'b'}'\n": "reuses the f-string's quote",
            'x = f"{f"{y}"}"\n': "reuses the outer quote",
            "x = f'{\"\\n\".join(y)}'\n": "backslash",
        }
        for src, problem in bad.items():
            with self.subTest(src=src):
                self.assertTrue(any(problem in p for _, p in pep701_only(src)), pep701_only(src))
        self.assertEqual(pep701_only("x = f\"{'a' if y else 'b'}\"\n"), [])


if __name__ == "__main__":
    unittest.main()
