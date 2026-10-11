"""Local question bank: the deterministic fallback used when Gemini is not configured.

Every question has four options and exactly one correct answer. Questions are picked deterministically per job
(same job + same skills -> same questions), so results are reproducible without any paid AI API.
Recruiters must still review and approve every question before an assessment is published.
"""
from __future__ import annotations

import hashlib
import re

# canonical skill -> aliases (lower-case)
ALIASES: dict[str, set[str]] = {
    "python": {"python", "python3", "py", "django", "flask", "fastapi", "pandas"},
    "sql": {"sql", "mysql", "postgresql", "postgres", "sqlite", "oracle", "sql server", "mssql", "pl/sql", "database", "databases", "dbms"},
    "javascript": {"javascript", "js", "es6", "typescript", "ts", "node", "nodejs", "node.js"},
    "react": {"react", "reactjs", "react.js", "next.js", "nextjs"},
    "java": {"java", "spring", "spring boot", "springboot", "j2ee"},
    "html_css": {"html", "css", "html5", "css3", "html/css", "tailwind", "bootstrap", "frontend", "web design"},
    "git": {"git", "github", "gitlab", "version control"},
    "dsa": {"dsa", "data structures", "algorithms", "data structures and algorithms", "problem solving", "competitive programming"},
    "c_cpp": {"c", "c++", "cpp", "embedded c"},
    "ml": {"machine learning", "ml", "deep learning", "ai", "artificial intelligence", "scikit-learn", "sklearn", "tensorflow", "pytorch", "data science"},
}
LABELS = {"python": "Python", "sql": "SQL", "javascript": "JavaScript", "react": "React", "java": "Java", "html_css": "HTML & CSS",
          "git": "Git", "dsa": "Data Structures & Algorithms", "c_cpp": "C / C++", "ml": "Machine Learning"}


def canonical(skill: str) -> str | None:
    s = re.sub(r"\s+", " ", (skill or "").strip().lower())
    for key, names in ALIASES.items():
        if s in names:
            return key
    return None


def _q(qid, prompt, options, answer, explanation, difficulty="easy", code=None):
    assert len(options) == 4 and answer in "abcd"
    return {"bankId": qid, "prompt": prompt, "code": code, "difficulty": difficulty,
            "options": [{"id": k, "text": t} for k, t in zip("abcd", options)], "answer": answer, "explanation": explanation}


