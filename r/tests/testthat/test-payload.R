test_that("the matrix arrives in the order the formula reads: rows affected, columns the actor", {
    glv <- example_glv()
    A <- glv_matrix(glv)
    expect_equal(dim(A), c(3L, 3L))
    expect_equal(rownames(A), c("A", "B", "C"))
    expect_equal(A["A", "B"], 2e-9)       # B affects A, rows affected
    expect_equal(A["B", "A"], 0)          # and nothing says A affects B
    # the diagonal is fitted, -r_i / K_i: 0.4 over 1e9, 0.2 over 5e8, and C's own
    expect_equal(diag(A), c(A = -4e-10, B = -4e-10, C = -5e-10))
    expect_true(glv$fitted)
    expect_equal(glv$unit, "1/(h x Cells/mL)")
})

test_that("organisms counted in different units are in different matrices, and one is named", {
    two <- grownet:::as_grownet_glv(two_unit_payload())
    expect_equal(length(two$matrices), 2L)
    expect_error(glv_matrix(two), "one per abundance unit")
    expect_equal(dim(glv_matrix(two, unit = "CFUs/mL")), c(2L, 2L))
    expect_equal(glv_matrix(two, unit = "CFUs/mL")["D", "E"], 5e-9)
    expect_error(glv_matrix(two, unit = "g/L"), "no matrix in g/L")
    expect_equal(names(glv_rates(two, unit = "CFUs/mL")), c("D", "E"))
})

test_that("the parameters of grownet 0.2.0 are still read, and say what they are", {
    old <- grownet:::as_grownet_glv(v0_payload())
    expect_false(old$fitted)
    expect_equal(old$interactions["B", "A"], 1.5)     # a log2 effect size, as it was
    expect_equal(diag(old$interactions), c(A = -1, B = -1, C = -1))
    text <- paste(capture.output(print(old)), collapse = "\n")
    expect_match(text, "stated extremes, not measured ratios")
    expect_match(text, "effect sizes")
    expect_warning(glv_scale(old), NA)                # no warning: scaling is for these
})

test_that("an organism without a growth rate arrives as NA, not as a number nobody measured", {
    rates <- glv_rates(example_glv())
    expect_equal(rates, c(A = 0.4, B = 0.2, C = NA_real_))
    expect_equal(glv_rates(example_glv(), missing = 0.1)[["C"]], 0.1)
})

test_that("the caveats arrive as data, not only as text", {
    caveats <- example_glv()$caveats
    expect_equal(caveats$censored_cells$actor, "B")
    expect_equal(caveats$censored_cells$affected, "A")
    expect_equal(caveats$sign_conflicts$affected, "C")
    expect_equal(caveats$without_a_rate, "C")
    expect_equal(caveats$left_out$what, "D")
    expect_match(caveats$left_out$why, "no growth rate")
    expect_match(caveats$coefficients, "per-capita")
    expect_match(caveats$unbounded, "A x = -r")
    expect_equal(caveats$absence_k, 1)
})

test_that("what a coefficient is made of arrives with each rate", {
    detail <- example_glv()$growth_rate_detail[[1]]
    expect_equal(detail$organism, "A")
    expect_equal(detail$carrying_capacity, 1e9)
    expect_equal(detail$lag, 0.5)
    expect_equal(detail$lag_method, "baranyi")
})

test_that("printing says every caveat without being asked", {
    text <- paste(capture.output(print(example_glv())), collapse = "\n")
    expect_match(text, "fitted per-capita coefficient")
    expect_match(text, "one side did not grow")
    expect_match(text, "B on A")
    expect_match(text, "disagree in sign")
    expect_match(text, "no growth rate: C")
    expect_match(text, "in no matrix")
    expect_match(text, "rows are affected, columns are the actor")
    expect_false(grepl("effect sizes", text))
    expect_false(grepl("stated extreme", text))
})

test_that("printing names the units when there is more than one matrix", {
    text <- paste(capture.output(print(grownet:::as_grownet_glv(two_unit_payload()))), collapse = "\n")
    expect_match(text, "one matrix per abundance unit")
    expect_match(text, "CFUs/mL")
    expect_match(text, "glv_matrix\\(x, unit = \\)")
})

