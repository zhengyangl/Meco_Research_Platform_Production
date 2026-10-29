# The Big Picture

*A plain-language introduction to what this project is, why it exists, and what you can do with it. No background in biology, ecology or data science assumed. Think of this as a preface — it sketches the idea and points you to where the real detail lives. If you want the technical story, each section links to the right document.*

---

## The one-paragraph version

A researcher named Dr. Shoshanah Jacobs and her group study **biomimetics** — technology that borrows ideas from nature (think velcro, copied from the burrs that stick to your socks, or building ventilation modelled on how termite mounds stay cool). Over the years they gathered two collections of research data, but both lived in spreadsheets that were hard for outside scholars to search or explore — even as more and more people asked to use them. This project turns those collections into two live, searchable platforms, and, in the process, takes a closer look at the data and raises a few questions worth exploring further. This repository holds both platforms.

---

## Two collections, two platforms

The group had two separate bodies of data. Each became its own platform, and the two share nothing except this code repository — kept together only because it makes them easier to maintain.

### 1. MEco — the research literature

**The big idea: when we build technology "inspired by nature," are we working *with* nature, or quietly replacing it?**

Nature does a lot of work for us for free — forests clean our air, wetlands filter our water, insects pollinate our crops. Scientists call these **ecosystem services**. Bio-inspired design is often held up as a greener way to build things, on the premise that copying nature's principles should help us live more lightly alongside it.

But is that premise actually borne out across the field? A study by Jacobs et al. (2025) looked at the research as a whole and suggested a more uncomfortable possibility: that much "bio-inspired" technology may be designed to *replace* a natural process rather than support it — what the authors framed as a *design paradigm crisis*. It's a provocative claim, and the kind that invites you to check it for yourself.

The trouble was that you couldn't. The finding sat inside a single paper as fixed charts and tables. A curious researcher, policymaker, or designer who wanted to ask their own question — which natural services get the least attention? which countries fund this work? — had no way in. You could read the conclusion, but you couldn't touch the evidence.

**That's what MEco opens up.** It takes a large body of research papers (tens of thousands, spanning 2004–2025), uses an AI model to sort each one, and presents the result as two connected pages:

- A **Narrative page** that walks any visitor through the main story in plain charts. Its numbers are deliberately held steady at a specific published version of the data, so a figure you cite today still means the same thing later.
- A **Data Explorer** that lets researchers filter, search, and download the full dataset themselves — and which keeps growing as new papers are added.

Explore it and you'll find that the platform's own analysis echoes the original study's central pattern — a strong lean toward replacing ecosystem services rather than supporting them — and then opens up a couple of threads the original work didn't pursue: questions about *which* academic fields are driving this research (and which, notably, are absent), and about whether even the "nature-supporting" work really speaks the language of ecology, or of engineering. We'll leave those for you to find in the data rather than spell out here.

### 2. BioM — the innovation database

**The big idea: a decade's worth of real bio-inspired products, finally made searchable.**

Separately, the group maintains the **BioM Innovation Database**: detailed records of real-world **biomimetic innovations** — actual products and designs inspired by biology. It's one of the more detailed catalogues of its kind, built up over roughly ten years. Outside researchers keep asking to use it, but it has only ever existed as a spreadsheet that's awkward to search or analyse.

BioM is the dashboard that puts those records online in a browsable form, so scholars can finally dig into questions like: are products labelled "bio-inspired" genuinely bio-inspired? How closely do they imitate the forms and processes of living systems? And what can we learn from the designers who do it best?

---

## Who is this for?

Mainly the **researchers** who kept asking Dr. Jacobs for access to the data. More broadly, anyone curious enough to look at the evidence behind bio-inspired design for themselves rather than take a single paper's word for it.

---

## Where to go next

| If you want to... | Go to |
|---|---|
| See the platforms live | [meco.manufacturedecosystems.com](https://meco.manufacturedecosystems.com) |
| Understand how the whole system is built, and why | [`architecture.md`](architecture.md) |
| Know what the data actually means (ecosystem services, the Replace/Enhance/Support labels) | [`data_dictionary.md`](data_dictionary.md) |
| Set the system up from scratch | [`environment_setup.md`](environment_setup.md) |
| Operate it day to day | [`handover.md`](handover.md) |
