# Changelog

## 0.1.1 – unreleased

- "Learned pattern" now shows what is learned over all stations, also while no prices arrive (was 0 %).
- Recommendation state `unavailable` renamed to `no_prices` (the word is reserved for entity availability).
- Brand icon for HACS and the Home Assistant UI.
- Translations: French, Italian, Spanish, Dutch, Portuguese.
- Savings are now "Saving if you wait (per litre / full tank)", per litre in cents, and they – like the recommendation – show what they compare: price and station now vs. expected price, station and time.
- Forecast anchored on each station's 24 h median instead of the current hour only, and never more than 2 ct below the station's lowest price of the last 24 h. Fixes a live case where a late noon spike made the forecast drop 15 ct too low and recommend waiting.
- Recommendation no longer flips between wait and fill now while the saving hovers around the minimum: wait is kept until the saving drops below two thirds of the minimum.
- "Learned pattern" only counts the hours in which a station reports prices. Stations closed at night showed about 70 % forever although everything that can be learned was learned.
- Cheapest time no longer jumps between hours that differ by fractions of a cent: it is now, unless something is at least 1/6 of the minimum saving (0.5 ct) cheaper, and otherwise the earliest hour about as cheap as the lowest.
- Once found, the cheapest time is kept while it is still about as cheap as the lowest (it switched between 10:00 and 11:00 every half hour for 0.1 ct).
- Price changes are recomputed once the source is quiet for 5 seconds. Sources update their stations one after another; this showed short-lived in-between recommendations and cheapest times that could trigger automations.
- Diagnostics no longer contain the entity id of the fuel level sensor.
- README: states vs. attributes explained per entity, backtest numbers updated for the current model.
- More examples: card "now vs. expected", forecast chart, notifications for "worth waiting", cheapest time and nearly empty tank.
- Price sensors keep their unit while the price source is down.
- Cleaner station names (no "None" house numbers, no double spaces).

## 0.1.0

- First version: learns a working day / weekend hourly price pattern per station
  from existing price sensors, 24 h forecast, recommendation (fill now / wait /
  no need), saving per litre and per fill-up, optional fuel level sensor.
- Imports up to 10 weeks of hourly long-term statistics on first setup.
- Plausibility filter against obviously wrong prices (for example 0 €).
