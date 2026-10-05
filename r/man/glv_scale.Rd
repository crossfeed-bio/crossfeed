\name{glv_scale}
\alias{glv_scale}
\title{Scale the interaction strengths for a simulation}
\usage{
glv_scale(x, max_effect = 1)
}
\arguments{
\item{x}{gLV parameters from \code{\link{grownet_listen}} or \code{\link{grownet_glv}}.}

\item{max_effect}{The size the strongest off-diagonal cell should have. 1 makes no partner stronger than
an organism's own self-limitation.}
}
\value{
The same object with its interaction matrix scaled, carrying \code{scaled_by}.
}
\description{
The cells are effect sizes, log2 means of a growth comparison, and they are often larger than the -1 on
the diagonal: a partner whose effect outweighs an organism's own self-limitation. A gLV simulation run on
such a matrix unchanged can grow without bound, which \code{deSolve} returns as \code{NA}. Scaling every
off-diagonal cell by one factor keeps their signs and their relative sizes and brings the strongest one
to \code{max_effect}.
}
\details{
The factor is a free parameter, not a calibration: nothing in the growth data fixes the scale, so whoever
simulates chooses it, and that choice, rather than the measurements, sets where the simulation settles.
Report the factor you used with any result that depends on it (Craig, reviewing 0.2.0).

This is a modeling choice, so nothing here does it for you (Karoline, 2026-10-03: "keep glv_scale off by
default"): the object arrives unscaled, carrying the numbers grownet derived, and this function returns a
copy that remembers the factor it used.
}
\examples{
\dontrun{
tse <- do.call(miaSim::simulateGLV, as_miasim(glv_scale(glv)))
}
}
