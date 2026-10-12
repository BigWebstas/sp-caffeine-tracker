#!/usr/bin/env python3
"""Build dist/caffeine-tracker-v<version>.zip under SP's 100 KiB ceiling.

Super Productivity rejects any *uncompressed* manifest.json, index.html or
icon over MAX_PLUGIN_MANIFEST_SIZE (100 KiB, per file, see plugin.const.ts),
so the zip must contain a minified index.html.
The repo source stays readable; only the packaged copy is minified.

Minification is whitespace-only outside of JS strings/template literals
and comments (tracked with a small tokenizer), so semantics can't change:
  - HTML/CSS: strip each line, drop blank lines.
  - JS: drop leading/trailing whitespace per line and blank lines,
    emitting JS strings, template literals and comments verbatim.

Usage: python3 build_dist.py
"""
import json
import re
import zipfile

SRC_FILES = ["icon.svg", "index.html", "manifest.json", "plugin.js", "README.md"]
SIZE_CEILING = 100 * 1024
CAPPED_FILES = ["icon.svg", "index.html", "manifest.json"]


def minify_html_css(segment):
    out = []
    for line in segment.split("\n"):
        s = line.strip()
        if s:
            out.append(s)
    return "\n".join(out)


def minify_css(css):
    """Whitespace-only, and only the kinds that can't change a rule: line breaks, and spaces around
    { } ; , and after a colon. CSS strings here are simple ('' and 'number'), with no spaces to damage."""
    css = re.sub(r"[ \t]*\n[ \t]*", "", css)
    css = re.sub(r"\s*([{};,])\s*", r"\1", css)
    return re.sub(r":\s+", ":", css)


def minify_js(js):
    out = []
    # stack frames: ('code', interp, braces) | ('sq',) | ('dq',) | ('tpl',) | ('lc',) | ('bc',)
    stack = [("code", False, 0)]
    pending_space = []
    line_has_content = True  # BOS counts as already-started (keeps doctype-adjacent logic simple)
    first_char = True

    def state():
        return stack[-1][0]

    i, n = 0, len(js)
    while i < n:
        c = js[i]
        nxt = js[i + 1] if i + 1 < n else ""
        st = state()

        if st == "code":
            if c == "/" and nxt == "/":
                stack.append(("lc",))
                out.append("//")
                i += 2
                line_has_content = True
                continue
            if c == "/" and nxt == "*":
                stack.append(("bc",))
                out.append("/*")
                i += 2
                line_has_content = True
                continue
            if c == "/" and nxt not in ("/", "*"):
                # regex literal vs division: a '/' starts a regex only after
                # these tokens (covers every regex site in this codebase,
                # which all follow '(' or '!'; divisions follow ')', names
                # or numbers).
                prev = next((ch for ch in reversed(out) if ch not in " \t\n"), "")
                if prev in "(,=:[!&|?{};":
                    j = i + 1
                    in_class = False
                    while j < n:
                        d = js[j]
                        if d == "\\":
                            j += 2
                            continue
                        if d == "[":
                            in_class = True
                        elif d == "]":
                            in_class = False
                        elif d == "/" and not in_class:
                            break
                        elif d == "\n":
                            break
                        j += 1
                    k = j + 1
                    while k < n and js[k] in "abcdefghijklmnopqrstuvwxyz":
                        k += 1
                    assert j < n and js[j] == "/", f"unterminated regex near line {js.count(chr(10), 0, i) + 1}"
                    out.append(js[i:k])
                    line_has_content = True
                    i = k
                    continue
            if c in ("'", '"', "`"):
                stack.append(({"'": "sq", '"': "dq", "`": "tpl"}[c],))
                out.append(c)
                line_has_content = True
                i += 1
                continue
            if c == "{":
                frame = stack[-1]
                if frame[1]:  # inside ${...}: track brace depth
                    stack[-1] = ("code", True, frame[2] + 1)
                else:
                    stack.append(("code", False, 0))
                out.append(c)
                line_has_content = True
                i += 1
                continue
            if c == "}":
                frame = stack[-1]
                if frame[1]:
                    if frame[2] == 0:
                        stack.pop()  # closes ${...}, back to tpl
                    else:
                        stack[-1] = ("code", True, frame[2] - 1)
                elif len(stack) > 1:
                    stack.pop()
                out.append(c)
                line_has_content = True
                i += 1
                continue
            if c in (" ", "\t"):
                pending_space.append(c)
                i += 1
                continue
            if c == "\n":
                pending_space = []
                if line_has_content:
                    out.append("\n")
                line_has_content = False
                i += 1
                continue
            if pending_space:
                if line_has_content:
                    out.extend(pending_space)
                pending_space = []
            out.append(c)
            line_has_content = True
            i += 1
        elif st == "lc":
            out.append(c)
            if c == "\n":
                stack.pop()
                line_has_content = False
            i += 1
        elif st == "bc":
            out.append(c)
            if c == "*" and nxt == "/":
                out.append("/")
                stack.pop()
                i += 2
            else:
                i += 1
        else:  # sq, dq, tpl: verbatim, honour escapes and ${...} nesting
            out.append(c)
            if c == "\\":
                if nxt:
                    out.append(nxt)
                    i += 1
            elif st == "sq" and c == "'":
                stack.pop()
            elif st == "dq" and c == '"':
                stack.pop()
            elif st == "tpl" and c == "`":
                stack.pop()
            elif st == "tpl" and c == "$" and nxt == "{":
                out.append("{")
                stack.append(("code", True, 0))
                i += 1
            i += 1

    result = "".join(out)
    assert stack == [("code", False, 0)], f"unbalanced tokenizer state: {stack}"
    return result


