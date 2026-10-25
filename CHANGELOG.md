# Changelog

## 0.1.1 – unreleased

- "Learned pattern" now shows what is learned over all stations, also while no prices arrive (was 0 %).
- Recommendation state `unavailable` renamed to `no_prices` (the word is reserved for entity availability).
- Brand icon for HACS and the Home Assistant UI.
- Translations: French, Italian, Spanish, Dutch, Portuguese.
- Savings are now "Saving if you wait (per litre / full tank)", per litre in cents, and they – like the recommendation – show what they compare: price and station now vs. expected price, station and time.
- Forecast anchored on each station's 24 h median instead of the current hour only, and never more than 2 ct below the station's lowest price of the last 24 h. Fixes a live case where a late noon spike made the forecast drop 15 ct too low and recommend waiting.
- Recommendation no longer flips between wait and fill now while the saving hovers around the minimum: wait is kept until the saving drops below two thirds of the minimum.
- More examples: card "now vs. expected", forecast chart, notifications for "worth waiting", cheapest time and nearly empty tank.
- Price sensors keep their unit while the price source is down.
- Cleaner station names (no "None" house numbers, no double spaces).

## 0.1.0

- First version: learns a working day / weekend hourly price pattern per station
  from existing price sensors, 24 h forecast, recommendation (fill now / wait /
  no need), saving per litre and per fill-up, optional fuel level sensor.
- Imports up to 10 weeks of hourly long-term statistics on first setup.
- Plausibility filter against obviously wrong prices (for example 0 €).
