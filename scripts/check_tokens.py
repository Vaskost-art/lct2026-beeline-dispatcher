"""Проверка, что все переменные стилей объявлены.

Правило с `var(--нет-такой)` браузер отбрасывает целиком, а не откатывает к
запасному значению: цвет наследуется, ширина становится auto. Ни сборка, ни
линтер, ни проверка вёрстки этого не видят - в карте так три месяца жили
`--accent-text`, `--text` и `--muted`, которых в палитре нет.

Запуск: python scripts/check_tokens.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "frontend" / "src"

#: Переменные, которые задаются не в палитре, а на месте (инлайн-стилем или
#: библиотекой), и потому в объявлениях не встречаются.
EXTERNAL = {"--radix-popper-available-height"}

USED = re.compile(r"var\((--[a-z0-9-]+)")
DECLARED = re.compile(r"^\s*(--[a-z0-9-]+)\s*:", re.MULTILINE)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    declared: set[str] = set(EXTERNAL)
    used: dict[str, list[str]] = {}

    for path in sorted(ROOT.rglob("*.css")):
        text = path.read_text(encoding="utf-8")
        declared.update(DECLARED.findall(text))
        for name in USED.findall(text):
            used.setdefault(name, []).append(path.name)

    # Классы Tailwind тоже читают переменные темы, но объявляются они в том же
    # index.css, поэтому отдельного разбора разметки не нужно.
    missing = {name: files for name, files in used.items() if name not in declared}

    if not missing:
        print(f"чисто: {len(used)} переменных, все объявлены")
        return

    print("НЕ ОБЪЯВЛЕНЫ (правило с такой переменной отбрасывается целиком):")
    for name, files in sorted(missing.items()):
        print(f"  {name} — {', '.join(sorted(set(files)))}")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
