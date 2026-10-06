# Payloads of the shape grownet sends, hand written, so every expected number here is checkable.
#
# v1 (grownet 0.3.0 and later) carries fitted coefficients, one matrix per abundance unit: three
# organisms in Cells/mL, A's own limitation -4e-10 (0.4 /h over a plateau of 1e9), B's effect on A
# +2e-9, one cell from a comparison where one side did not grow, one pair left at 0 for disagreeing in
# sign, and one organism with no growth rate.
example_payload <- function() {
    list(
        format = "grownet.glv/v1", tool = "grownet", tool_version = "0.3.0",
        derived_at = "2026-10-06T12:00:00+02:00", source_db = "mGrowthDB (live)",
        matrices = list(list(
            abundance_unit = "Cells/mL", unit = "1/(h x Cells/mL)",
            organisms = list("A", "B", "C"),
            interactions = list(list(-4e-10, 2e-9, 0), list(0, -4e-10, 0), list(0, 0, -5e-10)),
            media = list("Wilkins-Chalgren Anaerobe Broth (WC)", "mMCB"), cells = 1)),
        growth_rate_unit = "1/h",
        growth_rate_detail = list(
            list(organism = "A", rate = 0.4, unit = "1/h", replicates = 3, studies = list("S1"),
                 per_study = list(S1 = 0.4), method = "growth_rate:easylinear:5", lag = 0.5,
                 lag_method = "baranyi", carrying_capacity = 1e9,
                 carrying_capacity_unit = "Cells/mL", carrying_capacity_curves = 3),
            list(organism = "B", rate = 0.2, unit = "1/h", replicates = 3, studies = list("S1"),
                 per_study = list(S1 = 0.2), method = "growth_rate:easylinear:5", lag = 0,
                 lag_method = "baranyi", carrying_capacity = 5e8,
                 carrying_capacity_unit = "Cells/mL", carrying_capacity_curves = 3)),
        caveats = list(
            coefficients = paste("every cell is a fitted per-capita coefficient: the diagonal is",
                                 "-r_i / K_i and an off-diagonal cell is (r_with - r_without) / x_j"),
            diagonal = "fitted: -r_i / K_i, with K_i the organism's own plateau",
            units = "one matrix per abundance unit: abundances are never converted between units",
            abundance_units = list("Cells/mL"),
            unbounded = paste("the equilibrium of a fit is the solution of A x = -r, and a negative",
                              "entry there means there is no positive steady state"),
            censored = "one of the two rates behind these cells is 0, measured",
            censored_cells = list(list(affected = "A", actor = "B")),
            sign_conflicts = list(list(affected = "C", actor = "A")),
            left_out = list(list("D", paste("no growth rate, so neither its own limitation nor the",
                                            "effect of anything on it can be fitted"))),
            pairs_left_out = list(),
            media = list("Wilkins-Chalgren Anaerobe Broth (WC)", "mMCB"),
            dropout_arcs = 2,
            absence_k = 1,
            without_a_rate = list("C"),
            counts = list(arcs = 3, cells = 2, organisms = 3)),
        readme = "grownet 0.3.0: fitted parameters for a generalized Lotka-Volterra simulation\n",
        files = list(steady_state_check.txt = "steady-state check: nothing to score\n"),
        studies = list(list(id = "S1", citation = "a study", url = "", license = "")),
        settings = list(metric = "growth_rate"))
}

example_glv <- function() grownet:::as_grownet_glv(example_payload())

# Two matrices, because the organisms were counted in different units and nothing is ever converted.
two_unit_payload <- function() {
    payload <- example_payload()
    payload$matrices <- c(payload$matrices, list(list(
        abundance_unit = "CFUs/mL", unit = "1/(h x CFUs/mL)",
        organisms = list("D", "E"),
        interactions = list(list(-1e-9, 5e-9), list(0, -2e-9)),
        media = list("MWF"), cells = 1)))
    payload$caveats$abundance_units <- list("CFUs/mL", "Cells/mL")
    payload$growth_rate_detail <- c(payload$growth_rate_detail, list(
        list(organism = "D", rate = 0.5, unit = "1/h", carrying_capacity = 5e8,
             carrying_capacity_unit = "CFUs/mL"),
        list(organism = "E", rate = 0.6, unit = "1/h", carrying_capacity = 3e8,
             carrying_capacity_unit = "CFUs/mL")))
    payload$caveats$left_out <- list()
    payload
}

# What grownet 0.2.0 sent: one matrix of log2 effect sizes, -1 on the diagonal, +10 for an obligate pair.
v0_payload <- function() {
    list(
        format = "grownet.glv/v0", tool = "grownet", tool_version = "0.2.0",
        derived_at = "2026-10-03T12:00:00+02:00", source_db = "mGrowthDB (live)",
        organisms = list("A", "B", "C"),
        interactions = list(list(-1, 0, 0), list(1.5, -1, 10), list(0, 0, -1)),
        growth_rates = list(0.4, 0.2, NULL),
        growth_rate_unit = "1/h",
        growth_rate_detail = list(list(organism = "A", rate = 0.4, unit = "1/h", replicates = 3,
                                       studies = list("S1"), per_study = list(S1 = 0.4))),
        caveats = list(
            diagonal = -1, extreme = 10, absence_k = 1,
            placeholders = list(list(affected = "B", actor = "C", value = 10, outcome = "obligate")),
            sign_conflicts = list(list(affected = "C", actor = "A")),
            media = list("mMCB"),
            dropout_arcs = 0,
            without_a_rate = list("C"),
            effect_size = "a cell is an effect size, not a fitted gLV coefficient",
            counts = list(arcs = 3, cells = 2, organisms = 3)),
        readme = "grownet 0.2.0: parameters for a generalized Lotka-Volterra simulation\n",
        studies = list(list(id = "S1", citation = "a study", url = "", license = "")),
        settings = list(metric = "auc"))
}
