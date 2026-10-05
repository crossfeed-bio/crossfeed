\name{print.grownet_glv}
\alias{print.grownet_glv}
\alias{summary.grownet_glv}
\title{Print gLV parameters and their caveats}
\usage{
\method{print}{grownet_glv}(x, ...)

\method{summary}{grownet_glv}(object, ...)
}
\arguments{
\item{x, object}{gLV parameters from \code{\link{grownet_listen}} or \code{\link{grownet_glv}}.}

\item{...}{Ignored.}
}
\value{
\code{x}, invisibly, and for \code{summary} a list of the counts and the caveats.
}
\description{
The caveats are shown every time, because a number that is a stated extreme rather than a measured ratio
has to reach whoever simulates with it: which cells are placeholders, which pairs were left at 0 for
disagreeing in sign, which organisms have no growth rate, and that the cells are effect sizes rather
than fitted coefficients.
}
