\name{glv_matrix}
\alias{glv_matrix}
\alias{as.matrix.grownet_glv}
\title{The interaction matrix}
\usage{
glv_matrix(x, unit = NULL, placeholders = c("keep", "na", "zero"))

\method{as.matrix}{grownet_glv}(x, ...)
}
\arguments{
\item{x}{gLV parameters from \code{\link{grownet_listen}} or \code{\link{grownet_glv}}.}

\item{unit}{The abundance unit of the matrix wanted, for example \code{"Cells/mL"}. Only needed when the
parameters hold more than one, which happens when the organisms were counted in different units; the
error then names the units it has.}

\item{placeholders}{What to do with the cells that hold a stated extreme, in parameters old enough to
have them: \code{"keep"} leaves them as they are and warns, naming them; \code{"na"} sets them to
\code{NA}; \code{"zero"} sets them to 0, which reads them as no interaction. Fitted parameters have no
such cells, so the argument does nothing for them.}

\item{...}{Passed to \code{glv_matrix}.}
}
\value{
A square numeric matrix with the organisms as its row and column names.
}
\description{
\code{A[i, j]} is the effect of j on i: rows are affected, columns are the actor, which is the order
\code{dx_i/dt = x_i (r_i + sum_j A[i][j] x_j)} reads in.
}
\details{
Every cell is a fitted per-capita coefficient, in 1 over (time times abundance): the diagonal is
\code{-r_i / K_i} with K the organism's own plateau. What an off-diagonal cell is depends on the
derivation that made the package, and \code{print(x)} says which: the comparison of replicate sets fits
\code{(r_with - r_without) / x_j}, the difference between the affected organism's growth rate with the
actor and without it over the actor's abundance across that window, while the integrated form, the
default since 0.3.0, fits the whole row from the measured time course as a parameter of
\code{ln(x_i(T) / x_i(0)) = r_i T + sum_j A[i][j] integral(x_j dt)}. Nothing in it is a convention
either way, and nothing needs scaling to match the rest.

Abundances are never converted between units, so organisms counted in different units are in different
matrices and \code{unit} says which one to take. A cell whose comparison had one side that did not grow
is still a measurement, one of its two rates being 0, and \code{print(x)} names those cells.

Parameters from grownet 0.2.0 or earlier carry log2 effect sizes with -1 on the diagonal and +/-10 where
no ratio existed. This package reads them too, and \code{print(x)} says which kind it holds.
}
\examples{
\dontrun{
A <- glv_matrix(glv)
A <- glv_matrix(glv, unit = "Cells/mL")
}
}
