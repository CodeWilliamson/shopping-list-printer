from __future__ import annotations

from src.grocery_grouping import GrocerySection


def build_escpos_payload(
    title: str,
    subtitle: str,
    unchecked_items: list[str],
    grouped_sections: list[GrocerySection] | None = None,
) -> bytes:
    
    # log that we are building bytes
    print(f"Building ESC/POS payload for title: {title}")
    payload = bytearray()

    payload.extend(b"\x1b\x61\x01")
    payload.extend(b"\x1b\x45\x01")
    payload.extend(b"\x1d\x21\x22")
    payload.extend(title.encode("utf-8", errors="replace"))
    payload.extend(b"\n")
    payload.extend(b"\x1b\x45\x00")
    payload.extend(b"\x1d\x21\x11")
    payload.extend(subtitle.encode("utf-8", errors="replace"))
    payload.extend(b"\n")
    payload.extend(b"\x1b\x61\x00")
    payload.extend(b"\n")

    if grouped_sections:
        for index, section in enumerate(grouped_sections):
            payload.extend(b"\x1b\x45\x01")
            payload.extend(b"\x1d\x21\x11")
            payload.extend(f"{section.title}\n".encode("utf-8", errors="replace"))
            payload.extend(b"\x1b\x45\x00")
            payload.extend(b"\x1d\x21\x00")

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


def build_escpos_output(title: str, subtitle: str, unchecked_items: list[str]) -> list[int]:
    return list(build_escpos_payload(title, subtitle, unchecked_items))