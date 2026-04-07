from __future__ import annotations

from src.grocery_item_grouper import GrocerySection
from src.daily_fun import DailyFunSection


def build_shopping_list_escpos_payload(
    title: str,
    subtitle: str,
    unchecked_items: list[str],
    grouped_sections: list[GrocerySection] | None = None,
) -> bytes:
    
    # log that we are building bytes
    print(f"Building ESC/POS payload for title: {title}")
    payload = bytearray()

    payload.extend(b"\x1b\x61\x01") # center align
    payload.extend(b"\x1b\x45\x01") # bold on for title
    payload.extend(b"\x1d\x21\x22") # double size font for title
    payload.extend(title.encode("utf-8", errors="replace"))
    payload.extend(b"\n")
    payload.extend(b"\x1b\x45\x00") # reset bold/underline for subtitle
    payload.extend(b"\x1d\x21\x11") # medium font size for subtitle
    payload.extend(subtitle.encode("utf-8", errors="replace"))
    payload.extend(b"\n")
    payload.extend(b"\x1b\x61\x00") # left align for items
    payload.extend(b"\n")

    if grouped_sections:
        for index, section in enumerate(grouped_sections):
            payload.extend(b"\x1b\x45\x01") # bold on for section title
            payload.extend(b"\x1d\x21\x11") # medium font size for section title
            payload.extend(f"{section.title}\n".encode("utf-8", errors="replace"))
            payload.extend(b"\x1b\x45\x00") # reset bold/underline before items
            payload.extend(b"\x1d\x21\x00") # reset font size before items

            for item in section.items:
                payload.extend(f"- {item}\n".encode("utf-8", errors="replace"))

            if index < len(grouped_sections) - 1:
                payload.extend(b"\n")
    elif unchecked_items:
        for item in unchecked_items:
            payload.extend(f"- {item}\n".encode("utf-8", errors="replace"))
    else:
        payload.extend(b"(empty)\n")

    return bytes(payload)


# def build_escpos_output(title: str, subtitle: str, unchecked_items: list[str]) -> list[int]:
#     return list(build_shopping_list_escpos_payload(title, subtitle, unchecked_items))

def build_daily_fun_escpos_payload( 
    title: str,
    subtitle: str,
    items: list[DailyFunSection],) -> bytes:
    
    # log what we are doing
    print(f"Building ESC/POS payload for daily fun message")

    payload = bytearray()
    payload.extend(b"\x1b\x61\x01") # center align
    payload.extend(b"\x1b\x45\x01") # bold on
    payload.extend(b"\x1d\x21\x22") # double size font
    payload.extend(title.encode("utf-8", errors="replace"))
    payload.extend(b"\n")
    payload.extend(b"\x1b\x45\x00") # reset bold/underline for subtitle
    payload.extend(b"\x1d\x21\x11") # medium font size for subtitle
    payload.extend(subtitle.encode("utf-8", errors="replace"))
    payload.extend(b"\n")
    payload.extend(b"\x1b\x61\x00") # left align for items
    payload.extend(b"\x1d\x21\x00") # reset font size before items
    payload.extend(b"\n")

    def wrap_text(text: str, width: int) -> list[str]:
        words = text.split()
        lines = []
        current = ""
        for word in words:
            if len(current) + len(word) + (1 if current else 0) <= width:
                current = f"{current} {word}".strip()
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines

    for item in items:
        payload.extend(b"\x1d\x21\x11") # medium font size for section title
        payload.extend(f"{item.section}\n".encode("utf-8", errors="replace"))
        payload.extend(b"\x1d\x21\x00") # reset font size before items
        for line in wrap_text(item.content, 48):
            payload.extend(f"{line}\n".encode("utf-8", errors="replace"))
        payload.extend(b"\n")
    return bytes(payload)