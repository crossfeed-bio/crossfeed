\name{glv_rates}
\alias{glv_rates}
\title{The growth rates}
\usage{
glv_rates(x, missing = NULL)
}
\arguments{
\item{x}{gLV parameters from \code{\link{grownet_listen}} or \code{\link{grownet_glv}}.}

\item{missing}{A number to use for the organisms that have no rate, or \code{NULL} to leave them
\code{NA}. Giving one is a choice about data that is not there, so it is never made for you.}
}
\value{
A named numeric vector in the row order of the matrix.
}
\description{
Each organism's maximum specific growth rate in monoculture, as grownet derived it: the median over the
replicates and studies that have one. An organism that has none is \code{NA}, since a simulation needs a
number nobody measured here.
}
\examples{
\dontrun{
r <- glv_rates(glv)
r <- glv_rates(glv, missing = 0.2)
}
}
