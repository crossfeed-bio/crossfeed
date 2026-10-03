# The gLV payload grownet sends, and the object it becomes in R.
#
# Karoline, 2026-10-03, on what this package is for: "The problem is the README: caveats such as the
# placeholders for obligates/abolished taxa have to reach the user". So the caveats travel as data
# beside the numbers, and this file is where they become part of the object rather than prose a reader
# may never open: `print` shows them every time, and `glv_matrix` and `as_miasim` act on them.

GLV_FORMAT <- "grownet.glv/v0"

#' @noRd
stop_grownet <- function(...) stop(paste0(...), call. = FALSE)

#' @noRd
as_number <- function(x) {
    if (is.null(x)) NA_real_ else as.numeric(x)
}

#' @noRd
chr <- function(x, default = "") {
    if (is.null(x) || !length(x)) default else as.character(x)[1]
}

# A payload (a list parsed from JSON, never simplified, so a null stays a null) to the object this
# package works with.
#' @noRd
as_grownet_glv <- function(payload) {
    if (!is.list(payload) || is.null(payload$format)) {
        stop_grownet("this is not a grownet gLV payload: it has no format field")
    }
    if (!identical(chr(payload$format), GLV_FORMAT)) {
        warning("this payload says it is ", chr(payload$format), ", and this package reads ", GLV_FORMAT,
                "; reading it anyway", call. = FALSE)
    }
    organisms <- vapply(payload$organisms, as.character, character(1))
    n <- length(organisms)
    interactions <- matrix(
        vapply(unlist(payload$interactions, recursive = FALSE), as_number, numeric(1)),
        nrow = n, ncol = n, byrow = TRUE, dimnames = list(organisms, organisms))
    rates <- vapply(payload$growth_rates, as_number, numeric(1))
    names(rates) <- organisms
    caveats <- payload$caveats
    structure(
        list(organisms = organisms,
             interactions = interactions,
             growth_rates = rates,
             growth_rate_unit = chr(payload$growth_rate_unit),
             growth_rate_detail = payload$growth_rate_detail,
             caveats = list(
                 diagonal = as_number(caveats$diagonal),
                 extreme = as_number(caveats$extreme),
                 absence_k = as_number(caveats$absence_k),
                 placeholders = pairs_frame(caveats$placeholders, value = TRUE),
                 sign_conflicts = pairs_frame(caveats$sign_conflicts, value = FALSE),
                 without_a_rate = vapply(caveats$without_a_rate, as.character, character(1)),
                 effect_size = chr(caveats$effect_size)),
             readme = chr(payload$readme),
             tool = chr(payload$tool, "grownet"),
             tool_version = chr(payload$tool_version),
             derived_at = chr(payload$derived_at),
             source_db = chr(payload$source_db),
             studies = payload$studies,
             settings = payload$settings),
        class = "grownet_glv")
}

# The cells a caveat names, as a data frame, so a user can subset or loop over them.
#' @noRd
pairs_frame <- function(items, value) {
    if (is.null(items) || !length(items)) {
        empty <- data.frame(affected = character(0), actor = character(0), stringsAsFactors = FALSE)
        if (value) {
            empty$value <- numeric(0)
            empty$outcome <- character(0)
        }
        return(empty)
    }
    frame <- data.frame(
        affected = vapply(items, function(p) as.character(p$affected), character(1)),
        actor = vapply(items, function(p) as.character(p$actor), character(1)),
        stringsAsFactors = FALSE)
    if (value) {
        frame$value <- vapply(items, function(p) as_number(p$value), numeric(1))
        frame$outcome <- vapply(items, function(p) chr(p$outcome), character(1))
    }
    frame
}

#' @noRd
cells_line <- function(frame, with_value = FALSE, limit = 6) {
    shown <- seq_len(min(nrow(frame), limit))
    text <- paste0(frame$actor[shown], " on ", frame$affected[shown],
                   if (with_value) paste0(" (", format(frame$value[shown], trim = TRUE), ")") else "")
    if (nrow(frame) > limit) text <- c(text, paste0("and ", nrow(frame) - limit, " more"))
    paste(text, collapse = ", ")
}

#' Print gLV parameters and their caveats
#'
#' The caveats are shown every time, because a number that is a stated extreme rather than a measured
#' ratio has to reach whoever simulates with it.
#'
#' @param x gLV parameters from [grownet_listen()] or [grownet_glv()].
#' @param ... Ignored.
#' @return `x`, invisibly.
#' @export
print.grownet_glv <- function(x, ...) {
    cat(sprintf("gLV parameters from %s %s, derived %s from %s\n",
                x$tool, x$tool_version, x$derived_at, x$source_db))
    with_rate <- sum(!is.na(x$growth_rates))
    cat(sprintf("  %d organisms; interaction matrix %d x %d, diagonal %s\n",
                length(x$organisms), nrow(x$interactions), ncol(x$interactions),
                format(x$caveats$diagonal)))
    cat(sprintf("  growth rates: %d of %d organisms%s\n", with_rate, length(x$organisms),
                if (nzchar(x$growth_rate_unit)) paste0(" (", x$growth_rate_unit, ")") else ""))
    cat("  A[i, j] is the effect of j on i: rows are affected, columns are the actor.\n")
    cat("  Read before you simulate:\n")
    placeholders <- x$caveats$placeholders
    if (nrow(placeholders)) {
        cat(sprintf("   * %d cell(s) are stated extremes, not measured ratios (%s obligate, %s abolished):\n",
                    nrow(placeholders), format(x$caveats$extreme), format(-x$caveats$extreme)))
        cat("       ", cells_line(placeholders, with_value = TRUE), "\n", sep = "")
    }
    conflicts <- x$caveats$sign_conflicts
    if (nrow(conflicts)) {
        cat(sprintf("   * %d pair(s) left at 0 because their arcs disagree in sign: %s\n",
                    nrow(conflicts), cells_line(conflicts)))
    }
    if (length(x$caveats$without_a_rate)) {
        cat(sprintf("   * %d organism(s) have no growth rate: %s\n",
                    length(x$caveats$without_a_rate), paste(x$caveats$without_a_rate, collapse = ", ")))
        cat("       a simulation needs one from elsewhere; as_miasim() stops until you give it.\n")
    }
    cat("   * the cells are effect sizes (log2 means), not fitted gLV coefficients: scale them for\n")
    cat("     your model rather than using them unchanged.\n")
    steep <- stronger_than_self(x)
    if (steep) {
        cat(sprintf(paste0("   * %d cell(s) are stronger than the %s on the diagonal, so a simulation on ",
                           "these numbers\n       unchanged can grow without bound and come back as NA. ",
                           "glv_scale(x) brings them down.\n"),
                    steep, format(x$caveats$diagonal)))
    }
    cat("  glv_matrix(x) takes the matrix, glv_rates(x) the rates, glv_readme(x) the full text.\n")
    invisible(x)
}

#' Summarize gLV parameters
#'
#' @param object gLV parameters from [grownet_listen()] or [grownet_glv()].
#' @param ... Ignored.
#' @return A list with the counts and the caveats, invisibly; printing it shows the same as [print()].
#' @export
summary.grownet_glv <- function(object, ...) {
    print(object)
    invisible(list(organisms = length(object$organisms),
                   with_a_rate = sum(!is.na(object$growth_rates)),
                   placeholders = nrow(object$caveats$placeholders),
                   sign_conflicts = nrow(object$caveats$sign_conflicts),
                   without_a_rate = object$caveats$without_a_rate))
}
