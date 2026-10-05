# grownet for R

Receives generalized Lotka-Volterra parameters from [grownet](https://github.com/crossfeed-bio/crossfeed),
the tool that derives microbial interaction networks from mGrowthDB growth curves, and hands them to any
simulator or to your own code.

```r
install.packages("remotes")
remotes::install_github("crossfeed-bio/crossfeed", subdir = "r")
```

It needs R 4.1 or later and jsonlite. Nothing else: the listener uses base R sockets.

**If the install answers `HTTP error 404`** on this public repository, a GitHub token stored on the machine
is being used and cannot see it (a fine-grained token answers 404 for everything outside its scope).
Installing from a clone needs no GitHub access at all:

```r
remotes::install_local("<the repository>/r")
```

From a terminal, in a clone, `R CMD INSTALL r` does the same without remotes.

## Receiving the parameters

Run grow**net**'s local page (`grownet gui`), press **gLV mode** beside All, search, and then, in R:

```r
library(grownet)
glv <- grownet_listen()     # then choose Get gLV parameters, Send to R on the page
```

`grownet_listen()` takes one parameter set and returns it, printing a summary of what arrived, so you
always see when a new set has come in and superseded the one before. Run it again before each send,
including after restarting grow**net**, whose new run has its own address and token.

When a port cannot be opened, read the same parameters from the page instead, at the address it shows
under the gLV control:

```r
glv <- grownet_glv("http://127.0.0.1:8791/glv.json?token=PASTE_THE_TOKEN")
```

## What arrives, and what it hides

Printing the object shows the caveats every time, because numbers that are not measurements have to reach
whoever simulates with them:

```
gLV parameters from grownet 0.1.1, derived 2026-10-03T22:35:36+02:00 from mGrowthDB (live)
  3 organisms; interaction matrix 3 x 3, diagonal -1
  growth rates: 3 of 3 organisms (1/h)
  A[i, j] is the effect of j on i: rows are affected, columns are the actor.
  Read before you simulate:
   * 1 pair(s) left at 0 because their arcs disagree in sign: Roseburia intestinalis L1-82 on ...
   * the cells are effect sizes (log2 means), not fitted gLV coefficients: scale them for
     your model rather than using them unchanged.
   * 4 cell(s) are stronger than the -1 on the diagonal, so a simulation on these numbers
       unchanged can grow without bound and come back as NA. glv_scale(x) brings them down.
```

| Function | What it does |
| --- | --- |
| `glv_matrix(x)` | the interaction matrix, warning about and naming the cells that hold a stated extreme (+10 obligate, -10 abolished); `placeholders = "na"` or `"zero"` converts them |
| `glv_rates(x)` | the growth rates, `NA` where grow**net** has none; `missing =` fills them with a number of yours |
| `glv_scale(x)` | one factor over the off-diagonal cells, so the strongest is no stronger than the self-limitation on the diagonal |
| `as_miasim(x)` | the arguments `miaSim::simulateGLV` takes, stopping when an organism has no growth rate |
| `glv_readme(x)` | grow**net**'s own README, every convention in its own words |
| `glv_write(x, dir)` | the three files the download holds, written beside your analysis |

## Simulating

miaSim is suggested, never required; any simulator takes the same pieces.

```r
args <- as_miasim(glv_scale(glv))
tse <- do.call(miaSim::simulateGLV, c(args, list(x0 = rep(0.1, args$n_species))))

x <- SummarizedExperiment::assay(tse)          # one row per organism, one column per time point
matplot(t(x), type = "l", lty = 1, xlab = "time", ylab = "abundance")
legend("topleft", legend = rownames(x), lty = 1, col = seq_len(nrow(x)), bty = "n")
```

`simulateGLV` solves dx/dt = x(b + Ax), which is the order this matrix is written in: `A[i, j]` is the
effect of j on i.

## License

Apache 2.0, with the rest of grownet.
