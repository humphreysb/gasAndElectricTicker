# gasAndElectricTicker
This code tracks the Ohio Electric and Gas Rate on a daily basis.  It grabs the minimum gas and electric rates from the [Ohio Energy Choice Website](https://energychoice.ohio.gov/).

The resulting data is published [Here](https://humphreysb.github.io/gasAndElectricTicker/)

The mimim price is established by filtering the rates for:
1) Only fixed rates
2) Plans that only have no cancelation fees*
3) Rates that are not introductory
4) Rate terms that are 6 months or longer (experience has shown anything shorter is not long enough for phase in/out)
5) No monthly fees
6) No promos

