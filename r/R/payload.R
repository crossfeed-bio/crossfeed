# The gLV payload grownet sends, and the object it becomes in R.
#
# Karoline, 2026-10-03, on what this package is for: "The problem is the README: caveats such as the
# placeholders for obligates/abolished taxa have to reach the user". So the caveats travel as data
# beside the numbers, and this file is where they become part of the object rather than prose a reader
# may never open: `print` shows them every time, and `glv_matrix` and `as_miasim` act on them.

# The payload format this package reads. v2 (grownet 0.5.0) adds where each left-out effect is, the media
# of the cells and the drop-out arcs in them, and narrows each matrix's `media` to its cells'; v1 (grownet
# 0.3.0) carries fitted coefficients, one matrix per abundance unit; v0 carried one matrix of log2 effect
# sizes with -1 on the diagonal and +/-10 for a pair with no ratio. All are read, a field a version lacks
# reads as absent, and the object says whether it holds fitted coefficients (`fitted`), because what a
# cell means differs.
GLV_FORMAT <- "grownet.glv/v2"
GLV_FORMATS <- c("grownet.glv/v2", "grownet.glv/v1", "grownet.glv/v0")

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
    format <- chr(payload$format)
    if (!format %in% GLV_FORMATS) {
        warning("this payload says it is ", format, ", and this package reads ",
                paste(GLV_FORMATS, collapse = " or "), "; reading it anyway", call. = FALSE)
    }
    fitted <- !identical(format, "grownet.glv/v0")
    matrices <- if (fitted) as_matrices(payload$matrices) else list(as_one_matrix(payload))
    organisms <- unique(unlist(lapply(matrices, function(m) m$organisms), use.names = FALSE))
    rates <- rates_of(payload, organisms)
    caveats <- payload$caveats
    structure(
        list(organisms = organisms,
             fitted = fitted,
             matrices = matrices,
             # the single matrix, for the usual case of one abundance unit; NULL when there are several,
             # and glv_matrix(x, unit = ) then says which units there are
             interactions = if (length(matrices) == 1) matrices[[1]]$interactions else NULL,
             unit = if (length(matrices) == 1) chr(matrices[[1]]$unit) else "",
             growth_rates = rates,
             growth_rate_unit = chr(payload$growth_rate_unit),
             growth_rate_detail = payload$growth_rate_detail,
             caveats = list(
                 diagonal = if (fitted) chr(caveats$diagonal) else as_number(caveats$diagonal),
                 extreme = as_number(caveats$extreme),
                 absence_k = as_number(caveats$absence_k),
                 placeholders = pairs_frame(caveats$placeholders, value = TRUE),
                 censored_cells = pairs_frame(caveats$censored_cells, value = FALSE),
                 sign_conflicts = pairs_frame(caveats$sign_conflicts, value = FALSE),
                 left_out = reasons_frame(caveats$left_out),
                 # (affected, actor, why): read as reasons, the actor was dropped, so two pairs on one
                 # organism could not be told apart, and the effects in no matrix were not read at all
                 # (found in review)
                 pairs_left_out = effects_frame(caveats$pairs_left_out),
                 across_units = effects_frame(caveats$across_units),
                 arcs_left_out = effects_frame(caveats$arcs_left_out),
                 media = vapply(caveats$media, as.character, character(1)),
                 # NULL in a package from before it was written, which names only every arc's media; empty
                 # in a package whose matrices hold no effect between organisms (found in review)
                 cell_media = if (is.null(caveats$cell_media)) NULL else
                     vapply(caveats$cell_media, as.character, character(1)),
                 dropout_arcs = as_number(caveats$dropout_arcs),
                 dropout_arcs_in_cells = as_number(caveats$dropout_arcs_in_cells),
                 without_a_rate = vapply(caveats$without_a_rate, as.character, character(1)),
                 abundance_units = vapply(caveats$abundance_units, as.character, character(1)),
                 coefficients = chr(caveats$coefficients),
                 units = chr(caveats$units),
                 unbounded = chr(caveats$unbounded),
                 censored = chr(caveats$censored),
                 effect_size = chr(caveats$effect_size)),
             files = payload$files,
             readme = chr(payload$readme),
             tool = chr(payload$tool, "grownet"),
             tool_version = chr(payload$tool_version),
             derived_at = chr(payload$derived_at),
             source_db = chr(payload$source_db),
             studies = payload$studies,
             settings = payload$settings),
        class = "grownet_glv")
}

