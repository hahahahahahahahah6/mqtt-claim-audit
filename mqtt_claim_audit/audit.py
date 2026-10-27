"""Offline AST and documentation analysis."""
import ast
import fnmatch
import re
from pathlib import Path

MQTT = ("support for mqtt", "mqtt subscriber", "mqtt publisher", "mqtt protocol", "mqtt broker", "mqtt client", "mqtt interface", "mqtt support", "mqtt enabled", "mqtt powered", "mqtt based", "mqtt publish", "mqtt subscribe", "supports mqtt", "uses mqtt", "using mqtt", "over mqtt", "via mqtt", "with mqtt")
NOMQTT = ("no mqtt support", "does not support mqtt", "does not use mqtt", "mqtt not supported", "without mqtt", "no mqtt client", "no mqtt")

def normalize(text):
    return re.sub(r"\s+", " ", text.lower().replace("n't", " not").replace("-", " "))

def pattern(phrases):
    return re.compile(r"\b(?:" + "|".join(re.escape(p) for p in sorted(phrases, key=len, reverse=True)) + r")\b")

def claims(text):
    lines = []
    fence = None
    for line in text.splitlines():
        match = re.match(r"^\s*(`{3,}|~{3,})", line)
        if match:
            mark = match.group(1)
            if fence is None:
                fence = mark
            elif mark[0] == fence[0] and len(mark) >= len(fence):
                fence = None
            lines.append("")
        elif fence is None:
            lines.append(line)
    yes = no = False
    for paragraph in re.split(r"\n\s*\n", "\n".join(lines)):
        text = normalize(paragraph)
        no = no or bool(pattern(NOMQTT).search(text))
        text = pattern(NOMQTT).sub(" ", text)
        yes = yes or bool(pattern(MQTT).search(text))
    return yes, no

def dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted(node.value)
        return base + "." + node.attr if base else None
    return None

def evidence(text):
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return False
    modules, constructors = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if "mqtt" in alias.name.split("."):
                    modules.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and "mqtt" in (node.module or "").split("."):
            for alias in node.names:
                if alias.name == "Client":
                    constructors.add(alias.asname or alias.name)
                else:
                    modules.add((alias.asname or alias.name))
    def creation(node):
        if not isinstance(node, ast.Call):
            return False
        func = node.func
        return (isinstance(func, ast.Name) and func.id in constructors or
                isinstance(func, ast.Attribute) and func.attr == "Client" and dotted(func.value) in modules)
    bindings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and creation(node.value):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            bindings.update(filter(None, (dotted(t) for t in targets)))
    return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
               and n.func.attr in ("publish", "subscribe")
               and (creation(n.func.value) or dotted(n.func.value) in bindings)
               for n in ast.walk(tree))

def audit(root, ignores=(), fail_on="HIGH"):
    root = Path(root)
    if not root.is_dir():
        raise ValueError("root must be a readable directory")
    if root.stat().st_mode & 0o444 == 0 or root.stat().st_mode & 0o111 == 0:
        raise ValueError("root must be a readable directory")
    positive = negative = False
    prod, tests = [], []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if path.is_symlink() or any((root.joinpath(*rel.parts[:i])).is_symlink() for i in range(1, len(rel.parts))):
            continue
        if not path.is_file() or any(fnmatch.fnmatch(rel.as_posix(), g) for g in ignores):
            continue
        if rel.as_posix() == "README.md" or ("docs" in rel.parts[:-1] and path.suffix.lower() == ".md"):
            yes, no = claims(path.read_text(encoding="utf-8"))
            positive |= yes
            negative |= no
        if path.suffix != ".py" or any(p in ("fixtures", "docs", "examples") for p in rel.parts[:-1]):
            continue
        test = "tests" in rel.parts[:-1] or path.name.startswith("test_") or path.name.endswith("_test.py")
        if evidence(path.read_text(encoding="utf-8")):
            (tests if test else prod).append(rel.as_posix())
    findings = []
    if positive and not prod:
        findings.append(dict(rule="documented-mqtt-claim-false", severity="MEDIUM" if tests else "HIGH", message="Documented transport capability lacks production creation and publish/subscribe evidence."))
    if negative and prod:
        findings.append(dict(rule="documented-no-mqtt-claim-false", severity="HIGH", message="Documented absence conflicts with production creation and publish/subscribe evidence."))
    failed = any(f["severity"] == "HIGH" or fail_on == "MEDIUM" for f in findings)
    return dict(verdict="FAIL" if failed else "PASS", findings=findings, claims=dict(positive=positive, negative=negative), evidence=prod, test_evidence=tests)
