test_that("taking the matrix warns and names the cells that are not measurements", {
    expect_warning(glv_matrix(example_glv()), "stated extremes")
    expect_warning(glv_matrix(example_glv()), "C on B")
})

test_that("the placeholders can be turned into NA or 0 deliberately, and then nothing warns", {
    expect_silent(A <- glv_matrix(example_glv(), placeholders = "na"))
    expect_true(is.na(A["B", "C"]))
    expect_equal(A["B", "A"], 1.5)                 # the measured cells are untouched
    expect_silent(zeroed <- glv_matrix(example_glv(), placeholders = "zero"))
    expect_equal(zeroed["B", "C"], 0)
})

test_that("a missing growth rate stops a simulation instead of passing unnoticed", {
    expect_error(as_miasim(example_glv()), "no growth rate for C")
    args <- suppressWarnings(as_miasim(example_glv(), missing_rate = 0.3))
    expect_equal(args$n_species, 3L)
    expect_equal(args$names_species, c("A", "B", "C"))
    expect_equal(args$growth_rates, c(0.4, 0.2, 0.3))
    expect_equal(args$A["B", "A"], 1.5)
    expect_null(args$x0)
})

test_that("the README and the files travel with the numbers", {
    glv <- example_glv()
    expect_match(glv_readme(glv, print = FALSE), "generalized Lotka-Volterra")
    dir <- file.path(tempdir(), "glv-test")
    on.exit(unlink(dir, recursive = TRUE))
    written <- suppressWarnings(glv_write(glv, dir))
    expect_true(all(file.exists(written)))
    expect_equal(basename(written),
                 c("interaction_matrix.csv", "growth_rates.csv", "README.txt"))
})

test_that("scaling brings the strongest cell down without changing signs or relative sizes", {
    glv <- example_glv()
    scaled <- glv_scale(glv, max_effect = 1)
    A <- suppressWarnings(glv_matrix(scaled))
    off <- row(A) != col(A)
    expect_equal(max(abs(A[off])), 1)                 # the strongest cell is now the self-limitation
    expect_equal(A["B", "A"] / A["B", "C"], 1.5 / 10) # and the cells keep their ratio to each other
    expect_equal(diag(A), c(A = -1, B = -1, C = -1))  # the diagonal is untouched
    expect_equal(scaled$scaled_by, 1 / 10)
})

test_that("a matrix that can run away says so when it is printed", {
    text <- paste(capture.output(print(example_glv())), collapse = "\n")
    expect_match(text, "stronger than the -1 on the diagonal")
    expect_match(text, "glv_scale")
    # and after scaling it no longer does
    quiet <- paste(capture.output(print(glv_scale(example_glv()))), collapse = "\n")
    expect_false(grepl("can grow without bound", quiet))
})
