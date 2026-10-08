"""What makes two experiments the same medium (`grownet.media`), on the phrasings mGrowthDB holds.

Karoline, 2026-10-07, closing the open decision on #141: "capacity merge by medium is a good idea. in
addition, we can do the stricter test that foodnet does; medium matches but contradicting extras, such as
acetic acid or mucin, do not count as matching medium", and on where it applies: "foodnet's strict medium
rule should be applied in general in case someone specifies it in the 2nd search box (because such changes
alter interactions); and it should also be documented".

Every description quoted here is one mGrowthDB serves today. The rule is foodnet's, with one adaptation
grownet needs, which the last test pins: an experiment's **name** is not read for alterations, because in
a tool that reads co-cultures "+X" names a community member.
"""


from grownet import media


def _exp(name, description="", compartments=None, **gases):
    return {"name": name, "description": description,
            "compartments": compartments or [{"mediumName": "Wilkins-Chalgren", **gases}]}


# ---- the name, reduced to what tells media apart --------------------------------------------------

def _key(name, **aliases):
    return media.base_key({"compartments": [{"mediumName": name}]})


def test_case_punctuation_and_an_abbreviation_do_not_make_another_medium():
    """Two studies writing one medium two ways are one medium, without any help from the alias table."""
    assert _key("Wilkins-Chalgren Anaerobe Broth (WC)") == _key("Wilkins-Chalgren Anaerobe Broth")
    assert _key("Db-MM medium") == _key("Db-MM medium ")
    assert _key("mMCB") != _key("Wilkins-Chalgren Anaerobe Broth")
    assert _key("") == "unnamed medium"


def test_the_alias_table_is_what_makes_the_four_live_spellings_one_medium():
    """Karoline, 2026-10-07: "yes, add the alias table". Two of the four spellings mGrowthDB serves
    disagree with the others rather than being less complete: "Anerobe" is a typo and "Wilkins-Chalgren"
    alone is a short form, and the rule by itself tells both apart from the full name. The table says
    they are one medium anyway, and `identity` reports which entry fired so no merge is silent.

    Without the table the two would not match, which is the measured cost the table buys back: keying
    took the chemostat validation from 2 scored to 1 (`docs/METHOD_NOTES.md`, section 8)."""
    full = "Wilkins-Chalgren Anaerobe Broth"
    for other in (full, "Wilkins-Chalgren Anaerobe Broth (WC)", "Wilkins-Chalgren Anerobe Broth (WC)",
                  "Wilkins-Chalgren"):
        assert _key(other) == _key(full), other

    short = media.identity({"compartments": [{"mediumName": "Wilkins-Chalgren"}]})
    assert short["aliases"] == (("wilkins chalgren", "wilkins chalgren anaerobe broth"),)
    typo = media.identity({"compartments": [{"mediumName": "Wilkins-Chalgren Anerobe Broth (WC)"}]})
    assert typo["aliases"] == (("anerobe", "anaerobe"),)
    assert media.identity({"compartments": [{"mediumName": full}]})["aliases"] == ()

    # and the label is still what the study wrote: an alias decides identity, never what a reader is told
    assert short["label"] == "Wilkins-Chalgren"

    # without the table the rule tells them apart, which is why each entry is a judgement rather than a
    # rule: a character substitution says two names disagree
    saved_words, saved_names = dict(media.WORD_ALIASES), dict(media.NAME_ALIASES)
    try:
        media.WORD_ALIASES.clear()
        media.NAME_ALIASES.clear()
        assert _key("Wilkins-Chalgren Anerobe Broth (WC)") != _key(full)
        assert _key("Wilkins-Chalgren") != _key(full)
    finally:
        media.WORD_ALIASES.update(saved_words)
        media.NAME_ALIASES.update(saved_names)


def test_an_alias_does_not_reach_an_alteration():
    """The table merges names, not environments: a medium with glucose taken out stays its own medium
    however its base name is spelled."""
    plain = {"compartments": [{"mediumName": "Wilkins-Chalgren"}]}
    changed = {"compartments": [{"mediumName": "Wilkins-Chalgren Anaerobe Broth"}],
               "description": "WC without glucose"}
    assert not media.same_medium(plain, changed)


def test_a_two_compartment_design_is_not_the_same_medium_as_either_compartment():
    """`selection.medium_of` joins one name per compartment, and the subset rule this replaced matched
    the joined name to one of its own compartments, which loses which compartment the organism was in
    (#142 item 13). Both names of SMGDB00000002's design are kept, sorted."""
    composite = {"compartments": [{"mediumName": "Wilkins-Chalgren Anaerobe Broth (WC)"},
                                  {"mediumName": "Mucin"}]}
    one_side = {"compartments": [{"mediumName": "Wilkins-Chalgren Anaerobe Broth (WC)"}]}
    assert media.base_key(composite) == "mucin; wilkins chalgren anaerobe broth"
    assert media.base_key(composite) != media.base_key(one_side)
    assert not media.same_medium(composite, one_side)


