\name{as_miasim}
\alias{as_miasim}
\title{Shape the parameters for miaSim}
\usage{
as_miasim(x, x0 = NULL, missing_rate = NULL, placeholders = c("keep", "na", "zero"))
}
\arguments{
\item{x}{gLV parameters from \code{\link{grownet_listen}} or \code{\link{grownet_glv}}.}

\item{x0}{Starting abundances, or \code{NULL} to leave them to the simulator.}

\item{missing_rate}{A growth rate for the organisms that have none, or \code{NULL} to stop when any
does.}

\item{placeholders}{What to do with the cells that hold a stated extreme, as in
\code{\link{glv_matrix}}.}
}
\value{
A list with \code{n_species}, \code{names_species}, \code{A}, \code{growth_rates}, and \code{x0} when
given.
}
\description{
Returns the arguments \code{miaSim::simulateGLV} takes, which solves \code{dx/dt = x(b + Ax)}, the same
order this matrix is written in. miaSim is not needed to call this, and no other simulator is assumed:
the result is a plain list, so \code{do.call(miaSim::simulateGLV, c(as_miasim(glv), list(t_end = 100)))}
runs it, and any other model can take the same pieces.
}
\details{
A simulation needs a growth rate for every organism, so this stops when one is missing, rather than
passing a number nobody measured. Give \code{missing_rate} to supply one, or drop those organisms first.
}
\examples{
\dontrun{
args <- as_miasim(glv)
tse <- do.call(miaSim::simulateGLV, c(args, list(t_end = 100)))
}
}
