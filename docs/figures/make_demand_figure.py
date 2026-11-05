"""Plot the 2027 daily heating and cooling demand with one- and two-doublet capacity lines.

Run from the repository root. Author: Sa'eed Telvari
"""
import pandas as pd, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
B = "simulator_examples/hackathon_inputs/"
h=pd.read_csv(B+'GEMINI_Heating_Demand_Daily_2027.csv',parse_dates=[0]); c=pd.read_csv(B+'GEMINI_Cooling_Demand_Daily_2027.csv',parse_dates=[0])
fig,ax=plt.subplots(figsize=(7.2,2.6),dpi=200)
ax.fill_between(h.iloc[:,0],h.iloc[:,1],color='#C2501E',alpha=.85,label='Heating, 100 °C supply (111.7 GWh, peak 30.0 MW)')
ax.fill_between(c.iloc[:,0],-c.iloc[:,1],color='#1F6FA8',alpha=.85,label='Cooling, 20 °C supply (23.7 GWh, peak 10.0 MW)')
ax.axhline(14.4,ls='--',lw=1,color='#14213D'); ax.text(h.iloc[200,0],15.2,'one doublet at the caps ≈ 14.4 MW',fontsize=7,color='#14213D')
ax.axhline(28.7,ls=':',lw=1,color='#14213D'); ax.text(h.iloc[200,0],29.4,'two doublets ≈ 28.7 MW',fontsize=7,color='#14213D')
ax.axhline(0,color='k',lw=.8); ax.set_ylabel('Daily mean power, MW\n(cooling shown negative)',fontsize=8)
ax.tick_params(labelsize=7); ax.legend(fontsize=7,loc='lower left',frameon=False); ax.set_xlim(h.iloc[0,0],h.iloc[-1,0])
import matplotlib.dates as md; ax.xaxis.set_major_formatter(md.DateFormatter('%b'))
for s in ('top','right'): ax.spines[s].set_visible(False)
fig.tight_layout(); fig.savefig('docs/figures/fig_demand.png')
