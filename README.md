# Caffeine Tracker

A Super Productivity plugin that logs caffeine intake and simulates blood
caffeine level decay using a half-life model, and its effects on productivity throughout the day.

## Screenshots

<p>
  <img src="Images/desktop1.png" alt="Desktop view: gauge with Spent today and Daily avg, quick add, custom drink with cost, and sleep entry" width="100%" />
  <img src="Images/desktop2.png" alt="Desktop view: decay curve with task and habit burndown, cost and sleep in the legend, and today's log with drink cost and pinned sleep row" width="100%" />
</p>
<p>
  <img src="Images/mobile.png" alt="Mobile view: gauge with Spent today and Daily avg, quick add, and custom drink entry with cost" width="31%" />
  <img src="Images/mobile_settings.png" alt="Mobile view: Settings &amp; drinks overlay with drink costs and log drink for previous day" width="31%" />
  <img src="Images/mobile_reports.png" alt="Mobile view: Reports summary with sleep, mg, and cost per day" width="31%" />
</p>

## Features

- Gauge stats: left in cup, sip time left, metabolized, live "Spent today"
  cost, and Daily Avg (average caffeine per day across past days, first log
  through yesterday)
- Cost tracking: set a cost per drink in Manage drinks (or per custom entry);
  costs are calculated live from your drink settings, so changing a price
  updates all history. Shown in Today's log, the decay chart legend, the
  daily breakdown, and the report summary (total plus per-day average)
- Editing a drink's name, mg, or cost in Manage drinks recalculates every
  past entry of that drink
- Reporting with export to markdown includes mermaid charts to show graphing
  data, including a combined decay-curve chart (caffeine plus task/habit
  remaining-lines, scaled onto the same axis) over the same window as the
  on-screen chart, cost and average-sleep columns, and a Sleep log table
- Report summary (day/week/month/year) with caffeine, cost, and average sleep
  per period
- Quick-add buttons for common drinks (coffee, espresso, tea, energy drink,
  soda, pre-workout) plus a custom name/mg entry
- Live current caffeine level (mg), recomputed from every logged dose using
  `mg * 0.5^(hoursElapsed / halfLife)`
- Decay curve chart (past 4h to next 18h) with task burndown, habit tracking, today's sleep total, and today's metabolized mg vs caffeine in your system
- Caffeine impact reports: task completions by caffeine level and by hour,
  estimate accuracy, most-worked tag by caffeine level, and daily habit/time
  correlations
- Sleep tracking: log a duration (hrs/min) and a 0-5 star rating; entries
  logged the same day add up into one running daily total, shown with its
  date in the Sleep log (with per-entry removal), and shaded on the
  daily-breakdown decay panels; Settings has a "Log sleep for previous day"
  form (date + duration + rating) to backfill missed days
- Log a drink for a previous day: Settings has a "Log drink for previous day"
  form (date + time + saved drink) to backfill missed drinks
- Daily breakdown: a full 00:00–24:00 decay/task/habit panel per day, for a
  configurable number of past days (default 7), each labeled with that
  day's mg total, tasks completed/% scheduled, and habits completed/total
- Adjustable half-life (default 5h, the commonly cited average), threshold
  (default 50mg), daily-breakdown window, and the decay chart's hours-before/
  hours-after window (default 4h/18h)
- Today's log with per-entry removal, plus today's sleep pinned at the bottom
- Backup/restore in Settings: download all data as JSON, or restore from a
  backup file (validated, and confirmed before it replaces your data)
- Data synced via `persistDataSynced` / `loadSyncedData`, so history follows
  you across devices. Drinks (with costs) and habit marks sync under their own
  keys, so a background habit update or a stale device can't overwrite your
  drink settings (needs Super Productivity 18.8+)
- Update check on open: a 🔔 button appears next to Reports when a newer
  GitHub release exists, linking straight to it

## Install

1. Grab a release zip
2. In Super Productivity: **Settings → Plugins → Upload Plugin**
3. Open it from the ☕ header button

## Build

The release zip is minified to stay under Super Productivity's 100 KiB
per-file limit on the uncompressed `index.html`: `python3 build_dist.py`


## Notes

- The half-life model is a simplification for personal tracking, not medical
  advice — individual caffeine metabolism varies (genetics, pregnancy,
  medication, liver function).
- Caffeine entries and sleep log entries older than 400 days are pruned
  automatically on load.
- **Network access:** the only outbound call this plugin makes is a single
  read-only `GET` to `api.github.com/repos/BigWebstas/sp-caffeine-tracker/releases/latest`
  once per open, to check for a newer version. Nothing is sent besides the
  request itself — no telemetry, no data upload. This is what the `http`
  permission and `allowedHosts` entry in `manifest.json` are for.
- **Habit timing is approximate, not session-only:** Super Productivity's
  plugin API doesn't expose *when* a habit was checked off, only "what's true
  right now." The habit burndown line works around this by stamping each
  habit with the moment the plugin first sees it done that day, then
  persisting that stamp (it survives closing/reopening the plugin, syncs
  across devices, and rolls into a per-day history for the daily-breakdown
  panels) — so anything already done before you opened the plugin that day
  still lands at open-time rather than the real moment it happened. A day's
  habit line only exists from the day this feature shipped onward; there's no
  way to backfill days before that. Everything else (caffeine log, sleep log,
  tasks, estimate accuracy, hour-of-day, tag breakdown) uses real timestamps
  and isn't affected by this limitation.

## SleepSense variant

`python3 build_dist.py` builds two plugins that can be installed side by side:

- `dist/caffeine-tracker-v<version>.zip`: the standard plugin.
- `dist/caffeine-tracker-sleepsense-v<version>.zip`: "Caffeine Tracker + SleepSense", a separate plugin
  (its own id) that also logs each rated night from the SleepSense Android app. Settings has a broker
  WebSocket URL with the login in it (e.g. `ws://user:password@homeassistant.local:9001`; percent-encode
  special characters). It listens to the retained `sleepsense/last_night` topic, even while the view is
  closed, and logs the minutes asleep and stars into the Sleep log; a changed rating updates that night
  instead of adding it again. The broker needs a WebSocket listener, and the URL syncs with your other
  plugin data.

The variant's extra code is the `@sleepsense-begin`/`@sleepsense-end` blocks in `index.html` and
`plugin.sleepsense.js`; the standard build leaves them out. Install only one of the two, as both read and
write the same sleep log if they share data.
