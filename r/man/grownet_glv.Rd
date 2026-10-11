\name{grownet_glv}
\alias{grownet_glv}
\title{Fetch gLV parameters from the grownet page}
\usage{
grownet_glv(from, timeout = 60, quiet = FALSE)
}
\arguments{
\item{from}{The gLV address of a running grownet page, for example
\code{"http://127.0.0.1:8791/glv.json?token=...&job=..."}, which the page prints under the gLV
parameters control: copy it from there rather than typing it, because the page prints this address with its own `&job=` and that is the one to paste: without a job the server answers whichever search was looked at last, which with two tabs open is a different system's parameters (#251).
The path of a saved payload works too.}

\item{timeout}{Seconds to wait for the page.}

\item{quiet}{Set to \code{TRUE} to keep the function from printing what arrived.}
}
\value{
The gLV parameters, an object of class \code{grownet_glv}.
}
\description{
Reads the parameters from the page's own address, for when opening a port is not possible. The page
shows the address under its gLV control; it carries the session token, so it works only on the machine
the page runs on.
}
\examples{
\dontrun{
glv <- grownet_glv("http://127.0.0.1:8791/glv.json?token=PASTE_THE_TOKEN&job=PASTE_THE_JOB")
}
}
\seealso{
\code{\link{grownet_listen}}, which receives them from the page's Send to R button.
}
