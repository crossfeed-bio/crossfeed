# Taking the numbers out of the object, where the caveats are enforced rather than explained
# (Karoline, 2026-10-03): the matrix warns and names its placeholder cells, and a missing growth rate
# stops a simulation until the user supplies one.

#' The interaction matrix
#'
#' `A[i, j]` is the effect of j on i: rows are affected, columns are the actor, which is the order
#' `dx_i/dt = x_i (r_i + sum_j A[i][j] x_j)` reads in. The diagonal is -1 by convention, for
#' self-limitation.
#'
#' A cell is the log2 mean of a growth comparison, an effect size, not a fitted gLV coefficient. Some
#' cells are not measurements at all: an obligate interaction (the affected organism grows only with the
#' actor) carries +10 and an abolished one -10, because neither has a ratio, one side having not grown.
#' Those cells are named in a warning unless `placeholders` says what to do with them.
#'
#' @param x gLV parameters from [grownet_listen()] or [grownet_glv()].
#' @param placeholders What to do with the cells that hold a stated extreme: `"keep"` leaves them as
#'   they are and warns, naming them; `"na"` sets them to `NA`, so they cannot pass unnoticed into a
#'   simulation; `"zero"` sets them to 0, which reads them as no interaction.
#' @return A square numeric matrix with the organisms as its row and column names.
#' @examples
#' \dontrun{
#' A <- glv_matrix(glv)                      # warns about any placeholder cell
#' A <- glv_matrix(glv, placeholders = "na")  # or decide what they should be
#' }
#' @export
glv_matrix <- function(x, placeholders = c("keep", "na", "zero")) {
    stopifnot(inherits(x, "grownet_glv"))
    placeholders <- match.arg(placeholders)
    A <- x$interactions
    cells <- x$caveats$placeholders
    if (nrow(cells)) {
        index <- cbind(match(cells$affected, rownames(A)), match(cells$actor, colnames(A)))
        if (placeholders == "keep") {
            warning(nrow(cells), " cell(s) of this matrix are stated extremes, not measured ratios (",
                    format(x$caveats$extreme), " obligate, ", format(-x$caveats$extreme), " abolished): ",
                    cells_line(cells, with_value = TRUE),
                    ". Use glv_matrix(x, placeholders = \"na\") or \"zero\" to decide what they are.",
                    call. = FALSE)
        } else {
            A[index] <- if (placeholders == "na") NA_real_ else 0
        }
    }
    A
}

#' @rdname glv_matrix
#' @param ... Passed to [glv_matrix()].
#' @export
as.matrix.grownet_glv <- function(x, ...) glv_matrix(x, ...)

#' The growth rates
#'
#' Each organism's maximum specific growth rate in monoculture, as grownet derived it: the median over
#' the replicates and studies that have one. An organism that has none is `NA`, since a simulation needs
#' a number nobody measured here.
#'
#' @param x gLV parameters from [grownet_listen()] or [grownet_glv()].
#' @param missing A number to use for the organisms that have no rate, or `NULL` to leave them `NA`.
#'   Giving one is a choice about data that is not there, so it is never made for you.
#' @return A named numeric vector in the row order of the matrix.
#' @examples
#' \dontrun{
#' r <- glv_rates(glv)
#' r <- glv_rates(glv, missing = 0.2)   # your own number, for the organisms grownet has none for
#' }
#' @export
glv_rates <- function(x, missing = NULL) {
    stopifnot(inherits(x, "grownet_glv"))
    rates <- x$growth_rates
    if (!is.null(missing)) {
        if (!is.numeric(missing) || length(missing) != 1) stop_grownet("missing must be one number")
        rates[is.na(rates)] <- missing
    }
    rates
}

#' The README grownet wrote with these numbers
#'
#' Every convention and every caveat in grownet's own words, the same text the downloadable package
#' carries.
#'
#' @param x gLV parameters from [grownet_listen()] or [grownet_glv()].
#' @param print Set to `FALSE` to return the text without printing it.
#' @return The text, invisibly when printed.
#' @export
glv_readme <- function(x, print = TRUE) {
    stopifnot(inherits(x, "grownet_glv"))
    if (print) {
        cat(x$readme)
        return(invisible(x$readme))
    }
    x$readme
}

#' Write the parameters as files
#'
#' The same three files grownet's download holds: `interaction_matrix.csv`, `growth_rates.csv` and
#' `README.txt`, so what arrived over the wire can be kept beside the analysis that used it.
#'
#' @param x gLV parameters from [grownet_listen()] or [grownet_glv()].
#' @param dir Directory to write into. It is created when it does not exist.
#' @return The paths written, invisibly.
#' @export
glv_write <- function(x, dir) {
    stopifnot(inherits(x, "grownet_glv"))
    if (!dir.exists(dir)) dir.create(dir, recursive = TRUE)
    matrix_path <- file.path(dir, "interaction_matrix.csv")
    rates_path <- file.path(dir, "growth_rates.csv")
    readme_path <- file.path(dir, "README.txt")
    write.csv(x$interactions, matrix_path)
    write.csv(data.frame(organism = x$organisms, growth_rate = unname(x$growth_rates),
                         unit = x$growth_rate_unit, stringsAsFactors = FALSE),
              rates_path, row.names = FALSE)
    writeLines(x$readme, readme_path)
    invisible(c(matrix_path, rates_path, readme_path))
}