test_that("printing says how many arcs are from drop-out designs, which gLV should not use", {
    text <- paste(capture.output(print(example_glv())), collapse = "\n")
    expect_match(text, "2 arc\\(s\\) come from drop-out designs")
    expect_match(text, "direct effect of one organism")
    none <- example_payload()
    none$caveats$dropout_arcs <- 0
    quiet <- paste(capture.output(print(grownet:::as_grownet_glv(none))), collapse = "\n")
    expect_false(grepl("drop-out designs", quiet))
})

test_that("printing says which media the arcs come from, since a simulation is of one environment", {
    text <- paste(capture.output(print(example_glv())), collapse = "\n")
    expect_match(text, "these arcs come from 2 media")
    expect_match(text, "mMCB")
    expect_match(text, "second box")
    one <- example_payload()
    one$caveats$media <- list("mMCB")
    single <- paste(capture.output(print(grownet:::as_grownet_glv(one))), collapse = "\n")
    expect_match(single, "every arc was measured in one medium: mMCB")
})

test_that("a payload of another format is read but says so", {
    payload <- example_payload()
    payload$format <- "grownet.glv/v9"
    expect_warning(grownet:::as_grownet_glv(payload), "this package reads")
})

test_that("scaling fitted coefficients warns, since nothing about their units asks for it", {
    expect_warning(glv_scale(example_glv()), "fitted coefficients")
    scaled <- suppressWarnings(glv_scale(example_glv()))
    expect_equal(scaled$scaled_by, 1 / 2e-9)
    expect_equal(glv_matrix(scaled)["A", "B"], 1)
})

test_that("the coverage line counts the organisms outside every matrix too", {
    # It counted against the matrices' organisms, and an organism without a rate is what is left out of
    # them, so a live corpus object read "8 of 8 organisms" for an 11-organism network (#211 item 3).
    inside <- paste(capture.output(print(example_glv())), collapse = "\n")
    expect_match(inside, "growth rates: 2 of the 3 organisms in a matrix")
    expect_false(grepl("more in the network", inside))       # C has no rate and IS in the matrix
    payload <- example_payload()
    payload$caveats$without_a_rate <- list("C", "D", "E")      # D and E are in no matrix
    glv <- grownet:::as_grownet_glv(payload)
    text <- paste(capture.output(print(glv)), collapse = "\n")
    expect_match(text, "2 of the 3 organisms in a matrix")
    expect_match(text, "2 more in the network have none and are in no matrix")
    # as_miasim() stops for C, which is in a matrix, and simulates without D and E (found in review)
    expect_match(text, "needs one from elsewhere for C; as_miasim() stops", fixed = TRUE)
    expect_match(text, "D, E are in no matrix; as_miasim() simulates without them", fixed = TRUE)
    # one side at a time: each line only when it has organisms to name (found in review)
    only_outside <- example_payload()
    only_outside$caveats$without_a_rate <- list("D")
    text <- paste(capture.output(print(grownet:::as_grownet_glv(only_outside))), collapse = "\n")
    expect_false(grepl("as_miasim() stops", text, fixed = TRUE))
    expect_match(text, "D are in no matrix", fixed = TRUE)
    only_inside <- example_payload()
    only_inside$caveats$without_a_rate <- list("C")
    text <- paste(capture.output(print(grownet:::as_grownet_glv(only_inside))), collapse = "\n")
    expect_false(grepl("simulates without them", text, fixed = TRUE))
    expect_match(text, "needs one from elsewhere for C;", fixed = TRUE)
    summary_of <- NULL
    invisible(capture.output(summary_of <- summary(glv)))
    expect_equal(summary_of$organisms, 3)
    expect_equal(summary_of$network_organisms, 5)
})


