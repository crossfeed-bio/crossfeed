test_that("the matrix arrives in the order the formula reads: rows affected, columns the actor", {
    glv <- example_glv()
    A <- suppressWarnings(glv_matrix(glv))
    expect_equal(dim(A), c(3L, 3L))
    expect_equal(rownames(A), c("A", "B", "C"))
    expect_equal(A["B", "A"], 1.5)        # A affects B by +1.5
    expect_equal(A["A", "B"], 0)          # and nothing says B affects A
    expect_equal(diag(A), c(A = -1, B = -1, C = -1))
})

test_that("an organism without a growth rate arrives as NA, not as a number nobody measured", {
    rates <- glv_rates(example_glv())
    expect_equal(rates, c(A = 0.4, B = 0.2, C = NA_real_))
    expect_equal(glv_rates(example_glv(), missing = 0.1)[["C"]], 0.1)
})

test_that("the caveats arrive as data, not only as text", {
    caveats <- example_glv()$caveats
    expect_equal(caveats$placeholders$actor, "C")
    expect_equal(caveats$placeholders$value, 10)
    expect_equal(caveats$sign_conflicts$affected, "C")
    expect_equal(caveats$without_a_rate, "C")
    expect_equal(caveats$extreme, 10)
})

test_that("printing says every caveat without being asked", {
    text <- paste(capture.output(print(example_glv())), collapse = "\n")
    expect_match(text, "stated extremes, not measured ratios")
    expect_match(text, "C on B \\(10\\)")
    expect_match(text, "disagree in sign")
    expect_match(text, "no growth rate: C")
    expect_match(text, "effect sizes")
    expect_match(text, "rows are affected, columns are the actor")
})

test_that("a payload of another format is read but says so", {
    payload <- example_payload()
    payload$format <- "grownet.glv/v9"
    expect_warning(grownet:::as_grownet_glv(payload), "this package reads")
})
