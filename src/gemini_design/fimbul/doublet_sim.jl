# Fimbul.jl / JutulDarcy thermal simulation of one or two geothermal doublets
# for the GeoHackathon reservoir.
#
# Usage:
#   julia --project=<env> doublet_sim.jl <input.json> <output.json>
#
# The input JSON gives the geometry, rock and schedule; the output JSON gives
# per-report-step bottomhole temperatures and pressures of every
# well at the sandface (wells are simple, single-node; the wellbore is
# modelled on the Python side). Everything is in SI units on the Julia side except where a key name
# says otherwise (_c, _bar, _m3h, _md, _years). See gemini_design/fimbul/
# runner.py for the Python side and the default inputs.

using Jutul, JutulDarcy, Fimbul
using JSON
using HYPRE
using LinearAlgebra

# Cell sizes: uniform `h` over [a, b], growing geometrically by `r` out to
# `outer` on both sides, capped at `hmax`.
function graded_sizes(a, b, h, outer, r, hmax)
    n_in = max(1, Int(ceil((b - a) / h)))
    inner = fill((b - a) / n_in, n_in)
    side = Float64[]
    dx, tot = h, 0.0
    while tot < outer
        dx = min(dx * r, hmax)
        push!(side, dx)
        tot += dx
    end
    side .*= outer / tot
    return vcat(reverse(side), inner, side)
end

# Layer sizes for confining rock: fine next to the aquifer, coarse away from it
function confining_sizes(total, n, first)
    r = 2.0
    for _ in 1:200
        r = (total / first * (r - 1) + 1)^(1 / n)
    end
    return first .* r .^ (0:n-1)
end

function build_case(inp)
    depth_mid = inp["depth_m"]
    H = inp["thickness_m"]
    top = depth_mid - H / 2
    cap = inp["confining_m"]
    nc = inp["nz_confining"]
    hz_conf = confining_sizes(cap, nc, inp["confining_first_dz_m"])
    hz = vcat(reverse(hz_conf), fill(H / inp["nz_reservoir"], inp["nz_reservoir"]), hz_conf)
    z0 = top - cap

    # Doublet layout: injector at x = -L/2, producer at x = +L/2; doublets
    # are stacked along y, a distance D apart.
    L = inp["well_spacing_m"]
    nd = inp["n_doublets"]
    D = inp["doublet_separation_m"]
    ys = nd == 1 ? [0.0] : collect(range(-D / 2, D / 2, length = nd))
    h = inp["dx_m"]
    pad = inp["fine_pad_m"]
    hx = graded_sizes(-L / 2 - pad, L / 2 + pad, h, inp["outer_m"], inp["growth"], inp["dx_max_m"])
    hy = graded_sizes(minimum(ys) - pad, maximum(ys) + pad, h, inp["outer_m"], inp["growth"],
        inp["dx_max_m"])
    x0 = -L / 2 - pad - (sum(hx) - (L + 2pad)) / 2
    y0 = minimum(ys) - pad - (sum(hy) - (maximum(ys) - minimum(ys) + 2pad)) / 2
    dims = (length(hx), length(hy), length(hz))
    # The mesh top sits at z = 0 (depth z0): Fimbul's set_dirichlet_bcs
    # subtracts the top depth twice, so a mesh starting below z = 0 gets the
    # wrong initial pressure and temperature. Only relative depth matters.
    mesh = CartesianMesh(dims, (hx, hy, hz), origin = [x0, y0, 0.0])

    nl = length(hz)
    k_res = (nc + 1):(nc + inp["nz_reservoir"])
    in_res = zeros(Bool, nl)
    in_res[k_res] .= true
    md = 9.869233e-16
    nxy = dims[1] * dims[2]
    layer = repeat(1:nl, inner = nxy)
    res = in_res[layer]
    k_eff = inp["permeability_md"] * inp["mobility_factor"]
    perm = ifelse.(res, k_eff, inp["confining_perm_md"]) .* md
    kv = ifelse.(res, k_eff * inp["kv_kh"], inp["confining_perm_md"]) .* md
    domain = reservoir_domain(mesh,
        permeability = hcat(perm, perm, kv)',
        porosity = ifelse.(res, inp["porosity"], 0.05),
        rock_density = inp["rock_density"],
        rock_heat_capacity = inp["rock_heat_capacity"],
        rock_thermal_conductivity = ifelse.(res, inp["reservoir_conductivity"],
            inp["confining_conductivity"]),
        component_heat_capacity = inp["brine_cp"],
    )

    xc = cumsum(hx) .- hx ./ 2 .+ x0
    yc = cumsum(hy) .- hy ./ 2 .+ y0
    wells = []
    names = Symbol[]
    for (i, y) in enumerate(ys)
        for (kind, x) in (("Injector", -L / 2), ("Producer", L / 2))
            name = Symbol("$kind$i")
            ix = argmin(abs.(xc .- x))
            iy = argmin(abs.(yc .- y))
            w = setup_vertical_well(domain, ix, iy; heel = first(k_res), toe = last(k_res),
                name = name, simple_well = true, radius = inp["well_radius_m"])
            push!(wells, w)
            push!(names, name)
        end
    end

    model = setup_reservoir_model(domain, :geothermal, wells = wells)

    t_top = inp["surface_temperature_c"] + inp["gradient_c_per_km"] * z0 / 1000.0
    p_top = inp["pressure_ref_bar"] * 1e5 +
        inp["brine_density"] * gravity_constant * (z0 - inp["pressure_ref_depth_m"])
    bc, state0, = set_dirichlet_bcs(model, [:top, :bottom];
        pressure_surface = p_top,
        temperature_surface = convert_to_si(t_top, :Celsius),
        geothermal_gradient = inp["gradient_c_per_km"] / 1000.0,
    )
    rho = reservoir_model(model).system.rho_ref[1]

    # Schedule: one entry per period with per-doublet rate and injection T.
    periods = inp["schedule"]
    dt = Float64[]
    forces = Any[]
    for p in periods
        control = Dict{Symbol, Any}()
        for i in 1:nd
            q = p["flow_m3h"][i] / 3600.0
            prod = Symbol("Producer$i")
            inj = Symbol("Injector$i")
            if q > 1e-6
                control[prod] = ProducerControl(TotalRateTarget(-q))
                t_inj = convert_to_si(p["injection_temperature_c"][i], :Celsius)
                control[inj] = InjectorControl(JutulDarcy.ReinjectionTarget([prod]), [1.0],
                    density = rho, temperature = t_inj, check = false)
            else
                control[prod] = DisabledControl()
                control[inj] = DisabledControl()
            end
        end
        f = setup_reservoir_forces(model, control = control, bc = bc)
        n = max(1, Int(p["substeps"]))
        for _ in 1:n
            push!(dt, p["duration_days"] * si_unit(:day) / n)
            push!(forces, f)
        end
    end
    case = JutulCase(model, dt, forces; state0 = state0)
    return case, names, mesh