#' Shape the parameters for miaSim
#'
#' Returns the arguments `miaSim::simulateGLV` takes, which solves `dx/dt = x(b + Ax)`, the same order
#' this matrix is written in. miaSim is not needed to call this, and no other simulator is assumed: the
#' result is a plain list, so `do.call(miaSim::simulateGLV, c(as_miasim(glv), list(t_end = 100)))` runs
#' it, and any other model can take the same pieces.
#'
#' A simulation needs a growth rate for every organism, so this stops when one is missing, rather than
#' passing a number nobody measured. Give `missing_rate` to supply one, or drop those organisms first.
#'
#' @param x gLV parameters from [grownet_listen()] or [grownet_glv()].
#' @param x0 Starting abundances, or `NULL` to leave them to the simulator.
#' @param missing_rate A growth rate for the organisms that have none, or `NULL` to stop when any does.
#' @param placeholders What to do with the cells that hold a stated extreme, as in [glv_matrix()].
#' @return A list with `n_species`, `names_species`, `A`, `growth_rates`, and `x0` when given.
#' @examples
#' \dontrun{
#' args <- as_miasim(glv)
#' tse <- do.call(miaSim::simulateGLV, c(args, list(t_end = 100)))
#' }
#' @export
as_miasim <- function(x, x0 = NULL, missing_rate = NULL, placeholders = c("keep", "na", "zero")) {
    stopifnot(inherits(x, "grownet_glv"))
    rates <- glv_rates(x, missing = missing_rate)
    if (anyNA(rates)) {
        stop_grownet("no growth rate for ", paste(names(rates)[is.na(rates)], collapse = ", "),
                     ": a gLV simulation needs one for every organism. Give as_miasim(x, missing_rate = ) ",
                     "a number of your own, or leave those organisms out.")
    }
    A <- glv_matrix(x, placeholders = match.arg(placeholders))
    args <- list(n_species = length(x$organisms), names_species = x$organisms, A = A,
                 growth_rates = unname(rates))
    if (!is.null(x0)) args$x0 <- x0
    args
}

#' Scale the interaction strengths for a simulation
#'
#' The cells are effect sizes, log2 means of a growth comparison, and they are often larger than the -1
#' on the diagonal: a partner whose effect outweighs an organism's own self-limitation. A gLV simulation
#' run on such a matrix unchanged can grow without bound, which `deSolve` returns as `NA`. Scaling every
#' off-diagonal cell by one factor keeps their signs and their relative sizes and brings the strongest
#' one to `max_effect`.
#'
#' The factor is a free parameter, not a calibration: nothing in the growth data fixes the scale, so
#' whoever simulates chooses it, and that choice, rather than the measurements, sets where the simulation
#' settles. Report the factor you used with any result that depends on it (Craig, reviewing 0.2.0).
#'
#' This is a modeling choice, so nothing here does it for you (Karoline, 2026-10-03: "keep glv_scale off
#' by default"): the object arrives unscaled, carrying the numbers grownet derived, and this function
#' returns a copy that remembers the factor it used.
#'
#' @param x gLV parameters from [grownet_listen()] or [grownet_glv()].
#' @param max_effect The size the strongest off-diagonal cell should have. 1 makes no partner stronger
#'   than an organism's own self-limitation.
#' @return The same object with its interaction matrix scaled, carrying `scaled_by`.
#' @examples
#' \dontrun{
#' tse <- do.call(miaSim::simulateGLV, as_miasim(glv_scale(glv)))
#' }
#' @export
glv_scale <- function(x, max_effect = 1) {
    stopifnot(inherits(x, "grownet_glv"))
    if (!is.numeric(max_effect) || length(max_effect) != 1 || max_effect <= 0) {
        stop_grownet("max_effect must be one positive number")
    }
    A <- x$interactions
    off <- row(A) != col(A)
    strongest <- max(abs(A[off]), na.rm = TRUE)
    factor <- if (strongest > 0) max_effect / strongest else 1
    A[off] <- A[off] * factor
    x$interactions <- A
    x$scaled_by <- factor * if (is.null(x$scaled_by)) 1 else x$scaled_by
    x
}

# Cells stronger than the self-limitation on the diagonal, which is what makes a simulation run away.
#' @noRd
stronger_than_self <- function(x) {
    A <- x$interactions
    off <- row(A) != col(A)
    sum(abs(A[off]) > abs(x$caveats$diagonal), na.rm = TRUE)
}
