/* ============================================================
   sensor.js — Sensor communicatie StressChecker®
   Ondersteunt: WebHID (USB Kyto) + Web Bluetooth (Heart Rate Service)
   ============================================================ */

const Sensor = (() => {

  let _type      = null;   // 'bluetooth' | 'usb'
  let _device    = null;
  let _onBeat    = null;   // callback(rrMs)
  let _onConnect = null;
  let _onError   = null;
  let _lastBTTimestamp = 0;

  // ── Bluetooth ──────────────────────────────────────────────

  async function connectBluetooth(onBeat, onConnect, onError) {
    _onBeat = onBeat; _onConnect = onConnect; _onError = onError;
    try {
      _device = window._btDev || await navigator.bluetooth.requestDevice({
        acceptAllDevices: true,
        optionalServices: [0x180D]
      });
      const server  = await _device.gatt.connect();
      const service = await server.getPrimaryService(0x180D);
      const char    = await service.getCharacteristic(0x2A37);
      await char.startNotifications();
      char.addEventListener('characteristicvaluechanged', _handleBTData);
      _device.addEventListener('gattserverdisconnected', () => {
        if (_onError) _onError('Bluetooth verbinding verbroken');
      });
      _type = 'bluetooth';
      if (_onConnect) _onConnect('bluetooth', _device.name || 'Bluetooth sensor');
    } catch (err) {
      if (_onError) _onError(err.name + ': ' + err.message + ' (' + err.constructor.name + ')');
    }
  }

  function _handleBTData(event) {
    const data  = event.target.value;
    const flags = data.getUint8(0);
    const rrOffset = (flags & 0x01) ? 3 : 2; // 16-bit HR = offset 3, 8-bit = offset 2
    const rrCount  = Math.floor((data.byteLength - rrOffset) / 2);
    for (let i = 0; i < rrCount; i++) {
      const rr1024 = data.getUint16(rrOffset + i * 2, true);
      const rrMs   = Math.round(rr1024 * 1000 / 1024);
      if (rrMs > 300 && rrMs < 2000 && _onBeat) _onBeat(rrMs);
    }
  }

  // ── USB (WebHID Kyto sensor) ───────────────────────────────

  async function connectUSB(onBeat, onConnect, onError) {
    _onBeat = onBeat; _onConnect = onConnect; _onError = onError;
    try {
      const devices = await navigator.hid.requestDevice({
        filters: [{ vendorId: 0x0B9C, productId: 0x0315 }] // Lifestyle Monitors USB sensor
      });
      if (!devices || devices.length === 0) {
        if (_onError) _onError('Geen USB sensor gevonden'); return;
      }
      _device = devices[0];
      if (!_device.opened) await _device.open();
      _device.addEventListener('inputreport', _handleUSBData);
      _type = 'usb';
      if (_onConnect) _onConnect('usb', _device.productName || 'USB sensor');
    } catch (err) {
      if (_onError) _onError(err.message || 'USB fout');
    }
  }

  let _usbRRBuffer = [];
  let _usbLastTime = 0;

  function _handleUSBData(event) {
    const data = new DataView(event.data.buffer);
    // Kyto protocol: byte 0 = type, bytes 1-2 = RR interval in ms
    if (event.reportId === 1 || data.byteLength >= 3) {
      try {
        const rrMs = data.getUint16(3, true); // little-endian bytes 3-4
        if (rrMs > 300 && rrMs < 2000 && _onBeat) _onBeat(rrMs);
      } catch (e) { /* ongeldige data, negeer */ }
    }
  }

  // ── Demo modus ─────────────────────────────────────────────

  let _demoInterval = null;
  let _demoBaseRR   = 800;

  function startDemo(onBeat, onConnect) {
    _onBeat = onBeat;
    _onConnect = onConnect;
    _type   = 'demo';
    _demoBaseRR = 750 + Math.random() * 100;
    if (_onConnect) onConnect('demo', 'Demo sensor');
    _demoInterval = setInterval(() => {
      // Realistische HRV simulatie
      const variation = (Math.random() - 0.5) * 30;
      const trend     = Math.sin(Date.now() / 8000) * 30;
      const rr = Math.round(Math.max(500, Math.min(1200, _demoBaseRR + variation + trend)));
      if (_onBeat) _onBeat(rr);
    }, _demoBaseRR * (0.9 + Math.random() * 0.2));
  }

  function stopDemo() {
    if (_demoInterval) { clearInterval(_demoInterval); _demoInterval = null; }
  }

  // ── Disconnect ─────────────────────────────────────────────

  function disconnect() {
    if (_type === 'demo') { stopDemo(); }
    if (_type === 'bluetooth' && _device?.gatt?.connected) {
      try { _device.gatt.disconnect(); } catch (e) {}
    }
    if (_type === 'usb' && _device) {
      _device.removeEventListener('inputreport', _handleUSBData);
      try { _device.close(); } catch (e) {}
    }
    _type = null; _device = null; _onBeat = null;
  }

  function isAvailable() {
    return {
      bluetooth: !!(navigator.bluetooth),
      usb:       !!(navigator.hid),
    };
  }

  return { connectBluetooth, connectUSB, startDemo, disconnect, stop: disconnect, isAvailable };
})();