end

function run_one(inp)
    t0 = time()
    case, names, mesh = build_case(inp)
    res = simulate_reservoir(case; info_level = -1,
        max_timestep = inp["max_timestep_days"] * si_unit(:day))
    states = res.result.states
    out = Dict{String, Any}()
    out["time_days"] = cumsum(case.dt) ./ si_unit(:day)
    out["num_cells"] = number_of_cells(mesh)
    out["wall_time_s"] = time() - t0
    s0 = case.state0[:Reservoir]
    wells = Dict{String, Any}()
    for name in names
        cells = case.model[name].domain.representation.perforations.reservoir
        T = [convert_from_si(s[name][:Temperature][1], :Celsius) for s in states]
        p = [s[name][:Pressure][1] / 1e5 for s in states]
        wells[String(name)] = Dict(
            "bottomhole_temperature_c" => T,
            "bottomhole_pressure_bar" => p,
            # well pressure is reported at the well's reference depth (top
            # perforation), so compare with the initial well-node pressure
            "initial_pressure_bar" => case.state0[name][:Pressure][1] / 1e5,
            "initial_temperature_c" =>
                convert_from_si(sum(s0[:Temperature][cells]) / length(cells), :Celsius),
        )
    end
    out["wells"] = wells
    return out
end

# The input file holds one case (a dict) or a batch (a list of dicts, run in
# one Julia session to compile once); the output mirrors it. A batch output
# is rewritten after every case so finished runs survive an interruption.
function main(args)
    inp = JSON.parsefile(args[1])
    if inp isa AbstractVector
        outs = Any[]
        for (i, c) in enumerate(inp)
            push!(outs, run_one(c))
            println("case $i/$(length(inp)) done in $(round(outs[end]["wall_time_s"], digits = 1)) s")
            flush(stdout)
            open(io -> JSON.print(io, outs), args[2], "w")
        end
    else
        open(io -> JSON.print(io, run_one(inp)), args[2], "w")
    end
end

main(ARGS)
