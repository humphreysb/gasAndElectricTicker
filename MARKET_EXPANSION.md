# Target Markets for RateSavvy

This document outlines the expansion roadmap for RateSavvy beyond Ohio. It categorizes deregulated US energy markets based on data availability, specifically identifying states with official, centralized comparison websites that can be scraped for current rates, versus states that lack centralized data.

## 🟢 Tier 1: Prime Targets (Scrapable Official Sites)
These states have deregulated markets and provide an official government-run website that aggregates provider rates. These are the immediate targets for building our national database, as we can build scrapers similar to the Ohio `energy_scraper.py`.

### Electricity & Natural Gas
*   **Ohio (Current)**
    *   **Site:** [Energy Choice Ohio (Apples to Apples)](https://energychoice.ohio.gov)
    *   **Data:** Electricity and Natural Gas.
*   **Pennsylvania**
    *   **Site (Electric):** [PAPowerSwitch.com](https://www.papowerswitch.com)
    *   **Site (Gas):** [PAGasSwitch.com](https://www.pagasswitch.com)
    *   **Data:** High-quality, centralized comparison engines for both utilities.
*   **New York**
    *   **Site:** [PowerToChoose.ny.gov](http://www.powertochoose.ny.gov)
    *   **Data:** Electricity and Natural Gas.
*   **Maryland**
    *   **Site (Electric):** [MarylandElectricChoice.com](https://www.marylandelectricchoice.com)
    *   **Site (Gas):** [MDGasChoice.com](https://www.mdgaschoice.com)
    *   **Data:** Electricity and Natural Gas.
*   **Illinois**
    *   **Site:** [PlugInIllinois.org](https://www.pluginillinois.org) (Electric) / ICC website for Gas.
    *   **Data:** Electricity and Natural Gas.

### Electricity Only
*   **Texas**
    *   **Site:** [PowerToChoose.org](https://www.powertochoose.org)
    *   **Data:** Electricity only. **Note:** This is the largest deregulated market in the US.
*   **Connecticut**
    *   **Site:** [EnergizeCT.com](https://energizect.com)
    *   **Data:** Electricity.
*   **Massachusetts**
    *   **Site:** [EnergySwitchMA.gov](https://energyswitchma.gov)
    *   **Data:** Electricity.

### Natural Gas Only
*   **Michigan**
    *   **Site:** [Compare MI Gas](https://www.lara.state.mi.us/mpsc/gas/compare/)
    *   **Data:** Natural Gas.
*   **Georgia**
    *   **Site:** [Georgia PSC Marketers' Pricing](https://psc.ga.gov/utilities/natural-gas/marketers-pricing-comparison/)
    *   **Data:** Natural Gas.
*   **Washington D.C.**
    *   **Site:** [DC Power Connect](https://www.dcpowerconnect.com)
    *   **Data:** Natural Gas.

---

## 🔴 Tier 2: Difficult Targets (No Centralized Pricing Data)
These states have deregulated markets (or "Choice" programs) but **DO NOT** publish a centralized database of current rates. The state usually only provides a PDF or list of licensed suppliers. Scraping these states would require building individual scrapers for dozens of private supplier websites, making them low-priority.

*   **New Jersey:** Provides a list of licensed suppliers ([NJ.gov/BPU](https://www.nj.gov/bpu/commercial/shopping.html) / NJ Powerswitch), but lacks a live "shopping engine" like PA or TX.
*   **New Hampshire:** Provides information and a list of suppliers, but no live rate comparison tool.
*   **Maine:** Lists standard offer rates and licensed suppliers, but no centralized comparison.
*   **Nebraska & Wyoming:** Participate in the "Choice Gas Program," but enrollment happens in a specific annual window and rates are not centrally aggregated for scraping.
*   **Virginia & Kentucky:** Gas choice is limited to specific utility service areas (e.g., Columbia Gas) and lacks a statewide rate aggregation tool.
*   **Massachusetts (Gas):** While they have a centralized site for electricity, for natural gas they only provide a list of licensed suppliers.
*   **Florida:** Gas deregulation is mostly limited to commercial/industrial customers, with no residential comparison portal.
