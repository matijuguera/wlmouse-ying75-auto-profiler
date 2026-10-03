# WLMouse YING 75 — Firmware Reverse Engineering

Deep analysis of the XS117 RISC-V firmware (`XS117_YING75_App_v1.0.2_20250423b.bin`).

## Chip Identification

| Field | Value |
|-------|-------|
| **MCU** | XS117 (no public documentation) |
| **Architecture** | RISC-V 32-bit with Compressed extensions (RVC) |
| **Flash** | 256 KB total, ~120 KB used |
| **RAM** | ~640 KB address space (SP init at 0xA0000) |
| **RTOS** | FreeRTOS (confirmed by `Tmr Svc`, task creation, osal layer) |
| **Firmware** | App V1.0.2, compiled Apr 23 2025 at 12:32:08 |
| **Protocol** | v1.0.7 |

## Memory Map

| Region | File Offset | Runtime Address | Description |
|--------|-------------|-----------------|-------------|
| Header | 0x00000–0x0005C | N/A | 92-byte custom firmware header |
| Boot code | 0x0005C–0x000CC | 0x8002005C | Reset vector, GP/SP init |
| Data tables | 0x00100–0x004D8 | 0x80020100 | Keyboard scancodes, keymap tables |
| Code + rodata | 0x005B4–0x10B50 | 0x800205B4 | RTOS kernel + application code |
| Debug strings | 0x07614–0x076F6 | 0x80027614 | Function labels (compiled out) |
| USB strings | 0x07BF8–0x08B40 | 0x80027BF8 | ANSI-colored USB debug strings |

### Key Registers

| Register | Value | Purpose |
|----------|-------|---------|
| GP | 0x0008D524 | Global pointer (SRAM base for globals) |
| TP | 0x0008DBF0 | Thread pointer |
| SP | 0x000A0000 | Initial stack pointer (top of RAM) |
| mtvec | 0x000007E0 | Machine trap vector (interrupt handler) |

### Firmware Header Format

```
Offset  Size  Value       Description
0x00    4     01 0D 03 01 Version/flags
0x04    4     5A 5A A5 A5 Magic bytes
0x08    4     00006750    Code section size (26,448 bytes)
0x0C    4     0001DFC4    Total firmware size (122,820 bytes)
0x10    8     ...         Board ID / metadata
0x18    4     14 D3 AD 2E Checksum
```

## RTOS Task Structure

The firmware runs 3 main FreeRTOS tasks:

| Task | String Ref | Description |
|------|------------|-------------|
| `task_KB` | 0x0AB8 | Keyboard scanning — reads Hall Effect sensors via ADC/DMA |
| `task_RGB` | 0x0ADC | LED control — handles all lighting modes |
| `hid_loop` | 0x8330 | USB HID report processing — receives/sends HID packets |

## HID Command Processing Pipeline

When a HID report arrives (like our `0x5C 0x04` profile switch), it flows through:

```
USB Interrupt
  └─> hid_loop_task (0x833A)
        └─> dequeue_report (0x884E)
              └─> event_processor (0x8952)
                    └─> RTOS event dispatch table [0x6CF8]
                          └─> hid_dispatch (0x8DD0)
                                ├─> type & 0x60 == 0x40 → vendor_handler (0x9752)
                                ├─> type & 0x60 == 0x20 → handler_0x20 (0x965C)
                                └─> type & 0x60 == 0x00 → sub-dispatch tables
```

### Vendor Command Handler (0x9752)

For our profile switch command (`0x5C`), since `0x5C & 0x60 == 0x40`, it routes to the vendor handler:

```c
vendor_handler(report):
    endpoint = calculate_endpoint(report, GP+0x6D4)
    cmd = (report[5] << 8) | report[4]

    if cmd == 4:  // GET descriptor
        return descriptor_data    // at 0x9802
    elif cmd == 5:  // GET indexed data
        return indexed_data       // at 0x9826
    else:
        // Iterate registered alternate handlers
        for handler in registered_handlers:
            handler->callback(report)   // indirect call via JALR
```

The actual profile switch logic is executed through **dynamically-registered callback function pointers** stored in SRAM structures. These are populated at runtime during USB enumeration.

## Dispatch Tables

| Table Offset | Entries | Description |
|---|---|---|
| 0x6C34 | 44 | USB endpoint + setup + class + HID class handlers |
| 0x6CF8 | 10 | RTOS event dispatch (event types 0–9) |
| 0x6D28 | 10 | HID command sub-dispatch (command types 0–9) |

## String Map (All Meaningful Strings)

### System Strings
```
0x0009C1: usb_osal_thread_create3
0x0009E9: flash_init
0x000A00: CONFIG_MODE: 0x%x
0x000A25: ============ APP ============
0x000A51: Board ID:%08x  Hardware Ver:%03x
0x000A8C: Apr 23 2025
0x000AB8: task_KB
0x000ADC: task_RGB
```

