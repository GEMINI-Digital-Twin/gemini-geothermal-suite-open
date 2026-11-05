# Sources

Full references for the short names in code comments. One line per source, grouped by file.

## geo/plant.py
- IEA HPT Annex 58 2023: IEA Heat Pumping Technologies, Annex 58 Task 1 report HPT-AN58-2 (2023), Lorenz efficiency 35-59 %, https://heatpumpingtechnologies.org/content/uploads/sites/70/2023/09/annex-58-task-1-technologies-task-report.pdf
- Arpagaus 2018: Arpagaus et al., high-temperature heat pumps, Energy 152 (2018) 985-1010, COP 6-8 at small lifts, https://doi.org/10.1016/j.energy.2018.03.166

## geo/well.py
- Mijnlieff 2015: TNO note AGE 15-10.072, SodM protocol for maximum injection pressure (0.135 bar/m to reservoir top), https://acc.nlog.nl/sites/default/files/begeleidende%20notitie%20geomech.pdf
- TNO 2014, DoubletCalc: DoubletCalc 1.4 manual, TNO report R11396 (well spacing as drainage radius), https://acc.nlog.nl/sites/default/files/6ab98fc3-1ca1-4bbe-b0a2-c5a9658a3597_doubletcalc%20v143%20manual.pdf

## geo/gas.py
- NIST WebBook: NIST Chemistry WebBook, CO2 entry C124389, methane entry C74828 (molar mass, gross heat of combustion 890.7 kJ/mol, https://webbook.nist.gov/cgi/cbook.cgi?ID=C74828&Mask=1), water entry C7732185 (latent heat)
- NIST CODATA: molar gas constant, https://physics.nist.gov/cgi-bin/cuu/Value?r
- Sander 2023: Sander, Compilation of Henry's law constants, Atmos. Chem. Phys. 23, 10901 (2023), https://www.henrys-law.org
- Burkholder 2019: van 't Hoff values for CH4 and CO2 as quoted on the Sander pages
- Fang 2023: Fang et al., J. Chem. Eng. Data 69, 3330-3346 (2023), Table 2 methane Setschenow constant, DOI 10.1021/acs.jced.3c00225
- GHG Protocol 2024: IPCC Global Warming Potential Values, August 2024, AR6 column (WG1 7.6.1.1), fossil methane fugitive emissions, https://ghgprotocol.org/sites/default/files/2024-08/Global-Warming-Potential-Values%20%28August%202024%29.pdf
- GEMINI chp.py: CHP.ELECTRICAL_POWER_FRACTION in src/gemini_model/chp/chp.py (development branch, commit d86e8bb)
- Default gas handling (engine): the challenge allows any handling option (organiser answer on Discord, 3 Nov 2026)

## geo/year.py, geo/cooling.py
- Hydreco 2020: production plan Haagse Aardwarmte Leyweg (backup boiler practice), https://www.nlog.nl/sites/default/files/2020-10/200129_verzoek_tot_instemming_wp_haagse_aardwarmte_leyweg_publiek_gelakt.pdf
- US DOE 2017: CHP Technology Fact Sheet: Absorption Chillers, DOE/EE-1608 (single-effect LiBr COP 0.75), https://www.energy.gov/sites/prod/files/2017/06/f35/CHP-Absorption%20Chiller-compliant.pdf
- KNMI: De Bilt station 260 hourly weather, 2024
- Stull 2011: wet-bulb temperature from air temperature and relative humidity, J. Appl. Meteor. Climatol. 50, 2267

## ai/AI02_tools_common.py
- ThermoGIS: ESP setting depth range 300-1 250 m keeps the pump above half the true vertical depth
