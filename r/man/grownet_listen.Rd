\name{grownet_listen}
\alias{grownet_listen}
\title{Receive gLV parameters from the grownet page}
\usage{
grownet_listen(port = 8793, timeout = 300, quiet = FALSE)
}
\arguments{
\item{port}{Port to listen on. The grownet page sends to 8793 unless told otherwise.}

\item{timeout}{Seconds to wait for the parameters before giving up.}

\item{quiet}{Set to \code{TRUE} to keep the function from printing what it is waiting for and what
arrived.}
}
\value{
The gLV parameters, an object of class \code{grownet_glv}. Printing it shows its caveats; see
\code{\link{glv_matrix}}, \code{\link{glv_rates}} and \code{\link{as_miasim}}.
}
\description{
Opens a port on this machine and waits for grownet's "Send to R" to post the parameters to it. The page
sends them to 127.0.0.1 and nowhere else, and this function answers one request and closes the port
again.
}
\examples{
\dontrun{
glv <- grownet_listen()
glv
A <- glv_matrix(glv)
}
}
\seealso{
\code{\link{grownet_glv}}, which fetches the same parameters when opening a port is not possible.
}
