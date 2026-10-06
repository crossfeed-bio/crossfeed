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
