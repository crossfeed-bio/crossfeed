test_that("the listener takes a posted payload and answers what it received", {
    skip_on_cran()
    port <- 8795L
    payload <- jsonlite::toJSON(example_payload(), auto_unbox = TRUE, null = "null")
    # the POST is sent from a background process, so the listener can run in this one
    script <- tempfile(fileext = ".R")
    writeLines(c(
        sprintf("Sys.sleep(1); con <- socketConnection('127.0.0.1', %d, open = 'a+b', blocking = TRUE)", port),
        "body <- readLines(commandArgs(trailingOnly = TRUE)[1], warn = FALSE)",
        "body <- paste(body, collapse = '')",
        paste0("request <- paste0('POST /grownet/glv HTTP/1.1\\r\\nHost: 127.0.0.1\\r\\n",
               "Content-Type: application/json\\r\\nContent-Length: ', nchar(body, type = 'bytes'),",
               " '\\r\\n\\r\\n', body)"),
        "writeBin(charToRaw(request), con)",
        "answer <- rawToChar(readBin(con, 'raw', 4096))",
        "close(con)",
        "writeLines(answer, paste0(commandArgs(trailingOnly = TRUE)[1], '.answer'))"), script)
    body_file <- tempfile(fileext = ".json")
    writeLines(as.character(payload), body_file)
    on.exit(unlink(c(script, body_file, paste0(body_file, ".answer"))), add = TRUE)
    system2(file.path(R.home("bin"), "Rscript"), c(script, body_file), wait = FALSE,
            stdout = NULL, stderr = NULL)

    glv <- grownet_listen(port = port, timeout = 30, quiet = TRUE)
    expect_s3_class(glv, "grownet_glv")
    expect_equal(glv$organisms, c("A", "B", "C"))
    expect_equal(suppressWarnings(glv_matrix(glv))["B", "A"], 1.5)
    # and the sender was told what arrived, so grownet can report it on its page
    for (i in 1:50) {
        if (file.exists(paste0(body_file, ".answer"))) break
        Sys.sleep(0.1)
    }
    answer <- paste(readLines(paste0(body_file, ".answer"), warn = FALSE), collapse = "")
    expect_match(answer, "\"received\": true")
    expect_match(answer, "\"organisms\": 3")
    expect_match(answer, "\"without_a_rate\": 1")
})

test_that("a saved payload can be read from a file, which is the fetch path without a page", {
    file <- tempfile(fileext = ".json")
    on.exit(unlink(file))
    writeLines(as.character(jsonlite::toJSON(example_payload(), auto_unbox = TRUE, null = "null")), file)
    glv <- grownet_glv(file, quiet = TRUE)
    expect_equal(glv$organisms, c("A", "B", "C"))
    expect_equal(glv$caveats$without_a_rate, "C")
})
