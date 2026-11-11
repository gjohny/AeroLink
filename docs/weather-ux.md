# Weather usability review

This review focuses on Nihal's weather feature: location entry, travel weather,
forecast changes, and the summary shown inside My Trips. It uses interface
inspection and browser checks; it is not a study with real travelers.

| Friction in the original flow | Change |
| --- | --- |
| Re-entering a destination already selected for the trip | Reuse the saved city and dates; offer “Change city” only when needed |
| Separate search buttons and selection lists | Reuse the same autocomplete in trip creation and weather setup |
| Optional flight times look like mandatory setup | Collapse them under “Add departure times (optional)” |
| Travel mode and driving defaults are unclear | Use Flying/Driving buttons; show driving times with the local 9 a.m. default |
| Five expanded weather windows make the main message hard to find | Start with a weather concern, its place/time, and a useful next step; group detail into three expandable sections |
| Repeated “Not assessed” warnings look like a broken feature | For distant trips, show one approximate forecast opening date and explain scheduled checks |
| Missing measurements can look reassuring | Distinguish unknown and partial forecasts; avoid a green “all clear” when data is incomplete |
| Travelers need to press Refresh to get the first forecast | Check eligible first-time forecasts automatically on page entry |
| Technical alert copy exposes scores and assessed-hour counts | Describe what changed; keep detailed comparisons and older updates expandable |
| Users see stale results and unfamiliar UTC timestamps | Label saved forecasts clearly and show update timestamps in the viewer's local timezone; city forecast times use that city's timezone |

## Interaction defaults

- A confirmed destination is enough to view its weather. Departure city is optional
  for flights and required for driving.
- Editing focuses the page on the form. Cancel leaves the saved forecast unchanged.
- Saving unchanged details closes the form without triggering a redundant refresh.
- Selecting a city carries its coordinates and timezone; a typed, unconfirmed city
  prompts the user to choose a suggestion before saving.
- Three forecast summaries cover the journey there, destination stay, and journey
  home. Hourly tables and road samples remain available inside each section.
- Risk scoring, provider data, ownership checks, and update detection continue to
  use the existing backend service.

## Verification

Browser checks cover desktop and mobile layouts, location autocomplete, saved-city
reuse, flight/driving inputs, Cancel, first-load refresh, far-future trips, partial
forecasts, clear/stormy weather, read/unread updates, and the My Trips summary.
Frontend tests protect the date and forecast-state presentation. Backend tests
continue to check the weather service and trip ownership.

## Visual treatment

The weather and My Trips entry points retain AeroLink's navy type and blue
interaction color. The layout uses open sections, thin rules and aligned journey
rows. Gradients, large rounded containers, colored icon tiles, floating card
shadows and pill-shaped risk badges are removed from these views. Form fields and
autocomplete menus keep compact borders because they are interactive controls.

The destination temperature range and hourly trace come from the first available
local forecast day. No graph or temperature is displayed when those measurements
are unavailable. Local-hour labels and Fahrenheit units provide context. The trip
summary, creation form and tool links use the same flat visual hierarchy. Site
navigation and the underlying weather logic are preserved.
