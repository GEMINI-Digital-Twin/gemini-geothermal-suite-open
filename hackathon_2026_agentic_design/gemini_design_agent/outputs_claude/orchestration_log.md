
### Claude: build `base-2dbl-2500m-abs`
Start at the specified 2,500 m reservoir with two doublets (one doublet cannot cover 365 days under the 330-day rule). Brine ~85 C at the wellhead is below the 100 C supply, so I expect the heat pump to carry all heating; I size absorption cooling to see whether 85 C can drive it.

[01] claude      base-2dbl-2500m-abs          feasible=True  hard=0 soft=1 COP=3.8 LCOE=86.0 EUR/MWh (10s) :: build candidate

### Claude: build `deep-3dbl-3500m-abs`
Deeper target: at 3,500 m the reservoir is 117 C and the wellhead ~114 C, which permits direct plate-HX supply at 100 C and gives the absorption chiller a full-COP driving temperature. Three doublets because the 40 C brine-cooling cap limits each doublet to ~13.4 MW and the peak is 30 MW.

[02] claude      deep-3dbl-3500m-abs          feasible=True  hard=0 soft=1 COP=17.3 LCOE=66.6 EUR/MWh (16s) :: build candidate

### Claude: build `mid-3dbl-3000m-abs`
Intermediate depth: at 3,000 m the wellhead is ~99-100 C, right at the edge of direct 100 C supply. This tests whether a shallower, cheaper well can avoid the large heat pump.

[03] claude      mid-3dbl-3000m-abs           feasible=True  hard=0 soft=1 COP=5.1 LCOE=92.1 EUR/MWh (13s) :: build candidate

### Claude: build `deeper-3dbl-4000m-abs`
Check whether going beyond 3,500 m still pays: hotter brine (~128 C wellhead) does not raise the 40 C cap on extracted heat, so I expect higher well capex with little operating gain.

[04] claude      deeper-3dbl-4000m-abs        feasible=True  hard=0 soft=1 COP=18.4 LCOE=70.7 EUR/MWh (18s) :: build candidate

### Claude: modify `deep-3dbl-3500m-abs` -> `two-2dbl-3500m-abs-hp15` {'n_doublets': 2, 'heat_pump_mw': 15.0}
Test whether two doublets at 3,500 m can cover the 30 MW peak if the heat pump is enlarged to 15 MW: the two doublets give ~26.8 MW of direct heat at the 40 C cap, and the heat pump could add compressor work on top.

[05] claude      two-2dbl-3500m-abs-hp15      feasible=False hard=2 soft=1 COP=13.7 LCOE=57.2 EUR/MWh (16s) :: modify ['n_doublets', 'heat_pump_mw']

### Claude: modify `deep-3dbl-3500m-abs` -> `deep-3dbl-3500m-electric` {'absorption_chiller_mw': 0.0, 'electric_chiller_mw': 10.0}
Comparison: replace the absorption chiller with a 10 MW electric chiller to quantify what brine-driven cooling is worth in electricity and cost.

[06] claude      deep-3dbl-3500m-electric     feasible=True  hard=0 soft=1 COP=11.2 LCOE=68.5 EUR/MWh (11s) :: modify ['absorption_chiller_mw', 'electric_chiller_mw']

### Claude: modify `deep-3dbl-3500m-abs` -> `final-3dbl-3500m-abs-trim` {'heat_pump_mw': 2.5, 'well.esp_bep_m3_h': 170.0}
Right-sizing: the annual simulation used at most ~1.8 MW of heat-pump output (cold-spell top-up when direct HX is at the 40 C cap), so the heat pump is trimmed from 7.5 to 2.5 MW, saving ~3.8 MEUR capex. The ESP frame is re-selected with BEP 170 m3/h (= 221 m3/h peak / 1.3) so the peak sits inside the pump window; low-flow days are handled by VSD turndown and a recirculation line.

[07] claude      final-3dbl-3500m-abs-trim    feasible=True  hard=0 soft=0 COP=17.3 LCOE=63.8 EUR/MWh (15s) :: modify ['heat_pump_mw', 'well.esp_bep_m3_h']

### Claude: finalize `final-3dbl-3500m-abs-trim`
Selected: three doublets at 3,500 m (117 C reservoir, ~114 C wellhead) with direct plate-HX heating at 100 C, a 10 MW single-effect absorption chiller driven by the brine, and a 2.5 MW high-temperature heat pump for cold-spell top-up. Reasoning: (1) the 330-day rule makes one doublet infeasible and the 40 C brine-cooling cap limits each doublet to ~13.4 MW, so the 30 MW peak needs three doublets regardless of depth; (2) at the specified 2,500 m the brine is 85 C, below the 100 C supply, forcing a 31 MW heat pump and 36 GWh/yr of electricity (COP 3.8, 86 EUR/MWh); (3) 3,000 m is still just below the 103 C needed for direct supply and is the worst of both worlds (92 EUR/MWh); (4) 3,500 m enables direct supply and full-COP absorption cooling, cutting electricity to 7.8 GWh/yr (COP 17.3) at 63.8 EUR/MWh; (5) 4,000 m adds well cost without raising the cap-limited heat per doublet (70.7 EUR/MWh); (6) two doublets at 3,500 m fail on 16 peak days and during maintenance; (7) absorption cooling saves 4.3 GWh/yr and 0.65 MEUR/yr versus electric chillers. ESP set at 1,000 m keeps the intake 40 bar above the CH4 bubble point; tubing velocity 2.3 m/s is below the API erosional limit; CO2 corrosion (8 mm/yr un-mitigated) is handled with inhibitor and GRE-lined tubing. Trade-off: higher well capex (3 x 3,780 m MD) against the lowest electricity use and highest geothermal share of all feasible options.

