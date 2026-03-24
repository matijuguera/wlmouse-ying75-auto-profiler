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

# Special param value that means "read" for CONFIG_ID
CONFIG_ID_READ = 4


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


def set_profile(profile_id: int) -> bytes:
    """Build a packet to switch the active profile (0-indexed)."""
    return cmd_pack(CMD_CONFIG_ID, profile_id)


def get_profile() -> bytes:
    """Build a packet to read the current active profile."""
    return cmd_pack(CMD_CONFIG_ID, CONFIG_ID_READ)
