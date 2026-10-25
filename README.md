# Fuel Forecast

**Fill up now or wait?** Fuel Forecast learns when the fuel stations you use are usually cheapest and tells you whether it pays to wait – right inside Home Assistant.

[![hacs][hacs-badge]][hacs] [![Validate][validate-badge]][validate]

- Works with **any fuel price sensor** in Home Assistant: [Tankerkönig][tankerkoenig] (Germany) and price integrations for other countries alike. Fuel Forecast only reads sensors you already have – it never calls the price service itself, so it cannot get you rate-limited.
- **Learns locally.** No cloud, no AI service, no account.
- **Useful from day one** if Home Assistant already recorded prices: it imports up to 10 weeks of long-term statistics on setup.
- Optional **fuel level sensor** (for example from your car integration): no recommendation when the tank is full, "fill up now" when it is nearly empty.

## How it works

Fuel prices follow a daily rhythm: stations raise prices in the morning and lower them in the evening, and weekends differ from working days. Fuel Forecast learns, for every station, how far its price usually sits above or below its own recent median in each hour – separately for working days and weekends. Because it learns the *deviation* and not the absolute price, a general rise or fall of oil prices does not break the pattern.

From the current prices and the learned pattern it predicts the cheapest price over the next hours (24 h by default) and compares it with the best price right now.

Backtest on five weeks of real German prices (18 stations, three test windows of one to two weeks): whenever Fuel Forecast said *wait*, waiting saved **6.5–8.3 ct per litre on average**, and in **none of 134 cases** was waiting more expensive than filling up immediately. Your results depend on your region and stations.

## Installation

Requires Home Assistant 2025.1 or newer.

### HACS (recommended)

1. HACS → three-dot menu → *Custom repositories* → add `https://github.com/nijaobscvra666/ha-fuel-forecast`, category *Integration*.
2. Install **Fuel Forecast** and restart Home Assistant.

### Manual

Copy `custom_components/fuel_forecast` into your `config/custom_components/` folder and restart Home Assistant.

## Setup

*Settings → Devices & services → Add integration → Fuel Forecast*

| Option | Meaning |
|---|---|
| Name | For example "Super E5". Entity ids are built from it. |
| Price sensors | The stations you would actually drive to, all for **one** fuel type and in the same unit. |
| Minimum saving | Waiting is only recommended if the expected price is at least this much lower (default 3 ct/l). Once it says wait, it keeps saying so until the saving drops below two thirds of this (2 ct), so it does not flip back and forth around the threshold. |
| Look ahead | How many hours ahead to search for a cheaper moment (default 24). |
| Tank size | Optional, needed for the saving per fill-up (litres). |
| Fuel level sensor | Optional, a sensor in % (or litres together with the tank size). |
| No recommendation above / Fill up now below | Fuel level thresholds (defaults 60 % and 15 %). |

Create one entry per fuel type or per area (for example "E5 home" and "Diesel work").

## Entities

Entity ids below assume English as system language; Home Assistant builds them from the translated names.

| Entity | State | Attributes |
|---|---|---|
| `sensor.<name>_recommendation` | `fill_now`, `wait`, `no_need`, `learning` or `no_prices` (shown translated in the UI) | comparison (see below), `saving_per_litre`, `min_saving`, `urgent` |
| `binary_sensor.<name>_good_time_to_fill_up` | `on` while the recommendation is `fill_now` – handy for automations | `station`, `price_now`, `urgent` |
| `sensor.<name>_best_price_now` | Cheapest price right now | `station`, `entity_id` (of the price sensor) |
| `sensor.<name>_lowest_price` | Expected lowest price within the look-ahead | `station`, `entity_id`, `forecast` (hourly list of `time` and `price`, not stored in the history) |
| `sensor.<name>_cheapest_time` | When that lowest price is expected (now, if nothing cheaper is expected) | – |
| `sensor.<name>_saving_if_you_wait_per_litre` | What waiting for the expected low would save, in cents (ct/¢/p) per litre | comparison (see below) |
| `sensor.<name>_saving_if_you_wait_full_tank` | The same for a fill-up: the missing litres if a fuel level sensor is set, otherwise the full tank | comparison, `litres` |
| `sensor.<name>_learned_pattern` | Diagnostic: how much of the pattern is learned (%) | – |

**Which stations are compared is in the attributes, not in the state.** The state of a saving sensor is just the number (for example `0.7` ct); open the entity and expand *Attributes* to see what it compares, or use them in templates:

| Attribute | Meaning |
|---|---|
| `price_now`, `station_now` | Best price and station right now |
| `expected_price`, `expected_station`, `expected_time` | Expected lowest price, at which station and when |

So a saving of 0.7 ct reads as "fill up now at ELAN for 2.079 or wait until 07:00 for 2.072 at OIL". The [card example](examples/card_now_vs_expected.yaml) shows this on a dashboard without opening the attributes; in a template: `{{ state_attr('sensor.super_e5_recommendation', 'expected_station') }}`.

The recommendation stays `learning` until at least half of the hourly pattern is known – usually after about three days, immediately if long-term statistics exist.

See [`examples/`](examples) for dashboard cards (now vs. expected, forecast chart) and notification automations (good time, worth waiting, cheapest time reminder, tank nearly empty).

## Languages

The setup dialog and entity names are available in English, German, French, Italian, Spanish, Dutch and Portuguese. Translations other than English and German were written without a native speaker – corrections and new languages are very welcome as a pull request (`custom_components/fuel_forecast/translations/`).

## Privacy

Everything is computed inside your Home Assistant. Diagnostics downloads contain neither station names nor entity ids (stations are numbered, the fuel level sensor only shows whether one is set).

## Deutsch

**Jetzt tanken oder warten?** Fuel Forecast lernt aus deinen vorhandenen Spritpreis-Sensoren (z.B. Tankerkönig), wann deine Tankstellen meist am günstigsten sind – getrennt nach Werktag und Wochenende – und empfiehlt, ob sich Warten lohnt. Keine Cloud, keine zusätzlichen Abfragen beim Preisdienst (keine IP-Sperre), optional mit Tankstand vom Auto. Welche Tankstellen verglichen werden (jetzt vs. erwartet, mit Preis und Uhrzeit), steht in den **Attributen** der Empfehlung und der Ersparnis-Sensoren, nicht im Zustand – siehe *Entities* oben und die [Beispiele](examples). Einrichtung über *Einstellungen → Geräte & Dienste → Integration hinzufügen → Fuel Forecast*; die Oberfläche ist auf Deutsch übersetzt.

## License

MIT

[hacs]: https://hacs.xyz
[hacs-badge]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg
[validate]: https://github.com/nijaobscvra666/ha-fuel-forecast/actions/workflows/validate.yml
[validate-badge]: https://github.com/nijaobscvra666/ha-fuel-forecast/actions/workflows/validate.yml/badge.svg
[tankerkoenig]: https://www.home-assistant.io/integrations/tankerkoenig/