# ---- the alterations the description states -------------------------------------------------------

def test_an_added_compound_makes_another_medium_and_the_amount_is_part_of_it():
    """SMGDB00000014 runs one minimal medium at five concentrations of linoleic acid, which are five
    environments: "0.1% and 0.75% linoleic acid" is the case Karoline named."""
    low = _exp("At_LA_0.05", "Growth of At on minimal medium with 0.05% linoleic acid")
    high = _exp("At_LA_0.75", "Growth of At on minimal medium with 0.75% linoleic acid")
    assert media.alterations(low) == ("+0.05% linoleic acid",)
    assert media.alterations(high) == ("+0.75% linoleic acid",)
    assert not media.same_medium(low, high)
    assert media.same_medium(low, _exp("other", "minimal medium with 0.05 % linoleic acid"))


def test_the_phrasings_the_database_uses_for_something_added():
    cases = {
        "WC plus mucin beads": ("+mucin",),
        "supplemented with 2g/L trehalose": ("+2g/l trehalose",),
        "mZMB supplemented with lactose (20 g/liter),": ("+lactose",),
        "WC + 10 mM acetate": ("+10mm acetate",),
        "0.1mg/L pantothenate added in the culture": ("+0.0001g/l pantothenate",),
        "with initial acetate": ("+acetate",),
        "20 mM fructose instead of glucose": ("+20mm fructose", "-glucose"),
    }
    for description, expected in cases.items():
        assert media.alterations(_exp("E", description)) == tuple(sorted(expected)), description


def test_the_phrasings_the_database_uses_for_something_taken_away():
    cases = {
        "WC without glucose and pyruvate": ("-glucose", "-pyruvate"),
        "with no additional acetate": ("-acetate",),
        "No supplied pantothenate in culture": ("-pantothenate",),
        "glucose-free WC": ("-glucose",),
        "DM29 lacking carbohydrates": ("-carbohydrates",),
    }
    for description, expected in cases.items():
        assert media.alterations(_exp("E", description)) == tuple(sorted(expected)), description


def test_one_amount_has_one_spelling():
    """5000 mg/L and 5 g/L are one medium, as are 1000 uM and 1 mM, so a study that writes the same
    concentration two ways does not become two media (SMGDB00000019 writes pantothenate in mg/L)."""
    for one, other in (("supplemented with 5000 mg/L glucose", "supplemented with 5 g/L glucose"),
                       ("supplemented with 1000 uM galactose", "supplemented with 1 mM galactose"),
                       ("supplemented with 1 mM galactose", "supplemented with 1mM galactose")):
        assert media.same_medium(_exp("E", one), _exp("E", other)), (one, other)


def test_an_amount_of_zero_is_the_control_and_not_an_addition():
    """SMGDB00000014's no-fatty-acid arms are stated as "0% linoleic acid" and "0% oleic acid", and the
    amount pattern matched the stated zero, so each became a medium with a compound added at zero: two
    media that do not exist. Neither was plain minimal medium and neither matched the other, though all
    three are the same plain medium, and the capacity went to whichever of these fictions had the most
    certified curves (#155 item 3).
    """
    plain = _exp("control", "At grown on a minimal medium")
    zero_linoleic = _exp("0% LA", "At grown on a minimal medium with 0% linoleic acid")
    zero_oleic = _exp("0% OA", "At grown on a minimal medium with 0.0% oleic acid")
    for control in (zero_linoleic, zero_oleic):
        assert media.alterations(control) == ()
        assert media.same_medium(plain, control), control["name"]
    assert media.same_medium(zero_linoleic, zero_oleic)

    # and a real amount is still an addition, including one whose first character is a zero
    some = _exp("0.1% LA", "At grown on a minimal medium with 0.1% linoleic acid")
    assert media.alterations(some) == ("+0.1% linoleic acid",)
    assert not media.same_medium(plain, some)
    # a zero of one compound beside a real amount of another keeps only what was added
    mixed = _exp("mixed", "minimal medium with 0% linoleic acid and 0.5% oleic acid")
    assert media.alterations(mixed) == ("+0.5% oleic acid",)
    # every unit, not only per cent
    assert media.alterations(_exp("E", "WC + 0 mM acetate")) == ()
    assert media.alterations(_exp("E", "WC + 10 mM acetate")) == ("+10mm acetate",)
    # the label carries nothing either, so an arc records the plain medium it was measured in
    assert media.identity(zero_linoleic)["label"] == media.identity(plain)["label"]