[closed-loop] mean flow 136 m3/h/doublet, mean injection T 69 C, breakthrough at 1500 m spacing after 125.8 yr; spacing for 30 yr without breakthrough: 732 m
[closed-loop] year  1: Tprod  117.0 C  skin+0.0  ESP eff 1.00  el   7.9 GWh  COP  17.2  feasible=True  
[closed-loop] year  2: Tprod  117.0 C  skin+0.6  ESP eff 0.98  el   8.1 GWh  COP  16.8  feasible=True  
[closed-loop] year  3: Tprod  117.0 C  skin+1.2  ESP eff 0.96  el   8.3 GWh  COP  16.4  feasible=True  
[closed-loop] year  4: Tprod  117.0 C  skin+1.8  ESP eff 0.94  el   8.4 GWh  COP  16.0  feasible=True  
[closed-loop] year  5: Tprod  117.0 C  skin+2.4  ESP eff 0.92  el   8.6 GWh  COP  15.7  feasible=True  
[closed-loop] year  6: Tprod  117.0 C  skin+3.0  ESP eff 0.90  el   8.8 GWh  COP  15.3  feasible=True  acid stimulation of injectors (skin +3.0 -> 0; WHP 41 bar); ESP workover / replacement (efficiency factor 0.90 -> 1.00)
[closed-loop] year  7: Tprod  117.0 C  skin+0.6  ESP eff 0.98  el   8.1 GWh  COP  16.8  feasible=True  
[closed-loop] year  8: Tprod  117.0 C  skin+1.2  ESP eff 0.96  el   8.3 GWh  COP  16.4  feasible=True  
[closed-loop] year  9: Tprod  117.0 C  skin+1.8  ESP eff 0.94  el   8.4 GWh  COP  16.0  feasible=True  
[closed-loop] year 10: Tprod  117.0 C  skin+2.4  ESP eff 0.92  el   8.6 GWh  COP  15.7  feasible=True  
[closed-loop] year 11: Tprod  117.0 C  skin+3.0  ESP eff 0.90  el   8.8 GWh  COP  15.3  feasible=True  acid stimulation of injectors (skin +3.0 -> 0; WHP 41 bar); ESP workover / replacement (efficiency factor 0.90 -> 1.00)
[closed-loop] year 12: Tprod  117.0 C  skin+0.6  ESP eff 0.98  el   8.1 GWh  COP  16.8  feasible=True  
[closed-loop] year 13: Tprod  117.0 C  skin+1.2  ESP eff 0.96  el   8.3 GWh  COP  16.4  feasible=True  
[closed-loop] year 14: Tprod  117.0 C  skin+1.8  ESP eff 0.94  el   8.4 GWh  COP  16.0  feasible=True  
[closed-loop] year 15: Tprod  117.0 C  skin+2.4  ESP eff 0.92  el   8.6 GWh  COP  15.7  feasible=True  
[closed-loop] year 16: Tprod  117.0 C  skin+3.0  ESP eff 0.90  el   8.8 GWh  COP  15.3  feasible=True  acid stimulation of injectors (skin +3.0 -> 0; WHP 41 bar); ESP workover / replacement (efficiency factor 0.90 -> 1.00)
[closed-loop] year 17: Tprod  117.0 C  skin+0.6  ESP eff 0.98  el   8.1 GWh  COP  16.8  feasible=True  
[closed-loop] year 18: Tprod  117.0 C  skin+1.2  ESP eff 0.96  el   8.3 GWh  COP  16.4  feasible=True  
[closed-loop] year 19: Tprod  117.0 C  skin+1.8  ESP eff 0.94  el   8.4 GWh  COP  16.0  feasible=True  
[closed-loop] year 20: Tprod  117.0 C  skin+2.4  ESP eff 0.92  el   8.6 GWh  COP  15.7  feasible=True  
[closed-loop] year 21: Tprod  117.0 C  skin+3.0  ESP eff 0.90  el   8.8 GWh  COP  15.3  feasible=True  acid stimulation of injectors (skin +3.0 -> 0; WHP 41 bar); ESP workover / replacement (efficiency factor 0.90 -> 1.00)
[closed-loop] year 22: Tprod  117.0 C  skin+0.6  ESP eff 0.98  el   8.1 GWh  COP  16.8  feasible=True  
[closed-loop] year 23: Tprod  117.0 C  skin+1.2  ESP eff 0.96  el   8.3 GWh  COP  16.4  feasible=True  
[closed-loop] year 24: Tprod  117.0 C  skin+1.8  ESP eff 0.94  el   8.4 GWh  COP  16.0  feasible=True  
[closed-loop] year 25: Tprod  117.0 C  skin+2.4  ESP eff 0.92  el   8.6 GWh  COP  15.7  feasible=True  
