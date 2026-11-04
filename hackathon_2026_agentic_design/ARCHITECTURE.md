# Architecture

```mermaid
flowchart TB
  subgraph Inputs
    D[2027 daily demand CSVs<br/>heating 30 MW peak, cooling 10 MW peak]
    S[Challenge spec<br/>reservoir, brine, hard caps]
  end

  subgraph Agent["Design agent (propose - evaluate - diagnose - repair)"]
    O1[Claude orchestration<br/>claude_session.py / --mode claude]
    O2[Rule-based agent<br/>engineering heuristics, offline]
    TB[Design toolbox<br/>archetype - evaluate - diagnose - trim - rank]
    O1 --> TB
    O2 --> TB
  end

  subgraph Twin["Annual evaluation (365 days)"]
    DS[Daily dispatcher<br/>min brine flow that meets both loads<br/>parallel split heating / cooling trains]
    SUB[Subsurface wrapper<br/>GEMINI gemini_model]
    PL[Surface plant models<br/>plate HX, HT heat pump,<br/>absorption + electric chiller, gas handling]
    CK[Constraint checks<br/>flow 50-300, dT 40 C, 330 days,<br/>bubble point, erosion, WHP]
    DS --> SUB
    DS --> PL
    DS --> CK
  end

  subgraph GEMINI["GEMINI digital twin (open source)"]
    R[bottomhole_skin_dp + IPR<br/>productivity / injectivity]
    W[DPDT wellbore P and T<br/>marched with gradient]
    E[ESP stage curve]
    C[CO2 corrosion, API erosion]
  end

  subgraph Loop["Closed-loop management, 25 years"]
    TH[Reservoir thermal model<br/>Gringarten-Sauty breakthrough]
    DEG[Skin growth, ESP wear]
    CTRL[Controller<br/>acid job, workover, retrofit, spacing]
  end

  subgraph Mon["Real-time ESP smart monitoring (hourly)"]
    SEN[Sensors: flow, Hz, P intake / discharge,<br/>T motor, current, power, vibration]
    RES[Twin residuals<br/>GEMINI ESP curve + IPR]
    DET[Robust Mahalanobis + Isolation Forest<br/>+ CUSUM on efficiency]
    CLS[Fault signature classifier<br/>gas / wear / thermal / trip]
    HI[Health index, RUL, alerts]
    SEN --> RES --> DET --> CLS --> HI
  end

  subgraph Opt["External optimisers (petlab interface)"]
    DF[DFTR-Filter py-trsqp]
    CO[COBYLA]
    ST[StoSAG robust<br/>geological ensemble]
  end

  D --> TB
  S --> TB
  TB -->|candidate design| DS
  CK -->|violations, KPIs, cost| TB
  SUB --> R
  SUB --> W
  SUB --> E
  SUB --> C
  TB -->|final design| Loop
  TH --> DS
  DEG --> DS
  DS --> CTRL
  CTRL --> DEG
  HI -->|esp_efficiency_factor, workover timing| CTRL
  HI -->|trip / gas: re-balance doublets| DS
  TB -->|start point| Opt
  Opt -->|candidates| TB
  TB --> REP[Report, figures, dashboard]
  Loop --> REP
  Opt --> REP
```

**Reading the loop.** The toolbox proposes a design; the dispatcher runs it through every day of
the year, calling the GEMINI well models at the flow each day needs; constraint checks return
violations, KPIs and cost; the diagnoser maps the worst violation to an engineering repair; the
loop repeats until the twin stops objecting. The same toolbox is then the objective function for
the external optimisers and the yearly evaluator inside the 25-year management loop.

**Reading the monitor.** Hourly sensor data is compared with the same twin; three detectors
flag deviations, a signature classifier names the fault, and the resulting health index and
remaining useful life replace the assumed ESP wear rate in the 25-year loop and bring the
workover forward when needed. A trip or gas slug is handed to the daily dispatcher, which
re-balances flow across the remaining doublets exactly as it does for maintenance windows.
