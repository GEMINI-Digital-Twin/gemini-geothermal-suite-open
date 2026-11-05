# Proposed port fields of every module class

Generated from the module classes of gemini 0.5.14 (153 ports, 41 classes). Proposal only, nothing implemented.
`flow` is DRAWN where `drawn` is true today, else IMPOSED; `many` and `offered` are today's values; every port is `required` (as today: each port is connected or named as a plant port). `!` marks a judgement call, explained in the last column.

| category | module | port | dir | carrier | phase | fluid | level | energy | generic | flow | many | offered | req | today kind | note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| subsurface | BoreholeField | fluid_in | IN | STREAM | LIQUID | ANY | WARM | - | - | IMPOSED | no | no | yes | hot_water | ! closed borehole loop: water or glycol at 5-20 C, so WARM not HOT; fluid ANY |
| subsurface | BoreholeField | fluid_out | OUT | STREAM | LIQUID | ANY | WARM | - | - | IMPOSED | no | no | yes | hot_water | ! as fluid_in |
| subsurface | BoreholeField | loss_out | OUT | POWER | - | - | - | HEAT | - | IMPOSED | no | no | yes | heat |  |
| subsurface | DownholeHeatExchanger | fluid_in | IN | STREAM | LIQUID | ANY | WARM | - | - | IMPOSED | no | no | yes | hot_water | ! closed loop like the borehole field |
| subsurface | DownholeHeatExchanger | fluid_out | OUT | STREAM | LIQUID | ANY | WARM | - | - | IMPOSED | no | no | yes | hot_water | ! as fluid_in |
| subsurface | DownholeHeatExchanger | loss_out | OUT | POWER | - | - | - | HEAT | - | IMPOSED | no | no | yes | heat |  |
| subsurface | InjectionReservoir | sandface_in | IN | STREAM | LIQUID | BRINE | GEOTHERMAL | - | - | IMPOSED | no | no | yes | brine |  |
| subsurface | ProductionReservoir | sandface_out | OUT | STREAM | LIQUID | BRINE | GEOTHERMAL | - | - | IMPOSED | no | no | yes | brine |  |
| subsurface | ThermalDecline | fluid_in | IN | STREAM | LIQUID | BRINE | GEOTHERMAL | - | - | IMPOSED | no | no | yes | brine |  |
| subsurface | ThermalDecline | fluid_out | OUT | STREAM | LIQUID | BRINE | GEOTHERMAL | - | - | IMPOSED | no | no | yes | brine |  |
| wells | InjectionWell | wellhead_in | IN | STREAM | LIQUID | BRINE | GEOTHERMAL | - | - | IMPOSED | no | no | yes | brine |  |
| wells | InjectionWell | bottom_out | OUT | STREAM | LIQUID | BRINE | GEOTHERMAL | - | - | IMPOSED | no | no | yes | brine |  |
| wells | InjectionWell | loss_out | OUT | POWER | - | - | - | HEAT | - | IMPOSED | no | no | yes | heat |  |
| wells | ProductionWell | bottom_in | IN | STREAM | LIQUID | BRINE | GEOTHERMAL | - | - | IMPOSED | no | no | yes | brine |  |
| wells | ProductionWell | wellhead_out | OUT | STREAM | LIQUID | BRINE | GEOTHERMAL | - | - | IMPOSED | no | no | yes | brine |  |
| wells | ProductionWell | loss_out | OUT | POWER | - | - | - | HEAT | - | IMPOSED | no | no | yes | heat |  |
| pumps | CentrifugalPump | fluid_in | IN | STREAM | LIQUID | ANY | ANY | - | T | IMPOSED | no | no | yes | (none) | ! no kind today; inlet and outlet share one liquid (generic T) |
| pumps | CentrifugalPump | power_in | IN | POWER | - | - | - | ELECTRICITY | - | DRAWN | no | no | yes | electricity |  |
| pumps | CentrifugalPump | fluid_out | OUT | STREAM | LIQUID | ANY | ANY | - | T | IMPOSED | no | no | yes | (none) | ! no kind today; inlet and outlet share one liquid (generic T) |
| pumps | CentrifugalPump | loss_out | OUT | POWER | - | - | - | HEAT | - | IMPOSED | no | no | yes | heat |  |
| pumps | CirculationPump | fluid_in | IN | STREAM | LIQUID | ANY | ANY | - | T | IMPOSED | no | no | yes | (none) | ! no kind today; inlet and outlet share one liquid (generic T) |
| pumps | CirculationPump | power_in | IN | POWER | - | - | - | ELECTRICITY | - | DRAWN | no | no | yes | electricity |  |
| pumps | CirculationPump | fluid_out | OUT | STREAM | LIQUID | ANY | ANY | - | T | IMPOSED | no | no | yes | (none) | ! no kind today; inlet and outlet share one liquid (generic T) |
| pumps | CirculationPump | loss_out | OUT | POWER | - | - | - | HEAT | - | IMPOSED | no | no | yes | heat |  |
| pumps | ESP | fluid_in | IN | STREAM | LIQUID | BRINE | GEOTHERMAL | - | - | IMPOSED | no | no | yes | brine |  |
| pumps | ESP | power_in | IN | POWER | - | - | - | ELECTRICITY | - | DRAWN | no | no | yes | electricity |  |
| pumps | ESP | fluid_out | OUT | STREAM | LIQUID | BRINE | GEOTHERMAL | - | - | IMPOSED | no | no | yes | brine |  |
| pumps | GasCompressor | fluid_in | IN | STREAM | GAS | ANY | AMBIENT | - | - | IMPOSED | no | no | yes | gas | ! compresses co-produced gas or natural gas: fluid ANY within GAS |
| pumps | GasCompressor | power_in | IN | POWER | - | - | - | ELECTRICITY | - | DRAWN | no | no | yes | electricity |  |
| pumps | GasCompressor | fluid_out | OUT | STREAM | GAS | ANY | AMBIENT | - | - | IMPOSED | no | no | yes | gas | ! same fluid as its inlet; generic T would be stricter |
| pumps | GasCompressor | loss_out | OUT | POWER | - | - | - | HEAT | - | IMPOSED | no | no | yes | heat |  |
| pumps | InjectionPump | fluid_in | IN | STREAM | LIQUID | BRINE | GEOTHERMAL | - | - | IMPOSED | no | no | yes | brine |  |
| pumps | InjectionPump | power_in | IN | POWER | - | - | - | ELECTRICITY | - | DRAWN | no | no | yes | electricity |  |
| pumps | InjectionPump | fluid_out | OUT | STREAM | LIQUID | BRINE | GEOTHERMAL | - | - | IMPOSED | no | no | yes | brine |  |
| pumps | LineShaftPump | fluid_in | IN | STREAM | LIQUID | BRINE | GEOTHERMAL | - | - | IMPOSED | no | no | yes | brine |  |
| pumps | LineShaftPump | power_in | IN | POWER | - | - | - | ELECTRICITY | - | DRAWN | no | no | yes | electricity |  |
| pumps | LineShaftPump | fluid_out | OUT | STREAM | LIQUID | BRINE | GEOTHERMAL | - | - | IMPOSED | no | no | yes | brine |  |
| treatment | Blowdown | fluid_in | IN | STREAM | LIQUID | BRINE | GEOTHERMAL | - | - | IMPOSED | no | no | yes | brine |  |
| treatment | Blowdown | fluid_out | OUT | STREAM | LIQUID | BRINE | GEOTHERMAL | - | - | IMPOSED | no | no | yes | brine |  |
| treatment | Blowdown | waste_out | OUT | STREAM | LIQUID | WASTE | ANY | - | - | IMPOSED | no | no | yes | waste | ! blowdown water with solids: LIQUID |
| treatment | Degasser | fluid_in | IN | STREAM | LIQUID | BRINE | GEOTHERMAL | - | - | IMPOSED | no | no | yes | brine |  |
| treatment | Degasser | liquid_out | OUT | STREAM | LIQUID | BRINE | GEOTHERMAL | - | - | IMPOSED | no | no | yes | brine |  |
| treatment | Degasser | gas_out | OUT | STREAM | GAS | NATURAL_GAS | AMBIENT | - | - | IMPOSED | no | no | yes | gas | ! co-produced gas (CH4 and CO2) burned as fuel: NATURAL_GAS, so it reaches GasMakeup and Flare |
| treatment | Desander | fluid_in | IN | STREAM | LIQUID | BRINE | GEOTHERMAL | - | - | IMPOSED | no | no | yes | brine |  |
| treatment | Desander | fluid_out | OUT | STREAM | LIQUID | BRINE | GEOTHERMAL | - | - | IMPOSED | no | no | yes | brine |  |
| treatment | Desander | waste_out | OUT | STREAM | LIQUID | WASTE | ANY | - | - | IMPOSED | no | no | yes | waste | ! sand slurry: LIQUID, could be its own phase |
| treatment | Filter | fluid_in | IN | STREAM | LIQUID | BRINE | GEOTHERMAL | - | - | IMPOSED | no | no | yes | brine |  |
| treatment | Filter | fluid_out | OUT | STREAM | LIQUID | BRINE | GEOTHERMAL | - | - | IMPOSED | no | no | yes | brine |  |
| treatment | Flare | gas_in | IN | STREAM | GAS | NATURAL_GAS | AMBIENT | - | - | IMPOSED | no | no | yes | gas | ! burns the excess co-produced gas |
| treatment | Flare | flue_out | OUT | STREAM | GAS | FLUE_GAS | AMBIENT | - | - | IMPOSED | no | no | yes | gas | ! kind gas today; it is flue gas |
| treatment | Flare | loss_out | OUT | POWER | - | - | - | HEAT | - | IMPOSED | no | no | yes | heat |  |
| treatment | InhibitorDosing | fluid_in | IN | STREAM | LIQUID | BRINE | GEOTHERMAL | - | - | IMPOSED | no | no | yes | brine |  |
| treatment | InhibitorDosing | chemical_in | IN | STREAM | LIQUID | CHEMICAL | AMBIENT | - | - | DRAWN | no | no | yes | chemical |  |
| treatment | InhibitorDosing | fluid_out | OUT | STREAM | LIQUID | BRINE | GEOTHERMAL | - | - | IMPOSED | no | no | yes | brine |  |
| exchangers | Cooler | fluid_in | IN | STREAM | LIQUID | WATER | WARM | - | - | IMPOSED | no | no | yes | hot_water | ! condenser water of a chiller, 25-40 C: WARM, kind hot_water today |
| exchangers | Cooler | air_in | IN | STREAM | GAS | AIR | AMBIENT | - | - | DRAWN | no | no | yes | air |  |
| exchangers | Cooler | power_in | IN | POWER | - | - | - | ELECTRICITY | - | DRAWN | no | no | yes | electricity |  |
| exchangers | Cooler | fluid_out | OUT | STREAM | LIQUID | WATER | WARM | - | - | IMPOSED | no | yes | yes | hot_water | ! as fluid_in |
| exchangers | Cooler | air_out | OUT | STREAM | GAS | AIR | AMBIENT | - | - | IMPOSED | no | no | yes | air |  |
| exchangers | HeatExchanger | hot_in | IN | STREAM | LIQUID | ANY | ANY | - | H | IMPOSED | no | no | yes | (none) | ! no kind today; generic per side, any liquid (brine, water, chilled water) |
| exchangers | HeatExchanger | cold_in | IN | STREAM | LIQUID | ANY | ANY | - | C | IMPOSED | no | no | yes | (none) | ! no kind today; generic per side, any liquid (brine, water, chilled water) |
| exchangers | HeatExchanger | hot_out | OUT | STREAM | LIQUID | ANY | ANY | - | H | IMPOSED | no | no | yes | (none) | ! no kind today; generic per side, any liquid (brine, water, chilled water) |
| exchangers | HeatExchanger | cold_out | OUT | STREAM | LIQUID | ANY | ANY | - | C | IMPOSED | no | no | yes | (none) | ! no kind today; generic per side, any liquid (brine, water, chilled water) |
| heating | Boiler | fluid_in | IN | STREAM | LIQUID | WATER | HOT | - | - | IMPOSED | no | no | yes | hot_water |  |
| heating | Boiler | fuel_in | IN | STREAM | GAS | NATURAL_GAS | AMBIENT | - | - | DRAWN | no | no | yes | gas |  |
| heating | Boiler | fluid_out | OUT | STREAM | LIQUID | WATER | HOT | - | - | IMPOSED | no | no | yes | hot_water |  |
| heating | Boiler | flue_out | OUT | STREAM | GAS | FLUE_GAS | AMBIENT | - | - | IMPOSED | no | no | yes | gas | ! kind gas today; it is flue gas |
| heating | Boiler | loss_out | OUT | POWER | - | - | - | HEAT | - | IMPOSED | no | no | yes | heat |  |
| heating | CHP | fluid_in | IN | STREAM | LIQUID | WATER | HOT | - | - | IMPOSED | no | no | yes | hot_water |  |
| heating | CHP | fuel_in | IN | STREAM | GAS | NATURAL_GAS | AMBIENT | - | - | DRAWN | no | no | yes | gas |  |
| heating | CHP | fluid_out | OUT | STREAM | LIQUID | WATER | HOT | - | - | IMPOSED | no | no | yes | hot_water |  |
| heating | CHP | flue_out | OUT | STREAM | GAS | FLUE_GAS | AMBIENT | - | - | IMPOSED | no | no | yes | gas | ! kind gas today; it is flue gas |
| heating | CHP | power_out | OUT | POWER | - | - | - | ELECTRICITY | - | IMPOSED | no | no | yes | electricity |  |
| heating | CHP | loss_out | OUT | POWER | - | - | - | HEAT | - | IMPOSED | no | no | yes | heat |  |
| heating | ElectricBoiler | fluid_in | IN | STREAM | LIQUID | WATER | HOT | - | - | IMPOSED | no | no | yes | hot_water |  |
| heating | ElectricBoiler | power_in | IN | POWER | - | - | - | ELECTRICITY | - | DRAWN | no | no | yes | electricity |  |
| heating | ElectricBoiler | fluid_out | OUT | STREAM | LIQUID | WATER | HOT | - | - | IMPOSED | no | no | yes | hot_water |  |
| heating | ElectricBoiler | loss_out | OUT | POWER | - | - | - | HEAT | - | IMPOSED | no | no | yes | heat |  |
| heating | HeatPump | source_in | IN | STREAM | LIQUID | ANY | ANY | - | S | IMPOSED | no | no | yes | (none) | ! no kind today; source can be brine, borehole loop or chilled return: generic S, any liquid |
| heating | HeatPump | sink_in | IN | STREAM | LIQUID | WATER | HOT | - | - | IMPOSED | no | no | yes | hot_water |  |
| heating | HeatPump | power_in | IN | POWER | - | - | - | ELECTRICITY | - | DRAWN | no | no | yes | electricity |  |
| heating | HeatPump | source_out | OUT | STREAM | LIQUID | ANY | ANY | - | S | IMPOSED | no | no | yes | (none) | ! no kind today; source can be brine, borehole loop or chilled return: generic S, any liquid |
| heating | HeatPump | sink_out | OUT | STREAM | LIQUID | WATER | HOT | - | - | IMPOSED | no | no | yes | hot_water |  |
| cooling | AbsorptionUnit | generator_in | IN | STREAM | LIQUID | WATER | HOT | - | - | IMPOSED | no | no | yes | hot_water |  |
| cooling | AbsorptionUnit | chilled_in | IN | STREAM | LIQUID | WATER | CHILLED | - | - | IMPOSED | no | no | yes | chilled_water |  |
| cooling | AbsorptionUnit | cooling_in | IN | STREAM | LIQUID | WATER | WARM | - | - | IMPOSED | no | no | yes | hot_water | ! rejection circuit to a Cooler: WARM, kind hot_water today |
| cooling | AbsorptionUnit | power_in | IN | POWER | - | - | - | ELECTRICITY | - | DRAWN | no | no | yes | electricity |  |
| cooling | AbsorptionUnit | generator_out | OUT | STREAM | LIQUID | WATER | HOT | - | - | IMPOSED | no | no | yes | hot_water |  |
| cooling | AbsorptionUnit | chilled_out | OUT | STREAM | LIQUID | WATER | CHILLED | - | - | IMPOSED | no | no | yes | chilled_water |  |
| cooling | AbsorptionUnit | cooling_out | OUT | STREAM | LIQUID | WATER | WARM | - | - | IMPOSED | no | no | yes | hot_water | ! as cooling_in |
| cooling | AdsorptionChiller | generator_in | IN | STREAM | LIQUID | WATER | HOT | - | - | IMPOSED | no | no | yes | hot_water |  |
| cooling | AdsorptionChiller | chilled_in | IN | STREAM | LIQUID | WATER | CHILLED | - | - | IMPOSED | no | no | yes | chilled_water |  |
| cooling | AdsorptionChiller | cooling_in | IN | STREAM | LIQUID | WATER | WARM | - | - | IMPOSED | no | no | yes | hot_water | ! rejection circuit to a Cooler: WARM |
| cooling | AdsorptionChiller | power_in | IN | POWER | - | - | - | ELECTRICITY | - | DRAWN | no | no | yes | electricity |  |
| cooling | AdsorptionChiller | generator_out | OUT | STREAM | LIQUID | WATER | HOT | - | - | IMPOSED | no | no | yes | hot_water |  |
| cooling | AdsorptionChiller | chilled_out | OUT | STREAM | LIQUID | WATER | CHILLED | - | - | IMPOSED | no | no | yes | chilled_water |  |
| cooling | AdsorptionChiller | cooling_out | OUT | STREAM | LIQUID | WATER | WARM | - | - | IMPOSED | no | no | yes | hot_water | ! as cooling_in |
| power | FlashTurbine | fluid_in | IN | STREAM | GAS | STEAM | GEOTHERMAL | - | - | IMPOSED | no | no | yes | gas | ! kind gas today; it is steam |
| power | FlashTurbine | fluid_out | OUT | STREAM | TWO_PHASE | STEAM | GEOTHERMAL | - | - | IMPOSED | no | no | yes | gas | ! exhaust steam, wet: TWO_PHASE |
| power | FlashTurbine | power_out | OUT | POWER | - | - | - | ELECTRICITY | - | IMPOSED | no | no | yes | electricity |  |
| power | FlashTurbine | loss_out | OUT | POWER | - | - | - | HEAT | - | IMPOSED | no | no | yes | heat |  |
| power | ORC | fluid_in | IN | STREAM | LIQUID | BRINE | GEOTHERMAL | - | - | IMPOSED | no | no | yes | brine |  |
| power | ORC | air_in | IN | STREAM | GAS | AIR | AMBIENT | - | - | IMPOSED | no | no | yes | air |  |
| power | ORC | fluid_out | OUT | STREAM | LIQUID | BRINE | GEOTHERMAL | - | - | IMPOSED | no | no | yes | brine |  |
| power | ORC | power_out | OUT | POWER | - | - | - | ELECTRICITY | - | IMPOSED | no | no | yes | electricity |  |
| power | ORC | loss_out | OUT | POWER | - | - | - | HEAT | - | IMPOSED | no | no | yes | heat |  |
| power | Separator | fluid_in | IN | STREAM | LIQUID | BRINE | GEOTHERMAL | - | - | IMPOSED | no | no | yes | brine |  |
| power | Separator | liquid_out | OUT | STREAM | LIQUID | BRINE | GEOTHERMAL | - | - | IMPOSED | no | no | yes | brine |  |
| power | Separator | gas_out | OUT | STREAM | GAS | STEAM | GEOTHERMAL | - | - | IMPOSED | no | no | yes | gas | ! kind gas today; it is flashed steam |
| storage | AquiferStorage | injection_in | IN | STREAM | LIQUID | BRINE | GEOTHERMAL | - | - | IMPOSED | no | no | yes | brine |  |
| storage | AquiferStorage | production_out | OUT | STREAM | LIQUID | BRINE | GEOTHERMAL | - | - | IMPOSED | no | yes | yes | brine |  |
| storage | AquiferStorage | loss_out | OUT | POWER | - | - | - | HEAT | - | IMPOSED | no | no | yes | heat |  |
| storage | IceStorage | fluid_in | IN | STREAM | LIQUID | WATER | CHILLED | - | - | IMPOSED | no | no | yes | chilled_water |  |
| storage | IceStorage | fluid_out | OUT | STREAM | LIQUID | WATER | CHILLED | - | - | IMPOSED | no | no | yes | chilled_water |  |
| storage | ThermalStorage | charge_in | IN | STREAM | LIQUID | WATER | HOT | - | - | IMPOSED | no | no | yes | hot_water |  |
| storage | ThermalStorage | discharge_in | IN | STREAM | LIQUID | WATER | HOT | - | - | IMPOSED | no | no | yes | hot_water |  |
| storage | ThermalStorage | air_in | IN | STREAM | GAS | AIR | AMBIENT | - | - | IMPOSED | no | no | yes | air |  |
| storage | ThermalStorage | charge_out | OUT | STREAM | LIQUID | WATER | HOT | - | - | IMPOSED | no | no | yes | hot_water |  |
| storage | ThermalStorage | discharge_out | OUT | STREAM | LIQUID | WATER | HOT | - | - | IMPOSED | no | no | yes | hot_water |  |
| storage | ThermalStorage | loss_out | OUT | POWER | - | - | - | HEAT | - | IMPOSED | no | no | yes | heat |  |
| piping | GasMakeup | gas_in | IN | STREAM | GAS | NATURAL_GAS | AMBIENT | - | - | IMPOSED | no | no | yes | gas |  |
| piping | GasMakeup | grid_in | IN | STREAM | GAS | NATURAL_GAS | AMBIENT | - | - | DRAWN | no | no | yes | gas |  |
| piping | GasMakeup | fuel_out | OUT | STREAM | GAS | NATURAL_GAS | AMBIENT | - | - | DRAWN | no | yes | yes | gas |  |
| piping | GasMakeup | excess_out | OUT | STREAM | GAS | NATURAL_GAS | AMBIENT | - | - | IMPOSED | no | no | yes | gas |  |
| piping | Mixer | branch1_in | IN | STREAM | LIQUID | ANY | ANY | - | T | IMPOSED | no | no | yes | (none) | ! no kind today; inlet and outlet share one liquid (generic T) |
| piping | Mixer | branch2_in | IN | STREAM | LIQUID | ANY | ANY | - | T | IMPOSED | no | no | yes | (none) | ! no kind today; inlet and outlet share one liquid (generic T) |
| piping | Mixer | fluid_out | OUT | STREAM | LIQUID | ANY | ANY | - | T | IMPOSED | no | no | yes | (none) | ! no kind today; inlet and outlet share one liquid (generic T) |
| piping | Pipe | fluid_in | IN | STREAM | LIQUID | ANY | ANY | - | T | IMPOSED | no | no | yes | (none) | ! no kind today; inlet and outlet share one liquid (generic T) |
| piping | Pipe | air_in | IN | STREAM | GAS | AIR | AMBIENT | - | - | IMPOSED | no | no | yes | air |  |
| piping | Pipe | fluid_out | OUT | STREAM | LIQUID | ANY | ANY | - | T | IMPOSED | no | no | yes | (none) | ! no kind today; inlet and outlet share one liquid (generic T) |
| piping | Pipe | loss_out | OUT | POWER | - | - | - | HEAT | - | IMPOSED | no | no | yes | heat |  |
| piping | PressurizationTank | fluid_in | IN | STREAM | LIQUID | ANY | ANY | - | T | IMPOSED | no | no | yes | (none) | ! no kind today; inlet and outlet share one liquid (generic T) |
| piping | PressurizationTank | fluid_out | OUT | STREAM | LIQUID | ANY | ANY | - | T | IMPOSED | no | no | yes | (none) | ! no kind today; inlet and outlet share one liquid (generic T) |
| piping | Splitter | fluid_in | IN | STREAM | LIQUID | ANY | ANY | - | T | IMPOSED | no | no | yes | (none) | ! no kind today; inlet and outlet share one liquid (generic T) |
| piping | Splitter | branch1_out | OUT | STREAM | LIQUID | ANY | ANY | - | T | IMPOSED | no | no | yes | (none) | ! no kind today; inlet and outlet share one liquid (generic T) |
| piping | Splitter | branch2_out | OUT | STREAM | LIQUID | ANY | ANY | - | T | IMPOSED | no | no | yes | (none) | ! no kind today; inlet and outlet share one liquid (generic T) |
| piping | Valve | fluid_in | IN | STREAM | LIQUID | ANY | ANY | - | T | IMPOSED | no | no | yes | (none) | ! no kind today; inlet and outlet share one liquid (generic T) |
| piping | Valve | fluid_out | OUT | STREAM | LIQUID | ANY | ANY | - | T | IMPOSED | no | no | yes | (none) | ! no kind today; inlet and outlet share one liquid (generic T) |
| grids | ChemicalGrid | chemical_out | OUT | STREAM | LIQUID | CHEMICAL | AMBIENT | - | - | DRAWN | no | yes | yes | chemical |  |
| grids | CoolingGrid | supply_in | IN | STREAM | LIQUID | WATER | CHILLED | - | - | IMPOSED | no | no | yes | chilled_water |  |
| grids | CoolingGrid | return_out | OUT | STREAM | LIQUID | WATER | CHILLED | - | - | IMPOSED | no | yes | yes | chilled_water |  |
| grids | ElectricityGrid | power_in | IN | POWER | - | - | - | ELECTRICITY | - | IMPOSED | yes | no | yes | electricity |  |
| grids | ElectricityGrid | power_out | OUT | POWER | - | - | - | ELECTRICITY | - | DRAWN | yes | no | yes | electricity |  |
| grids | GasGrid | gas_out | OUT | STREAM | GAS | NATURAL_GAS | AMBIENT | - | - | DRAWN | no | yes | yes | gas |  |
| grids | HeatingGrid | supply_in | IN | STREAM | LIQUID | WATER | HOT | - | - | IMPOSED | no | no | yes | hot_water |  |
| grids | HeatingGrid | return_out | OUT | STREAM | LIQUID | WATER | HOT | - | - | IMPOSED | no | yes | yes | hot_water |  |
| grids | WasteGrid | waste_in | IN | STREAM | LIQUID | WASTE | ANY | - | - | IMPOSED | yes | no | yes | waste |  |
| environment | Atmosphere | air_in | IN | STREAM | GAS | AIR | AMBIENT | - | - | IMPOSED | yes | no | yes | air |  |
| environment | Atmosphere | heat_in | IN | POWER | - | - | - | HEAT | - | IMPOSED | yes | no | yes | heat |  |
| environment | Atmosphere | gas_in | IN | STREAM | GAS | ANY | AMBIENT | - | - | IMPOSED | yes | no | yes | gas | ! takes flue gas of boilers, CHP and flare, and vented gas: fluid ANY within GAS |
| environment | Atmosphere | air_out | OUT | STREAM | GAS | AIR | AMBIENT | - | - | DRAWN | yes | yes | yes | air |  |
| environment | Atmosphere | wet_air_out | OUT | STREAM | GAS | AIR | AMBIENT | - | - | DRAWN | yes | yes | yes | air |  |
| environment | Formation | heat_in | IN | POWER | - | - | - | HEAT | - | IMPOSED | yes | no | yes | heat |  |

Judgement calls: 45.

Open questions for the owner:
1. `Level.WARM` is used for the condenser (rejection) water of chillers and the Cooler, and for the closed borehole loops; without it they would be HOT, which would let a chiller reject into the heating supply. Keep WARM?
2. `Fluid.ANY` within a phase is used where a module truly takes several fluids (Atmosphere.gas_in, GasCompressor, borehole loops). Each could instead get its own generic letter.
3. `Energy.FUEL` exists today as kind `fuel` but no module port uses it; keep it for later or drop it.
4. Plant-level ports (a plant's own inlets and outlets) take the fields of the module port they name; not listed here.
5. With these fields, two connections of today's sample plants may become stricter (Degasser.gas_out to Flare and GasMakeup stay NATURAL_GAS); every sample plant is checked before release.