test_that("the effects left at 0 and those in no matrix keep their actor and reach the print", {
    # found in review: pairs were read as (what, why), dropping the actor, and across_units not at all
    payload <- example_payload()
    # with none of them, none of their headers (round 18: a mutant printing "0 effect(s)" survived)
    text <- paste(capture.output(print(grownet:::as_grownet_glv(payload))), collapse = "\n")
    expect_false(grepl("effect(s) are left at 0", text, fixed = TRUE))
    expect_false(grepl("effect(s) are in no matrix", text, fixed = TRUE))
    expect_false(grepl("have arcs left out of their cell", text, fixed = TRUE))
    payload$caveats$pairs_left_out <- list(list("A", "B", "no abundance"), list("A", "C", "no abundance"))
    payload$caveats$across_units <- list(list("A", "D", "D is in no matrix"))
    glv <- grownet:::as_grownet_glv(payload)
    expect_equal(glv$caveats$pairs_left_out$actor, c("B", "C"))
    expect_equal(glv$caveats$pairs_left_out$affected, c("A", "A"))
    expect_equal(glv$caveats$across_units$actor, "D")
    text <- paste(capture.output(print(glv)), collapse = "\n")
    expect_match(text, "2 effect(s) are left at 0 (actor on affected):", fixed = TRUE)
    expect_match(text, "C on A: no abundance", fixed = TRUE)
    expect_match(text, "1 effect(s) are in no matrix (actor on affected):", fixed = TRUE)
    expect_match(text, "D on A: D is in no matrix", fixed = TRUE)
    payload$caveats$arcs_left_out <- list(list("A", "B", "1 arc(s) of this pair measure the actor in OD"))
    glv <- grownet:::as_grownet_glv(payload)
    expect_equal(glv$caveats$arcs_left_out$why, "1 arc(s) of this pair measure the actor in OD")
    text <- paste(capture.output(print(glv)), collapse = "\n")
    expect_match(text, "1 pair(s) have arcs left out of their cell", fixed = TRUE)
    expect_match(text, "B on A: 1 arc(s) of this pair measure the actor in OD", fixed = TRUE)
})

test_that("the unit sentence says what was measured between organisms counted differently", {
    # found in review: it said nothing was measured whatever the package's own rows held
    payload <- two_unit_payload()
    text <- paste(capture.output(print(grownet:::as_grownet_glv(payload))), collapse = "\n")
    expect_match(text, "no effect between organisms counted differently was measured", fixed = TRUE)
    # an effect in no matrix because an organism has no coefficient is not one between units (round 18)
    payload$caveats$across_units <- list(list("A", "D", "D could not be fitted, so this effect is in no matrix"))
    text <- paste(capture.output(print(grownet:::as_grownet_glv(payload))), collapse = "\n")
    expect_match(text, "no effect between organisms counted differently was measured", fixed = TRUE)
    payload$caveats$across_units <- list(list("A", "D", "D is counted in CFUs/mL and A in Cells/mL, so this effect is in neither matrix"))
    text <- paste(capture.output(print(grownet:::as_grownet_glv(payload))), collapse = "\n")
    expect_match(text, "1 effect(s) between organisms counted differently were measured and are in no matrix",
                 fixed = TRUE)
})


test_that("the media line is about the cells the matrices hold where the package names them", {
    # found in review: a matrix of one medium was warned about the media of arcs in no matrix
    payload <- example_payload()
    payload$caveats$media <- list("WC", "LB")
    text <- paste(capture.output(print(grownet:::as_grownet_glv(payload))), collapse = "\n")
    expect_match(text, "these arcs come from 2 media", fixed = TRUE)
    payload$caveats$cell_media <- list("WC")
    payload$matrices[[1]]$media <- list("WC")
    text <- paste(capture.output(print(grownet:::as_grownet_glv(payload))), collapse = "\n")
    expect_match(text, "every effect between organisms was measured in one medium: WC", fixed = TRUE)
    expect_match(text, "the network's other arcs, in no cell, come from LB", fixed = TRUE)
    expect_false(grepl("these arcs come from", text, fixed = TRUE))
    payload$caveats$cell_media <- list("WC", "LB")
    payload$matrices[[1]]$media <- list("WC", "LB")
    text <- paste(capture.output(print(grownet:::as_grownet_glv(payload))), collapse = "\n")
    expect_match(text, "a matrix's effects come from more than one medium", fixed = TRUE)
    expect_match(text, "Cells/mL matrix: WC, LB", fixed = TRUE)
    expect_false(grepl("in no cell", text, fixed = TRUE))
    # a package whose matrices hold no effect says so; one from before cell_media keeps the arcs' line
    payload$caveats$cell_media <- list()
    payload$matrices[[1]]$cells <- 0
    glv <- grownet:::as_grownet_glv(payload)
    expect_false(is.null(glv$caveats$cell_media))
    text <- paste(capture.output(print(glv)), collapse = "\n")
    expect_match(text, "no effect between organisms is in the matrices; the network's arcs, in no cell, come from WC, LB",
                 fixed = TRUE)
    # and with no media at all, nothing (round 21: a mutant printed "come from" followed by nothing)
    payload$caveats$media <- list()
    text <- paste(capture.output(print(grownet:::as_grownet_glv(payload))), collapse = "\n")
    expect_false(grepl("in no cell", text, fixed = TRUE))
    payload$caveats$media <- list("WC", "LB")
    payload$caveats$cell_media <- NULL
    glv <- grownet:::as_grownet_glv(payload)
    expect_null(glv$caveats$cell_media)
    text <- paste(capture.output(print(glv)), collapse = "\n")
    expect_match(text, "these arcs come from 2 media", fixed = TRUE)
})