# One matrix of a v1 payload: the numbers with their organisms, unit and media.
#' @noRd
as_matrices <- function(items) {
    if (is.null(items) || !length(items)) stop_grownet("this payload carries no matrix")
    lapply(items, function(item) {
        organisms <- vapply(item$organisms, as.character, character(1))
        n <- length(organisms)
        values <- matrix(vapply(unlist(item$interactions, recursive = FALSE), as_number, numeric(1)),
                         nrow = n, ncol = n, byrow = TRUE, dimnames = list(organisms, organisms))
        list(organisms = organisms, interactions = values,
             abundance_unit = chr(item$abundance_unit), unit = chr(item$unit),
             media = vapply(item$media, as.character, character(1)), cells = as_number(item$cells),
             cells_with_unrecorded_medium = as_number(item$cells_with_unrecorded_medium))
    })
}

# A v0 payload, which carried one matrix of effect sizes at the top level.
#' @noRd
as_one_matrix <- function(payload) {
    organisms <- vapply(payload$organisms, as.character, character(1))
    n <- length(organisms)
    values <- matrix(vapply(unlist(payload$interactions, recursive = FALSE), as_number, numeric(1)),
                     nrow = n, ncol = n, byrow = TRUE, dimnames = list(organisms, organisms))
    list(organisms = organisms, interactions = values, abundance_unit = "",
         unit = "log2 of a growth comparison", media = character(0), cells = NA_real_)
}

# The growth rates in the order the organisms come, from the detail of a v1 payload or the plain vector
# of a v0 one. An organism with no rate is NA, which is what a simulation has to be told about.
#' @noRd
rates_of <- function(payload, organisms) {
    if (!is.null(payload$growth_rates) && length(payload$growth_rates)) {
        rates <- vapply(payload$growth_rates, as_number, numeric(1))
        if (length(rates) == length(organisms)) {
            names(rates) <- organisms
            return(rates)
        }
    }
    rates <- stats::setNames(rep(NA_real_, length(organisms)), organisms)
    for (entry in payload$growth_rate_detail %||% list()) {
        name <- chr(entry$organism)
        if (name %in% organisms) rates[[name]] <- as_number(entry$rate)
    }
    rates
}

#' @noRd
`%||%` <- function(x, y) if (is.null(x)) y else x

# The (thing, reason) pairs a caveat names, as a data frame.
#' @noRd
reasons_frame <- function(items) {
    if (is.null(items) || !length(items)) {
        return(data.frame(what = character(0), why = character(0), stringsAsFactors = FALSE))
    }
    data.frame(what = vapply(items, function(p) chr(p[[1]]), character(1)),
               why = vapply(items, function(p) chr(p[[length(p)]]), character(1)),
               stringsAsFactors = FALSE)
}

