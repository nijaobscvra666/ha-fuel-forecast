# Changelog

## 0.1.1 – unreleased

- "Learned pattern" now shows what is learned over all stations, also while no prices arrive (was 0 %).
- Recommendation state `unavailable` renamed to `no_prices` (the word is reserved for entity availability).
- Brand icon for HACS and the Home Assistant UI.
- Translations: French, Italian, Spanish, Dutch, Portuguese.

## 0.1.0

- First version: learns a working day / weekend hourly price pattern per station
  from existing price sensors, 24 h forecast, recommendation (fill now / wait /
  no need), saving per litre and per fill-up, optional fuel level sensor.
- Imports up to 10 weeks of hourly long-term statistics on first setup.
- Plausibility filter against obviously wrong prices (for example 0 €).