# The standard plugin and the SleepSense variant (a separate plugin that also logs nights from the
# SleepSense Android app over MQTT) come from the same index.html: the variant keeps the blocks
# between "@sleepsense-begin" and "@sleepsense-end" lines, the standard build drops them.
VARIANTS = [
    {"suffix": "", "sleepsense": False, "plugin_js": "plugin.js"},
    {
        "suffix": "-sleepsense",
        "sleepsense": True,
        "plugin_js": "plugin.sleepsense.js",
        "id": "caffeine-tracker-sleepsense",
        "name": "Caffeine Tracker + SleepSense",
        "description": " Also logs each rated night from the SleepSense Android app, received over MQTT.",
    },
]


def select_variant(html, sleepsense):
    out, skipping = [], False
    for line in html.split("\n"):
        if "@sleepsense-begin" in line:
            skipping = not sleepsense
        elif "@sleepsense-end" in line:
            skipping = False
        elif not skipping:
            out.append(line)
    return "\n".join(out)


def main():
    for variant in VARIANTS:
        build(variant)


def build(variant):
    html = select_variant(open("index.html").read(), variant["sleepsense"])
    assert html.count("<style>") == 1 and html.count("<script>") == 1
    head, rest = html.split("<style>")
    css, rest = rest.split("</style>", 1)
    mid, js_and_tail = rest.split("<script>", 1)
    js, tail = js_and_tail.split("</script>", 1)

    min_html = (
        minify_html_css(head)
        + "<style>"
        + minify_css(css)
        + "</style>"
        + minify_html_css(mid)
        + "<script>"
        + minify_js(js)
        + "</script>"
        + minify_html_css(tail)
    )
    print(f"index.html {len(html)} -> {len(min_html)} bytes")

    manifest = json.load(open("manifest.json"))
    version = manifest["version"]
    if "id" in variant:
        manifest.update(id=variant["id"], name=variant["name"], description=manifest["description"] + "." + variant["description"])
    zip_path = f"dist/caffeine-tracker{variant['suffix']}-v{version}.zip"
    payload = {
        "icon.svg": open("icon.svg").read(),
        "index.html": min_html,
        "manifest.json": json.dumps(manifest, indent=2) + "\n",
        "plugin.js": open(variant["plugin_js"]).read(),
        "README.md": open("README.md").read(),
    }
    for name in CAPPED_FILES:
        size = len(payload[name].encode("utf-8"))
        print(f"{name}: {size} bytes (ceiling {SIZE_CEILING})")
        assert size <= SIZE_CEILING, f"{name} is over the size ceiling!"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in payload.items():
            z.writestr(name, data)
    print(f"wrote {zip_path}")


if __name__ == "__main__":
    main()
