# A payload of the shape grownet sends, hand written, so every expected number here is checkable:
# three organisms, one measured cell (+1.5), one obligate placeholder (+10), one pair left at 0 for
# disagreeing in sign, and one organism with no growth rate.
example_payload <- function() {
    list(
        format = "grownet.glv/v0", tool = "grownet", tool_version = "0.1.1",
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
            media = list("Wilkins-Chalgren Anaerobe Broth (WC)", "mMCB"),
            without_a_rate = list("C"),
            effect_size = "a cell is an effect size, not a fitted gLV coefficient",
            counts = list(arcs = 3, cells = 2, organisms = 3)),
        readme = "grownet 0.1.1: parameters for a generalized Lotka-Volterra simulation\n",
        studies = list(list(id = "S1", citation = "a study", url = "", license = "")),
        settings = list(metric = "auc"))
}

example_glv <- function() grownet:::as_grownet_glv(example_payload())
