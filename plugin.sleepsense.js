(() => {
  const p = PluginAPI;
  const openView = () => p.showIndexHtmlAsView();

  // ---- SleepSense: each rated night arrives over MQTT (WebSockets) and lands in the sleep log ----
  // Lives here rather than in the view so it keeps listening while the view is closed.
  // The broker is the 'sleepsense' synced part ({url}, as ws://user:password@host:port), edited in the view's Settings.
  const TOPIC = 'sleepsense/last_night';
  let cfgJson = null;
  let socket = null;
  let retry = null;
  let ping = null;

  const dayKey = (ms) => {
    const d = new Date(ms);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  };
  const isNum = (v) => typeof v === 'number' && isFinite(v);

  // {start, end, minutes asleep, rating} from the phone. It is re-sent when the rating changes, so the
  // same night is updated in place instead of adding its minutes twice.
  async function importNight(n) {
    if (!n || !isNum(n.start) || !isNum(n.end) || !isNum(n.minutes) || !(n.rating >= 1 && n.rating <= 5)) return;
    const state = JSON.parse((await p.loadSyncedData()) || '{}');
    const entries = state.sleepEntries || [];
    const key = dayKey(n.end);
    const existing = entries.find((e) => e.dayKey === key);
    if (existing) {
      if (existing.night === n.start && existing.nightMin === n.minutes && existing.rating === n.rating) return;
      existing.durationMin += n.minutes - (existing.night === n.start ? existing.nightMin || 0 : 0);
      existing.rating = n.rating;
      existing.night = n.start;
      existing.nightMin = n.minutes;
      existing.time = Math.max(existing.time, n.end);
    } else {
      const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      entries.push({ id, dayKey: key, time: n.end, durationMin: n.minutes, rating: n.rating, night: n.start, nightMin: n.minutes });
      p.showSnack?.({ msg: `Logged last night's sleep (${Math.floor(n.minutes / 60)}h ${n.minutes % 60}m)`, type: 'SUCCESS' });
    }
    state.sleepEntries = entries;
    await p.persistDataSynced(JSON.stringify(state)); // the open view reloads on this
  }

  // Just enough MQTT 3.1.1 to connect and listen to one topic
  const str = (s) => {
    const b = new TextEncoder().encode(s);
    return [b.length >> 8, b.length & 255, ...b];
  };

  const packet = (first, body) => {
    const len = [];
    let n = body.length;
    do {
      const digit = n % 128;
      n = Math.floor(n / 128);
      len.push(n > 0 ? digit | 128 : digit);
    } while (n > 0);
    return new Uint8Array([first, ...len, ...body]);
  };

  function disconnect() {
    clearTimeout(retry);
    clearInterval(ping);
    if (socket) {
      socket.onclose = null;
      socket.close();
      socket = null;
    }
  }

  // After a settings change the first outcome is written to the 'sleepsense-status' part, tagged with
  // the saved settings' `t`, for the view's Settings to show.
  function connect(cfg, test) {
    disconnect();
    let timeout = null;
    const report = (ok, msg) => {
      if (!test) return;
      test = false;
      clearTimeout(timeout);
      p.persistDataSynced(JSON.stringify({ t: cfg.t, msg: `${ok ? '✅' : '❌'} ${msg}` }), 'sleepsense-status');
    };
    if (!cfg.url) return report(true, 'No broker set');
    let ws;
    let user = '';
    let pass = '';
    try {
      const u = new URL(cfg.url);
      user = decodeURIComponent(u.username);
      pass = decodeURIComponent(u.password);
      u.username = u.password = '';
      ws = new WebSocket(u.href, 'mqtt');
    } catch (e) {
      return report(false, `Bad URL (${e.message})`);
    }
    timeout = setTimeout(() => report(false, 'No answer from the broker (is the WebSocket listener on, and is it ws:// or wss://?)'), 6000);
    ws.binaryType = 'arraybuffer';
    socket = ws;
    let buf = [];
    ws.onopen = () => {
      const flags = 0x02 | (user ? 0x80 | (pass ? 0x40 : 0) : 0);
      const body = [...str('MQTT'), 4, flags, 0, 60, ...str(`caffeine-${Math.random().toString(36).slice(2, 10)}`)];
      if (user) body.push(...str(user));
      if (user && pass) body.push(...str(pass));
      ws.send(packet(0x10, body));
    };
    ws.onmessage = (ev) => {
      buf.push(...new Uint8Array(ev.data));
      while (buf.length >= 2) {
        let len = 0;
        let mult = 1;
        let i = 1;
        let digit;
        do {
          if (i >= buf.length) return; // the length itself is still arriving
          digit = buf[i++];
          len += (digit & 127) * mult;
          mult *= 128;
        } while (digit & 128);
        if (buf.length < i + len) return; // wait for the rest of the packet
        const type = buf[0] >> 4;
        const qos = (buf[0] >> 1) & 3;
        const body = buf.slice(i, i + len);
        buf = buf.slice(i + len);
        if (type === 2) {
          if (body[1] !== 0) {
            report(false, body[1] === 4 || body[1] === 5 ? 'Broker refused the user or password' : `Broker refused the connection (code ${body[1]})`);
            ws.onclose = null;
            ws.close();
            return;
          }
          report(true, 'Connected');
          ws.send(packet(0x82, [0, 1, ...str(TOPIC), 0]));
          ping = setInterval(() => ws.send(new Uint8Array([0xc0, 0])), 30000);
        } else if (type === 3) {
          const payload = body.slice(2 + ((body[0] << 8) | body[1]) + (qos ? 2 : 0));
          try {
            importNight(JSON.parse(new TextDecoder().decode(new Uint8Array(payload)))).catch((e) =>
              console.error('[Caffeine Tracker] could not log SleepSense night', e),
            );
          } catch (e) {
            console.error('[Caffeine Tracker] bad SleepSense message', e);
          }
        }
      }
    };
    ws.onclose = () => {
      report(false, 'Could not reach the broker (check the address, port and ws:// or wss://)');
      clearInterval(ping);
      retry = setTimeout(() => connect(cfg, false), 15000);
    };
  }

  async function applySettings() {
    const json = (await p.loadSyncedData('sleepsense')) || '{}';
    if (json === cfgJson) return;
    const test = cfgJson !== null; // not the first read at startup
    cfgJson = json;
    try {
      connect(JSON.parse(json), test);
    } catch (e) {
      console.error('[Caffeine Tracker] bad SleepSense settings', e);
    }
  }

  p.onReady(() => {
    p.registerHeaderButton?.({
      id: 'caffeine-tracker-header-btn',
      label: 'Caffeine',
      icon: 'coffee',
      onClick: openView,
    });
    applySettings();
    p.registerHook?.(p.Hooks.PERSISTED_DATA_CHANGED, applySettings);
  });
})();
