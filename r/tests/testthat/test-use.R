test_that("taking the matrix of fitted parameters needs no decision about placeholders", {
    expect_silent(A <- glv_matrix(example_glv()))
    expect_equal(A["A", "B"], 2e-9)
    expect_equal(diag(A), c(A = -4e-10, B = -4e-10, C = -5e-10))
})

test_that("the placeholders of older parameters can still be turned into NA or 0 deliberately", {
    old <- grownet:::as_grownet_glv(v0_payload())
    expect_warning(glv_matrix(old), "stated extremes")
    expect_silent(A <- glv_matrix(old, placeholders = "na"))
    expect_true(is.na(A["B", "C"]))
    expect_equal(A["B", "A"], 1.5)                 # the measured cells are untouched
    expect_silent(zeroed <- glv_matrix(old, placeholders = "zero"))
    expect_equal(zeroed["B", "C"], 0)
})

test_that("a missing growth rate stops a simulation instead of passing unnoticed", {
    expect_error(as_miasim(example_glv()), "no growth rate for C")
    args <- as_miasim(example_glv(), missing_rate = 0.3)
    expect_equal(args$n_species, 3L)
    expect_equal(args$names_species, c("A", "B", "C"))
    expect_equal(args$growth_rates, c(0.4, 0.2, 0.3))
    expect_equal(args$A["A", "B"], 2e-9)
    expect_null(args$x0)
})

test_that("a simulation of one unit's matrix takes that unit's organisms and rates", {
    two <- grownet:::as_grownet_glv(two_unit_payload())
    expect_error(as_miasim(two), "one per abundance unit")
    args <- as_miasim(two, unit = "CFUs/mL")
    expect_equal(args$names_species, c("D", "E"))
    expect_equal(args$growth_rates, c(0.5, 0.6))
    expect_equal(args$A["D", "E"], 5e-9)
})

test_that("the README and the files travel with the numbers", {
    glv <- example_glv()
    expect_match(glv_readme(glv, print = FALSE), "generalized Lotka-Volterra")
    dir <- file.path(tempdir(), "glv-test")
    on.exit(unlink(dir, recursive = TRUE))
    written <- glv_write(glv, dir)
    expect_true(all(file.exists(written)))
    # the matrix is named after its abundance unit, as the download is, and whatever the payload carried
    # beside the numbers is written too (the steady-state check of #125)
    expect_equal(basename(written),
                 c("interaction_matrix.Cells_per_mL.csv", "growth_rates.csv", "README.txt",
                   "steady_state_check.txt"))
    expect_match(paste(readLines(file.path(dir, "steady_state_check.txt")), collapse = " "),
                 "steady-state check")
})

test_that("one file per matrix is written when the organisms were counted in different units", {
    two <- grownet:::as_grownet_glv(two_unit_payload())
    dir <- file.path(tempdir(), "glv-two")
    on.exit(unlink(dir, recursive = TRUE))
    written <- glv_write(two, dir)
    expect_true(all(c("interaction_matrix.Cells_per_mL.csv", "interaction_matrix.CFUs_per_mL.csv")
                    %in% basename(written)))
})

test_that("nothing scales the matrix by itself", {
    # Karoline, 2026-10-03: "keep glv_scale off by default". What arrives is what grownet derived.
    glv <- example_glv()
    expect_null(glv$scaled_by)
    expect_equal(glv_matrix(glv)["A", "B"], 2e-9)
    expect_equal(as_miasim(glv, missing_rate = 0.3)$A["A", "B"], 2e-9)
})

test_that("scaling an older matrix brings the strongest cell down without changing signs", {
    old <- grownet:::as_grownet_glv(v0_payload())
    scaled <- glv_scale(old, max_effect = 1)
    A <- suppressWarnings(glv_matrix(scaled))
    off <- row(A) != col(A)
    expect_equal(max(abs(A[off])), 1)                 # the strongest cell is now the self-limitation
    expect_equal(A["B", "A"] / A["B", "C"], 1.5 / 10) # and the cells keep their ratio to each other
    expect_equal(diag(A), c(A = -1, B = -1, C = -1))  # the diagonal is untouched
    expect_equal(scaled$scaled_by, 1 / 10)
})

test_that("a fit with no bounded state says so when it is printed, and scaling is not the cure", {
    text <- paste(capture.output(print(example_glv())), collapse = "\n")
    expect_match(text, "outweigh the organism's own limitation")
    expect_match(text, "A x = -r")
    expect_false(grepl("glv_scale\\(x\\) brings them down", text))
})