# The (affected, actor, reason) effects a caveat names, as a data frame.
#' @noRd
effects_frame <- function(items) {
    if (is.null(items) || !length(items)) {
        return(data.frame(affected = character(0), actor = character(0), why = character(0),
                          stringsAsFactors = FALSE))
    }
    data.frame(affected = vapply(items, function(p) chr(p[[1]]), character(1)),
               actor = vapply(items, function(p) chr(p[[2]]), character(1)),
               why = vapply(items, function(p) chr(p[[3]]), character(1)),
               stringsAsFactors = FALSE)
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
    for (block in x$matrices) {
        cat(sprintf("  %d organisms; matrix %d x %d%s\n",
                    length(block$organisms), nrow(block$interactions), ncol(block$interactions),
                    if (nzchar(block$unit)) paste0(", every cell in ", block$unit) else ""))
    }
    if (length(x$matrices) > 1) {
        # what was measured between them comes from the package's own rows (found in review)
        between <- sum(grepl("neither matrix", x$caveats$across_units$why, fixed = TRUE))
        measured <- if (between) {
            sprintf("%d effect(s) between organisms counted differently were measured and are in no matrix", between)
        } else {
            "no effect between organisms counted differently was measured"
        }
        cat(sprintf(paste0("   * one matrix per abundance unit (%s): abundances are never converted ",
                           "between units,\n       and %s. glv_matrix(x, unit = )\n       takes one.\n"),
                    paste(vapply(x$matrices, function(m) m$abundance_unit, character(1)), collapse = ", "),
                    measured))
    }
    # counted against the organisms in a matrix, and an organism without a rate is what is left out of
    # the matrices, so this read "8 of 8" for an 11-organism network while caveats$without_a_rate named
    # the other 3 (#211 item 3). The ones outside every matrix are now counted where the coverage is.
    outside <- setdiff(x$caveats$without_a_rate, x$organisms)
    cat(sprintf("  growth rates: %d of the %d organisms in a matrix%s%s\n", with_rate, length(x$organisms),
                if (nzchar(x$growth_rate_unit)) paste0(" (", x$growth_rate_unit, ")") else "",
                if (length(outside)) sprintf("; %d more in the network have none and are in no matrix",
                                             length(outside)) else ""))
    cat("  A[i, j] is the effect of j on i: rows are affected, columns are the actor.\n")
    if (x$fitted) {
        # the package's own sentence, which says what its derivation fitted: an integrated cell is not a
        # difference of two rates, and this used to state the comparison's formula for both (#142 item 6)
        said <- x$caveats$coefficients
        if (length(said) == 1L && nzchar(said)) {
            cat(paste0("  ", sub("^every", "Every", said), ".\n"))
        } else {
            # the fallback for a payload carrying no caveats: it named the comparison's direction,
            # which is wrong for an integrated package, so it names neither (#231)
            cat("  Every cell is a fitted per-capita coefficient; caveats$diagonal says what the\n")
            cat("  diagonal is under the derivation that made this package.\n")
        }
    }
    cat("  Read before you simulate:\n")
    censored <- x$caveats$censored_cells
    if (nrow(censored)) {
        cat(sprintf(paste0("   * %d cell(s) come from a comparison where one side did not grow, so one of ",
                           "the two\n       rates behind them is 0, measured: %s\n"),
                    nrow(censored), cells_line(censored)))
    }
    placeholders <- x$caveats$placeholders
    if (!x$fitted && nrow(placeholders)) {
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
        # as_miasim() stops only for one inside a matrix; the others it simulates without (found in review)
        missing <- unlist(x$caveats$without_a_rate)
        inside <- intersect(missing, x$organisms)
        if (length(inside)) {
            cat("       a simulation needs one from elsewhere for ", paste(inside, collapse = ", "),
                "; as_miasim() stops until you give it.\n", sep = "")
        }
        outside <- setdiff(missing, x$organisms)
        if (length(outside)) {
            cat("       ", paste(outside, collapse = ", "),
                " are in no matrix; as_miasim() simulates without them.\n", sep = "")
        }
    }
    left_out <- x$caveats$left_out
    if (nrow(left_out)) {
        cat(sprintf("   * %d organism(s) are in no matrix, because a coefficient of theirs could not be\n",
                    nrow(left_out)))
        for (i in seq_len(nrow(left_out))) {
            cat("       fitted: ", left_out$what[i], ": ", left_out$why[i], "\n", sep = "")
        }
    }
    # the effects the matrices hold at 0 for want of a coefficient, and those in no matrix at all, as the
    # package README lists them (found in review: R said neither)
    for (part in list(list(x$caveats$pairs_left_out, "effect(s) are left at 0 (actor on affected)"),
                      list(x$caveats$across_units, "effect(s) are in no matrix (actor on affected)"),
                      list(x$caveats$arcs_left_out,
                           "pair(s) have arcs left out of their cell, the median of the pair's other arcs (actor on affected)"))) {
        effects <- part[[1]]
        if (!is.null(effects) && nrow(effects)) {
            cat(sprintf("   * %d %s:\n", nrow(effects), part[[2]]))
            for (i in seq_len(nrow(effects))) {
                cat("       ", effects$actor[i], " on ", effects$affected[i], ": ", effects$why[i], "\n", sep = "")
            }
        }
    }
    if (!x$fitted) {
        cat("   * the cells are effect sizes (log2 means), not fitted gLV coefficients: scale them for\n")
        cat("     your model rather than using them unchanged.\n")
    }
    # the drop-out arcs in the cells where the package counts them, since one in no cell is in no
    # simulation (found in review); the network's in a package from before
    dropout <- x$caveats$dropout_arcs
    in_cells <- x$caveats$dropout_arcs_in_cells
    counted <- if (!is.null(in_cells) && !is.na(in_cells)) in_cells else dropout
    if (!is.na(counted) && counted > 0) {
        cat(sprintf(paste0("   * %d arc(s)%s come from drop-out designs, where the effect may run through a ",
                           "third\n       species; a gLV coefficient is meant to be the direct effect of ",
                           "one organism on\n       another. grownet's Include drop-out communities leaves ",
                           "them out.\n"), counted,
                    if (!is.null(in_cells) && !is.na(in_cells)) " in the cells" else ""))
    }
    print_media(x)
    steep <- stronger_than_self(x)
    if (steep && x$fitted) {
        cat(sprintf(paste0("   * %d cell(s) outweigh the organism's own limitation on the diagonal. A fit ",
                           "like that can\n       have no bounded state: the equilibrium is the solution ",
                           "of A x = -r, and a negative\n       entry there means there is none above ",
                           "zero. Scaling would hide it rather than settle it.\n"), steep))
    } else if (steep) {
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
                   # `organisms` is the matrices' count; the network's includes those with no rate
                   network_organisms = length(union(object$organisms, object$caveats$without_a_rate)),
                   fitted = object$fitted,
                   matrices = length(object$matrices),
                   with_a_rate = sum(!is.na(object$growth_rates)),
                   censored_cells = nrow(object$caveats$censored_cells),
                   placeholders = nrow(object$caveats$placeholders),
                   sign_conflicts = nrow(object$caveats$sign_conflicts),
                   left_out = object$caveats$left_out$what,
                   without_a_rate = object$caveats$without_a_rate))
}


