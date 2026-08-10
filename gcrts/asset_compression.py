"""Game-stream codec adapter, deliberately independent from TIM parsing."""
from __future__ import annotations

from dataclasses import dataclass

from gcrts.cdb_codec import decompress


@dataclass(frozen=True)
class StreamRecord:
    block: int
    offset: int
    consumed_size: int
    decoded: bytes


def decode_stream(source: bytes, offset: int = 0) -> StreamRecord:
    i = offset
    while i < len(source):
        control = source[i]
        i += 1
        if control == 0xFF:
            break
        if control < 0x80:
            i += control + 1
        elif control < 0xC0:
            i += 1
        elif control < 0xF0:
            i += 2
        else:
            raise ValueError(f"unsupported control byte 0x{control:02X} at {i-1:#x}")
        if i > len(source):
            raise ValueError("truncated compressed stream")
    else:
        raise ValueError("compressed stream has no terminator")
    encoded = source[offset:i]
    return StreamRecord(-1, offset, len(encoded), decompress(encoded))


def discover_streams(source: bytes, limit: int | None = None) -> list[StreamRecord]:
    records: list[StreamRecord] = []
    offset = 0
    while offset < len(source) and (limit is None or len(records) < limit):
        record = decode_stream(source, offset)
        records.append(StreamRecord(len(records), offset, record.consumed_size, record.decoded))
        offset += record.consumed_size
    return records


def encode_stream(data: bytes) -> bytes:
    """Deterministic greedy encoder for the confirmed codec."""
    out = bytearray()
    positions: dict[bytes, list[int]] = {}
    i = 0
    literal = bytearray()

    def flush() -> None:
        nonlocal literal
        while literal:
            chunk = literal[:128]
            del literal[: len(chunk)]
            out.append(len(chunk) - 1)
            out.extend(chunk)

    def index_range(start: int, end: int) -> None:
        for pos in range(start, end):
            if pos + 4 <= len(data):
                positions.setdefault(data[pos : pos + 4], []).append(pos)

    while i < len(data):
        best_len = best_type = best_arg = 0
        run = 1
        while run < 66 and i + run < len(data) and data[i + run] == data[i]:
            run += 1
        if run >= 3:
            best_len, best_type = run, 1

        if i + 4 <= len(data):
            delta = (data[i + 1] - data[i]) & 0xFF
            inc = 2
            if delta:
                while inc < 19 and i + inc < len(data) and data[i + inc] == ((data[i] + inc * delta) & 0xFF):
                    inc += 1
                if inc >= 4 and inc > best_len:
                    best_len, best_type, best_arg = inc, 2, delta
            for previous in reversed(positions.get(data[i : i + 4], [])):
                distance = i - previous
                if distance > 0xFFFF:
                    break
                match = 4
                while match < 35 and i + match < len(data) and data[previous + match] == data[i + match]:
                    match += 1
                if match > best_len:
                    best_len, best_type, best_arg = match, 3, distance
                    if match == 35:
                        break

        if best_len:
            flush()
            if best_type == 1:
                out.extend((best_len + 0x7D, data[i]))
            elif best_type == 2:
                out.extend((best_len + 0xDC, best_arg, data[i]))
            else:
                out.extend((best_len + 0xBC, best_arg >> 8, best_arg & 0xFF))
            index_range(i, i + best_len)
            i += best_len
        else:
            literal.append(data[i])
            index_range(i, i + 1)
            i += 1
            if len(literal) == 128:
                flush()
    flush()
    out.append(0xFF)
    return bytes(out)


def pad_to_exact_size(encoded: bytes, required_size: int) -> bytes:
    """Expand compressed tokens into equivalent literals to hit an exact size."""
    if len(encoded) > required_size:
        raise ValueError(f"encoded stream is {len(encoded)} bytes; limit is {required_size}")
    need = required_size - len(encoded)
    if not need:
        return encoded
    decoded = bytearray()
    tokens: list[tuple[bytes, int, int, int]] = []  # raw, out_start, out_len, growth
    i = 0
    while i < len(encoded):
        start, out_start, control = i, len(decoded), encoded[i]
        i += 1
        if control == 0xFF:
            tokens.append((encoded[start:i], out_start, 0, 0))
            break
        if control < 0x80:
            count = control + 1
            decoded.extend(encoded[i : i + count]); i += count
        elif control < 0xC0:
            count = control - 0x7D
            decoded.extend(bytes((encoded[i],)) * count); i += 1
        elif control < 0xE0:
            count = control - 0xBC
            distance = (encoded[i] << 8) | encoded[i + 1]; i += 2
            source = len(decoded) - distance
            for k in range(count): decoded.append(decoded[source + k])
        else:
            count = control - 0xDC
            delta, value = encoded[i], encoded[i + 1]; i += 2
            decoded.extend(((value + k * delta) & 0xFF) for k in range(count))
        raw = encoded[start:i]
        tokens.append((raw, out_start, count, count + 1 - len(raw)))

    # A literal run can be split into N equivalent literal runs, adding N-1
    # control bytes. A compressed token can first become a literal (``growth``)
    # and that literal can then be split too. Together these choices make exact
    # sizing possible without fake padding after the 0xFF terminator.
    ways: dict[int, tuple[tuple[int, int], ...]] = {0: ()}
    for index, (raw, _, out_len, growth) in enumerate(tokens):
        if not out_len:
            continue
        minimum = 1 if raw[0] < 0x80 else growth
        choices = range(minimum, growth + out_len) if raw[0] >= 0x80 else range(1, out_len)
        snapshot = list(ways.items())
        for total, selected in snapshot:
            for addition in choices:
                new_total = total + addition
                if new_total <= need and new_total not in ways:
                    ways[new_total] = selected + ((index, addition),)
        if need in ways:
            break
    if need not in ways:
        raise ValueError(f"cannot safely expand stream by exactly {need} bytes")

    selected = dict(ways[need])
    result = bytearray()
    for index, (raw, out_start, out_len, _) in enumerate(tokens):
        if index in selected:
            addition = selected[index]
            base_growth = 0 if raw[0] < 0x80 else out_len + 1 - len(raw)
            parts = addition - base_growth + 1
            payload = decoded[out_start : out_start + out_len]
            cursor = 0
            for part in range(parts):
                remaining_parts = parts - part
                take = (len(payload) - cursor + remaining_parts - 1) // remaining_parts
                result.append(take - 1)
                result.extend(payload[cursor : cursor + take])
                cursor += take
        else:
            result.extend(raw)
    if len(result) != required_size or decompress(result) != bytes(decoded):
        raise AssertionError("exact-size expansion changed decoded data")
    return bytes(result)
