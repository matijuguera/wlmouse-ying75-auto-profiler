/**
 * Step 2: WebHID Interceptor v3 — Prototype-level patching
 *
 * Patches HIDDevice.prototype directly so ALL device instances are
 * intercepted, regardless of how/when they were obtained.
 *
 * Usage:
 *   1. Open the WLMouse web config page
 *   2. Open DevTools (F12) -> Console
 *   3. Paste this script and press Enter
 *   4. Now connect/use the device normally
 *   5. Change profiles and watch the console for captured packets
 *   6. Run: window.__HID_CLEAR()  to reset before capturing
 *   7. Change profiles again
 *   8. Run: copy(JSON.stringify(window.__HID_LOG, null, 2))
 */

(() => {
  "use strict";

  window.__HID_LOG = [];
  let _counter = 0;

  const formatBytes = (data) => {
    const arr = data instanceof DataView
      ? new Uint8Array(data.buffer, data.byteOffset, data.byteLength)
      : data instanceof ArrayBuffer
        ? new Uint8Array(data)
        : new Uint8Array(data);
    const hex = Array.from(arr).map(b => b.toString(16).padStart(2, "0")).join(" ");
    const dec = Array.from(arr).join(", ");
    return { hex, dec, raw: Array.from(arr), length: arr.length };
  };

  const ts = () => new Date().toISOString();

  const addEntry = (entry) => {
    entry.seq = _counter++;
    window.__HID_LOG.push(entry);

    const colors = {
      SEND: "color:#ff6b6b;font-weight:bold",
      RECV: "color:#69db7c;font-weight:bold",
      SEND_FEAT: "color:#ffa94d;font-weight:bold",
      RECV_FEAT: "color:#74c0fc;font-weight:bold",
      OPEN: "color:#b197fc;font-weight:bold",
      CLOSE: "color:#b197fc;font-weight:bold",
    };

    if (entry.bytes) {
      console.log(
        `%c[HID #${entry.seq} ${entry.dir}] reportId=${entry.reportId} | ${entry.bytes.hex}`,
        colors[entry.dir] || ""
      );
    } else {
      console.log(`%c[HID #${entry.seq} ${entry.dir}]`, colors[entry.dir] || "", entry);
    }
  };

  // === Patch HIDDevice.prototype.sendReport ===
  const _origSendReport = HIDDevice.prototype.sendReport;
  HIDDevice.prototype.sendReport = async function (reportId, data) {
    const bytes = formatBytes(data);
    addEntry({
      dir: "SEND", reportId, bytes, ts: ts(),
      device: `${this.productName} [${this.vendorId.toString(16)}:${this.productId.toString(16)}]`
    });
    return _origSendReport.call(this, reportId, data);
  };

  // === Patch HIDDevice.prototype.sendFeatureReport ===
  const _origSendFeature = HIDDevice.prototype.sendFeatureReport;
  HIDDevice.prototype.sendFeatureReport = async function (reportId, data) {
    const bytes = formatBytes(data);
    addEntry({
      dir: "SEND_FEAT", reportId, bytes, ts: ts(),
      device: `${this.productName} [${this.vendorId.toString(16)}:${this.productId.toString(16)}]`
    });
    return _origSendFeature.call(this, reportId, data);
  };

  // === Patch HIDDevice.prototype.receiveFeatureReport ===
  const _origRecvFeature = HIDDevice.prototype.receiveFeatureReport;
  HIDDevice.prototype.receiveFeatureReport = async function (reportId) {
    const result = await _origRecvFeature.call(this, reportId);
    const bytes = formatBytes(result);
    addEntry({
      dir: "RECV_FEAT", reportId, bytes, ts: ts(),
      device: `${this.productName} [${this.vendorId.toString(16)}:${this.productId.toString(16)}]`
    });
    return result;
  };

  // === Patch HIDDevice.prototype.open ===
  const _origOpen = HIDDevice.prototype.open;
  HIDDevice.prototype.open = async function () {
    addEntry({
      dir: "OPEN", ts: ts(),
      device: `${this.productName} [${this.vendorId.toString(16)}:${this.productId.toString(16)}]`
    });
    return _origOpen.call(this);
  };

  // === Patch HIDDevice.prototype.close ===
  const _origClose = HIDDevice.prototype.close;
  HIDDevice.prototype.close = async function () {
    addEntry({
      dir: "CLOSE", ts: ts(),
      device: `${this.productName} [${this.vendorId.toString(16)}:${this.productId.toString(16)}]`
    });
    return _origClose.call(this);
  };

  // === Helpers ===
  window.__HID_CLEAR = () => { window.__HID_LOG = []; _counter = 0; console.log("HID log cleared"); };
  window.__HID_EXPORT = () => {
    const j = JSON.stringify(window.__HID_LOG, null, 2);
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([j], { type: "application/json" }));
    a.download = `hid_capture_${Date.now()}.json`;
    a.click();
    console.log(`Exported ${window.__HID_LOG.length} entries`);
  };
  // Filter helper: show only SEND entries
  window.__HID_SENDS = () => window.__HID_LOG.filter(e => e.dir === "SEND" || e.dir === "SEND_FEAT");

  console.log("%c[HID Interceptor v3] Ready! Prototype-level patching active.", "color:#69db7c;font-weight:bold;font-size:14px");
  console.log("Commands:");
  console.log("  window.__HID_CLEAR()     — clear log");
  console.log("  window.__HID_SENDS()     — show only sent packets");
  console.log("  window.__HID_EXPORT()    — download JSON");
  console.log("  copy(JSON.stringify(window.__HID_SENDS(), null, 2))  — copy only sends");
})();