BANK: dict[str, list[dict]] = {
    "python": [
        _q("py-01", "What does this code print?", ["[1, 2, 3]", "[1, 2, 3, 4]", "None", "An error"], "b",
           "list.append mutates the list in place; b refers to the same list as a.", code="a = [1, 2, 3]\nb = a\nb.append(4)\nprint(a)"),
        _q("py-02", "Which of these is immutable?", ["list", "dict", "set", "tuple"], "d", "Tuples cannot be changed after creation."),
        _q("py-03", "What is the output of `print(7 // 2, 7 % 2)`?", ["3 1", "3.5 1", "3 0", "4 1"], "a", "// is floor division and % is the remainder."),
        _q("py-04", "What does `[x * x for x in range(4)]` evaluate to?", ["[1, 4, 9, 16]", "[0, 1, 4, 9]", "[0, 1, 2, 3]", "[0, 2, 4, 6]"], "b",
           "range(4) yields 0, 1, 2, 3."),
        _q("py-05", "Which keyword is used to handle exceptions?", ["catch", "except", "rescue", "handle"], "b", "Python uses try / except."),
        _q("py-06", "What does this function return for `f()` called twice?", ["[1] then [1]", "[1] then [1, 1]", "An error", "None"], "b",
           "Default argument values are created once, so the same list is reused between calls.", "medium",
           code="def f(items=[]):\n    items.append(1)\n    return items"),
        _q("py-07", "What does `len({'a': 1, 'b': 2, 'a': 3})` return?", ["3", "2", "1", "An error"], "b", "Duplicate keys overwrite; the dict has 2 keys.", "medium"),
        _q("py-08", "Which statement about generators is true?", ["They store all values in memory", "They produce values lazily with yield",
           "They can be indexed like lists", "They are only available in Python 2"], "b", "Generators yield one value at a time.", "medium"),
    ],
    "sql": [
        _q("sql-01", "Which clause filters rows after grouping?", ["WHERE", "HAVING", "ORDER BY", "LIMIT"], "b", "HAVING filters groups; WHERE filters rows before grouping."),
        _q("sql-02", "Which JOIN returns only rows with matches in both tables?", ["LEFT JOIN", "RIGHT JOIN", "INNER JOIN", "FULL OUTER JOIN"], "c",
           "INNER JOIN keeps matching rows only."),
        _q("sql-03", "What does `COUNT(*)` count?", ["Non-null values in the first column", "All rows, including NULLs", "Distinct rows", "Columns"], "b",
           "COUNT(*) counts rows regardless of NULL values."),
        _q("sql-04", "Which constraint guarantees that a column has no duplicate values?", ["NOT NULL", "CHECK", "UNIQUE", "DEFAULT"], "c", "UNIQUE prevents duplicates."),
        _q("sql-05", "What is the result of `SELECT NULL = NULL;` in standard SQL?", ["TRUE", "FALSE", "NULL (unknown)", "An error"], "c",
           "Comparisons with NULL are unknown; use IS NULL.", "medium"),
        _q("sql-06", "Which statement removes all rows but keeps the table structure?", ["DROP TABLE", "DELETE TABLE", "TRUNCATE TABLE", "ALTER TABLE"], "c",
           "TRUNCATE empties the table; DROP removes it.", "medium"),
        _q("sql-07", "An index mainly speeds up…", ["INSERTs", "lookups and filtering", "backups", "schema changes"], "b",
           "Indexes help reads; they add a small cost to writes.", "medium"),
        _q("sql-08", "Which normal form removes partial dependency on a composite key?", ["1NF", "2NF", "3NF", "BCNF"], "b",
           "2NF requires full functional dependency on the whole key.", "hard"),
    ],
    "javascript": [
        _q("js-01", "What does `typeof null` return?", ["'null'", "'object'", "'undefined'", "'number'"], "b", "A long-standing quirk of JavaScript."),
        _q("js-02", "Which declares a block-scoped variable that cannot be reassigned?", ["var", "let", "const", "static"], "c", "const is block-scoped and not reassignable."),
        _q("js-03", "What is `[1, 2, 3].map(n => n * 2)`?", ["[2, 4, 6]", "[1, 2, 3, 1, 2, 3]", "6", "[1, 4, 9]"], "a", "map returns a new array."),
        _q("js-04", "What does `'5' + 3` evaluate to?", ["8", "'53'", "NaN", "An error"], "b", "+ with a string concatenates."),
        _q("js-05", "What does this print?", ["0 1 2", "3 3 3", "undefined x3", "An error"], "a",
           "let creates a new binding per loop iteration.", "medium", code="for (let i = 0; i < 3; i++) {\n  setTimeout(() => console.log(i));\n}"),
        _q("js-06", "Which is true about `===`?", ["It converts types before comparing", "It compares value and type", "It only works on numbers",
           "It is the same as ="], "b", "Strict equality does not coerce types."),
        _q("js-07", "What does `await` do inside an async function?", ["Blocks the whole browser", "Pauses that function until the promise settles",
           "Creates a new thread", "Cancels the promise"], "b", "Only the async function is paused.", "medium"),
        _q("js-08", "What is logged?", ["1 2 3", "1 3 2", "2 1 3", "3 1 2"], "b", "Synchronous code runs before queued callbacks.", "hard",
           code="console.log(1);\nsetTimeout(() => console.log(2), 0);\nconsole.log(3);"),
    ],
    "react": [
        _q("re-01", "Which hook stores local state in a function component?", ["useEffect", "useState", "useRef", "useMemo"], "b", "useState returns state and a setter."),
        _q("re-02", "What is the purpose of the `key` prop in lists?", ["Styling", "Helping React match items between renders", "Accessibility", "Routing"], "b",
           "Stable keys let React reuse the right elements."),
        _q("re-03", "When does an effect with an empty dependency array run?", ["Every render", "Only after the first render (mount)", "Never", "Before render"], "b",
           "[] means no dependencies, so it runs once after mount (twice in StrictMode development)."),
        _q("re-04", "Props in React are…", ["mutable by the child", "read-only for the child", "global variables", "only strings"], "b", "Children must not modify props."),
        _q("re-05", "Why might `setCount(count + 1)` called twice in one handler only add 1?", ["React ignores the second call", "Both calls use the same stale `count` value",
           "setState is synchronous", "It is a bug in React"], "b", "Use the updater form setCount(c => c + 1).", "medium"),
        _q("re-06", "Which hook is best for caching an expensive computed value?", ["useMemo", "useState", "useId", "useLayoutEffect"], "a",
           "useMemo recomputes only when dependencies change.", "medium"),
    ],
    "java": [
        _q("jv-01", "Which keyword creates a subclass?", ["implements", "extends", "inherits", "super"], "b", "Classes extend classes and implement interfaces."),
        _q("jv-02", "What is the default value of an int field?", ["null", "0", "undefined", "-1"], "b", "Numeric fields default to 0."),
        _q("jv-03", "Which collection does NOT allow duplicate elements?", ["ArrayList", "LinkedList", "HashSet", "Vector"], "c", "Sets hold unique elements."),
        _q("jv-04", "How should two String values be compared for equal text?", ["==", ".equals()", "compareTo() == 1", "="], "b",
           "== compares references; equals compares content."),
        _q("jv-05", "Which is a checked exception?", ["NullPointerException", "ArithmeticException", "IOException", "ArrayIndexOutOfBoundsException"], "c",
           "IOException must be declared or caught.", "medium"),
        _q("jv-06", "What does `final` on a method mean?", ["It cannot be called", "It cannot be overridden", "It is static", "It runs last"], "b",
           "final methods cannot be overridden.", "medium"),
    ],
    "html_css": [
        _q("hc-01", "Which HTML element is most appropriate for the main navigation?", ["<div>", "<nav>", "<section>", "<aside>"], "b", "<nav> is the semantic element."),
        _q("hc-02", "Which CSS property changes the space INSIDE an element's border?", ["margin", "padding", "gap", "outline"], "b", "Padding is inside; margin is outside."),
        _q("hc-03", "Which selector has the highest specificity?", [".card", "#main", "div", "*"], "b", "ID selectors beat class and type selectors."),
        _q("hc-04", "What does `display: flex` do?", ["Hides the element", "Makes children flex items laid out along an axis", "Floats the element", "Makes text bold"],
           "b", "It creates a flex formatting context."),
        _q("hc-05", "Which attribute provides alternative text for images?", ["title", "alt", "src", "aria-hidden"], "b", "alt is read by screen readers.", "easy"),
        _q("hc-06", "With `box-sizing: border-box`, an element's width includes…", ["content only", "content and padding and border", "margin too", "nothing"], "b",
           "border-box includes padding and border in the width.", "medium"),
    ],
    "git": [
        _q("gt-01", "Which command records staged changes in the repository?", ["git add", "git commit", "git push", "git stash"], "b", "commit records a snapshot."),
        _q("gt-02", "Which command creates a new branch and switches to it?", ["git branch -d x", "git switch -c x", "git merge x", "git log x"], "b",
           "git switch -c (or git checkout -b) creates and switches."),
        _q("gt-03", "What does `git pull` do?", ["Uploads commits", "Fetches and integrates remote changes", "Deletes a branch", "Shows history"], "b",
           "pull = fetch + merge (or rebase)."),
        _q("gt-04", "Which file lists paths Git should not track?", [".gitconfig", ".gitignore", ".gitkeep", "README"], "b", ".gitignore lists untracked patterns."),
        _q("gt-05", "What does `git revert <commit>` do?", ["Deletes the commit from history", "Creates a new commit that undoes it", "Moves HEAD back", "Discards local files"],
           "b", "revert is safe for shared history.", "medium"),
    ],
    "dsa": [
        _q("ds-01", "Time complexity of binary search on a sorted array?", ["O(n)", "O(log n)", "O(n log n)", "O(1)"], "b", "Each step halves the range."),
        _q("ds-02", "Which structure works Last-In-First-Out?", ["Queue", "Stack", "Heap", "Graph"], "b", "Stacks are LIFO."),
        _q("ds-03", "Average lookup time in a hash table?", ["O(1)", "O(log n)", "O(n)", "O(n²)"], "a", "With a good hash function, lookups are constant on average."),
        _q("ds-04", "Which traversal of a binary search tree gives sorted order?", ["Pre-order", "In-order", "Post-order", "Level-order"], "b",
           "In-order visits left, node, right."),
        _q("ds-05", "Which algorithm finds shortest paths with non-negative edge weights?", ["DFS", "Dijkstra's", "Kruskal's", "Bubble sort"], "b",
           "Dijkstra's algorithm.", "medium"),
        _q("ds-06", "Worst-case time of quicksort?", ["O(n log n)", "O(n²)", "O(n)", "O(log n)"], "b", "Bad pivots give quadratic time.", "medium"),
        _q("ds-07", "Which structure is best for BFS?", ["Stack", "Queue", "Hash set only", "Array sorted"], "b", "BFS processes nodes in FIFO order.", "medium"),
    ],
    "c_cpp": [
        _q("cc-01", "What does the `&` operator return when applied to a variable in C?", ["Its value", "Its address", "Its size", "A copy"], "b", "& takes the address."),
        _q("cc-02", "Which function frees memory allocated with malloc?", ["delete", "free", "release", "dispose"], "b", "free() pairs with malloc()."),
        _q("cc-03", "What is `sizeof(char)` in C?", ["1", "2", "4", "Depends on the compiler"], "a", "sizeof(char) is 1 by definition."),
        _q("cc-04", "In C++, which feature allows the same function name with different parameters?", ["Overriding", "Overloading", "Templates only", "Friend"], "b",
           "Function overloading.", "medium"),
        _q("cc-05", "What happens when you dereference a NULL pointer?", ["It returns 0", "Undefined behaviour", "It allocates memory", "Compile error always"], "b",
           "Dereferencing NULL is undefined behaviour.", "medium"),
    ],
    "ml": [
        _q("ml-01", "Which is a supervised learning task?", ["Clustering", "Classification", "Dimensionality reduction", "Association rules"], "b",
           "Classification learns from labelled data."),
        _q("ml-02", "Overfitting means the model…", ["performs well on training data but poorly on new data", "is too simple", "trains too slowly", "has no parameters"],
           "a", "It memorises the training set."),
        _q("ml-03", "Why do we keep a separate test set?", ["To train faster", "To estimate performance on unseen data", "To increase accuracy", "To label data"], "b",
           "Evaluation must use data the model has not seen."),
        _q("ml-04", "Which metric is most informative for a heavily imbalanced classification problem?", ["Accuracy", "F1 score / recall", "Mean squared error", "R²"], "b",
           "Accuracy can be misleading when one class dominates.", "medium"),
        _q("ml-05", "What does regularisation (e.g. L2) mainly do?", ["Speeds up inference", "Penalises large weights to reduce overfitting", "Adds more data",
           "Removes features"], "b", "It discourages overly complex models.", "medium"),
    ],
}
for _skill, _items in BANK.items():
    for _it in _items:
        _it["skill"] = LABELS[_skill]


def _order_key(seed: str, qid: str) -> str:
    return hashlib.sha256(f"{seed}:{qid}".encode()).hexdigest()


def pick(skills: list[str], count: int, seed: str) -> tuple[list[dict], list[str]]:
    """Pick up to `count` questions spread across the given skills. Returns (questions, skills with no local questions)."""
    keys, unknown = [], []
    for s in skills:
        k = canonical(s)
        if k and k not in keys:
            keys.append(k)
        elif not k:
            unknown.append(s)
    if not keys:
        return [], unknown
    per_skill = {k: sorted(BANK[k], key=lambda q: _order_key(seed, q["bankId"])) for k in keys}
    chosen: list[dict] = []
    i = 0
    while len(chosen) < count and any(per_skill.values()):
        k = keys[i % len(keys)]
        if per_skill[k]:
            chosen.append(dict(per_skill[k].pop(0)))
        i += 1
    return chosen, unknown
