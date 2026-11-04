# Five-minute video pitch script (executive version)

Screen recording with voice over the slide deck. Target 3:30 to 4:00, leaving margin under the
5-minute cap. Speak slowly; the slides carry the numbers, you carry the story.

---

**Slide 1. The problem (30 s)**

"A district needs thirty megawatts of heating and ten megawatts of cooling. The geothermal
reservoir on offer is too cold for the heating network. We gave this problem to an AI agent,
armed with the GEMINI digital twin, and asked it to design the system, prove it works, and
explain its choices."

**Slide 3. How the agent works (45 s)**

"The agent works like an engineer, not a calculator. It proposes a design, runs it through a full
year on the GEMINI twin, reads what fails, fixes the cause, and tries again. GEMINI supplies the
well, pump, corrosion and erosion physics. The heating and cooling plant did not exist in GEMINI,
so the agent uses models we built for it. Every step is logged with its reasoning and its token
count. A rule-based mode reaches the same design with no LLM at all."

**Slide 2. The answer (40 s)**

"The answer is three doublets drilled deeper than the brief suggested, to thirty-five hundred
metres. That one decision changes everything: the brine is hot enough to feed the network
directly and to drive an absorption chiller, so almost no electricity is needed. Thirty megawatts
of heat and ten of cooling on the peak day, nothing unmet all year, ninety-four percent of the
energy from the ground."

**Slide 5. Why that design (35 s)**

"The agent got there by testing alternatives and rejecting them with a number: the shallow
reservoir needs a huge heat pump; a mid depth is the worst of both; two doublets fail on peak days;
electric chillers cost more to run. Each rejection is in the log with its reason."

**Slide 6. Proof (25 s)**

"Every day of the year is simulated and every limit in the brief is checked, plus three engineering
guards the brief did not ask for. All pass."

**Slides 7, 8, 9. Beyond the brief (60 s)**

"Three things we added. One: uncertainty. We re-ran the design over a range of geology and found a
cliff in the design space, so our recommendation comes with a safety margin and a condition.
Two: optimisation. Three external optimisers confirmed the agent's design and trimmed its cost by
five percent. Three: operations. The plant runs for twenty-five years, so we closed the loop: a
yearly controller that schedules maintenance, and a real-time pump monitor that catches faults
from live data and feeds them back into the plan."

**Slide 10. The agent as a colleague, and close (35 s)**

"Finally, the agent knows its limits. Give it incomplete data and it asks for what is missing.
Ask it for something out of scope and it declines. Give it contradictory inputs and it refuses to
size the plant until you resolve them. Everything is open source, runs offline in five minutes,
and is pushed to the GEMINI repository. Thank you."

---

Optional live moment before the close (15 s): switch to a terminal and run
`python claude_session.py suggest final-3dbl-3500m-abs-trim`. It returns no repair, which is the
twin saying it has nothing left to object to.
