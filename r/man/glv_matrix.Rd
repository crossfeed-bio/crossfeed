\name{glv_matrix}
\alias{glv_matrix}
\alias{as.matrix.grownet_glv}
\title{The interaction matrix}
\usage{
glv_matrix(x, placeholders = c("keep", "na", "zero"))

\method{as.matrix}{grownet_glv}(x, ...)
}
\arguments{
\item{x}{gLV parameters from \code{\link{grownet_listen}} or \code{\link{grownet_glv}}.}

\item{placeholders}{What to do with the cells that hold a stated extreme: \code{"keep"} leaves them as
they are and warns, naming them; \code{"na"} sets them to \code{NA}, so they cannot pass unnoticed into
a simulation; \code{"zero"} sets them to 0, which reads them as no interaction.}

\item{...}{Passed to \code{glv_matrix}.}
}
\value{
A square numeric matrix with the organisms as its row and column names.
}
\description{
\code{A[i, j]} is the effect of j on i: rows are affected, columns are the actor, which is the order
\code{dx_i/dt = x_i (r_i + sum_j A[i][j] x_j)} reads in. The diagonal is -1 by convention, for
self-limitation.
}
\details{
A cell is the log2 mean of a growth comparison, an effect size, not a fitted gLV coefficient. Some cells
are not measurements at all: an obligate interaction (the affected organism grows only with the actor)
carries +10 and an abolished one -10, because neither has a ratio, one side having not grown. Those
cells are named in a warning unless \code{placeholders} says what to do with them.
}
\examples{
\dontrun{
A <- glv_matrix(glv)
A <- glv_matrix(glv, placeholders = "na")
}
}
