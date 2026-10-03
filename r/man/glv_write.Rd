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
The same three files grownet's download holds: \code{interaction_matrix.csv},
\code{growth_rates.csv} and \code{README.txt}, so what arrived over the wire can be kept beside the
analysis that used it.
}
