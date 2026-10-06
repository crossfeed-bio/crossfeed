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
gLV parameters from grownet 0.3.0, derived 2026-10-06T12:00:00+02:00 from mGrowthDB (live)
  3 organisms; matrix 3 x 3, every cell in 1/(h x Cells/mL)
  growth rates: 3 of 3 organisms (1/h)
  A[i, j] is the effect of j on i: rows are affected, columns are the actor.
  Every cell is a fitted per-capita coefficient: the diagonal is -r_i / K_i and an
  off-diagonal cell is (r_with - r_without) / x_j. Nothing here is a convention.
  Read before you simulate:
   * 1 cell(s) come from a comparison where one side did not grow, so one of the two
       rates behind them is 0, measured: Blautia hydrogenotrophica on Roseburia intestinalis
   * 1 pair(s) left at 0 because their arcs disagree in sign: Roseburia intestinalis L1-82 on ...
   * 1 cell(s) outweigh the organism's own limitation on the diagonal. A fit like that can
       have no bounded state: the equilibrium is the solution of A x = -r, and a negative
       entry there means there is none above zero. Scaling would hide it rather than settle it.
```

Every cell is in 1 over (time times abundance), so the numbers are per-capita coefficients rather than
effect sizes. Organisms counted in different abundance units are in **different matrices**, because
nothing is ever converted between units, and `glv_matrix(x, unit = )` takes one. The parameters of
grow**net** 0.2.0 and earlier carried log2 effect sizes with -1 on the diagonal; this package still reads
them and `print(x)` says which kind it holds.

| Function | What it does |
| --- | --- |
| `glv_matrix(x)` | the interaction matrix; `unit = ` picks one when the organisms were counted in more than one abundance unit, and the error names the units it has |
| `glv_rates(x)` | the growth rates of that matrix's organisms, `NA` where grow**net** has none; `missing =` fills them with a number of yours |
| `glv_scale(x)` | one factor over the off-diagonal cells. Unnecessary for fitted coefficients, and it warns and says why; it stays for the effect-size parameters of 0.2.0 and earlier |
| `as_miasim(x)` | the arguments `miaSim::simulateGLV` takes, stopping when an organism has no growth rate |
| `glv_readme(x)` | grow**net**'s own README, every formula in its own words |
| `glv_write(x, dir)` | the files the download holds, one matrix per abundance unit, written beside your analysis |

## Simulating

miaSim is suggested, never required; any simulator takes the same pieces.

```r
args <- as_miasim(glv)
# miaSim simulates with stochasticity and migration on (stochastic = TRUE, migration_p = 0.01).
# For the deterministic model, call it yourself with stochastic = FALSE and migration_p = 0.
tse <- do.call(miaSim::simulateGLV, c(args, list(x0 = rep(0.1, args$n_species))))

x <- SummarizedExperiment::assay(tse)          # one row per organism, one column per time point
matplot(t(x), type = "l", lty = 1, xlab = "time", ylab = "abundance")
legend("topleft", legend = rownames(x), lty = 1, col = seq_len(nrow(x)), bty = "n")
```

`simulateGLV` solves dx/dt = x(b + Ax), which is the order this matrix is written in: `A[i, j]` is the
effect of j on i.

## License

Apache 2.0, with the rest of grownet.
