# Examples

All examples use an entry named **"Super E5"** (entity ids `sensor.super_e5_…`).
Replace `super_e5` with the prefix of your entry and `notify.notify` with your
notify action (for example `notify.mobile_app_<phone>`).

| File | What it does |
|---|---|
| [`card_now_vs_expected.yaml`](card_now_vs_expected.yaml) | Markdown card: recommendation, station and price now vs. expected station, price and time, saving per litre and per fill-up. No custom cards needed. |
| [`card_forecast_chart.yaml`](card_forecast_chart.yaml) | Chart of the last 12 h and the 24 h forecast (needs [apexcharts-card](https://github.com/RomRider/apexcharts-card)). |
| [`dashboard_card.yaml`](dashboard_card.yaml) | Simple entities card with the most useful sensors. |
| [`automation_good_window.yaml`](automation_good_window.yaml) | Notification when it is a good time to fill up. |
| [`automation_wait_notification.yaml`](automation_wait_notification.yaml) | Notification when waiting is worth it – how much, where and until when. |
| [`automation_cheapest_time_reminder.yaml`](automation_cheapest_time_reminder.yaml) | Reminder at the expected cheapest time (time trigger on the timestamp sensor). |
| [`automation_urgent.yaml`](automation_urgent.yaml) | Tank nearly empty: fill up now, with the cheapest station (needs a fuel level sensor). |

Automations: Settings → Automations → Create → ⋮ → Edit in YAML, paste.
Cards: Edit dashboard → Add card → Manual, paste.
