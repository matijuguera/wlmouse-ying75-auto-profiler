"""
WLMouse WLKB YING 75 HID Protocol
Reverse-engineered from https://kb75.wlmouse.gg/ (index-B5Byzn-K.js)

Packet structure (64 bytes, reportId=0):
  [0] = 0x5C (header constant)
  [1] = payload_length (number of bytes from [4] onward)
  [2] = protocol_cmd (0x00=CMD, 0x01=SYNC, etc.)
  [3] = checksum
  [4..] = payload (command + params + 0xFF 0xFF terminator)

Checksum: 53 + buf[0] + buf[1] + buf[2] + buf[payload_length + 3]
(result truncated to uint8 when written to buf[3])
"""

HEADER = 0x5C

# Protocol command types (buf[2])
KB2_CMD = 0x00
KB2_CMD_SYNC = 0x01

# Command orders (buf[4]) — used with KB2_CMD
CMD_PROTOCOL_VERSION = 1
CMD_START_ADJUSTING = 12
CMD_SAVE_ADJUSTING = 13
CMD_QUERY_SYS_WIN = 33
CMD_QUERY_SYS_MAC = 34
CMD_QUERY_PRECISION = 37
CMD_QUERY_KEYBOARD_NAME = 38
CMD_CHANGE_SYS_WIN = 48
CMD_CHANGE_SYS_MAC = 49
CMD_TOP_DEAD_SWITCH = 52
CMD_RATE_OF_RETURN = 80
CMD_CONFIG_ID = 112  # Profile ID — read with param=4, write with param=profile_id
CMD_AXIS_LIST = 118

# Brightness lookup table (found in firmware App V1.0.2, not used by the hub).
# CMD 0x40..0x43 read/write the PWM value for luminance levels 1..4.
# param=0xFF reads; any other value writes it (RAM only — reverts on power cycle).
# Each LED channel is computed as (color * value) >> 8, so 255 ≈ 100%.
CMD_BRIGHTNESS_LEVEL1 = 0x40
BRIGHTNESS_READ = 0xFF
BRIGHTNESS_MAX_VALUE = 0xFE  # 0xFF is reserved for "read"
STOCK_BRIGHTNESS_TABLE = (30, 50, 80, 120)  # levels 1..4, 120/256 ≈ 47%

# Special param value that means "read" for CONFIG_ID
CONFIG_ID_READ = 4

# Protocol command types for lighting (buf[2])
KB2_CMD_PRGB = 24
KB2_CMD_LOGORGB = 25

# Default colors used by the hub when querying (7 slots)
DEFAULT_COLORS = [
    "#FF0000", "#FFFF00", "#00FF00", "#00FFFF",
    "#0000FF", "#FF00FF", "#FFFFFF",
]


def _checksum(buf: bytearray) -> int:
    """Compute the WLMouse protocol checksum."""
    t = 53
    payload_len = buf[1]
    t += buf[0]  # header
    t += payload_len
    t += buf[2]  # cmd type
    if 0 < payload_len <= 63 * 4:
        t += buf[payload_len + 3]  # last byte of payload region
    return t & 0xFF


def cmd_pack(command: int, param: int | None = None) -> bytes:
    """Build a CMDPack — general command packet."""
    buf = bytearray(64)
    idx = 4
    buf[0] = HEADER
    buf[2] = KB2_CMD
    buf[idx] = command
    idx += 1
    if param is not None:
        buf[idx] = param & 0xFF
        idx += 1
    buf[idx] = 0xFF
    idx += 1
    buf[idx] = 0xFF
    idx += 1
    buf[1] = idx - 4  # payload length
    buf[3] = _checksum(buf)
    return bytes(buf)


def sync_pack() -> bytes:
    """Build a SYNCPack — synchronization/handshake packet."""
    buf = bytearray(64)
    idx = 4
    buf[0] = HEADER
    buf[2] = KB2_CMD_SYNC
    buf[idx] = 1; idx += 1
    buf[idx] = 2; idx += 1
    buf[idx] = 3; idx += 1
    buf[idx] = 4; idx += 1
    buf[idx] = 0xFF; idx += 1
    buf[idx] = 0xFF; idx += 1
    buf[1] = idx - 4
    buf[3] = _checksum(buf)
    return bytes(buf)


