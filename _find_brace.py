import json

with open("notebooks/metrics_report.ipynb", "r", encoding="utf-8") as f:
    content = f.read()

depth = 0
for i, ch in enumerate(content):
    if ch == "{":
        depth += 1
    elif ch == "}":
        depth -= 1
    if depth == 0 and i < len(content) - 10:
        # Check if file actually ends here
        rest = content[i+1:].strip()
        if not rest or rest == "\n":
            print(f"File properly ends at {i}")
            break
        # Check if rest is just whitespace/CJK
        only_ws = all(c in " \t\r\n" for c in rest[:50])
        if not only_ws:
            print(f"Depth=0 at pos {i} but file continues")
            print(f"Char: {repr(ch)}")
            print(f"Context prev: {repr(content[i-100:i])}")
            print(f"Context next: {repr(content[i+1:i+101])}")
            break
