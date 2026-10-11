# Taking the numbers out of the object, where the caveats are enforced rather than explained
# (Karoline, 2026-10-03): the matrix warns and names its placeholder cells, and a missing growth rate
# stops a simulation until the user supplies one.

#' The interaction matrix
#'
#' `A[i, j]` is the effect of j on i: rows are affected, columns are the actor, which is the order
#' `dx_i/dt = x_i (r_i + sum_j A[i][j] x_j)` reads in.
#'
#' Every cell is a fitted per-capita coefficient, in 1 over (time times abundance): the diagonal is
#' `-r_i / K_i` with K the organism's own plateau. What an off-diagonal cell is depends on the derivation
#' that made the package, and `print(x)` says which: the comparison of replicate sets fits
#' `(r_with - r_without) / x_j`, the difference between the affected organism's growth rate with the
#' actor and without it over the actor's abundance across that window, while the integrated form, which
#' gLV mode selects, fits the whole row from the measured time course as a parameter of
#' `ln(x_i(T) / x_i(0)) = r_i T + sum_j A[i][j] integral(x_j dt)`. Nothing in it is a convention either
#' way, and nothing needs scaling to match the rest.
#'
#' Abundances are never converted between units, so organisms counted in different units are in
#' different matrices and `unit` says which one to take. A cell whose comparison had one side that did
#' not grow is still a measurement, one of its two rates being 0, and `print(x)` names those cells.
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
glv_matrix <- function(x, unit = NULL, placeholders = c("keep", "na", "zero")) {
    stopifnot(inherits(x, "grownet_glv"))
    placeholders <- match.arg(placeholders)
    A <- chosen_matrix(x, unit)$interactions
    cells <- if (x$fitted) x$caveats$placeholders[0, , drop = FALSE] else x$caveats$placeholders
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

# The matrix a call means: the only one, or the one for `unit`. With several and no choice, the error
# names the units, because nothing is ever converted between them (#120).
#' @noRd
chosen_matrix <- function(x, unit = NULL) {
    units <- vapply(x$matrices, function(m) m$abundance_unit, character(1))
    if (is.null(unit)) {
        if (length(x$matrices) == 1) return(x$matrices[[1]])
        stop_grownet("these parameters hold ", length(x$matrices),
                     " matrices, one per abundance unit (", paste(units, collapse = ", "),
                     "), because abundances are never converted between units. Name one, for example ",
                     "glv_matrix(x, unit = \"", units[1], "\").")
    }
    at <- match(unit, units)
    if (is.na(at)) {
        stop_grownet("no matrix in ", unit, "; these parameters hold ", paste(units, collapse = ", "))
    }
    x$matrices[[at]]
}

#' The growth rates
#'
#' Each organism's maximum specific growth rate in monoculture, as grownet derived it: the median over
#' the replicates and studies that have one. An organism that has none is `NA`, since a simulation needs
#' a number nobody measured here.
#'
#' @param x gLV parameters from [grownet_listen()] or [grownet_glv()].
#' @param unit The abundance unit of the matrix whose organisms are wanted, as in [glv_matrix()]. Only
#'   needed when the parameters hold more than one matrix.
#' @param missing A number to use for the organisms that have no rate, or `NULL` to leave them `NA`.
#'   Giving one is a choice about data that is not there, so it is never made for you.
#' @return A named numeric vector in the row order of the matrix.
#' @examples
#' \dontrun{
#' r <- glv_rates(glv)
#' r <- glv_rates(glv, missing = 0.2)   # your own number, for the organisms grownet has none for
#' }
#' @export
glv_rates <- function(x, unit = NULL, missing = NULL) {
    stopifnot(inherits(x, "grownet_glv"))
    organisms <- chosen_matrix(x, unit)$organisms
    rates <- x$growth_rates[organisms]
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
    written <- character(0)
    for (block in x$matrices) {
        name <- if (nzchar(block$abundance_unit)) {
            paste0("interaction_matrix.", gsub("[^A-Za-z0-9_.-]", "_",
                                               gsub("/", "_per_", block$abundance_unit)), ".csv")
        } else {
            "interaction_matrix.csv"
        }
        path <- file.path(dir, name)
        write.csv(block$interactions, path)
        written <- c(written, path)
    }
    rates_path <- file.path(dir, "growth_rates.csv")
    write.csv(data.frame(organism = x$organisms, growth_rate = unname(x$growth_rates),
                         unit = x$growth_rate_unit, stringsAsFactors = FALSE),
              rates_path, row.names = FALSE)
    readme_path <- file.path(dir, "README.txt")
    writeLines(x$readme, readme_path)
    written <- c(written, rates_path, readme_path)
    for (name in names(x$files %||% list())) {
        extra <- file.path(dir, name)
        writeLines(as.character(x$files[[name]]), extra)
        written <- c(written, extra)
    }
    invisible(written)
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
as_miasim <- function(x, unit = NULL, x0 = NULL, missing_rate = NULL,
                      placeholders = c("keep", "na", "zero")) {
    stopifnot(inherits(x, "grownet_glv"))
    organisms <- chosen_matrix(x, unit)$organisms
    rates <- glv_rates(x, unit = unit, missing = missing_rate)
    if (anyNA(rates)) {
        stop_grownet("no growth rate for ", paste(names(rates)[is.na(rates)], collapse = ", "),
                     ": a gLV simulation needs one for every organism. Give as_miasim(x, missing_rate = ) ",
                     "a number of your own, or leave those organisms out.")
    }
    A <- glv_matrix(x, unit = unit, placeholders = match.arg(placeholders))
    args <- list(n_species = length(organisms), names_species = organisms, A = A,
                 growth_rates = unname(rates))
    if (!is.null(x0)) args$x0 <- x0
    args
}

#' Scale the interaction strengths for a simulation
#'
#' Scaling every off-diagonal cell by one factor keeps their signs and their relative sizes and brings
#' the strongest one to `max_effect`.
#'
#' **Fitted parameters do not need this.** Their cells are per-capita coefficients in 1 over (time times
#' abundance), the same units as the diagonal they sit beside, so nothing about them asks for scaling,
#' and this function warns when it is called on them. A fit whose cells outweigh the organisms' own
#' limitations has no bounded state, and scaling hides that rather than settling it: the equilibrium of
#' a fit is the solution of `A x = -r`, and a negative entry there means there is none with every
#' organism above zero.
#'
#' It stays for the parameters of grownet 0.2.0 or earlier, whose cells are log2 effect sizes and are
#' often larger than the -1 on their diagonal, where a simulation run on them unchanged can grow without
#' bound and `deSolve` returns `NA`.
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
#' @param unit The abundance unit of the matrix to scale, as in [glv_matrix()]. Only needed when the
#'   parameters hold more than one matrix.
#' @return The same object with its interaction matrix scaled, carrying `scaled_by`.
#' @examples
#' \dontrun{
#' tse <- do.call(miaSim::simulateGLV, as_miasim(glv_scale(glv)))
#' }
#' @export
glv_scale <- function(x, max_effect = 1, unit = NULL) {
    stopifnot(inherits(x, "grownet_glv"))
    if (!is.numeric(max_effect) || length(max_effect) != 1 || max_effect <= 0) {
        stop_grownet("max_effect must be one positive number")
    }
    if (isTRUE(x$fitted)) {
        warning("these are fitted coefficients, in ", chosen_matrix(x, unit)$unit,
                ", so nothing about their units asks for scaling. Scaling them is a modeling choice ",
                "that moves where the simulation settles, and it hides an unbounded fit rather than ",
                "settling it: the equilibrium is the solution of A x = -r.", call. = FALSE)
    }
    at <- if (is.null(unit) && length(x$matrices) == 1) 1 else {
        match(chosen_matrix(x, unit)$abundance_unit,
              vapply(x$matrices, function(m) m$abundance_unit, character(1)))
    }
    A <- x$matrices[[at]]$interactions
    off <- row(A) != col(A)
    strongest <- max(abs(A[off]), na.rm = TRUE)
    factor <- if (strongest > 0) max_effect / strongest else 1
    A[off] <- A[off] * factor
    x$matrices[[at]]$interactions <- A
    if (length(x$matrices) == 1) x$interactions <- A
    x$scaled_by <- factor * if (is.null(x$scaled_by)) 1 else x$scaled_by
    x
}

# Cells stronger than the self-limitation on the diagonal, which is what makes a simulation run away.
#' @noRd
stronger_than_self <- function(x) {
    total <- 0
    for (block in x$matrices) {
        A <- block$interactions
        off <- row(A) != col(A)
        own <- abs(diag(A))
        if (x$fitted) {
            # each cell against the limitation of the organism it acts on, which is that row's diagonal
            limit <- matrix(own, nrow = nrow(A), ncol = ncol(A))
            total <- total + sum(abs(A[off]) > limit[off], na.rm = TRUE)
        } else {
            total <- total + sum(abs(A[off]) > abs(x$caveats$diagonal), na.rm = TRUE)
        }
    }
    total
}
