"""
Step 1: HID Device Scanner
Scans all connected HID devices and highlights WLMouse devices.
Requires: pip install hidapi
"""

import hid


def scan_devices():
    devices = hid.enumerate()

    if not devices:
        print("No HID devices found.")
        return

    wlmouse_devices = []
    all_devices = []

    for dev in devices:
        info = {
            "vendor_id": f"0x{dev['vendor_id']:04X}",
            "product_id": f"0x{dev['product_id']:04X}",
            "usage_page": f"0x{dev['usage_page']:04X}",
            "usage": f"0x{dev['usage']:04X}",
            "manufacturer": dev.get("manufacturer_string", "N/A") or "N/A",
            "product": dev.get("product_string", "N/A") or "N/A",
            "interface": dev.get("interface_number", -1),
            "path": dev.get("path", b"").decode("utf-8", errors="replace"),
        }
        all_devices.append(info)

        name = (info["manufacturer"] + " " + info["product"]).lower()
        if "wlmouse" in name or "wl mouse" in name:
            wlmouse_devices.append(info)

    # Print all devices
    print(f"{'='*80}")
    print(f" ALL HID DEVICES ({len(all_devices)} found)")
    print(f"{'='*80}")
    for i, dev in enumerate(all_devices):
        print(f"\n  [{i}] {dev['manufacturer']} - {dev['product']}")
        print(f"      VID: {dev['vendor_id']}  PID: {dev['product_id']}")
        print(f"      Usage Page: {dev['usage_page']}  Usage: {dev['usage']}")
        print(f"      Interface: {dev['interface']}")
        print(f"      Path: {dev['path'][:80]}")

    # Highlight WLMouse
    print(f"\n{'='*80}")
    if wlmouse_devices:
        print(f" WLMOUSE DEVICES ({len(wlmouse_devices)} found)")
        print(f"{'='*80}")
        for dev in wlmouse_devices:
            print(f"\n  >> {dev['manufacturer']} - {dev['product']}")
            print(f"     VID: {dev['vendor_id']}  PID: {dev['product_id']}")
            print(f"     Usage Page: {dev['usage_page']}  Usage: {dev['usage']}")
            print(f"     Interface: {dev['interface']}")
            print(f"     Path: {dev['path'][:80]}")

        print(f"\n  Copy these values to config.json for Step 3.")
    else:
        print(" NO WLMOUSE DEVICES DETECTED")
        print(f"{'='*80}")
        print("  Check the full list above and identify your device manually.")
        print("  Look for unusual vendor IDs or product names that match your keyboard.")
        print("  Tip: unplug the keyboard, run again, and compare the lists.")


if __name__ == "__main__":
    scan_devices()