### Hardware Init
```
0x000BD1: adc initialization failed!
0x000BF9: dma error!
0x000C11: dma abort!
0x000C29: scan freq : %dkHz
0x000C45: dma setup channel failed 0
0x000C79: Write failed : addr=%x, size=%x
0x000CA5: Erase failed : addr=%x, size=%x
```

### Profile / Config Management
```
0x007614: driver_reload
0x007625: Factory Reset
0x007641: swtich to windows mode     (note: typo "swtich" in original)
0x007665: swtich to macos mode
0x007689: start calibration
0x0076A9: stop calibration
0x0076C8: set key send mode
0x0076DC: set config4
0x0076E8: switch config               ← PROFILE SWITCH
```

### LED / Logo
```
0x0077C8: logo_RGB1 through logo_RGB8
0x007828: logo_Bitmap
0x007834: logo_Mode
0x007840: logo_Speed
0x00784C: logo_Gray
0x007858: logo_Color
```

### USB / HID
```
0x007C08: string size overflow
0x007C20: descriptor <type:%x,index:%x> not found!
0x007C78: standard request error
0x007C90: class request error
0x007CA8: unknown vendor code
0x007D38: bus overflow
0x007DAC: usbd intr error!
0x007DC8: usbd transfer error!
0x008090: Parameter version number mismatch, using default parameters
0x00814C: kb_config_info_Addr is 0
0x008168: kb_default_magnetic_Addr is 0
0x008330: hid_loop
0x0083C8: Setup: bmRequestType 0x%02x, bRequest 0x%02x ...
0x0084A8: Unhandled HID Class bRequest 0x%02x
0x008B08: flag_usb_configured:%d
0x008B25: SOFT--RESET
```

### Product Identity
```
0x006634: App V1.0.2
0x006641: BL_CMD_REBOOT ...
0x006C14: WLKB YING 75
0x008B60: WLKB YING 75
```

## USB Reset on Profile Switch — Analysis

### The Problem

When switching profiles, the keyboard performs a full USB bus reset, causing a ~1-2 second disconnect/reconnect visible to the OS.

### Root Cause

The firmware calls `driver_reload` after a profile switch, which reinitializes the entire USB stack. This is likely done because:

1. The USB HID report descriptor may change between profiles (different key mappings)
2. The ADC/DMA configuration for Hall Effect scanning needs reinitialization for different actuation points
3. The polling rate may differ between profiles

### Can It Be Patched?

**Short answer: Not easily via static binary patching.**

The debug strings (`switch config`, `driver_reload`, `SOFT--RESET`) are **dead code** in this release build — they exist in .rodata but no LUI+ADDI instruction pair in the binary constructs their addresses. This means:

1. The debug `printf()` calls were compiled out (likely `#ifdef DEBUG`)
2. The actual reset logic executes through **hardware register writes** to the USB peripheral at `0xF4000000`–`0xF4128000`
3. The profile switch handler is a **dynamically-registered callback** (indirect JALR through function pointers in SRAM), making static analysis insufficient

### What Would Be Needed

To patch the USB reset out of profile switching:

1. **Runtime debugging** with JTAG/SWD to trace the actual execution path
2. **Identify the chip** — open the keyboard PCB and read the XS117 marking to find the datasheet
3. **Find the USB peripheral reset register** writes within the callback chain
4. **NOP out** the specific register writes that trigger the USB bus reset
5. **Verify** that profile data (keymaps, actuation points, LEDs) still loads correctly without the full USB stack reinit

### Risk Assessment

| Approach | Risk | Difficulty |
|----------|------|------------|
| NOP the USB reset registers | **High** — may cause USB stack corruption | Hard without datasheet |
| Replace full reset with descriptor reload | **Medium** — needs understanding of USB peripheral | Requires XS117 datasheet |
| Add a "fast switch" mode that only reloads keymaps | **Low** — but requires significant RE | Requires full firmware RE |
| Ask WLMouse to fix it | **None** | Just send an email :) |

## Update: Why Profile Switching Resets (solved)

`CMD 0x70` (RAM `0x12A8`) calls `switch_profile(p)` at RAM `0x10460`:

```c
old_tick = EP_TICK;                 // 0x8D695, polling rate index (CMD 0x50)
load_profile(p); load_params();     // keymaps, lighting, magnetic params
if (EP_TICK != old_tick) {          // only when the polling rate differs
    *(volatile u32*)0xF410001C = 0xA; // system reset -> USB re-enumeration
    for (;;);
}
```

