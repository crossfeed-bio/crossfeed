# The two ways parameters reach R: the page pushes them to a port this package opens, or this package
# fetches them from the page (Karoline, 2026-10-03, choosing both). Base R sockets only, so installing
# this package pulls in nothing but jsonlite.

#' @noRd
http_response <- function(body, status = "200 OK", type = "application/json") {
    paste0("HTTP/1.1 ", status, "\r\n",
           "Content-Type: ", type, "\r\n",
           "Content-Length: ", nchar(body, type = "bytes"), "\r\n",
           "Connection: close\r\n\r\n", body)
}

# Read one HTTP request from a connection: the request line, the headers, and the body named by
# Content-Length. Headers are small, so they are read a byte at a time until the blank line, which keeps
# this free of any parsing library.
#' @noRd
read_request <- function(con, limit = 64e6) {
    header <- raw(0)
    repeat {
        byte <- readBin(con, "raw", 1L)
        if (!length(byte)) break
        header <- c(header, byte)
        n <- length(header)
        if (n >= 4L && identical(header[(n - 3L):n], as.raw(c(13, 10, 13, 10)))) break
        if (n > 1e6) stop_grownet("the request headers are too long to be grownet's")
    }
    lines <- strsplit(rawToChar(header), "\r\n", fixed = TRUE)[[1]]
    first <- if (length(lines)) lines[1] else ""
    named <- grep("^content-length:", lines, ignore.case = TRUE, value = TRUE)
    size <- if (length(named)) as.integer(trimws(sub("^[^:]*:", "", named[1]))) else 0L
    if (is.na(size) || size < 0 || size > limit) stop_grownet("the request body is not a size we accept")
    body <- ""
    if (size > 0) {
        body <- rawToChar(readBin(con, "raw", size))
        Encoding(body) <- "UTF-8"
    }
    list(request = first, body = body)
}

# One accepted connection: answer it, and return the parameters when it carried them.
#' @noRd
serve_one <- function(server) {
    con <- socketAccept(server, blocking = TRUE, open = "a+b", timeout = 10)
    on.exit(try(close(con), silent = TRUE), add = TRUE)
    request <- read_request(con)
    if (!grepl("^POST ", request$request)) {
        # a browser or a port scan: say what this port is, and go on waiting for the real thing
        writeBin(charToRaw(http_response(
            "this port belongs to the grownet R package; grownet posts gLV parameters to it",
            type = "text/plain")), con)
        return(NULL)
    }
    payload <- tryCatch(fromJSON(request$body, simplifyVector = FALSE), error = function(e) NULL)
    if (is.null(payload)) {
        writeBin(charToRaw(http_response("{\"received\": false, \"error\": \"not JSON\"}",
                                         status = "400 Bad Request")), con)
        return(NULL)
    }
    glv <- as_grownet_glv(payload)
    answer <- sprintf(paste0("{\"received\": true, \"organisms\": %d, \"growth_rates\": %d, ",
                             "\"placeholders\": %d, \"without_a_rate\": %d}"),
                      length(glv$organisms), sum(!is.na(glv$growth_rates)),
                      nrow(glv$caveats$placeholders), length(glv$caveats$without_a_rate))
    writeBin(charToRaw(http_response(answer)), con)
    glv
}

#' Receive gLV parameters from the grownet page
#'
#' Opens a port on this machine and waits for grownet's "Send to R" to post the parameters to it. The
#' page sends them to 127.0.0.1 and nowhere else, and this function answers one request and closes the
#' port again.
#'
#' @param port Port to listen on. The grownet page sends to 8793 unless told otherwise.
#' @param timeout Seconds to wait for the parameters before giving up.
#' @param quiet Set to `TRUE` to keep the function from printing what it is waiting for and what arrived.
#' @return The gLV parameters, an object of class `grownet_glv`. Printing it shows its caveats; see
#'   [glv_matrix()], [glv_rates()] and [as_miasim()].
#' @seealso [grownet_glv()], which fetches the same parameters when opening a port is not possible.
#' @examples
#' \dontrun{
#' glv <- grownet_listen()          # then press Send to R on the grownet page
#' glv
#' A <- glv_matrix(glv)
#' }
#' @export
grownet_listen <- function(port = 8793, timeout = 300, quiet = FALSE) {
    server <- serverSocket(port)
    on.exit(close(server), add = TRUE)
    if (!quiet) {
        message("grownet: listening on http://127.0.0.1:", port, " for up to ", timeout,
                " seconds. Press Send to R on the grownet page.")
    }
    deadline <- Sys.time() + timeout
    repeat {
        left <- as.numeric(difftime(deadline, Sys.time(), units = "secs"))
        if (left <= 0) {
            stop_grownet("no parameters arrived within ", timeout, " seconds. Start again with ",
                         "grownet_listen(), then press Send to R on the grownet page.")
        }
        if (!isTRUE(socketSelect(list(server), timeout = min(left, 1))[1])) next
        glv <- serve_one(server)
        if (is.null(glv)) next
        if (!quiet) print(glv)
        return(invisible(glv))
    }
}

#' Fetch gLV parameters from the grownet page
#'
#' Reads the parameters from the page's own address, for when opening a port is not possible. The page
#' shows the address under its gLV control; it carries the session token, so it works only on the machine
#' the page runs on.
#'
#' @param from The gLV address of a running grownet page, for example
#'   `"http://127.0.0.1:8791/glv.json?token=..."`. The path of a saved payload works too.
#' @param timeout Seconds to wait for the page.
#' @param quiet Set to `TRUE` to keep the function from printing what arrived.
#' @return The gLV parameters, an object of class `grownet_glv`.
#' @seealso [grownet_listen()], which receives them from the page's Send to R button.
#' @examples
#' \dontrun{
#' glv <- grownet_glv("http://127.0.0.1:8791/glv.json?token=PASTE_THE_TOKEN")
#' }
#' @export
grownet_glv <- function(from, timeout = 60, quiet = FALSE) {
    if (!is.character(from) || length(from) != 1 || !nzchar(from)) {
        stop_grownet("give the gLV address of a running grownet page, or the path of a saved payload")
    }
    if (grepl("^https?://", from)) {
        old <- options(timeout = timeout)
        on.exit(options(old), add = TRUE)
        connection <- base::url(from, open = "rb")
        on.exit(try(close(connection), silent = TRUE), add = TRUE)
        text <- paste(readLines(connection, warn = FALSE), collapse = "\n")
    } else {
        text <- paste(readLines(from, warn = FALSE), collapse = "\n")
    }
    glv <- as_grownet_glv(fromJSON(text, simplifyVector = FALSE))
    if (!quiet) print(glv)
    invisible(glv)
}