# The media line of the print, as the package README states it: about the cells each matrix holds, since
# an arc in no cell is not in a simulation and a simulation takes one matrix. A matrix whose effects come
# from several media is warned about, one of a single medium is not, and cells whose arcs record no medium
# are named. A package written before `cell_media` names every arc's media, as it did. Found in review over
# several rounds: warnings about arcs in no cell, about two matrices of one medium each, and cells that
# record no medium left out.
#' @noRd
print_media <- function(x) {
    media <- x$caveats$media
    cells_in <- x$caveats$cell_media
    if (is.null(cells_in)) {
        if (length(media) > 1) {
            cat(sprintf(paste0("   * these arcs come from %d media, and a simulation is of one environment:\n",
                               "       %s\n       grownet's second box (media, experiments or studies) keeps ",
                               "one.\n"),
                        length(media), paste(media, collapse = ", ")))
        } else if (length(media) == 1) {
            cat(sprintf("   * every arc was measured in one medium: %s\n", media))
        }
        return(invisible(NULL))
    }
    held <- Filter(function(m) isTRUE(m$cells > 0), x$matrices)
    if (!length(held)) {
        if (length(media)) {
            cat("   * no effect between organisms is in the matrices; the network's arcs, in no cell, come from ",
                paste(media, collapse = ", "), "\n", sep = "")
        }
        return(invisible(NULL))
    }
    unrecorded <- function(m) if (isTRUE(m$cells_with_unrecorded_medium > 0)) m$cells_with_unrecorded_medium else 0
    # a recorded medium beside cells recording none is not a second medium (found in review)
    one <- function(m) {
        if (length(m$media) && unrecorded(m)) {
            sprintf("%s, and %d cell(s) with an arc recording no medium, so whether they share it is not recorded",
                    m$media, unrecorded(m))
        } else if (length(m$media)) m$media else "no medium recorded"
    }
    if (!any(vapply(held, function(m) length(m$media) > 1, logical(1)))) {
        if (length(held) == 1) {
            m <- held[[1]]
            if (length(m$media) && !unrecorded(m)) {
                cat(sprintf("   * every effect between organisms was measured in one medium: %s\n", m$media))
            } else if (length(m$media)) {
                cat(sprintf("   * the effects between organisms were measured in %s\n", one(m)))
            } else {
                cat("   * the effects between organisms in the matrices record no medium\n")
            }
        } else {
            cat("   * each matrix's effects between organisms come from at most one recorded medium, and a simulation takes one matrix:\n")
            for (m in held) cat("       ", m$abundance_unit, ": ", one(m), "\n", sep = "")
        }
    } else {
        cat("   * a matrix's effects come from more than one medium, and a simulation is of one environment:\n")
        for (m in held) {
            parts <- c(m$media, if (unrecorded(m)) sprintf("%d cell(s) with an arc recording no medium", unrecorded(m)))
            cat("       ", m$abundance_unit, " matrix: ", paste(parts, collapse = ", "), "\n", sep = "")
        }
        cat("       grownet's second box (media, experiments or studies) keeps one.\n")
    }
    others <- setdiff(media, cells_in)
    if (length(others)) {
        cat(sprintf("     the network's other arcs, in no cell, come from %s\n", paste(others, collapse = ", ")))
    }
    invisible(NULL)
}
