from __future__ import annotations


def build_escpos_payload(title: str, unchecked_items: list[str]) -> bytes:
    payload = bytearray()

    payload.extend(b"\x1b\x61\x01")
    payload.extend(b"\x1b\x45\x01")
    payload.extend(b"\x1d\x21\x22")
    payload.extend(title.encode("utf-8", errors="replace"))
    payload.extend(b"\n")
    payload.extend(b"\x1b\x45\x00")
    payload.extend(b"\x1d\x21\x11")
    payload.extend(b"\x1b\x61\x00")
    payload.extend(b"\n")

    if unchecked_items:
        for item in unchecked_items:
            payload.extend(f"- {item}\n".encode("utf-8", errors="replace"))
    else:
        payload.extend(b"(empty)\n")

    return bytes(payload)


def build_escpos_output(title: str, unchecked_items: list[str]) -> list[int]:
    return list(build_escpos_payload(title, unchecked_items))