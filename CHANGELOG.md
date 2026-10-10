# Changelog

All notable changes to grownet (called crossfeed before 0.1.0) are recorded here. The format follows Keep
a Changelog. A released version is a promise about content: a tagged version is never reused for changed
content.

## [Unreleased]

### Fixed
- **A download could hand over a different search's network** (#189). Every output a reader takes away
  (the four download formats, the report, the rates, the gLV package, Send to Cytoscape) is looked up by
  the `job` in the request, and a request naming a search the server no longer had fell through to the
  **most recently viewed** result instead. The page refused the same id and said so, while the download did not:
  HTTP 200, the ordinary filename, and somebody else's matrix inside. Searches are pruned after twenty
  (`KEPT_JOBS`), so a tab left open while you work in another meets it without doing anything unusual. A
  request that names a search the server cannot produce is now refused, with the same words the page
  uses; naming no search at all still means the latest one, which is what that fallback is for.
- **A study with no `uploadedAt` was cached forever** (#190). The stamp was read with
  `data.get("uploadedAt", "")`, so a missing or blank one became `""`, which compares equal to itself on
  every later run: the freshness check said "current" forever and a revised study was never read again.
  The guarantee the whole cache rests on was satisfied vacuously, and for exactly the studies whose
  version nothing can establish. `null` was already safe; a missing key and a blank string now behave the
  same way, and nothing is kept for such a study.
- **A redirect from mGrowthDB was read as a growth curve** (#191). `_send` raised only on 4xx and 5xx, and
  `http.client` does not follow redirects as the `urllib.request` opener it replaced did, so a 3xx body,
  which is empty, reached `json.loads`. The command line has no handler for that and told the user **their
  own file** was not valid JSON, with the exit code for a user error and no status on the error. Anything
  that is not a representation now raises the client's own error, carrying its status, and it is not
  retried, since a redirect does not become a representation by asking again.
- **The page's Example gave an empty network** (Karoline, 2026-10-09, the day 0.3.0 was released). Two
  causes, both of them in the button rather than in the derivation.
  **It inherited whatever settings were in the form.** Pressing gLV mode and then Example ran the example
  in gLV mode, which turns drop-out communities off; pressing the gLV example and then Example ran it with
  that example's study still in the second box, so it searched one study that holds neither species.
  Either gave no interactions, and nothing on the page said why. The Example now puts **every setting back
  to its default** and says so, which is what a button that shows the tool working has to do.
  **And its two species no longer have an arc between them under the shipped default.** What those two
  hold is a drop-out comparison inside a three-member community, and the integrated form does not fit a
  row from a community of three or more, so the default derivation has nothing to report for the pair.
  The example is now the three organisms that are actually grown together, which is the smallest change
  that keeps the biology and the studies: measured live, **three arcs over three organisms against none**.
  The worked example in the README, the command line's help and the help page moved with it.
- **The release-date guard failed on every pull request from the morning after a release.** It reads
  `__version__`, finds that section in the changelog, and refuses a date earlier than the tree's newest
  commit, which is what catches a release dated before the work it contains (#155 item 8). After the
  release, `__version__` still names the version that shipped and its section is still dated, so every
  commit of the next cycle is newer than that date and the check failed on work that has nothing to do
  with it. It asks the question only while the tree is the release being prepared now, and stops once
  `## [Unreleased]` has content, which is what `RELEASING.md` says to start when work continues. A tag
  would say it exactly, but `actions/checkout` fetches none, so a tag-based check would pass on a
  developer's machine and skip in CI.

## [0.3.0] (2026-10-09)

### Upgrading
- **The default derivation is now the integrated form** (`--derivation integrated`, Karoline,
  2026-10-06): each organism's row is fitted from its whole time course rather than from a difference of
  two separately fitted growth rates divided by one partner mean. It is the form published work fits for
  this purpose, and the difference form's coefficient carries the organism's own density as a confound,
  which no number of replicates removes. The specified comparison of replicate sets is unchanged and is
  one setting away, `--derivation replicate`, and it is what a sparsely sampled study can still give: the
  integrated form needs a time course, so a study measured at two or three points now yields nothing by
  default and the page says which setting to change.
- **The network format id moves to `grownet.interaction_network/v3`** (#121, Craig's agent's trace, and
  #155 item 1). It moved twice inside this release, `/v1` to `/v2` to `/v3`, because each step added
  optional arc fields and **a field addition moves the id whether or not the id it moves from was
  released**. No release carries `/v2`; a reader still accepts it, and `grownet validate` names it. The
  rest of this entry is why the first move happened.
  Files from 0.1.x (`/v0`) and 0.2.x (`/v1`) stay valid and `grownet validate` still names the version it
  read. The id is what `published.fresh` checks before an installed copy uses the daily All network, and
  #118 added optional arc fields that an installed 0.2.0 cannot build, because it builds each arc from
  every field a document carries. Under the unchanged id that copy would have accepted the next daily
  artifact and then raised inside the All button, with the derive-live fallback never reached. With the id
  moved it reads the artifact as a format it does not know and derives live, which is what the fallback is
  for. A reader of its own is unaffected: nothing an older field means has changed, and the new fields are
  optional. Two readers are hardened with it: **every** record kind now drops a field it does not know
  rather than raising, nodes and studies as well as arcs, and any failure to read the published network
  means derive live.
- **Reinstall the R companion package** when you upgrade: `remotes::install_github("crossfeed-bio/crossfeed", subdir = "r")`.
  A 0.2.0 R package reads no organisms out of a 0.3.0 payload. Send to R now says so and names that
  command rather than reporting a successful send into an empty matrix.
- **A gLV package now states where its matrix settles**, and says plainly when it settles nowhere with
  every organism above zero. Nothing about the coefficients changed because of it; the equilibrium was
  always the solution of `A x = -r` and the reader had to work it out.

### Added
- **What the data cannot settle is listed on its own, in `docs/LIMITATIONS.md`** (Karoline on 2026-10-08:
  "if p-val computation is indefensible, we do not report p-values and comment on the weakness"). Six
  questions, each with what is not known, what grownet publishes instead of a number that would imply it
  was settled, what would settle it, and what it blocks, which is nothing in every case: the held
  monoculture rate, whether a fitted growth rate is plausible, what the absence threshold means inside a
  matrix, which partner abundance a coefficient is divided by, when a culture has reached stationary
  phase, and whether a gLV model describes these communities at all. It states the rule the rest of the
  tool already follows, that where the data cannot settle a question grownet publishes the measurement and
  names the weakness, and it is linked from the README and the help page. A seventh entry, added after
  Craig's agent read the first six, is the most general and the one with an open issue of its own: **the
  tool never establishes a mechanism.** A non-zero coefficient cannot tell a metabolite handed over from a
  pH shift, from competition for a shared resource, or from one organism sparing another a cost, and a
  perfect fit leaves that exactly where it was. It is Karoline's own reason for #71, the naming question,
  and the output already says effect rather than route: `facilitation` means the target grew more with the
  source, and nothing in a file or on the page claims a mechanism.
- **The statistics are labeled as support, and an arc says what its test assumed.** The p-value and the
  q-value decide nothing and never did: the status comes from the absence threshold and the q-value filter
  is off unless you set it. The help page now says that where the fields are described, and adds the third
  reason the p-value does not decide, which is specific to the default derivation: its null assumes the
  organism grew at its monoculture rate in the co-culture, and no growth curve in these designs measures
  whether it did. So the report prints, beside the q-value, how large an error in that rate would explain
  the arc away, and a new caution **`rate_unchecked`** marks an arc whose organism has one matched
  monoculture set in its study, where nothing checks that assumption at all. 7 of 16 live arcs carry it;
  the other 9 carry the measured lower bound instead.
- **An arc's error carries a third component: which monoculture set stage 1 was given** (#155 item 1,
  Karoline on 2026-10-08, taking Craig's agent's recommendation). The condition matcher resolves a
  monoculture set per co-culture experiment, so one organism in one study can enter two arcs with two
  different stage-1 rates: on SMGDB00000007 *Roseburia* enters one arc at 0.5091 /h and another at 0.6521,
  17 per cent apart. Each arc took its own as though the other did not exist. The spread of those selected
  rates is now a measured third variance component, `se_rate_selection`, with the spread itself in
  `rate_selection_spread` and both named in the arc's notes with the rates behind them. **It moves `se`,
  `sd`, `p_value` and the degrees of freedom only**: `strength`, the effect and the status stay as fitted,
  because the point estimate is what it is and the confidence in it was what was overstated. It needs no
  number from the reader. On the live corpus **9 of 16 arcs widen** and one loses significance at
  `q < 0.05` (3 arcs to 2); no arc changes status. It is a **lower bound** on what an arc assumes, since
  the gap each arc takes on trust is between a monoculture and a co-culture the monocultures were never
  grown in, and the notes say so. Where two arcs of one organism took nearly the same rate and still imply
  mismatches of opposite sign, the arc says that too: they cannot both be the rate being wrong, so for at
  least one the implied mismatch is growth that depends on the partner. No live arc meets that condition
  today. The spread is the **sample** standard deviation of those rates, which the field description and
  the method notes now say rather than leaving it to the choice of function (Craig's agent on #177): which
  sets a study holds and which one each arc was matched to is one realisation of a matching, so they are a
  sample rather than the whole population, and the population form would be narrower by a factor of 1.41
  where two sets were selected.
- **Every growth rate is published with the doubling time it implies** (#173, Karoline on 2026-10-08).
  `ln(2) / r` in the time unit of the rate, as the appended `doubling_time` column of `growth_rates.csv`
  and beside each rate in the report. No stage of the derivation asks whether a rate is plausible: the
  guards are identifiability, model fit, growth above zero and the fit against the interaction-free null,
  and a rate's magnitude is never questioned. Of 123 live monoculture fits that pass every guard, three
  imply a doubling slower than 24 hours and all three are from one study, where `0.0147 /h` reads as a
  number and 47 hours reads as a mistake. This catches nothing automatically and is not a guard; it puts
  the fit in front of the reader who can catch it. The column is appended, so a reader parsing that file
  by column index is unaffected.
- **A censored cell of the plain adjacency matrix is `NA`, and its bound travels on the arc** (#129,
  Karoline on 2026-10-08). A pair whose only arcs are obligate or abolished has no log2 ratio, because one
  side did not grow. Such a cell used to hold +/-10 by convention, and within this release it briefly held
  the measured bound the no-growth rule puts on that side. It now holds **`NA`**: measured on the live
  corpus, 11 of the 12 bounds land inside the range of the quantified arcs and 7 below their median, so a
  bound printed in a cell sorts among the ratios rather than past them, and nothing in a CSV cell can say
  that a number is a floor rather than a measurement, which is the same objection that retired +/-10. `NA`
  is what R reads as not a number, where 0 would read as no interaction about the strongest effect in the
  set. The bound itself is unchanged and is on the arc (`strength_bound`, `bound_rule`): the report prints
  it with its rule, the page names every cell left `NA` beside the download, and `matrix.bounded_cells`
  gives the listing as data. The three censored cells whose rule bounds nothing away from zero now read
  `NA` too, where they fell through to 0. **A reader of the matrix must handle `NA`**, and a pair left at 0
  for disagreeing in sign is still 0, named as a conflict.
- **What a study holds is kept between runs and reused while its `uploadedAt` is unchanged** (#182).
  Until now every run read everything again: a corpus run sends 3738 requests (2195 bioreplicate records,
  930 series, 559 experiments, 54 studies) and a single study 153. The rule was that measurements are read
  fresh, because mGrowthDB serves only the latest version of a study; what makes keeping them safe is that
  a study's `uploadedAt` moves whenever it is revised, which **Karoline confirmed for the mGrowthDB team**:
  "uploadedAt is kept fresh", and "it's coupled to study submission". So responses go to the user's own cache
  directory (`GROWNET_CACHE` moves it, `--no-cache` keeps nothing, never inside the repository), each file
  carrying the study and the stamp it was read at; **the study record is always read live**, because it is
  the check; and a stamp that has moved drops everything kept for that study. Measured live on
  SMGDB00000007: a first run sends 153 requests and a second sends **1**, deriving the same network. The
  **command line's** report says how much was read, how much was reused, and which studies were read again
  because their stamp moved, and those two counts are now incremented under the same lock as the rest of
  the shared state, since one client serves six worker threads and `x += 1` is three steps (Craig's agent
  on #185); an undercounted reuse makes a network look fresher than it is. **The page's report does not
  carry that line yet** (#187): the page keeps the kept responses and the speed, and says nothing about
  either, which is a gap in the reporting and not in the caching. The daily All workflow is unaffected,
  since its runners keep nothing.
- **Each arc says what both sides of its comparison were inoculated at** (#81, Karoline on 2026-10-08).
  mGrowthDB's `inoculumConcentration` is empty in every experiment checked and its descriptions state a
  starting density unsystematically, so the number is taken from the first measured abundance, which the
  curves always carry. The note gives both sides and the factor between them, and says plainly when that
  factor is above 3, so a reader can see that an arc rests on a monoculture started several times denser
  than its co-culture. It is **reported and never matched on**: across the comparisons the tool makes the
  two sides agree to a median of 1.17 times and differ by more than 3 times in 6 of 39, and those six are
  a choice about how to start a co-culture rather than a confound, so putting a starting density in the
  condition key would discard measurements. On the live All network **all 12 arcs carry the note and the
  warning fires on 4 of them**, the largest being a co-culture started 7.43 times thinner than the
  monocultures it is compared with.

### Changed
- **A monoculture fit is refused for model failure rather than for the rate's sign** (#160, Karoline on
  2026-10-08, taking Craig's agent's option 2). A non-negative `A_ii` is no self-limitation: the fit
  implies no plateau and an unbounded culture, which is the direct answer to whether the model describes
  the curve. The old guard read the sign of the rate, which on SMGDB00000006's *S. thermophilus* kept the
  one replicate of three whose rate happened to land above zero while all three had fitted a **positive**
  self-limitation; because only a near-zero positive survives such a cut, the survivor is biased toward
  zero by construction, which produced a published rate of 0.0109 /h, a 64 hour doubling time for a dairy
  starter. A non-positive rate is still refused.
  Three things move on the live corpus. *S. thermophilus* loses its rate, so SMGDB00000006 yields a
  one-organism matrix rather than a pair. *A. tumefaciens*'s rate moves from 0.1022 to **0.1579 /h**,
  because two of its three replicates had fitted tiny positive self-limitations and were contributing to
  the median unnoticed. And the All network goes from 14 arcs to 12: the two lost are
  *L. delbrueckii* -> *S. thermophilus* (q 0.024, which was significant) and
  *Comamonas* -> *A. tumefaciens* in metalworking fluid (q 0.064, which was not). **A significant arc is
  withdrawn**, and that is the point rather than a cost: it rested on a rate of 0.0109 /h that only a
  sign cut on the wrong statistic had kept.

### Removed
- **The retired `BaselineDeriver` is gone** (#139). It was the placeholder grownet shipped before either
  real derivation existed: one summarized `growthRate` per culture, `log2(co / mono)` with a fixed
  deadband, no replicates, no spread, no test. It had been off the default path since #34 and reachable
  only through `--deriver`, and the seam it was built to demonstrate now holds two real derivations.
  `interactions_from_experiments`, `_strain_growth`, `DEADBAND` and the baseline's own method label go
  with it, each having had no other caller. Nothing user-facing changes: no default path and no
  documented workflow used it, and `derive SMGDB00000004 --live` gives the same network as before, to the
  byte apart from its two timestamps. What it did is recorded in `docs/METHOD_NOTES.md`, where the
  register's `[baseline]` tags say which option the first implementation took in each menu.

### Fixed
- **The release check refuses a release date that is not the day of the tag** (found while preparing
  0.3.0). A date in the past passed every check: the future-date guard does not see it, and the agreement
  guard compares the changelog with `CITATION.cff`, which have nothing to disagree about while the
  changelog says `(unreleased)` and gives no date. 0.3.0 sat in exactly that state, with `CITATION.cff`
  naming the day it was prepared, and tagged later that date would have shipped as the release date, as one
  release's date was carried into the next before. The check now asks that both files name the day the tag
  is cut, with one day of slack for a tag pushed just after UTC midnight from a tree prepared the evening
  before, and it says what to do. It is a release-day rule only: preparing a tree with an older date is
  not a problem.
- **A black-holed IPv6 address no longer costs 17 seconds on every connection** (found with the sibling
  tool foodnet on the same network, 2026-10-09). mGrowthDB publishes an AAAA and an A record, and on some
  networks the IPv6 address is a black hole: measured at KU Leuven, it never answers and the operating
  system takes **17.5 seconds** to say so, while IPv4 connects in 14 milliseconds. `getaddrinfo` returns
  IPv6 first and `http.client` walks the addresses in that order with the full timeout on each, so every
  new connection paid it, once per worker thread in a cold run. Now an unproven address family gets three
  seconds and the next family is tried as soon as it fails, and the family that answered is remembered for
  the rest of the process, so only the first connection can wait at all. **Nothing forces IPv4**: a network
  with only IPv6 is served as before, because the order is a preference and both families are still tried.
  Measured end to end on the whole corpus: a cold `derive --all --live --no-published` went from **368
  seconds to 113**, deriving a network identical apart from its timestamps. Overriding `connect()` to
  choose the address meant writing the TLS handshake out again, and it handed the certificate check the
  host rather than the tunnel target, which is the wrong name through a proxy (Craig's agent on #184).
  Nothing in grownet configures a proxy, so the branch is unreachable and nothing was ever verified
  against the wrong name; it now computes that name the way `http.client` computes it, so the only
  difference from the base class is the address choice, and a test holds the override to it.
- **Send to Cytoscape carries the parts of an arc's error, which it did not** (found by a round trip
  through Cytoscape 3.10.4, 2026-10-09). `se_replicates` and `se_rate_stage` have been in the file and in
  GraphML since 0.3.0 was being prepared, and `se_rate_selection` and `rate_selection_spread` since #155
  item 1, and none of the four reached the Cytoscape edge table: that payload names every field it sends,
  so a field added anywhere else stops there. A reader in Cytoscape could style or filter on the total
  `se` and not on which stage it came from. All four are sent now and declared as columns, so an arc with
  no value for one leaves the cell empty rather than reading as zero. The test that checks a column is not
  declared twice now reads the list from the sender rather than repeating it, which is what let this
  through: the list in the test was shorter than the list in the code and nothing compared the two.
  **That guard was still the wrong direction, and the right one found sixteen more** (Craig's agent on
  #181): comparing the test's list with the sender's cannot see a sender that is short, which is what
  happened. GraphML's key table and the Cytoscape payload both answer "what do we emit for an arc", so
  they are compared with each other, and the payload was missing the **gLV coefficient**, its error, its
  unit and its count, the fit's `r2`, null `r2` and condition number, the monoculture stage's method and
  count, the partner-abundance count, the target's capacity with its unit and count, the rule behind a
  censored arc's bound, and the derivation method. All sixteen are sent now, and `evidence` is the one
  field that travels under another name, as the interaction column Cytoscape merges parallel edges on,
  which the test checks rather than excuses. The column declaration was completed the same way: it held 18
  of the 33 numbers an arc may lack, so a network whose arcs carry no capacity arrived with no
  `target_capacity` column at all. Measured by the same round trip, the edge table goes from **47 columns
  to 64**.
- **Fifteen smaller things, from the two reviews** (#142 items 10, 14 and 15). A reader drops a field it
  does not know for **nodes and studies** as well as edges, so the 0.2.0-against-0.3.0 failure is no
  longer armed for the next release that adds one. The shipped JSON Schema and the model agreed in
  neither direction, which nothing asserted: `merged_arcs`, `strength_range`, `supporting_pairs` and
  `merged_pairs` were emitted and undeclared, and a test now closes the loop for all three record kinds.
  `grownet validate` names a key the format does not declare, which is the only place a misspelling can
  be caught now that the reader drops it. `_least_squares` scores its stage about zero, since the model
  has no intercept, and its docstring says its condition number is of the normal equations and not of the
  design, which differ by a square. A co-culture replicate refused for too few usable points says that,
  rather than the informational window note that replaced the real cause 196 times over the corpus.
  `rbridge.send`'s refusal tells the reader to run `grownet_listen()` again, which "send again" needed
  and did not say. `check_release.py` reads `r/DESCRIPTION`, which RELEASING.md calls the only signal an
  installed R copy is out of date, and runs **on every build** with no tag, in `make check` and in CI,
  instead of firing first when somebody pushes the tag. The drop-out setting says it applies to the
  comparison of replicate sets only, since the default derivation refuses a community of three or more,
  and the prefetch no longer reads those designs under the default. The one-unit-per-organism invariant
  is re-checked in `matrix.py` rather than assumed, with the comment pointing at `derive` where it is
  enforced, and `plateaus()` names a plateau it leaves out instead of dropping it on a bare `continue`.
  GraphML carries the absence rule and its threshold, the suppressed counts and the test the derivation
  ran, so an edge marked absent can be read against the `k` that marked it on the route Cytoscape uses,
  along with the fit's null R2 and the two halves of its standard error. The eight `meta` keys that said
  "a promise of the format" say what is true instead, that a current derivation writes them and their
  meaning is fixed, since a `required` list would break older artifacts. And a test asserts that the
  package's matrix CSV and `/glv.json` carry the same numbers to four significant digits, which the
  README now states, since the CSV is `.4g` and the payload is the raw float.
- **A row the package publishes is now the row that was fitted** (#142 item 7). An organism whose fit
  implies no plateau was given the measured one *after* its partners had been fitted against the fitted
  self-limitation, so the published row satisfied no equation anyone had fitted and its R2 and condition
  number described a row that was not published: on *S. thermophilus* the self term moved by 2.24 times
  the whole partner coefficient the row's claim rested on, and in the opposite direction, and the
  substitution manufactured an equilibrium in which that organism settles at twice the plateau that was
  substituted in. It was not condition-matched either: on SMGDB00000013 it gave ancestral
  *A. tumefaciens* the evolved line's plateau, 56 times the ancestral organism's own. The substitution
  now happens before the partners are fitted, from the monocultures of the co-culture's own condition, and
  `capacity_source` says where every diagonal came from, in the report, the rates CSV and the payload. The
  second pass that re-read every study's monocultures to substitute afterwards is gone, with the crawl it
  cost.
- **A lag the Baranyi fit found and the guards discarded is no longer dropped in silence** (#142 item 8).
  A lag at least half the run was discarded, which is the case where it matters most, and the fit then
  paid for the flat start by trading the rate against the self-limitation: on a seven-point curve with a
  7.97 h lag it returned a rate 31 times below the project's own estimator, a positive self-limitation, an
  R2 of 0.909 and a condition number of 13, so every published gate passed it. A lag shorter than one
  sampling interval cannot move the window and is not used either (56 of the 193 lags used were below
  1e-6 h). Both guards now say what they did, a monoculture replicate whose lag was discarded for being
  half the run is refused rather than contributing a rate, and an arc whose organism's own limitation came
  out not negative carries a note saying it has no row in any matrix and why.
- **An equilibrium is not printed from a matrix too ill-conditioned to solve** (#142 item 9). It was
  solved with no condition estimate at all, `steady.solve`'s only test being an absolute pivot below
  1e-300, and printed to four significant digits with a categorical verdict: a near-singular block
  returned a number like 1e24 and had it reported as a steady state, and a change of 0.05 percent in one
  coefficient flipped the verdict. `steady.condition_of` now measures it, nothing above 1e8 is printed,
  the reason is given instead, and where an equilibrium is printed its condition number is printed beside
  it. The fit's R2 is scored over the replicates stage 2 actually used, since a replicate the fit never
  saw could otherwise discard a whole organism, and the interaction-free null is published beside it
  (`fit_null_r2`), so a reader sees how much the partners bought: on study 7's rows, 0.542 against
  -17.825 on one and 0.956 against 0.718 on another.
- **A crash that took out a whole derivation** (#142 item 12, traced by Craig's agent on #134).
  `design` leaves a partner with no curve out of the columns, since a column of zeros would claim it was
  absent rather than unmeasured, so a replicate's rows are as wide as that replicate's own partners,
  while the pooled fallback in `two_stage` asked for the union of partners across replicates.
  `_least_squares` indexed past the short rows and raised `IndexError`, which nothing caught: the call
  sits inside the loop over every target organism in every experiment, so one organism in one experiment
  ended the run for all of them. The shape is ordinary: monocultures of A with co-cultures A+B and A+C,
  which is pairwise co-culture in a community of three. Only replicates that measured the same partners
  are pooled now, the largest such set being used and every other named in the report, because padding
  the short rows with zeros would reintroduce the claim `design` refuses and dropping a partner's column
  would claim it had no effect at all.

### Upgrading
- **The strict medium rule now decides every match, not only the capacity** (Karoline, 2026-10-07: "the
  strict medium matching (exclusion of cases with modifications e.g. mucin addition) should be applied
  everywhere where medium matching is done"). `conditions` compares the compartment records, and
  mGrowthDB states a supplement, an added sugar or a removed carbon source only in the **description**,
  which `media.identity` reads and `conditions` does not. So `conditions` alone put chemically different
  experiments under one key: on SMGDB00000014 a single `conditions` value covers twelve media, and the
  monocultures of all twelve were offered to one co-culture, to be told apart afterwards by the wording
  of their descriptions. One function, `derive.condition_key`, now answers "is this the same condition"
  for the monoculture index both derivations read, the drop-out designs and the run variants, so the rule
  cannot hold in one path and not another.
  **This removes arcs**, and that is the rule working: on the live All network 22 arcs become 14. All
  eight are SMGDB00000004's, whose co-cultures are recorded in mMCB with and without initial acetate
  while its monocultures are recorded in plain mMCB, so a comparison across them would read the acetate's
  effect as the partner's. **No arc with an adjusted p-value below 0.05 is lost** (four before, four
  after). Where a comparison is refused this way the report says so instead of reporting missing data: it
  names the medium that was measured, what it has that this experiment does not, and that an added or
  removed compound makes another environment.

### Fixed
- **`grownet validate` and the shipped JSON Schema were strict in opposite directions** (#155 item 5). A
  document with one undeclared **record** key was INVALID to `validate` and valid to the schema, where
  draft-07 reads an omitted `additionalProperties` as allowing anything; meanwhile the document **root**
  carried `additionalProperties: false`, so an undeclared top-level key was the other way round, and the
  standalone viewer, which preserves unknown top-level fields on export, could write a file the schema
  rejected. Both halves are permissive now, which is what the schema's own sentence promises. An
  undeclared key is a **note** rather than a problem: calling it a problem also skipped the
  referential-integrity pass, which runs only when there are none, so one unrecognised field turned off
  the check that catches an edge citing a study the document does not hold.
- **The decline limit did not reach the co-culture plateau** (#155 item 10). `derive.target_capacity` is
  the other place a plateau becomes a self-limitation and was the only one that did not refuse a curve
  whose peak it had long since lost: 18 live values rested on curves past the limit, several with every
  curve behind the value past it. The limit now applies there too, and the advanced setting reaches it,
  which it did not before, so one setting means one thing.
- **Smaller ones** (#155 item 14). `q_value` was rounded to six **decimal places**, so an adjusted
  p-value below 5e-7 published as exactly `0.0`, the strongest q there is, and `significance` came out
  infinite; it is six significant figures now. `published.fetch_from`'s guard covered the fetch and the
  JSON parse while the `TypeError` its own comment describes comes from `from_payload`, which sat outside
  it; the whole read is inside now. `meta.study_id` was emitted by every single-study derivation and
  declared nowhere, because the schema-agreement test covered node, edge and study and not `meta`;
  `_meta_problems` also ignored an undeclared key in silence while `_unknown_keys` called one a problem
  three lines away, and both are notes now. `derived_on` was documented as UTC and has always been the
  local date. `--glv`'s help demanded `--metric growth_rate`, which only the specified comparison needs.
  `r/README.md` quoted a `print(x)` line the R code cannot produce.
- **The release workflow published to PyPI without running the suite, the gate or the linter** (#155
  item 7). Its job graph was `check` -> `dist` -> `install` -> `pypi`, where `check` ran only
  `check_release.py` and `install` ran `grownet --help` and the smoke script. `ci.yml` does fire on a tag,
  but the two workflows are independent and nothing linked them, so a tag whose suite was red still
  reached PyPI, held back only by the optional environment approval. A version on PyPI cannot be replaced,
  which makes it the one failure in that workflow that cannot be undone. `check` now runs `ruff`,
  `checks/gate.py` and the whole suite before the tag is believed, and both the workflow's own header and
  RELEASING.md said otherwise and now say what happens.
- **The release gate could not be green and honest at the same time** (#155 item 8). With no tag it
  synthesised `v{version}` and ran the full tag check, including "CHANGELOG.md still marks {version}
  unreleased", so any tree whose in-development version was marked unreleased failed `make check`, which
  is the Keep a Changelog convention the file follows. The only green states were to leave the version at
  the last released one or to mark the next release released before it is; the tree took the second and a
  test pinned it. That check now applies only when a release is being cut. Two more holes with it: the
  date agreement read only a parenthesised date, so `## [0.3.0] - 2099-01-01` passed in silence against a
  different date in `CITATION.cff`, and two files agreeing with each other is not either being right, so
  a date in the future is now refused. The tree was wrong in exactly that way, dating the release
  2026-10-06 while every commit in it was 2026-10-07 and both files agreed; both now say 2026-10-07, and
  a test compares the release's date with the newest commit rather than only the two files with each
  other.
- **The package README described the diagonal backwards under the default** (#155 item 11). The
  off-diagonal prose was branched by derivation and the diagonal's was not, so a package from the
  derivation that ships said `K_i` is "the plateau of the curves that reached stationary phase" when on
  that path `A_ii` is a parameter of the fit and `K_i = -r_i / A_ii` is derived from it, the opposite
  direction, while `capacity_source` in the same zip said "fitted from the monoculture time courses". The
  diagonal now has its own words per derivation. The promised SELF-LIMITATION FITTED AT A CO-CULTURE
  PLATEAU section was also unreachable on that path, because it is filled from `edge.target_capacity`
  which the integrated derivation never sets, so the one diagonal in a package that is **not** a fit
  appeared in no section at all; a DIAGONALS THAT ARE NOT A FIT section now names those organisms and
  what was put in place of the plateau their fit did not imply.
- **Shipped text quoted counts of mGrowthDB, and the counts were wrong** (#155 item 6). The help and the
  README said the medium names alone give 15 media and the rule gives 60, or 58 with the alias table.
  Measured over all 559 live experiments with the table on, which is the only way the tool runs, it is 13
  and 57; the older figures predate the alias table and the rule that a stated amount of zero is not an
  addition. Karoline's rule is that shipped text quotes no corpus numbers, since they depend on the state
  of a database grownet does not control, so both passages now describe the rule without counting.
- **The README and the register described machinery that had been deleted** (#155 item 12). The README
  still said an arc carries the spread over "leaving out each monoculture replicate in turn" and "the
  share of that spread" from the monoculture stage, which is the sentence the register formally withdrew
  as not a share of anything; it now describes the two disjoint designs that replaced it. It headed the
  integrated form "A second derivation" while calling it the default elsewhere, and gave the comparison's
  formula as what `--glv` writes for every derivation. `docs/METHOD_NOTES.md`'s live figures are
  re-measured: 14 arcs, 9 at p < 0.05, 4 at q < 0.05, the monoculture stage dominating on 8 of the 13
  arcs that have both halves, and a median `fit_r2` of 0.917 with none failing to beat its
  interaction-free null.
- **A GraphML exported from the page carried none of the graph-level attributes** (#155 item 4). The
  Python writer reads them from a nested `meta`: `absence_rule` is `meta.absence.rule`, `absence_count`
  is `meta.absence.absent`, `statistics_test` is `meta.statistics.test`, and `hidden` is the counts
  joined. The viewer looked up the flat names directly on `meta`, so four came back empty and `hidden`
  was written as `[object Object]`. The purpose of adding them was that an absent arc can be read against
  the `k` that marked it on the route Cytoscape uses, and on that route there was no `k`. The viewer now
  resolves them the same way, and writes a double whose value is whole as a float, so 2.4e8 is
  `240000000.0` on both routes rather than differing by a formatting artifact.
  The test that keeps the two writers equal built its network with no `meta` and a record carrying none
  of the fitted fields, so every key this release added was skipped on both sides and the equality held
  vacuously. Its fixture now carries a full `meta` and all thirty-odd arc fields, which is what found the
  two float cases above.
- **A stated amount of zero was read as something added** (#155 item 3). SMGDB00000014 states its
  no-fatty-acid arms as "0% linoleic acid" and "0% oleic acid", and the amount pattern matched the stated
  zero, so each became a medium with a compound added at zero: two media that do not exist. Neither was
  plain minimal medium and neither matched the other, though all three are the same plain medium. An
  addition now needs an amount above zero, in `media.alterations` and in `key_from_label`, which reverses
  the label it writes, so a network derived before the rule reads as the plain medium rather than
  disagreeing with a freshly derived one. SMGDB00000014 holds 11 media instead of 12, and the four
  experiments of the two phantom arms join plain minimal medium.
  **This changes no number in today's corpus**: the growth rates and all three interaction matrices of
  the live All package are byte-identical before and after, and SMGDB00000014's three arcs are unchanged.
  The item recorded an 18.4-fold change to *A. tumefaciens*'s carrying capacity, which was true when it
  was written and is not now: keying capacities by medium and the strict rule moved that capacity to
  metalworking fluid, a medium these arms were never in.
- **The `conditions_unverified` caution had silently stopped firing on drop-out arcs.** `_variants` keys
  by community and condition, and `_dropout` looked that key up with one element fewer than it was built
  with, so the lookup missed every time and defaulted to "one variant": two full communities told apart
  only by their descriptions were no longer cautioned. Found by a test while the key gained the medium.
- **A capacity came from one medium on one derivation and from several on the default** (#155 item 2).
  Karoline's decision of 2026-10-07, that plateaus are not pooled across media because a capacity sits
  beside off-diagonals measured in one of them, was in force for `--derivation replicate` and not for the
  derivation that ships: `integrated.fitted_rates` collected the media for reporting and then took the
  median over every fitted row whatever the medium, with `capacity_medium` unset and
  `capacity_curves_left_out` empty. Fitted plateaus are now collected per medium, the medium with the
  most rows is published and named, and the rest are named in `capacity_curves_left_out` instead of
  pooled in. On the live All network four of the eight carrying capacities move: *Roseburia intestinalis*
  by 5.3 times (3.835e9 to 7.268e8 Cells/mL), *Blautia hydrogenotrophica* by 2.5, *Comamonas
  testosteroni* by 1.8 and *Agrobacterium tumefaciens* by 1.02, and each gLV diagonal, which is `-r/K`,
  moves with its capacity. The rate itself is still the median over every row, since a rate is a property
  of the organism in each medium it was measured in and only the plateau is the one the matrix sits on.
- **`capacity_fall_from_peak` was always empty under the default derivation** (#155 item 2). The fall was
  measured inside the measured-plateau rule and discarded, while the help said it is published beside the
  capacity. It now travels with the plateau, and the help says it is empty where the capacity is the
  plateau a fit implies rather than one a curve reached, since there no curve exists whose fall could be
  measured. The help also says the lag column is empty under the default derivation, whose model has no
  lag term at all.
- **The gLV example rested on a monoculture fit that had failed, and the help called it the only one of
  its kind** (#155 item 13). The example moved from SMGDB00000006 to SMGDB00000002. Of the yoghurt pair's
  three *S. thermophilus* monoculture replicates two were refused for a negative rate and the third was
  kept at 0.0109 /h, a 64 hour doubling time for a dairy starter, while all three fitted a **positive**
  self-limitation and so failed in the same way; its carrying capacity had to be taken from one measured
  curve; and the package's steady state inverted the co-culture it was fitted from by about 90 times. The
  claim that it was "the only package in the database whose matrix settles with every organism above
  zero" was false: of the five studies that yield a package of two organisms or more, three settle. The
  new example's rates are each the median of three monoculture replicates that were all kept and all
  fitted a negative self-limitation, and its steady state puts both organisms below their own monoculture
  plateaus in the order the co-culture measured. The walkthrough now ends by holding the simulated steady
  state against that co-culture, which is the step that catches a package settling where the data never
  was, and the shipped text no longer claims the example is unique.
- **`growth_rates.csv` counted fitted rows under `replicates`** (#155 item 13). The column has meant
  monoculture replicates since 0.2.0, where it was right because the only derivation compared replicate
  sets. The integrated form merges fitted rows instead, and its row count went into that column, so a
  rate resting on three monocultures read as resting on one culture and a rate resting on one read the
  same way. It now holds the replicates the rate stage fitted, `capacity_curves` holds the curves behind
  the capacity on the same basis, and the row count stays in the text report, which already named it
  "fitted row(s)". The package README and the recorded rate rule no longer say "median over replicates"
  of a derivation that takes a median of medians.

### Added
- **What a gLV model assumes, stated where a reader meets the parameters** (Karoline, 2026-10-07). Two
  assumptions belong to the form rather than to the fit: every coefficient is constant in time, which a
  batch culture does not satisfy because the medium is consumed and metabolites accumulate, so an effect
  can change in size and in sign along the growth curve; and interactions are pairwise and add up, so a
  higher-order interaction, where a third organism changes how the first two affect each other, has no
  term in the model. The help has a section of its own, "What a gLV model assumes", ahead of the
  walkthrough; the package README has "WHAT THIS MODEL ASSUMES"; and the payload carries both as data
  under `caveats.model_assumptions`, so the zip and the R object say it without the page. Modeling a
  coefficient that varies with time or with the community stays out of scope; `docs/METHOD_NOTES.md`
  records the design that answers it instead.

- **Every fitted arc now says how large a rate mismatch would explain it away, and how much of the course
  it rests on** (Karoline, 2026-10-07). The monoculture rate is held fixed while the partners are fitted,
  so the arc is the only parameter left to absorb a difference between the rate an organism had alone and
  the rate it had beside its partner, and no growth curve measures that difference. `rate_mismatch_to_zero`
  is the fractional change in that rate which would drive the arc's coefficient to zero, exactly and
  signed, from the derivatives the fit already computes: an arc at 0.5 survives a 50 per cent error in the
  rate, an arc at 0.04 does not survive 4 per cent. Checked against a simulation with a known mismatch
  planted in it, where it recovers 0.1109 against the true 0.1111.
- **A `window_partial` caution, and the share of the course a fit covers** (Karoline, 2026-10-07: "the
  effect 1 organism has on another can change along the growth curve. this is not something we treat here,
  but something we can warn about"). The integrated model has no lag term and no death term, so the rows
  start where growth starts and stop at the end of the plateau after the maximum: a course measured well
  past its peak is fitted on the early part of itself, and grownet fits one constant coefficient per arc,
  so an effect that changes along the curve is reported as whatever it was inside the window.
  `fit_window_share` is the fraction of the measured span the rows cover, a note names both spans, and an
  arc below half carries the caution. On SMGDB00000002 both arcs between *Roseburia intestinalis* and
  *Bacteroides thetaiotaomicron* are fitted on 0 to 32 of 120 measured hours and now say so.
- **A gLV example button, and the steps to simulate it** (Karoline, 2026-10-07). Beside All, **gLV
  example** fills both boxes and the one setting a package cannot be built without, and runs the search.
  The study it picks was chosen by running every study that yields a package: SMGDB00000006, two
  organisms in one abundance unit, both with a fitted rate and a plateau, and the only package in the
  database whose matrix settles with every organism above zero. The help has a section of its own, "The
  gLV example, step by step", which installs miaSim, listens in R, prints the matrix and the equilibrium,
  runs `simulateGLV` deterministically and says what to expect, with the numbers this search gives today
  and a note that mGrowthDB changes. The route above it stays generic; only the numbers are the
  example's.

### Changed
- **The gLV package states the formula its own derivation fitted** (#142 item 6). `README.txt` inside the
  package, the payload's `caveats.coefficients`, the R package's printout and its `glv_matrix`
  documentation, the help's gLV section and the About page's 0.3.0 entry all said an off-diagonal cell is
  `(r_with - r_without) / x_j` over a rate window, which is the comparison's formula and not what the
  integrated form fits: there a cell is a parameter of the fit of the whole row,
  `ln(x_i(T) / x_i(0)) = r_i T + sum_j A[i][j] integral(x_j dt)`. The package text now follows the
  derivation that made it, `caveats.derivation` names it, the R package prints the package's own sentence
  rather than one of its own, and the static R documentation gives both. The About page also no longer
  calls the integrated form a second derivation in Advanced settings: it is the default, and the setting
  switches to the comparison.
- **A network says what test its own derivation ran, not what the specified comparison runs** (#142
  items 5 and 11). `meta.statistics` and `meta.provisional` were module constants copied into every
  network, so a file derived by the integrated form claimed Welch's two-sided t-test on per-replicate
  log2 values and a comparison of replicate sets, neither of which that form does, and the claim
  traveled into the JSON, GraphML, the Cytoscape legend, the page, the report and the daily artifact. A
  derivation now states both, as it already states its `name` and its `method`, and `output_meta` reads
  them from the derivation that made the records. The ten other places a reader meets the claim say which
  derivation runs Welch: the arc glossary, the help's statistics section, the correction setting on the
  page and the command line, the Cytoscape legend, `model.py`'s own documentation of `p_value`, the
  standalone viewer and the README. `checks/claims_check.py` holds it as a retired claim, so text that
  says an edge carries Welch's test without naming the derivation fails the build.
  **And the reason it survived twelve commits is fixed too:** every page, command-line, report, export and
  threshold test asked for `derivation=replicate`, because the double they share measures two points per
  set, so the derivation that produces the daily artifact and every default user's file was covered end to
  end nowhere. `tests/test_default_end_to_end.py` serves simulated gLV time courses, runs the page's own
  `run_query` with nothing overridden, and asserts both halves: the search gives arcs, and the report, the
  page, the GraphML and `meta` all describe the derivation that made them.
- **A fitted rate, plateau and diagonal are the median of every row behind them, not the first one**
  (#142 item 4). `integrated.fitted_rates` kept the first row it met per organism, so an organism's rate,
  the plateau its fit implies, the diagonal `-r/K`, the printed equilibrium and the chemostat prediction
  were all "whichever arc the loop reached first". Every row is now merged by the median, which is the
  rule register item 14 sets for arcs and `derive.merge_rates` follows for the measured parameters, with
  each study's own median beside it, the studies sorted and unioned, and a rate in another time unit or a
  plateau in another abundance unit named rather than converted. Measured live by feeding the rows in both
  orders: the published rate differed by up to 1.42 times (*C. testosteroni* on SMGDB00000014) and the
  plateau by up to 1.2 times, while on SMGDB00000004 and 6 the rows agree and the defect was invisible.
  The count beside a fitted rate also says what it counts now, "2 fitted row(s)" rather than a number of
  monoculture replicates the fitting path never had.
- **The integrated form fits each organism's row from the monocultures of its own condition, and its
  statistics carry both stages' error** (#142 items 1 and 2). Two fixes to the derivation that is now the
  default. Stage 1 used to be every monoculture replicate of the organism anywhere in the study: it now
  follows the rule settled on #47, identical recorded conditions and the same description apart from a run
  number, through the same two functions the specified comparison uses, so both derivations compare like
  with like. On SMGDB00000014 the arc at 0.75 percent linoleic acid is gone, refused by the R2 gate that
  it had passed only because stage 1 handed it a rate from the conditions where the organism does grow;
  the TBHQ arc's coefficient nearly doubles and its reverse direction becomes identifiable. On
  SMGDB00000007 five arcs become six and every coefficient moves, the largest by 3.2 times. And `sd`,
  `se`, `p_value`, `q_value` and the absence threshold used to be computed from the co-culture replicates
  alone, so the monoculture stage was treated as exact in the one place that decides which arcs reach a
  file: that stage is now resampled over its own replicates, each co-culture replicate carries the exact
  derivative of its coefficient with respect to the stage's two numbers, and the two variances are added.
  Both halves are published (`se_replicates`, `se_rate_stage`, `rate_stage_method`, `rate_stage_n`), and
  `coefficient_sd` and `coefficient_sd_from_rate_stage` now mean what they say, on disjoint designs.
  Measured over the six studies that give arcs: 20 arcs become 17, p < 0.05 goes from 12 to 9, q < 0.05
  from 8 to 5, the largest sd grows 8.3 times, and on 5 of the 17 the monoculture stage contributes more
  of the variance than the co-culture replicates do.
- **What counts as one medium is a rule now, and it decides every medium comparison** (Karoline,
  2026-10-07, closing the open decision on #141 and then: "foodnet's strict medium rule should be applied
  in general in case someone specifies it in the 2nd search box (because such changes alter
  interactions)"). mGrowthDB names a medium per compartment and states an added sugar, a removed carbon
  source or a supplement only in the experiment's description, so a medium's identity (`grownet.media`) is
  its compartments' names without case, punctuation or a parenthesized abbreviation, plus every alteration
  the description states with its amount, plus the atmosphere where one is recorded. Over the whole
  database the names alone give 15 media and this rule gives 60, or 58 once the alias table below merges
  the two names it merges. Four things follow. **A carrying capacity
  comes from one medium**, the one with the most certified curves, named in `capacity_medium`, with every
  other medium's plateaus named rather than pooled in, which is the decision itself: a diagonal sits
  beside off-diagonals measured in one environment. **Every arc records the medium it was measured in**
  with its alterations, so SMGDB00000014's twelve chemistries no longer all read "Minimal medium (MM)".
  **A gLV package is scored against a chemostat only when the two media are the same by this rule**, which
  replaces a subset rule over the names' words that was not transitive and that matched a two-compartment
  design to one of its own compartments; where two studies spell one medium differently the report now
  says the names differ and names the word, instead of asserting that the environments do. Two live names
  do disagree with the others rather than being less complete, SMGDB00000001's "Anerobe" and
  SMGDB00000005's bare "Wilkins-Chalgren", and keying alone took the chemostat validation from 2 scored to
  1, so those two are merged by a **hand-curated alias table** (`grownet.media.WORD_ALIASES` and
  `NAME_ALIASES`, Karoline's call of 2026-10-07) rather than by a looser match, which would also merge
  names differing by a digit. It is the one place the tool calls two names that disagree one medium, so it
  is never silent: a chemostat scored across an alias says which entry did it, a capacity whose curves
  were recorded under several spellings names them all, and the label a reader sees is always what the
  study wrote. **The second
  box** still matches a medium as text, because mGrowthDB's names are prose, but says how many media one
  word reached, and the monocultures it keeps alongside a named comparison must now share the medium and
  not only the recorded conditions. The rule is foodnet's, the sister tool's, with one adaptation: foodnet
  also reads "+X" in an experiment's **name**, which is safe for a tool that reads monocultures and is not
  for grownet, where `At+Ct` and `LB+STneg` name community members and would have split two studies into
  media that do not exist.
- **A carrying capacity says how far its curves fell from their peak, and the worst of them are refused**
  (Karoline, 2026-10-07, closing the open decision on #141). `reached_stationary` certifies a culture that
  grew, reached a peak and then declined, because it has stopped growing, and the plateau recorded for it
  is that peak. Measured over all 1,331 per-strain batch curves in the database, 443 certify and 417 of
  them end more than 10 percent below their peak, the median one at a third of its peak, so a decline is
  the ordinary shape of a batch culture and refusing every declining curve would leave 20 of the 29
  organism-study pairs that have a capacity with none. The tail is a different matter: one certified curve
  hands over a peak 82 million times its last value. So the peak stays, the fall is published beside it in
  the report, in `growth_rates.csv` (`capacity_fall_from_peak`) and in the gLV payload, and a curve that
  fell further than the new **Carrying capacity decline limit** gives no capacity and is named with the
  others that gave none. The limit is an advanced setting and `--capacity-max-fall F`, 10 by default,
  which reads as "the culture still holds a tenth of its peak at the last measurement"; 0 keeps every
  certified plateau, as 0.2.0 did.
- **Send to R and `/glv.json` carry the same numbers as the zip** (#120): the payload is
  `grownet.glv/v1`, with `matrices`, one per abundance unit, holding fitted coefficients, the rates with
  the estimator, the lag and the carrying capacity beside each, and every caveat as a field: the cells
  from a comparison where one side did not grow, the pairs left at 0 for disagreeing in sign, the
  organisms and effects that could not be fitted, the media, the drop-out count and the standing note
  that a fit can have no bounded state. The R package reads v1 and still reads v0, says which kind it
  holds, and gained `unit =` on `glv_matrix()`, `glv_rates()`, `as_miasim()` and `glv_scale()` for the
  organisms counted in another unit; `glv_scale()` now warns when it is called on fitted coefficients,
  since their units already match the diagonal and scaling hides an unbounded fit rather than settling
  it. `glv_write()` writes one matrix per unit and anything the payload carried beside the numbers, such
  as the steady-state check. The page, the help and both READMEs say one thing rather than two, and the
  effect-size README that only this route still used is gone.
- **An organism with no certified monoculture plateau is fitted at its co-culture plateau** (#124 item 2,
  Karoline's "complete #124" of 2026-10-06), rather than left out of the package. The balance is the one
  #123 introduced for an organism that grows only with a partner, `0 = r_i + A_ii x_i + sum_j A_ij x_j` at
  its plateau, with every abundance measured; where it comes out at or above zero, which means the
  partners suppress the organism harder than its own rate, the organism is still named instead. Measured:
  SMGDB00000004's package now holds all three of its organisms and five fitted cells rather than two
  organisms and one, because B. hydrogenotrophica never settles alone in that study. **Each matrix also
  names the media its own arcs came from** (item 5), which keeps media together in one matrix per unit
  rather than fragmenting the corpus into one matrix per medium, since the second box already holds a
  search to one environment.
- **A censored cell of the plain adjacency matrix holds a measured bound, not the stated +/-10** (#129,
  Karoline's decision of 2026-10-06: "go with the bound in #129 following your recommendation"). A pair is
  censored because the no-growth rule judged one side not to have grown, and that rule bounds that side's
  own metric: at most its factor (1.5 by default) over its own measured start, which bounds the cell from
  below for an obligate pair and from above for an abolished one. The arc carries the bound and the rule
  behind it (`strength_bound`, `bound_rule`), the report prints both, and the gLV payload lists the
  bounded cells beside the conventional ones a network derived earlier still has. Where the rule bounds
  nothing away from zero, which happens with the area under the curve because a culture that did not grow
  still carries the area of its own inoculum, the cell stays 0 and says which growth property bounds it
  tightly. Measured on SMGDB00000013: with the growth rate the seven censored arcs come out between +4.4
  and +5.9 log2, in place of a flat +10, which as a log2 mean claimed a thousandfold effect.
- **Every cell of the gLV package comes from absolute rates, and an obligate pair is a measurement**
  (#123, her decision of 2026-10-06 after asking "Do we keep obligates despite the lack of a floor? If
  not, how can we keep them?"). The formula she settled is the same number written as a difference,
  `A_ij = (r_with - r_without) / x_j`, and that form is defined where the ratio is not: an obligate pair
  measured 0 without the actor and an abolished one 0 with it, so **the floor and the stated extreme are
  both gone from the package**, and such a cell enters the median of its pair like any other measurement.
  An organism that grows only with a partner now gets a whole row: `r_i = 0` by measurement, and its
  self-limitation fitted at the plateau it reaches beside that partner, `0 = A_ii x_i + sum_j A_ij x_j`
  there. Both rates behind every arc, and the target's own plateau in the co-culture, travel on the arc,
  in the schema, in GraphML, in the Cytoscape style and in the report, so every cell can be rebuilt by
  hand. A cell also no longer mixes sources: it used one experiment's ratio with a rate averaged over
  every study, and now both rates come from the same comparison. A network saved before this change
  carries no absolute rates and still converts through the ratio, with the README naming those cells.
  Measured: on SMGDB00000013 four censored pairs become measurements and one of them enters the matrix;
  on the whole corpus the cells move by up to a third and the chemostat check stays in the same range
  (1.6 and 3.2 times the observed steady state of SMGDB00000005's control).
- **The gLV package holds fitted coefficients, one matrix per abundance unit** (#119, Karoline's decision
  on #116). The diagonal is `A[i][i] = -r_i / K_i` with K the monoculture carrying capacity, and an
  off-diagonal cell is `A[i][j] = r_i (2^L - 1) / x_j` with L the log2 ratio of i's growth rate with j
  over without it and x_j the partner's abundance over i's growth window, so every cell is a per-capita
  effect in 1/(time x abundance). No convention is left in the package: no -1 diagonal, no +/-10, and
  nothing to scale. The zip holds one `interaction_matrix.<unit>.csv` per abundance unit, since a cell
  mass conversion would have to be invented while the dynamics are the same in any unit, and the README
  names every organism and effect that could not be fitted and why. An obligate or abolished pair takes a
  derived floor, the largest magnitude measured in the same run, rather than a stated extreme.
  A package therefore needs the comparison to be on the growth rate: **gLV mode now also sets the growth
  property to `growth_rate`**, `--glv` says which setting to change when it cannot convert, and the page
  says the same instead of failing. The rate estimator stays the reader's own setting, easylinear by
  default (Karoline, 2026-10-06: "use the lag from Baranyi and easylinear since it works better (users can
  always enforce Baranyi in the advanced options)"), and **the lag is always the Baranyi fit's**, the only
  estimator that has one, with `growth_rates.csv` naming both in `method` and `lag_method`. Measured on
  #116: every cell of a row carries the factor r_i, so the estimator sets how fast a simulation moves and
  nothing about where it settles. The plain adjacency matrix
  (`--format matrix`) is unchanged, and so is Send to R, which carries the effect-size matrix until the
  conversion reaches it (#120). Checked live: the converted matrix of SMGDB00000004 and of the whole
  corpus simulates in miaSim with no scaling and settles exactly at the solution of `A x = -r`.

### Added
- **A second derivation, from the whole time course** (#127, Karoline's "OK for 3, as an advanced option"
  of 2026-10-06). `--derivation integrated`, or Derivation in Advanced settings, fits each organism's row
  instead of comparing replicate sets: `ln(x_i(T)/x_i(0)) = r_i T + sum_j A_ij integral(x_j dt)` is linear
  in the parameters, so one least-squares fit per organism gives its rate, its own limitation and every
  partner's coefficient at once, with no growth property, no log2 ratio, no plateau to certify and no
  partner abundance to divide by. The monocultures identify `r_i` and `A_ii` and are held fixed while the
  co-cultures give the partners, since inside one experiment those columns rise too nearly together. The
  model has no lag term and no death term, so the rows start where growth starts (the Baranyi lag of #118)
  and stop where it ends (the plateau rule of register item 29). Every arc carries the coefficient, the
  residual and the condition number of its fit, and the growth rates and capacities of such a run come
  from the same fit, the capacity being the plateau it implies. A row the design cannot identify, and a
  community of three or more members, are reported rather than derived. The default derivation is
  unchanged. Measured on SMGDB00000007 against the steady state of SMGDB00000005's control: the integrated
  fit lands all three organisms at 0.41, 0.73 and 2.69 times the observed abundance, where the specified
  comparison gives 1.60 and 3.26 and fits B. hydrogenotrophica to wash out although the chemostat holds
  it; its implied plateaus (8.9e8, 1.2e9, 8.6e8 cells/mL) sit within about 15 percent of the measured
  ones, which never enter the fit.
- **The page says before the download when a package will hold several matrices** (#130, Karoline's
  decision of 2026-10-06 on the unit question): how many matrices, which abundance units, and that no
  effect between them was measured, since organisms counted differently were never grown together. No
  conversion between units is applied, by her decision, and the result section's text about the package
  now describes the fitted coefficients it holds rather than the convention it used to.
- **A gLV package can be scored against mGrowthDB's chemostat steady states** (#125, from Karoline's
  suggestion of 2026-10-06 and her go-ahead on the shortlist of #124). A continuous culture satisfies
  `A x = -(r - D)` at steady state with the dilution rate it records, and those numbers were never used to
  fit the parameters, so they test them. **Check against chemostat steady states** in Advanced settings,
  or `--steady-check`, puts predicted against observed per organism into the report and into the package
  as `steady_state_check.txt`, and names every chemostat it could not use with the reason: no dilution
  rate recorded, a perturbed run, another abundance unit, another medium, or no organism in common. It
  only reports: no coefficient or rate changes because of it. Off by default, since it reads the curves of
  chemostats a search does not otherwise need. Measured live on SMGDB00000007's package: against
  SMGDB00000005's `A8 control`, B. thetaiotaomicron lands at 1.6 times the observed steady state and
  R. intestinalis at 3.2, while B. hydrogenotrophica is fitted to wash out where the chemostat holds it;
  against SMGDB00000011's six-member run, 10 and 30 times, with the three organisms the package does not
  hold named as not scored.
- **Smaller things that came with the above**, each with its own setting or column: the rate estimator a
  reader chooses now reports the Baranyi lag beside it whichever one produced the rate, and
  `growth_rates.csv` names both (`method` and `lag_method`); gLV mode sets three settings rather than two,
  adding the growth property it needs; `--steady-check` and `--derivation` join the command line, matching
  the page's two new Advanced settings; the report prints both rates behind every arc, the partner
  abundance it divides by, the bound behind a censored cell, and the condition number and residual of a
  fitted row, so every number in a package can be rebuilt from it by hand.
- **The quantities a fitted gLV coefficient is made of, measured and reported** (#118, from Karoline's
  decision on #116). Every growth rate now travels with the estimator that produced it, the lag the
  Baranyi fit estimated, and the organism's monoculture carrying capacity: the plateau of its curves,
  taken only from curves certified to have reached stationary phase, in the abundance unit they were
  measured in and never converted, with every curve that gave no capacity named and why. Each biculture
  arc carries `partner_abundance`, the actor's own abundance in the co-cultures averaged over the window
  the target's growth rate was fitted in, with its unit and the replicates behind it. They are in
  `growth_rates.csv` (five new columns), in the network's meta, in the gLV payload and package, in the
  report, in GraphML, in the Cytoscape style and in the help. The matrix and the package still hold
  effect sizes and the convention on the diagonal: these numbers are reported, not yet applied. On study
  7 all eight monoculture curves of each of the three organisms are certified stationary, giving
  K of 1.05e9, 1.18e9 and 9.16e8 Cells/mL.

## [0.2.0] (2026-10-04)

### Added
- **The About page logs what each release brought**, a few lines each, newest first, with the changelog
  linked for the full record (Karoline, 2026-10-04). A test requires the newest entry to name the current
  version, so a release cannot forget its line.
- CI builds and checks the R companion package on every push (`R CMD check`, the `r-package` job, #112),
  with R and its two dependencies from Ubuntu's own packages, so no third-party action is added and
  nothing is compiled.
- **An R companion package and Send to R** (Karoline, 2026-10-03): the result section's gLV control is one
  drop-down, Download (.zip) or Send to R, and the R package in `r/` receives the parameters over a local
  port (`grownet_listen()`), or fetches them from the page (`grownet_glv(url)`) when no port can be opened.
  `grownet derive --report-rates --to-r` does the same from the command line, with `--r-port`. The package
  installs with `remotes::install_github("crossfeed-bio/crossfeed", subdir = "r")`, needs only jsonlite
  (the listener uses base R sockets), and assumes no simulator: `as_miasim()` shapes the arguments
  `miaSim::simulateGLV` takes, and miaSim stays a suggested package.
  **The caveats travel as data, not as a README to be read first**, which was her open question: the
  payload (`grownet.glv/v0`, served at `/glv.json`) carries which cells hold the stated extreme, which
  pairs were left at 0 for disagreeing in sign, which organisms have no growth rate, the absence threshold
  and grownet's own README text. In R the object prints them every time, `glv_matrix()` warns and names
  the placeholder cells (with `placeholders = "na"` or `"zero"` to convert them), and `as_miasim()` stops
  when an organism has no growth rate.
- **Get gLV parameters** in the result section, with the rates (`--glv FILE`): a zip holding
  `interaction_matrix.csv` (the matrix with -1 on the diagonal, by convention, for self-limitation),
  `growth_rates.csv` in the same order, and a `README.txt` that states the conventions, names any pair left
  at 0 for disagreeing in sign, and names every organism without a rate. The README says plainly that a
  cell is an effect size, not a fitted gLV coefficient, which is a per-capita effect in absolute units
  (Karoline, 2026-10-03).
- **The adjacency matrix as an export format** (`--format matrix`, the page's format menu): the network as
  a square CSV table, a cell holding the log2 mean of the comparison, so `A[i][j]` is the effect of j on i
  (rows affected, columns the actor). Each organism appears once, so arcs of one pair are merged across
  conditions and studies by their median; a pair whose arcs disagree in sign is left at 0; an empty cell
  and an arc below the absence threshold are 0. An obligate interaction carries +10 and an abolished one
  -10 (Karoline, 2026-10-03: "obligate and abolished arcs need to carry numbers reflecting the strong
  effect, how about 10 with the appropriate sign?"): neither has a log2 ratio, because one side did not
  grow at all, so the number is a stated extreme, named cell by cell in the gLV README, and it never enters
  the median of the arcs that do have a ratio. The diagonal is 0 here, and -1 in the gLV package.
- **Report growth rates**, an advanced setting (`--report-rates`) that the gLV mode button turns on, off
  by default: every
  organism in the network also gets its maximum specific growth rate in monoculture, by the chosen rate
  method, the median over the replicates and studies that have one, with each study's own median beside it
  in `meta.growth_rates`. Batch monocultures only (in a chemostat the rate is the dilution rate, and a rate
  from a co-culture is growth with a partner). The rates download as their own CSV (`--rates FILE`), and an
  organism whose curves give no rate is named on the page and in the report, never given a substitute.
- **A second input box: media, experiments or studies** (Karoline, 2026-10-04, weakening her stance against
  environment filtering now that gLV parameters are exported: "it's one thing to export a network of known
  interactions and another to do a gLV simulation"). Optional, beside the species box, with its own
  examples. A medium is matched as text, case-insensitively, against the medium name mGrowthDB records on
  the experiment's compartments, its description and its name, so one word finds the four spellings of
  Wilkins-Chalgren in the database; an id picks one study (SMGDB...) or one experiment (EMGDB...), and
  naming a comparison keeps the monocultures it is made against, which the report lists. On the command
  line it is `--conditions NAME ...`. **"Only these studies" has left Advanced settings**: a study id typed
  in the box does its job, and the study argument of a `--species` search still works.
- **Every arc records its `medium`**, the growth medium the comparison ran in, in the neutral format, in
  GraphML, in what Cytoscape receives and in the report. The schema gained the optional field. Nothing
  about the method changed: a comparison never mixed media, because the medium is part of the conditions
  two replicate sets must share.
- The gLV package and the R object **name the media their numbers come from**, and say in capitals when
  there is more than one, since a simulation is of one environment: the All network's package reports six.
- `glv_scale()` in the R package, and a line in the gLV README and the help: the cells are often stronger
  than the -1 on the diagonal, and a simulation run on them unchanged can grow without bound and come back
  as NA. Measured on SMGDB00000004, where the unscaled matrix diverges and the scaled one settles.
  **The factor is a free parameter, not a calibration** (Craig, reviewing 0.2.0): nothing in the growth
  data fixes the scale, so whoever simulates chooses it, and that choice, not the measurements, sets where
  the simulation settles. Report the factor you used with any result that depends on it.
- Filter on adjusted p-value (`--max-adjusted-p Q`), an advanced setting off by default (register item
  31): interactions whose adjusted p-value is above the threshold (0.05 unless another is given) are left
  out and counted (`meta.hidden.not_significant`, `meta.statistics.filter`); absent and undetermined arcs
  stay; arcs without a p-value (obligate, abolished, a single replicate) are kept with the caution
  `untested`; merging uses only the arcs that passed. The help says why it is off by default: with two or
  three replicates the test misses many real effects, and an adjusted p-value depends on the other
  comparisons in the same search.
- The help page explains how an interaction is decided, in a section of its own: the effect, the absence
  threshold, Welch's t-test, the multiple testing correction and its family (every comparison of one
  search), which arcs have no test, and the filter. The correction setting's text on the page, in the help
  and on the command line says what the correction runs over.

### Changed
- **The format id moved to `grownet.interaction_network/v1`** (Karoline, 2026-10-04, on her agent's
  recommendation; Craig's question on #107), because `significance` changed meaning in this release and a
  version is the one signal that says so: a reader branching on the id would otherwise read these numbers
  as 0.1.x ones, silently. The namespace is unchanged, nothing else about the format moved, and the fields
  added since v0 are optional. A v0 document is still valid, read with the older meaning, and
  `grownet validate` names the version it read. The daily All network is used only when it speaks this
  version, so the page derives live until the workflow republishes it, about a day.
- **`significance` is now -log10 of the q-value, and the corrected p-value has its own field, `q_value`**
  (Karoline, 2026-10-03). Before, `significance` held the corrected p-value itself, so the name ran
  against the number: larger looked stronger and was weaker, and a continuous Cytoscape mapping on it was
  backwards. Now `p_value` is Welch's raw value, `q_value` is that value corrected for multiple testing,
  and `significance` is -log10 of the q-value: 0 at q = 1, larger is stronger evidence, capped at 15 for a
  q-value of zero. The page's column is `q`, the viewer shows p, q and significance, and the filter
  (`--max-adjusted-p`) still acts on the q-value. A reader of an older file gets the old meaning: the
  change rides with 0.1.1, which has no released files yet.
- **Arcs below the absence threshold are left out of every output by default** (Karoline, 2026-10-03), so
  the page, a downloaded file and a network sent to Cytoscape all hold the same arcs: Cytoscape used to
  count the absences too, which was confusing. They are still reported, in their own section of the result
  and in the report, with how many and at which k; `meta.hidden.absent` counts them and
  `meta.absence.absent` still says how many the threshold marked. The new setting **Include arcs below the
  absence threshold** (`--include-absent`) puts them back in the file, with `effect_over_sd` on each, for
  moving the threshold inside Cytoscape.
- **Continuous culture is derived with the growth measure `max`** (Karoline, 2026-10-03): the level a
  chemostat or serial dilution settles at is comparable with and without a partner, while the area under
  its curve and its growth rate are not. Such arcs carry the caution `continuous_culture` and are shown.
  With `auc` or a growth rate they are still left out unless `--include-non-batch` is given, and then they
  keep the `non_batch` quality flag and stay hidden by default. A comparison never mixes modes. No network
  changes today: no study in mGrowthDB has a non-batch pairwise or drop-out design.
- **A gLV mode button beside All** (`--glv-mode`), which toggles what a simulation needs: Report growth rates
  on and Include drop-out communities off, both left in sight in Advanced settings with their defaults
  unchanged (Karoline, 2026-10-04: "how about moving both options back to advanced parameters, with their
  default settings, and instead introduce a button 'gLV mode' next to 'All', which will enable growth rate
  collection and disable drop-out communities?"). A drop-out arc may act through a third species, while a
  gLV coefficient is meant to be the direct effect of one organism on another. The text beside the buttons
  is two sentences now, and the gLV package and the R object count the drop-out arcs they hold, or say that
  none is there. Pressing it again puts both back to their defaults, and it is drawn as a switch: the slider
  is green when the mode is on and white when the settings are the defaults (Karoline, 2026-10-04). It is
  still a submit button, so the page needs no JavaScript for it. The result section's control is **Get gLV parameters**, the two input boxes line up whether or
  not their examples wrap, and the help's R example plots the simulation with `matplot` and says that every
  arrival prints in R and that `grownet_listen()` takes one parameter set per call.
- The result table's third column is **sign**, not direction: an arc already has a direction, from the
  source to the species it affects (Karoline, 2026-10-03).
- A number the derivation never computed reads as **not computed** on the page, and a comparison with no
  ratio (obligate, abolished) reads as **no ratio**, rather than leaving the cell blank. In the file and in
  Cytoscape such a number stays missing: null in JSON, left out of GraphML and of what Cytoscape is sent,
  never 0 (Karoline, 2026-10-03).
- A number that is empty is left out of what is sent to Cytoscape rather than sent as null: Cytoscape turns
  a null number into 0.0, and a q-value of 0 is the strongest there is, so an untested arc used to pass a
  "q below 0.05" filter inside Cytoscape. The columns an arc may not carry (`p_value`, `q_value`,
  `significance`, `strength`, `weight`, `effect_over_sd`, `sd`, `se`, the replicate counts and the merge
  counts) are declared on the edge table instead, so every arc carries all of them and the cells of the
  arcs without a value stay empty. Without that, a network whose arcs are all untested had no such column
  at all. Checked against Cytoscape 3.10.3.
- Opening the page's address without its token, by hand or from a tab left over from an earlier run, shows
  grownet's own page saying where to find the link, instead of a bare server error (Karoline, 2026-10-04:
  "localhost:8791 shows an error"). It is still refused, with 403, and the page never shows the token.
- The first advanced setting is **Growth property**, not Growth measure (Karoline, 2026-10-03).
- The help says plainly that the adjusted p-value is the q-value, in the section on how an interaction is
  decided and in the setting that filters on it, and the page, the report and the legend call it the
  q-value throughout, since the result table heads that column q.
- The help page explains how a continuous culture is treated, in "Which growth measure": derived with max
  and marked `continuous_culture`, left out with an area under the curve or a growth rate and why, what
  the setting does then, that a comparison never mixes modes, and that no study in mGrowthDB holds such a
  design today.
- The tool's name is marked as a name in running text, on the page, in the help and in the README, since it
  is all lowercase and a sentence starting with it read like a typo (Karoline, 2026-10-03). Commands,
  paths, link labels and the page title keep it plain.
- The README carries the name the way the help does, grow**net** in running prose, its title is lowercase
  throughout (Karoline, 2026-10-04), and the sections that had grown by accretion were rewritten: what the
  local page offers is now two boxes, four buttons and the result, "What it does" names the medium and the
  shapes a network can leave in, and the derivation section says that a comparison never mixes media.
- Commands keep the name plain, in the help and in the README: the styling that marks grow**net** as a name
  in prose never touches something a reader would type (it had reached `library(grownet)` in one command
  line entry).
- **What ships with the tool describes the released state**, not the branch it was written on (Karoline,
  2026-10-04: "The help should refer to the stage the tool is in when released"): the R install line in the
  help, the page and both READMEs is the plain `install_github("crossfeed-bio/crossfeed", subdir = "r")`,
  and installing from a branch or a clone is a development step, in CONTRIBUTING.md. A test refuses an
  install line pointing at one of our branches, or wording about work in progress, in anything a reader
  sees, including every page the local server renders.
- Each release's notes on GitHub open with how to start the Windows program and get past the "Windows
  protected your PC" warning: the small More info link, and only then Run anyway (as Karoline found on
  Windows). The README and the zip's README.txt say the same, more precisely than before. Signing through
  the SignPath Foundation waits until the project can show the use and trust it asks for.
- The README's PyPI section no longer offers the pre-release install from the repository, and says to
  use one install route at a time and what to do when pipx finds a `grownet` command left by an earlier
  `pip install --user` (found by Karoline).

## [0.1.0] (2026-09-29)

The first release, on PyPI (`grownet`) and as a Windows program. It holds everything since 0.0.1; 0.0.2
was never published.

### Added
- All reads the network the repository derives once a day (#96): `.github/workflows/all-network.yml`
  derives All with the default settings and publishes it as the assets of the `all-network` release. The
  page's All button and `derive --all` use it when it is less than a day old and the settings are the
  defaults, and derive live otherwise, or with `--no-published`; the page and the report say when it was
  derived. One derivation a day instead of about 1,300 requests to mGrowthDB per All. A failed daily
  build opens an issue labeled `all-network-failed`, closed by the next build that succeeds.
- Every derived network carries the page's caution on how to read it in `meta.provisional` (a graph
  attribute in GraphML), so a download or the daily All network states its own terms without the page.
- The local page offers the Cytoscape style as a download (`/grownet_style.xml`, the file `grownet style`
  writes), linked from the help page's Cytoscape answers, so styling a GraphML file needs no command line.
  Help, Legend and About have a Back at the upper right as well as at the end, and the grownet mark leads
  back to the search being worked on instead of an empty page.
- The help page compares the three growth measures (area, maximum, growth rate): what each captures, and
  its strengths and weaknesses. The README calls the tool grownet, keeping crossfeed only for the command,
  the module, the repository and the schema id until the rename is released.
- A monoculture set is also matched to a co-culture by identical wording of how it was grown, once the
  organisms and the kind of culture are set aside (register item 28): SMGDB00000014's five co-cultures
  now give 10 arcs. An obligate or abolished arc whose set without growth is zero from its first time point
  carries the caution `zero_at_start`.
- With max as the growth measure, arcs are checked for stationary phase (register item 27): the caution
  `stationary_phase_differs` marks an arc where one set reached stationary phase within the compared window
  and the other did not, and `stationary_unchecked` one whose curves have under 6 time points. The rule is
  not fooled by a diauxic shift: a pause followed by a measured second rise is not stationary.
- An All button beside Example (`derive --live --all`): the box is ignored and every study in mGrowthDB is
  derived, with every partner; Only these studies and Exclude these studies still apply (register item 25).
- Merge to genus (`--merge-genera`), an advanced setting off by default: one node per genus, and the arcs
  between two genera merged by sign, with the median log2 mean and new arc fields `supporting_pairs` and
  `merged_pairs` (species pairs, or strain pairs when only taxon ids were entered). Interactions within a
  genus stay as a self-loop; absent arcs as one hidden absent arc per genus pair. With Merge parallel arcs
  on too, a pair measured in several studies counts once. Nodes gain the identity `genus` (item 24). The
  genus skips qualifiers (Candidatus, unclassified, uncultured) and keeps NCBI's brackets, so [Clostridium]
  is not Clostridium, in the merge, the genus query and the genus colors alike.
- A genus entered alone ("Blautia") stands for every species of it in mGrowthDB, listed on the page and
  in the report, instead of being refused as "a genus alone".
- The README says the tool is now called grownet and what keeps the crossfeed name until the rename, that
  the tests also run on Windows and macOS, and that the local page's About says who built the tool.
- An About button beside Help (#80): who built grownet, in the wording Craig agreed to on #80, with the
  repository link and the version.
- The help page opens with the idea behind the tool, after Gause (1932, 1934): grow two species alone
  and together and compare. A figure, drawn from code with the Baranyi-Roberts model the tool fits, shows
  each species alone, both together, and the arcs the change gives, and marks the three growth measures
  the tool can compare (area, maximum, growth rate). Tests keep the figure in step with the measures.
- The help page now explains every advanced setting (with its command line flag and default), every arc
  and node attribute, the main design decisions and why, the command line with the page's own example,
  what to do when no network comes back, a short Q&A, how to cite, and links the issue tracker. Tests
  require an entry for every setting, command line option and model field, so it cannot fall behind (#78).
- `derive --live --species NAME ...` runs the local page's search from the command line, with
  `--all-partners` for the page's "only the species entered" box unticked (#78).
- The report and every network record when the search ran (date, time and offset) and the version of
  the data: mGrowthDB publishes none for the whole database, so each study's upload and publication
  dates. Input that gives nothing now says why, per entry (unreadable, a taxon id mGrowthDB does not hold,
  a genus alone, an unknown name, with suggestions), commas and `txid` ids are understood, an empty result
  names the setting that caused it, and the Cytoscape messages say what to do on the page and the
  command line alike.
- `derive --report FILE` writes the page's report from the command line, and `crossfeed derive --help`
  groups its options as the page does (what to derive, the settings, the outputs), in the page's
  wording, with examples. A test requires an option for every setting and all three outputs.
- Clearer advanced settings: the absence threshold says it decides when an interaction counts as absent
  (the species do not affect each other), and the no-growth settings say they test the replicate growth
  curves of one species in one culture condition. A new setting, Exclude these studies
  (`--exclude-studies` with `--species`), leaves the listed studies out of a search; empty by default.
- Release automation (#26, #27): a version tag runs `.github/workflows/release.yml`, which checks the tag
  against the version and this changelog, tests the wheel in a clean environment on Linux, Windows and
  macOS, builds and starts the Windows program, publishes to PyPI through trusted publishing once a
  maintainer approves, and creates the GitHub release with the notes from this changelog and
  `grownet-<version>-windows.zip` attached. CI builds and starts both on every push. A double-clicked
  `grownet.exe` opens the page, and on an error waits for Enter instead of closing. RELEASING.md gives the
  setup and the steps; the README's install section offers the Windows zip, uv and PyPI.
- The gate gained a merge-marker check, after conflict markers from a merge reached this changelog
  unseen (now removed, both sides kept).
- Documentation made to agree with the code, after an audit (21 conflicts): the README's Cytoscape style,
  output example and field descriptions, technique rule, metric options and correction; the help page's
  effect, community and empty-result wording; "k = 0 marks only a mean of exactly zero absent" everywhere;
  METHOD_NOTES' defaults at a glance, rewritten from the running code; the viewer's derivation panel,
  which described the retired baseline, replaced by a plain statement. The viewer's GraphML now writes all
  of export.py's keys (it wrote 9 of 34), and a test runs it with Node against the CLI's. Page and CLI
  defaults are checked equal by a test.
- Merge parallel arcs (register item 14, Karoline's choices): an advanced setting, off by default
  (`--merge-arcs`), making the arcs of each source and target, across conditions, studies and evidence, one
  arc with the median log2 mean and its range; arcs whose signs disagree are not merged, absent arcs stay
  separate. Minimum supporting studies (`--min-studies`) keeps arcs resting on that many studies. Edges
  gain `merged_arcs` and `strength_range`.
- A species is compared only when its monocultures and co-cultures (or full community and drop-out) were
  measured by the same technique, not only in the same unit (Karoline, METHOD_NOTES item 23). No edge in
  mGrowthDB changed; it guards future data.
- With "only interactions between the species entered" (the default), a search reads only what can give
  such an interaction: monocultures and co-cultures of the entered strains, and whole drop-out designs
  holding two of them. Searches take about half as long (the Example about 2 s once the species list is
  in); checked on eight searches, the networks are identical to reading everything.
- The standalone viewer (`gui/index.html`) draws the legend's colors, one arrowhead, dashes for evidence
  and quality, and genus colors. CI also runs on Windows and macOS. The species list looks 25 missing
  study ids ahead instead of 5. Download, Report and Send to Cytoscape answer for the search on screen. A
  study of monocultures only says so.
- A strain is shown by its current name (#24, Karoline's rule of 2026-09-18): the name used by the most
  recently published study holding its taxon id, in the network's nodes and the resolved list; old names
  still find it. Taxon 411483 now reads Faecalibacterium duncaniae throughout.
- Growth rate as a metric (#41): `--metric growth_rate` and the Growth measure setting, with the
  implementation as its own setting (`--rate-method`): easylinear by default, as mGrowthDB computes its
  reported rates (it matched them on 190 of 192 curves within 10%), window 5 (`--rate-window`); or a
  guarded Baranyi fit, where a curve the model does not describe is left out and reported. The edge's
  metric names the rule (`growth_rate:easylinear:5`). The default for interactions stays auc.
- Faster: the Example search takes about 10 s from a cold start instead of 84 s, and about 4.5 s for a
  later search in the same session instead of 25 s. Nearly all the time was requests made one after
  another; they are now made six at a time over kept-open connections (`crossfeed.fetch`), and the
  derivation reads them from the cache it always used. Checked on every study: records, skip reasons
  and the species list are identical to the one-by-one version. A growth curve download is now retried
  like every other request.
- Conditions recorded only in descriptions (Karoline, METHOD_NOTES item 22): monocultures are pooled only
  when their descriptions agree; a co-culture uses the monoculture set whose description names it, or is
  skipped with the reason when several fit; edges from description-only variants carry the new caution
  `conditions_unverified`; failing a name, the set whose name has the same qualifier ("Evolved AtCt" with
  "Evolved At"). SMGDB00000014 now derives nothing, each pair saying why.
- Nodes in Cytoscape: each genus its own color (Karoline), from a list of 48 ordered by how distinct each
  stays. Fixed: a second send in one Cytoscape session arrived unstyled, because updating the existing
  style asked CyREST to delete all mappings at once, which it refuses; they are now deleted one by one.
- Fixed: Send to Cytoscape delivered the network without its style. CyREST applies styles and layouts
  by GET and refused the POST (405), and the error was swallowed. The style is now called grownet,
  brought up to date in place when Cytoscape already has it, and a failure is reported on the page.
  Nodes are colored by genus (the first word of the name): four hues checked for color vision
  deficiency against the arc colors, and further genera each their own color from a list ordered by
  how distinct it stays; labels sit under the nodes.
- The species box starts empty, under the header "Species, strains or NCBI taxon ids" and a smaller row
  of examples (a species, a strain, a taxon id). An empty result says which step found nothing. GraphML
  nodes carry a `label` (the strain name), which Gephi uses as the node label.
- The result appears on the same page, under the settings that produced it (#74); a search in progress
  shows a progress bar and the page updates by itself, without JavaScript (#75); three outputs sit above
  the table: Download network with a JSON or GraphML menu, Send to Cytoscape, and Report, the detailed
  comments of the search with every setting and the tool version, shown on the page and downloadable as
  a text file (#76). `tests/test_interface.py` checks each of Karoline's requirements for these.
- The local page is drawn in the grownet style Karoline approved: a header with the mark, the name and
  the version, Legend and Help; one green primary action; quiet table headers, directions in the legend's
  two colors (inhibition the orange-red #C2410C) and flags as pills. The legend opens inside the same
  frame. The page, the help and every network's `meta` name the tool grownet; the command stays
  `crossfeed` until the package is renamed (#71).
- The tool version shows next to the name on the local page. Every network's `meta` records the tool,
  `tool_version`, `derived_on` and every setting used; GraphML carries the first three as graph
  attributes (#78).
- The local page gained an Example button, which fills the species box with a pair that derives a network
  (Faecalibacterium duncaniae and Blautia hydrogenotrophica), and a Help button opening a help page that
  explains what the tool does, how to read a result, and links the legend (#73).
- The mark (`docs/logo.svg`): three nodes joined by directed edges, green for facilitation and red for
  inhibition, both with the same arrowhead. It is the page's favicon and sits beside its title.
- A legend (`docs/legend.svg`, `make legend`, and "What the arcs mean" on the local page): one picture of
  what each arc, head, dash and flag means. It is drawn from the code, and a test requires it to name every
  value in the model's vocabulary, so it cannot drift from what the network shows.
- Chemostat and serial dilution experiments are left out of a derivation by default (#42), reported with
  their mode, and derived with `--include-non-batch` or the matching advanced setting, where their edges
  are flagged `non_batch`. An experiment with no recorded mode counts as not batch. Edges gained
  `cultivation_mode`. SMGDB00000001, SMGDB00000005 and SMGDB00000011 now say why they derive nothing.
- Send a network into a running Cytoscape (#25): `crossfeed derive ... --to-cytoscape` and a
  "Send to Cytoscape" button on the local page post it through CyREST on localhost, with the style the
  legend describes (direction by color and arrowhead, width by weight, absent edges hidden, drop-out arcs
  long-dashed and single-replicate arcs dotted). `crossfeed style` writes the style as a file instead.
  Cytoscape not running is reported with the port, never as a traceback. No new dependency.
- The no-growth rule (#37): before any ratio, a species counts as grown in a replicate set only when its
  rise from the first time point, log2(maximum / start) per replicate with each maximum at its own time,
  is significant (paired t-test, alpha 0.05) or reaches 1.5 times as a geometric mean. A set that did not
  grow feeds the existing `obligate`, `abolished` and `no_growth` outcomes instead of a ratio between two
  near-zero quantities. Both numbers are settings (`--no-growth-alpha`, `--no-growth-factor`, and the
  advanced settings on the local page), and `meta.no_growth` records them with the obligate and abolished
  counts. In SMGDB00000013 this makes Comamonas to Ochrobactrum obligate.
- A pluggable derivation seam (`crossfeed.derive.Deriver`): the comparison method is a drop-in strategy,
  with the provisional `BaselineDeriver` as one implementation. The agreed method arrives as another
  `Deriver` without touching the model or the pipeline.
- A generic command line (`python -m crossfeed derive|validate|schema`, and a `crossfeed` console script)
  that derives a network for any mGrowthDB study, validates a network document, or emits the schema.
- A `--deriver MODULE:CLASS` flag on `crossfeed derive` to run a custom derivation method live with no
  glue code, plus a complete, runnable `examples/custom_deriver.py` and tests that keep it working.
- The README rewritten as a complete guide: install, run, the output format with an annotated example,
  and how to plug in a method end to end, so a new contributor never has to root around other docs.
- A published JSON Schema for the neutral format (`schema/interaction_network.schema.json`) plus a
  dependency-free `crossfeed.schema.validate_document`.
- `crossfeed gui`: a local page (standard library server on 127.0.0.1, a token in the URL, no JavaScript)
  where you type species names or NCBI taxon ids and get their interactions as a table, with every
  setting behind "Advanced settings" and downloads for JSON and GraphML.
- The pipeline now derives through the comparison the collaboration specified: `ReplicateDeriver` is the
  default for a live derivation, comparing replicate sets on the log2 scale (area under the curve by
  default, maximal abundance selectable with `--metric`), so every edge carries a standard error, the
  replicate counts, and the outcome. `BaselineDeriver` remains only as the retired placeholder.
- Network edges gained optional `p_value`, `weight`, `effect_over_sd`, `status`, `sd`, `se`, `n_with`, `n_without`, `outcome`, `metric`, `quality`, and
  `notes` fields, in the model, the JSON Schema, and GraphML.
- Presence and absence follow an absence threshold k: an edge's `status` is `absent` when its
  |log2 mean| is below k times its standard deviation, `present` otherwise (default k = 1, the mean plus
  or minus sd rule; `--absence-threshold`, 0 marks nothing absent). Every tested comparison is exported as
  an edge with `status`, `weight` (|log2 mean|, always positive) and `effect_over_sd` (|log2 mean| / sd), so
  the threshold can be changed later, including in Cytoscape; the display hides absent edges by default.
  There is no neutral edge. Low-quality edges (a single replicate, pooled strains) keep the sign of their
  mean, are flagged in `quality`, and are left out by default (`--include-low-quality`).
- Welch's t-test on the per-replicate log2 values is reported on every comparison with two replicates per
  side, with the raw `p_value` and the Benjamini-Hochberg adjusted `significance`; it supports an edge but
  does not decide one (`crossfeed.stats`, standard library only).
- An implausible spike in a growth curve is flagged and that curve left out for its species only, never
  dropped silently (`crossfeed.growth.spike`: one or two consecutive interior points more than the limit above both
  neighbours, default limit 100, 0 to switch off). The report names the time points and, for the flagged strain, whether other measurements
  of it in the same replicate are clean; a community trace counts only in a monoculture.
- `crossfeed.adapter`: mGrowthDB experiments become replicate growth curves, so the comparison the
  collaboration specified (`crossfeed.interaction`) can run on real data. Time series come from the CSV
  representation of a measurement context (`MGrowthDBClient.get_measurement_series`); `Average(...)`
  bioreplicates are left out, since they are the mean of the real replicates.
- `crossfeed.taxonomy`: species names resolved to NCBI taxon ids from mGrowthDB's own strain records
  (`species_index`, `resolve_species`), so a person can type names where the API takes ids. A name
  resolves to every taxon id mGrowthDB holds under that genus and species, species level and strain level.
- A GraphML export (`crossfeed derive --format graphml`, and `crossfeed.export.to_graphml`) so a network
  drops straight into Cytoscape, igraph, networkx, or Gephi. Dependency-free (standard library xml only).
- Optional `evidence` (`biculture` or `dropout`) and `community` fields on network edges, in the model,
  the JSON Schema, and GraphML, so arcs from drop-out communities (not necessarily direct) are labeled
  apart from mono versus bi-culture arcs. The provisional baseline marks its edges `biculture`.
- mGrowthDB client hardening: in-memory and optional on-disk response caching, and retries with backoff
  on transient network failures and 5xx responses.
- An expanded guardrail gate (`checks/gate.py`) covering secrets, raw data, local-machine paths,
  self-contained imports, house style (ASCII punctuation, US spelling, no hedging caveats), and a schema
  contract check. A pre-commit hook and a Makefile run the gate, tests, and lint the same way CI does.
- Helpers for a pairwise interaction strength from replicate growth curves: `crossfeed.growth`
  (`GrowthCurve`, `Replicate`, unit and species checks across replicate sets, `curve_features` for the
  area under the curve and maximal abundance over a shared time window) and
  `crossfeed.interaction.interaction_strength` (per species, the difference of mean log2 growth property
  between co-culture and monoculture replicates, with standard deviation, standard error, and n).
- A shared workflow for coding agents: `AGENTS.md` (instructions and the mayor, worker, and verifier
  roles), Feature and Task issue forms, and `docs/agents/NOTES.md` as shared agent memory.
- `crossfeed.interaction.dropout_interaction_strengths`: arcs from drop-out communities (the full
  community against the community without one species), using the same log2 set comparison as
  `interaction_strength`, with each arc labeled `dropout` (not necessarily direct) or `biculture` and its
  community recorded.
- Zero growth is reported as a result instead of an error: a target that grows only with the source present
  gets the outcome `obligate` (obligate commensal or mutualist), one that grows only without it `abolished`,
  in both `interaction_strength` and `dropout_interaction_strengths`.

- Drop-out designs reach the default network (#47): a community plus experiments holding it without one
  member give arcs labeled `evidence: dropout`, included by default and left out with `--no-dropout` or
  the matching advanced setting. Experiments are pooled only under identical conditions, and
  SMGDB00000008 now derives.
- Edges gained optional `cautions` (`two_replicates`, shown without making an edge low quality) and
  `experiments` (the ids of the experiments an edge compares), plus the quality flag
  `removed_member_detected`.

### Fixed
- A file the command line cannot read or write (a missing fixture, an output folder that does not exist,
  a file that is not JSON) is reported in one line, with the folder a relative path was read from, instead
  of a traceback. The README's offline Quickstart says it runs from a clone: the fixture is in the
  repository's `tests/fixtures`, not in an installed grownet (found by Karoline after a pip install).
- The style file imports in Cytoscape: `grownet style` and the help page's download now write Cytoscape's
  XML style format (`grownet_style.xml`). File, Import, Styles from File refused the JSON file with "Don't
  know how to read file" (found by Karoline in Cytoscape 3.10.4); Cytoscape reads no JSON style file, its
  own exports included. Send to Cytoscape was not affected.

### Changed
- Fewer requests to mGrowthDB, with identical networks (checked on all of mGrowthDB): a monoculture no
  co-culture of its study is compared with is no longer read (All: 3709 -> 1313 requests, 26 s -> 9 s), and
  the local page keeps what it has read for an hour, renewed with the species list, so a second search
  reads only what is new (the Example after All: 141 -> 4 requests). The skip list no longer lists the
  replicates of monocultures that were never compared (All: 1961 -> 191 entries).
- The rename (#71): the package, the module and the command are `grownet` (`grownet derive ...`, `python -m
  grownet`, `uvx --from git+https://github.com/crossfeed-bio/crossfeed grownet gui`), with no `crossfeed`
  alias, since nothing had been released. The repository address and the method label stored in each
  network (`crossfeed replicate v1`) are unchanged. The README is titled "grownet: Growth-curve
  derived interaction networks".
- The schema id is `grownet.interaction_network/v0` (#71, Craig's half of the rename). A new namespace at
  the same version: the format itself does not change, and a version states what the content is, not what
  it is called. The id is written into every network grownet saves, so it is changed before 0.1.0, while
  nothing has been released and no published file carries the old one. A document with the old id is
  rejected with a message naming both, rather than accepted silently, so one format keeps one id.
- The Baranyi growth-rate fit uses the curve up to the end of the plateau after its maximum, not the whole
  curve, so a decline after the peak no longer rejects it (register item 29): 30 -> 40 arcs on mGrowthDB.
- A curve that starts after its design's common start leaves its replicate out of that member's own arcs
  only; the replicate still serves the other members (SMGDB00000008: 24 arcs regain a second replicate).
  The page, the report and the command line list average replicates as one line per experiment.
- Each bi-culture arc is compared over its own window, the target's curves alone and together, as drop-out
  arcs already were, so the partner's shorter monoculture no longer shortens it (register item 26). On
  mGrowthDB one arc changes (SMGDB00000006, L. bulgaricus -> S. thermophilus STpos: +0.088 to +0.074,
  absent either way).
- Inhibition is drawn in orange-red (#C2410C) rather than red (Karoline, 2026-09-27). With uniform arc
  tips the color is the only cue for the sign, and green against red is the hardest pair for a reader with
  a color vision deficiency: simulated, the new pair stays about 90 sRGB units apart under protanopia and
  deuteranopia, where green and red managed 58. `tests/test_palette.py` keeps it that way.
- Arcs end in the same arrowhead whether they facilitate or inhibit: the color carries the sign, in the
  legend and in the Cytoscape style (Karoline, 2026-09-27). The bar head is retired.
- Nodes are strains keyed by NCBI taxon id (`ncbi:411483`) and named with the strain name, with `taxon_id`,
  `species` (genus and species from the name) and `identity` as node fields (#23). Monocultures are matched
  to co-cultures by taxon id, so another strain of the same species is never used: in SMGDB00000006,
  L. bulgaricus to S. thermophilus LMG 18311 is now obligate instead of a +2.93 edge computed against the
  STpos strain's monoculture. A taxon id a study gives to different strains falls back to names.
- Single-replicate edges are shown by default, keeping the `single_replicate` flag and an undetermined
  status, for the Cytoscape style to mark; the other low-quality flags stay hidden by default.
- A co-culture is compared only with monocultures grown under the same conditions (cultivation mode and
  compartments); no current study is affected.
- crossfeed now has no runtime dependencies: the client uses the standard library `urllib`, and the
  unused `requests` dependency was dropped.

### Fixed
- From Karoline's checks (audit step 8): Help, Legend or About opened from a result, then Back, returned to
  an empty page and the result was lost; their links and Back now carry the search, so Back returns to it.
  A GraphML file imported into Cytoscape did not take the whole grownet style, because the file lacked the
  columns the style maps; GraphML now carries genus, genus_color, line_style and display_weight, from the
  tool and the viewer alike, and the viewer's genus rule matches the tool's (qualifiers skipped, NCBI's
  brackets kept). The help page says how to style a GraphML file in Cytoscape, and that Gephi may merge
  parallel arcs on import.
- From a code review of the whole package (2026-09-28): with the growth rate (easylinear), a curve that only
  declines crashed the comparison and dropped the whole pair or community (SMGDB00000014 lost three
  co-cultures); its rate is now its steepest, non-positive slope. A problem with one species (mixed
  abundance units, a technique mismatch, a later start) now leaves out that species' arcs only, not the
  pair or the community, and units are checked per species, since each is compared only with itself. The
  no-growth rule, the stationary check and the zero-at-start check leave out replicates excluded for a
  spike. Merge to genus counts a strain that studies name differently once. The local page keeps its 20
  latest searches, reads the species list again after an hour, and builds it once when two searches start
  together.
- When mGrowthDB could not be reached (a network failure, a timeout, server errors), the species list came
  back empty and a search said the species were not in mGrowthDB. Only "no such study" (HTTP 404) now ends
  the crawl; anything else stops the search with "mGrowthDB could not be read". A replicate or growth curve
  that fails to download partway through a search now marks the result incomplete at the top of the page,
  in the report and on the command line, instead of only among the pairs the data did not support.
- A node keyed by name, because mGrowthDB gives its taxon id to more than one species, keeps its own name:
  the current-name step renamed it by the id's latest name, so in SMGDB00000008 Lachnoclostridium
  symbiosum WAL-14673 appeared as a second L. clostridioforme (found by the audit of 2026-09-28).
- The README and the help page now say that curves are compared over the time window they share.
- "Only interactions between the species entered" no longer drops every edge when a study records a strain
  under another name: a species entered as Faecalibacterium duncaniae now matches the same taxon recorded
  as Faecalibacterium prausnitzii, because the filter matches taxon ids as well as names (#73).
- The spike guard no longer mistakes a die-off or late growth for a spike (#62). It compared a curve's
  maximum with its median, which flagged curves spanning several orders of magnitude (22 curves in
  SMGDB00000013, 7 in SMGDB00000014, 2 in SMGDB00000004) and emptied whole replicate sets. A spike is now
  one or two consecutive points above both neighbours by the limit, never the first or last point. The
  BH_14 spike it was built for is still caught; SMGDB00000013 goes from 10 edges to 16.
- An obligate or abolished edge is no longer flagged `single_replicate` for having no growing replicates on
  the side where no growth is its result; that side counts its replicates without growth (#47).
- A comparison whose replicate set was emptied by exclusions (every replicate spiked) is skipped with a
  reason instead of being reported as obligate or abolished; four such edges in SMGDB00000013 were false.
- The viewer in `gui/` shows an edge's `evidence`. A `dropout` arc is labeled indirect in the interaction
  list, the detail panel, and the hover text, carries the community it came from, and is drawn with an
  open ring at its midpoint. The ring is a channel the sign does not use (sign stays color, dash, and
  arrowhead), so an arc that may act through a third species no longer reads as a direct one.
- The baseline reports a monoculture it had to drop. Nodes are keyed at genus and species, so two strains
  of one species share a key and only the last monoculture read is used; that collision now appears in
  `skipped` naming both strains instead of passing silently. Which strain to keep is a method choice
  (see "Open decisions" in `docs/METHOD_NOTES.md`), so the derivation itself is unchanged.

## [0.0.1] (2026-09-14)

### Added
- Initial public release: the neutral interaction-network model with edge-level attribution, the live
  mGrowthDB API client, and the FP/BH first slice running on the published study SMGDB00000004 and
  recovering Blautia hydrogenotrophica facilitating Faecalibacterium prausnitzii.
