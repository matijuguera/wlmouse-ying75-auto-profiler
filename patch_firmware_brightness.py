"""
Patch the YING 75 firmware (App V1.0.2) brightness table so it persists without the profiler.

The firmware maps luminance levels 0-4 to PWM values via a 5-byte table in an
uncompressed .data init section (copied to RAM 0x8DBA8 at boot). Each LED channel
is computed as (color * value) >> 8, and the stock level 4 is 120 (~47%).

Header: payload starts at 0x5C, CRC32 of payload stored at 0x1C.

Usage: python patch_firmware_brightness.py <in.bin> <out.bin> [max_value 120-255]
"""

import struct
import sys
import zlib

TABLE_OFFSET = 0x10C7A  # level 0..4 values, flash 0x80030C7A
STOCK_TABLE = bytes([0, 30, 50, 80, 120])
PAYLOAD_OFFSET = 0x5C
CRC_OFFSET = 0x1C


def patch(data: bytes, max_value: int) -> bytes:
    if data[4:8] != b"\x5A\x5A\xA5\xA5":
        raise ValueError("Not a YING 75 firmware image (bad magic)")
    if struct.unpack_from("<I", data, CRC_OFFSET)[0] != zlib.crc32(data[PAYLOAD_OFFSET:]):
        raise ValueError("Input CRC mismatch — file corrupt or already modified")
    if data[TABLE_OFFSET:TABLE_OFFSET + 5] != STOCK_TABLE:
        raise ValueError("Brightness table not found — different firmware version?")

    table = [0] + [max(1, min(255, round(v * max_value / 120))) for v in STOCK_TABLE[1:]]
    out = bytearray(data)
    out[TABLE_OFFSET:TABLE_OFFSET + 5] = bytes(table)
    struct.pack_into("<I", out, CRC_OFFSET, zlib.crc32(out[PAYLOAD_OFFSET:]))
    print(f"Brightness table: {list(STOCK_TABLE)} -> {table}")
    return bytes(out)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    max_value = int(sys.argv[3]) if len(sys.argv) > 3 else 255
    if not 120 <= max_value <= 255:
        sys.exit("max_value must be 120-255")
    with open(sys.argv[1], "rb") as f:
        result = patch(f.read(), max_value)
    with open(sys.argv[2], "wb") as f:
        f.write(result)
    print(f"Wrote {sys.argv[2]}")