Polling rate index: `0=8K 1=4K 2=2K 3=1K 4=500 5=250 6=125 Hz`. The reset is required because `bInterval` is only read by the host at enumeration, so patching it out would just leave the old rate active. **Fix: set the same polling rate on every profile.** Verified on hardware: profiles at 1K/2K/4K reset for ~1.2–1.4 s per switch; with all at 4K, five consecutive switches had zero USB disconnects.

## Update: Compressed Code & Brightness Unlock

### Boot init table and compressed app code

The earlier conclusion that strings like `switch config` are dead code was wrong. The reset code walks an init table at flash `0x800301B4` (file `0x101B4`, flash base `0x80020000` = file offset 0):

| Routine | Args | Effect |
|---|---|---|
| `0x8003DFF0` | dst, len | zero `.bss` |
| `0x8003E004` | dst, src, len | copy (`0x0`←`0x80030268`, `0x400`←`0x80030600`, `.data` → `0x8xxxx`) |
| `0x8003DF90` | dst, src | **LZ decompress** `0x80030CC1` → RAM `0x9EA` (0x1289A bytes) |

The decompressor format: control byte `c`; `0` = end, `c < 0x80` = copy `c` literal bytes, `c ≥ 0x80` = back-reference of `c-0x80` bytes with a 1- or 2-byte distance (2 bytes when the first has bit 7 set). The compressed stream exactly fills file `0x10CC1`–`0x1DF90`, so any patch to app code must recompress to ≤ the same size.

Almost all application logic (HID command switch, `task_RGB`, `task_KB`, profile handling) lives in that decompressed RAM image, which is why the flash-only disassembly found no references.

### Parameter table

A descriptor table at file `0x59B0` lists `{name, RAM address, default, flash offset}` for each saved setting. Relevant entries (GP = `0x8D524`):

| Name | RAM | Default |
|---|---|---|
| `Mode` | `0x8D68D` | 1 |
| `Speed` | `0x8D68E` | 3 |
| `Gray` (brightness level) | `0x8D68F` | 3 |
| `logo_Gray` | `0x8D6BF` | 3 |

### Brightness cap

- `get_pwm()` at RAM `0x1292E`: `if (Gray > 3) Gray = 4; return table[Gray];` — table at RAM `0x8DBA8`, initialised from file `0x10C7A` (uncompressed `.data`): `[0, 30, 50, 80, 120]`.
- The LED encoder at RAM `0xDB84` scales each channel as `(c * pwm) >> 8`, so level 4 = 120/256 ≈ **47%**.
- Level values > 4 are clamped to 4 (on load at `0x9736`, on Fn-key decrement at `0x120C4`, and in `get_pwm`).

### Undocumented runtime command

The CMD jump table at flash `0x800267DC` (orders 0x00–0xB2) routes orders `0x40`–`0x43` to RAM `0x10D6`:

```
param == 0xFF  -> respond with table[order - 0x3F]   (read)
otherwise      -> table[order - 0x3F] = param        (write, RAM only)
response: 5C 04 80 chk 00 <order> <value> FF
```

Verified on hardware: reads `[30, 50, 80, 120]`; writing 180 to `0x43` takes effect immediately and survives a profile switch, but not a power cycle.

Other orders in the same table: `0x01` protocol version, `0x0C/0x0D` calibration, `0x20–0x22`, `0x25–0x28` queries, `0x30/0x31` Win/Mac, `0x34` top dead switch, `0x50` rate of return, `0x70` config ID, `0x76` axis list, `0xB1/0xB2`.

### Persistent patch

`patch_firmware_brightness.py` rewrites the 4 table bytes at `0x10C7B` and the payload CRC32 at header `0x1C` (CRC32 of everything after `0x5C`). The header field at `0x08` (`0x6750`) is not a standard CRC of the payload and is left untouched.

## Tools Used

- **capstone** — RISC-V disassembler (Python bindings)
- **Python struct** — Binary parsing
- **Manual analysis** — String cross-referencing, call chain tracing

## Data Section Analysis

### Keymap Tables (0x00100–0x004D8)

The firmware stores HID keycodes for the 84-key layout starting at offset 0x00C8:

```
Row 0: ESC F1 F2 F3 F4 F5 F6 F7 F8 F9 F10 F11 F12 PrtSc Del PgUp
Row 1: ` 1 2 3 4 5 6 7 8 9 0 - = Bksp Home
...
```

### RGB Gamma Tables (0x5860–0x6630)

Large lookup tables for LED brightness gamma correction, organized as 32 tables of varying sizes for smooth brightness transitions.

## Conclusion

The XS117 is a custom RISC-V MCU with no public documentation. The firmware is well-structured with FreeRTOS, separate tasks for keyboard scanning, RGB, and USB HID processing. The profile switch mechanism uses dynamically-registered callbacks through the vendor USB command handler, making static patching difficult. The USB reset on profile switch is a firmware design decision that would require either WLMouse cooperation or JTAG-level runtime debugging to modify.