def prgb_pack(
    mode: int,
    colors: list[str],
    switch: bool,
    direction: bool,
    super_response: bool,
    luminance: int,
    light_mode: int,
    speed: int,
    sleep_delay: int,
    static_mode: int = 0,
) -> bytes:
    """Build a PRGBPack — keyboard RGB lighting settings.

    mode: 0=read (query current), 1=write (apply changes).
    colors: list of 7 hex color strings like '#RRGGBB'.
    luminance: brightness level (hub uses 0-4, firmware byte allows 0-255).
    """
    buf = bytearray(64)
    d = 4
    buf[0] = HEADER
    buf[2] = KB2_CMD_PRGB

    buf[d] = mode; d += 1
    # 4 reserved bytes
    for _ in range(4):
        buf[d] = 0; d += 1
    # 7 colors × 4 bytes (B, G, R, 0xFF)
    for c in colors[:7]:
        c = c.lstrip("#")
        buf[d] = int(c[4:6], 16); d += 1   # B
        buf[d] = int(c[2:4], 16); d += 1   # G
        buf[d] = int(c[0:2], 16); d += 1   # R
        buf[d] = 0xFF;            d += 1
    # 4 padding bytes
    for _ in range(4):
        buf[d] = 0; d += 1
    # bitmap
    bitmap = 0
    if switch:         bitmap |= 1
    if direction:      bitmap |= 2
    if super_response: bitmap |= 16
    buf[d] = bitmap; d += 1
    buf[d] = luminance & 0xFF; d += 1
    buf[d] = light_mode & 0xFF; d += 1
    buf[d] = speed & 0xFF; d += 1
    buf[d] = sleep_delay & 0xFF; d += 1
    buf[d] = static_mode & 0xFF; d += 1

    buf[1] = d - 4
    buf[3] = _checksum(buf)
    return bytes(buf)


def parse_prgb_response(data: bytes | list[int]) -> dict | None:
    """Parse a KB2_CMD_PRGB response (data = full 64-byte HID report).

    Returns dict with current lighting state, or None if not a PRGB response.
    """
    if len(data) < 43 or data[2] != (KB2_CMD_PRGB + 128):
        return None

    # Payload starts at data[4]; JS uses r = buffer.slice(4)
    r = data[4:] if isinstance(data, (bytes, bytearray)) else data[4:]

    colors = []
    y = 5  # r[5] is first color byte → data[9]
    for _ in range(7):
        b_val, g_val, r_val = r[y], r[y + 1], r[y + 2]
        y += 4
        colors.append(f"#{r_val:02x}{g_val:02x}{b_val:02x}")

    bitmap = r[37]
    return {
        "colors": colors,
        "switch": bool(bitmap & 1),
        "direction": bool(bitmap & 2),
        "super_response": bool(bitmap & 16),
        "luminance": r[38],
        "light_mode": r[39],
        "speed": r[40],
        "sleep_delay": r[41],
        "static_mode": r[42],
    }


def prgb_read(colors: list[str] | None = None) -> bytes:
    """Build a PRGBPack in read mode (query current lighting state)."""
    if colors is None:
        colors = DEFAULT_COLORS
    return prgb_pack(0, colors, False, False, False, 0, 0, 0, 0)


def set_profile(profile_id: int) -> bytes:
    """Build a packet to switch the active profile (0-indexed)."""
    return cmd_pack(CMD_CONFIG_ID, profile_id)


def get_profile() -> bytes:
    """Build a packet to read the current active profile."""
    return cmd_pack(CMD_CONFIG_ID, CONFIG_ID_READ)


def parse_cmd_response(data: bytes | list[int], command: int) -> int | None:
    """Parse a CMD response: [0x5C, len, 0x80, chk, 0x00, command, value, 0xFF]."""
    if len(data) < 7 or data[0] != HEADER or data[2] != 0x80 or data[5] != command:
        return None
    return data[6]


def brightness_level_cmd(level: int, value: int = BRIGHTNESS_READ) -> bytes:
    """Read (default) or write the PWM value (0-254) for luminance level 1-4."""
    if not 1 <= level <= 4:
        raise ValueError("level must be 1-4")
    if value != BRIGHTNESS_READ:
        value = max(0, min(value, BRIGHTNESS_MAX_VALUE))
    return cmd_pack(CMD_BRIGHTNESS_LEVEL1 + level - 1, value)


def scaled_brightness_table(max_value: int) -> list[int]:
    """Stock curve for levels 1-4 rescaled so level 4 equals max_value."""
    max_value = max(1, min(max_value, BRIGHTNESS_MAX_VALUE))
    top = STOCK_BRIGHTNESS_TABLE[-1]
    return [max(1, round(v * max_value / top)) for v in STOCK_BRIGHTNESS_TABLE]
