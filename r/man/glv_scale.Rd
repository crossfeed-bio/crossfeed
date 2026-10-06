\name{glv_scale}
\alias{glv_scale}
\title{Scale the interaction strengths for a simulation}
\usage{
glv_scale(x, max_effect = 1, unit = NULL)
}
\arguments{
\item{x}{gLV parameters from \code{\link{grownet_listen}} or \code{\link{grownet_glv}}.}

\item{max_effect}{The size the strongest off-diagonal cell should have.}

\item{unit}{The abundance unit of the matrix to scale, as in \code{\link{glv_matrix}}. Only needed when
the parameters hold more than one matrix.}
}
\value{
The same object with that matrix scaled, carrying \code{scaled_by}.
}
\description{
Scaling every off-diagonal cell by one factor keeps their signs and their relative sizes and brings the
strongest one to \code{max_effect}.
}
\details{
**Fitted parameters do not need this.** Their cells are per-capita coefficients in 1 over (time times
abundance), the same units as the diagonal they sit beside, so nothing about them asks for scaling, and
this function warns when it is called on them. A fit whose cells outweigh the organisms' own limitations
has no bounded state, and scaling hides that rather than settling it: the equilibrium of a fit is the
solution of \code{A x = -r}, and a negative entry there means there is none above zero.

It stays for the parameters of grownet 0.2.0 or earlier, whose cells are log2 effect sizes and are often
larger than the -1 on their diagonal, where a simulation run on them unchanged can grow without bound
and \code{deSolve} returns \code{NA}.

The factor is a free parameter, not a calibration: nothing in the growth data fixes the scale, so whoever
simulates chooses it, and that choice, rather than the measurements, sets where the simulation settles.
Report the factor you used with any result that depends on it (Craig, reviewing 0.2.0). Nothing here does
it for you (Karoline, 2026-10-03: "keep glv_scale off by default").
}
\examples{
\dontrun{
tse <- do.call(miaSim::simulateGLV, as_miasim(glv))
}
}
