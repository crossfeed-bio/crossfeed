\name{glv_write}
\alias{glv_write}
\title{Write the parameters as files}
\usage{
glv_write(x, dir)
}
\arguments{
\item{x}{gLV parameters from \code{\link{grownet_listen}} or \code{\link{grownet_glv}}.}

\item{dir}{Directory to write into. It is created when it does not exist.}
}
\value{
The paths written, invisibly.
}
\description{
The files grownet's download holds: one \code{interaction_matrix.<abundance unit>.csv} per
abundance unit (plain \code{interaction_matrix.csv} when the unit is unknown),
\code{growth_rates.csv} with the same columns the download's has, and \code{README.txt}, so what
arrived over the wire can be kept beside the analysis that used it.
}
