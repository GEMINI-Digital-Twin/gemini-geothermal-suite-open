# Five-minute video pitch script

Record screen + voice. Show the dashboard (https://claude.ai/artifact/NsWjVJL11z7fZCAK5Fe4my)
and the slide deck; switch to the terminal only for the live move at the end. Target 4:45.

**0:00 - Hook (25 s).** Slide 1.
"A district needs thirty megawatts of heat in January and ten megawatts of cooling in July, at one
hundred and twenty degrees respectively. The reservoir on offer is twenty-five hundred metres deep
and eighty-seven degrees. Too cold for the heating network. We gave this problem to an AI agent
armed with the GEMINI digital twin and told it: design it, prove it, and explain every move."

**0:25 - The loop (60 s).** Slide 3, then dashboard "How the agent got there".
"The agent does not guess. It proposes a design, runs it through all three hundred and sixty-five
days with GEMINI's well, pump, corrosion and erosion models and our own heat-pump, heat-exchanger
and chiller models, reads the violations, diagnoses them, repairs, and repeats until the twin
stops objecting. Here is the trail. It started at the specified depth: feasible, but every
megawatt lifted by a thirty-one megawatt heat pump, COP under four. It went to three thousand
metres: worst of both worlds. At thirty-five hundred metres the wellhead clears one hundred and
three degrees, direct heat exchange switches on, the absorption chiller runs at full COP, and
electricity falls by four fifths. It tried two doublets and a bigger heat pump: sixteen peak days
failed, because once the brine is cooled forty degrees there is nothing left for the heat pump to
draw on. Three doublets it is. Every step has the reason and the number next to it."

**1:25 - The result (35 s).** Dashboard top tiles and constraint scorecard.
"Three doublets at thirty-five hundred metres. On the peak day, thirty megawatts of heat,
twenty-eight of them by direct heat exchange and two from the heat pump, and ten megawatts of
cooling from the absorption chiller. Every megawatt-hour of heat and cooling delivered, zero unmet. System COP seventeen. Ninety-four percent of the energy is geothermal. All eight
challenge caps pass on every day of the year, plus three engineering guards the brief did not ask
for: ESP intake forty bar above the gas bubble point, tubing velocity under the API erosional
limit, injection pressure within limit."

**2:00 - What we built versus what GEMINI gave us (30 s).** Slide 4.
"GEMINI gave us six physics models and we call them directly. GEMINI has no heating or cooling
plant, so we built the plate heat exchanger, the high-temperature heat pump, the absorption and
electric chillers, the gas handling, the daily dispatcher that finds the minimum brine flow, and
the cost model. The agent and the twin are ours. The physics is GEMINI's."

**2:30 - Beyond the brief (75 s).** Slides 7, 8, 9.
"Three things the brief did not ask for. First, uncertainty: the design is re-run over a
geological ensemble of permeability, gradient and skin. That exposed a cliff. A design at
thirty-two fifty metres is cheapest on paper and collapses if the gradient is one degree per
kilometre lower. Second, we handed the same twin to three external optimisers: a derivative-free
trust-region method, COBYLA, and StoSAG robust optimisation. They confirmed the agent's structure,
shaved five percent off the cost, and showed that starting from the specified depth lands in a
worse local optimum, which is exactly why the agent's engineering reasoning matters as the
starting point. Third, the plant lives for twenty-five years, so we closed the loop: a yearly
management controller that re-runs the twin with reservoir cooling, skin growth and pump wear
and books acid jobs and workovers, and an hourly ESP monitor that compares live telemetry with
the twin, catches gas slugs, wear, a hot motor and a trip, names each one, and hands the workover
date to the controller. On synthetic telemetry: ninety-one percent recall, under one percent
false alarms."

**3:45 - The agent as a colleague (35 s).** Slide 10, interaction evidence.
"Every move is logged with its prompt, its answer and its token count: eight turns, about
thirty-three thousand tokens. We also tested the agent as a colleague. Give it the heating file without the cooling file and
it lists what is missing and asks whether to proceed on heating alone. Ask it for a fifty megawatt
power plant and it declines: direct use only. Tell it the reservoir is one hundred and forty
degrees at twenty-five hundred metres and it points out that this contradicts the gradient and
refuses to size the plant until you say which to trust, because the whole design flips on that
answer."

**4:20 - Close (25 s).** Terminal, then slide 1.
Run: `python claude_session.py suggest final-3dbl-3500m-abs-trim`
"No repair suggested: the twin has nothing left to object to. Everything is open source, runs
offline from the command line in five minutes, and is pushed to the GEMINI repository. Thank you."