test_that("cells whose arcs record no medium are not said to be no cell", {
    # round 21: an empty cell_media beside matrices that hold cells read as "no effect is in the matrices"
    payload <- example_payload()
    payload$caveats$media <- list("LB")
    payload$caveats$cell_media <- list()
    payload$matrices[[1]]$media <- list()
    payload$matrices[[1]]$cells_without_medium <- 1
    glv <- grownet:::as_grownet_glv(payload)
    expect_true(any(vapply(glv$matrices, function(m) isTRUE(m$cells > 0), logical(1))))
    text <- paste(capture.output(print(glv)), collapse = "\n")
    expect_match(text, "the effects between organisms in the matrices record no medium", fixed = TRUE)
    expect_false(grepl("no effect between organisms is in the matrices", text, fixed = TRUE))
    expect_match(text, "the network's other arcs, in no cell, come from LB", fixed = TRUE)
})

test_that("two matrices of one medium each are not a mix of environments", {
    # round 21: each matrix is what a simulation takes, so one medium each needs no warning
    payload <- two_unit_payload()
    payload$matrices[[1]]$media <- list("WC")
    payload$caveats$media <- list("WC", "MWF")
    payload$caveats$cell_media <- list("WC", "MWF")
    text <- paste(capture.output(print(grownet:::as_grownet_glv(payload))), collapse = "\n")
    expect_match(text, "each matrix's effects between organisms were measured in one medium", fixed = TRUE)
    expect_match(text, "CFUs/mL: MWF", fixed = TRUE)
    expect_false(grepl("more than one medium", text, fixed = TRUE))
    payload$matrices[[1]]$media <- list("WC", "LB")
    payload$caveats$cell_media <- list("WC", "LB", "MWF")
    text <- paste(capture.output(print(grownet:::as_grownet_glv(payload))), collapse = "\n")
    expect_match(text, "a matrix's effects come from more than one medium", fixed = TRUE)
    # every matrix is named, the one of a single medium too (round 22)
    expect_match(text, "CFUs/mL matrix: MWF", fixed = TRUE)
    # a matrix whose cells record no medium is named as such, beside one of a medium (round 22)
    payload$matrices[[1]]$media <- list("WC")
    payload$matrices[[2]]$media <- list()
    payload$matrices[[2]]$cells_without_medium <- 1
    payload$caveats$cell_media <- list("WC")
    text <- paste(capture.output(print(grownet:::as_grownet_glv(payload))), collapse = "\n")
    expect_match(text, "CFUs/mL: no medium recorded", fixed = TRUE)
    expect_false(grepl("every effect between organisms was measured in one medium", text, fixed = TRUE))
    # and one matrix of WC and of cells recording none is warned about, naming both
    payload <- example_payload()
    payload$matrices[[1]]$media <- list("WC")
    payload$matrices[[1]]$cells_without_medium <- 1
    payload$caveats$media <- list("WC")
    payload$caveats$cell_media <- list("WC")
    text <- paste(capture.output(print(grownet:::as_grownet_glv(payload))), collapse = "\n")
    expect_match(text, "Cells/mL matrix: WC, 1 cell(s) recording no medium", fixed = TRUE)
})
