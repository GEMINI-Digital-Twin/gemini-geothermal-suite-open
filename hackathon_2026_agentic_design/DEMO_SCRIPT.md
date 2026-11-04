# Three-minute demo script

Open the dashboard (https://claude.ai/artifact/NsWjVJL11z7fZCAK5Fe4my) and the terminal with
`gemini_design_agent` as working directory.

**0:00 - The problem (20 s).** "Thirty megawatts of heating in January, ten of cooling in July,
supplied at 100 and 20 degrees from a 2,500-metre reservoir that is only 87 degrees hot. The
challenge gives hard caps: one to three doublets, 50 to 300 cubic metres per hour each, at most
40 degrees of brine cooling, 330 operating days." Point at the tiles: every MWh met, COP 17,
8.6 million a year.

**0:20 - The agent loop (50 s).** Scroll to "How the agent got there". "The agent starts from the
cheapest conceivable design and lets the GEMINI twin push back." Walk the cost-per-step chart:
one doublet fails on the 330-day rule; 2,500 metres needs a 31 MW heat pump; 3,000 metres is
the worst of both worlds; 3,500 metres unlocks direct heat exchange and brine-driven cooling;
two doublets fail on sixteen peak days because the 40-degree cap, not the temperature, sets heat
per doublet. "Every move has a number behind it, and the log says why."

**1:10 - GEMINI inside (30 s).** Scroll to the well table. "Six GEMINI models, called directly:
radial inflow, IPR, the wellbore pressure and temperature model marched with the geothermal
gradient, the ESP stage curve, CO2 corrosion and erosional velocity." Point at the ESP intake
column: "the pump sits at 1,000 metres so the intake stays 40 bar above the gas bubble point."

**1:40 - Validation (30 s).** Scroll up to the constraint scorecard and the dispatch charts.
"All caps checked for all 365 days: flow stays inside the band, brine cooling touches 40 degrees
only on the peak days, one doublet at a time is out for maintenance in the low-load season."

**2:10 - Closed loop and optimisers (35 s).** Scroll to the 25-year panel: "The twin is
re-evaluated every year with reservoir cooling, skin growth and ESP wear; the controller books
acid jobs and workovers before injection pressure drifts out of limit, and sets the well
spacing." Then the ESP monitoring panel: "Hourly telemetry against the same twin; the monitor caught a gas slug, creeping stage wear, a hot motor and a trip, named each one, and handed the workover date to the controller." Then the convergence chart: "We handed the same twin to DFTR-Filter, COBYLA and StoSAG
through petlab. They confirm the structure, shave 5 percent off the cost, and expose a cliff at
3,250 metres that only the robust and the agent designs avoid."

**2:45 - Live move (15 s, optional).** In the terminal:

```
python claude_session.py suggest final-3dbl-3500m-abs-trim
```

"No repair suggested: the twin has nothing left to object to." Close.