def test_a_label_written_before_the_zero_rule_reads_as_the_plain_medium():
    """`key_from_label` reverses `identity`'s label, so it has to apply the same rule. A network derived
    before the rule carries "Minimal medium (MM) (+0% linoleic acid)", and reading that as an alteration
    would make its arcs disagree with a freshly derived plain medium: the capacity would be keyed to one
    and the arcs to the other (#155 item 3)."""
    plain = media.key_from_label("Minimal medium (MM)")
    assert media.key_from_label("Minimal medium (MM) (+0% linoleic acid)") == plain
    assert media.key_from_label("Wilkins-Chalgren (-0 mM acetate)") == media.key_from_label("Wilkins-Chalgren")
    # and a real amount in a label is still an alteration, including beside a zero
    assert media.key_from_label("Minimal medium (MM) (+0.75% linoleic acid)") != plain
    assert (media.key_from_label("Minimal medium (MM) (+0% linoleic acid, +0.5% oleic acid)")
            == media.key_from_label("Minimal medium (MM) (+0.5% oleic acid)"))


# ---- the atmosphere ------------------------------------------------------------------------------

def test_a_recorded_atmosphere_splits_a_medium_and_an_unrecorded_one_joins_it():
    gassed = media.identity(_exp("E1", compartments=[{"mediumName": "WC", "CO2": 10, "N2": 90}]))
    other_gas = media.identity(_exp("E2", compartments=[{"mediumName": "WC", "CO2": 20, "N2": 80}]))
    silent = media.identity(_exp("E3", compartments=[{"mediumName": "WC"}]))
    assert gassed["atmosphere"] == "CO2 10, N2 90" and silent["atmosphere"] == ""
    keys = [i["key"] for i in media.assign_atmospheres([gassed, other_gas, silent])]
    assert keys[0] != keys[1]                 # two recorded atmospheres are two media
    assert keys[2] in (keys[0], keys[1])      # one that records none joins the commoner variant


# ---- the label a network carries -----------------------------------------------------------------

def test_the_label_a_network_carries_gives_the_key_back():
    """An arc and a chemostat run record a medium's label, not the experiment, so two media already
    measured have to be comparable from the label alone (`steady.same_medium`). Checked over the whole
    live database on 2026-10-07: all 559 experiments' labels give their own key back."""
    for exp in (_exp("E", "Growth of At on minimal medium with 0.05% linoleic acid",
                     [{"mediumName": "Minimal medium (MM)"}]),
                _exp("E", "", [{"mediumName": "Wilkins-Chalgren Anaerobe Broth (WC)"},
                               {"mediumName": "Mucin"}]),
                _exp("E", "WC without glucose and pyruvate")):
        ident = media.identity(exp)
        assert media.key_from_label(ident["label"]) == ident["key"], ident["label"]
    assert media.key_from_label("") == ""


def test_two_media_differing_in_one_word_are_named_as_a_near_miss_not_merged():
    """For a spelling nobody has put in the alias table: a reader is told the two names differ in one
    word, rather than that the environments differ (Craig's agent, on #141). The four Wilkins-Chalgren
    spellings are in the table, so they are one medium and not a near miss at all."""
    assert media.near_miss("Db-MM medium", "Db-MN medium") == ("mm", "mn")
    assert media.near_miss("Wilkins-Chalgren Anaerobe Broth (WC)",
                           "Wilkins-Chalgren Anerobe Broth (WC)") is None     # aliased, so one medium
    assert media.near_miss("Wilkins-Chalgren Anaerobe Broth", "mMCB") is None
    assert media.near_miss("WC", "WC") is None                       # the same medium is not a near miss
    assert media.near_miss("WC (+mucin)", "WC") is None              # an addition is a real difference


# ---- the adaptation grownet needs ----------------------------------------------------------------

def test_a_co_culture_name_is_not_read_as_a_supplement():
    """foodnet also reads "+X" and "-X" in an experiment's name, which its own module says is safe
    because foodnet reads monocultures. grownet reads co-cultures, where those forms name community
    members: SMGDB00000013's At+Ct and Ct+Ms, SMGDB00000006's LB+STneg. Reading them would split those
    two studies into 4 and 3 media that do not exist, which would keep a co-culture from ever matching
    its own monocultures."""
    members = _exp("At+Ct", "Pairwise co-culture of At and Ct.")
    alone = _exp("At", "Triplicate monoculture of At")
    assert media.alterations(members) == () and media.alterations(alone) == ()
    assert media.same_medium(members, alone)
    assert media.same_medium(_exp("LB+STneg", "LB+STneg"), _exp("STneg", "STneg"))


def test_switching_the_strict_rule_off_leaves_the_names_alone():
    """`strict=False` is what every medium comparison did before 0.3.0: the names only."""
    low = _exp("At_LA_0.05", "minimal medium with 0.05% linoleic acid")
    high = _exp("At_LA_0.75", "minimal medium with 0.75% linoleic acid")
    assert not media.same_medium(low, high)
    assert media.same_medium(low, high, strict=False)
