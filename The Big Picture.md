# The Big Picture

*A plain-language introduction to what we built and why. No background in biology, ecology or data science needed — think of this as a preface, the part of the book that gets you interested before the technical chapters begin. Every section points you to where the real detail lives.*

---

## Where this started

Our group studies **biomimetics** — technology that borrows ideas from nature. Velcro is the famous example: someone looked at how burrs cling to a dog's fur and turned it into a fastener. Engineers have modelled building ventilation on termite mounds, water-repellent coatings on lotus leaves, and a lot more.

Over the years we'd built up two collections of research data on this. The problem was that both of them lived in spreadsheets. They worked fine for us, but every time another researcher asked to use them — and people kept asking — there was no good way to hand them over. You can't really search a spreadsheet of tens of thousands of rows, and you certainly can't explore it. So we decided to put both collections online, in a form anyone could actually dig into. This repository is the result: two separate platforms, kept in one place only because it makes them easier to maintain.

While we were at it, we didn't just move the data — we took a fresh look at it, and a few things turned up that are worth a closer look. More on that below.

---

## MEco — the research literature

**The question behind it: when we build technology "inspired by nature," are we working *with* nature, or quietly replacing it?**

Here's the idea the first platform is built around. Nature does an enormous amount of work for us for free — forests clean the air, wetlands filter water, insects pollinate crops. Scientists call these **ecosystem services**. And "bio-inspired" design is usually sold as the green option, the assumption being that if we copy nature, we'll tread more lightly on it.

But does that actually hold up once you look across the whole field? Earlier work by Jacobs et al. (2025) suggested it might not — that a lot of bio-inspired technology seems built to *replace* a natural process rather than support it. The authors called it a *design paradigm crisis*. It's a bold claim, and honestly it's the kind of claim that makes you want to go check the evidence yourself.

That turned out to be the whole problem: you couldn't. The finding was locked inside one paper as a handful of fixed charts. If you wanted to ask your own question — which natural services get ignored the most? which countries are funding this? — there was nowhere to ask it.

So that's what we opened up. MEco takes a large body of research papers (tens of thousands of them, going back to 2004), has an AI model sort through each one, and lays the result out as two pages that work differently on purpose:

- A **Narrative page** that walks anyone through the main story in plain charts. We deliberately froze its numbers to one published version of the data, so a figure you cite from it today will still mean the same thing a year from now.
- A **Data Explorer** for researchers who want to get their hands dirty — filter, search, download the whole thing — and it keeps growing as new papers come in.

When we ran the analysis, our own data echoed that earlier study's central pattern: a strong tilt toward replacing ecosystem services rather than supporting them. But a couple of things showed up that the original work hadn't gone into — about *which* academic fields are doing all this research (and which ones are strikingly missing), and about whether the "nature-supporting" work really talks like ecology or more like engineering. We won't give those away here. They're more fun to find in the data, and that's exactly what the Explorer is for.

---

## BioM — the innovation database

**A decade of real bio-inspired products, finally searchable.**

The second collection is the **BioM Innovation Database** — detailed records of actual biomimetic products and designs, not research papers but real innovations. It's one of the more detailed catalogues of its kind, and our group has been building it for about ten years. Same story as before: outside researchers keep wanting to use it, and until now it was stuck in a spreadsheet nobody could comfortably search.

BioM is the dashboard that finally puts it online in a browsable form, so people can dig into the questions it was built to answer: are products labelled "bio-inspired" really bio-inspired? How closely do they actually imitate living systems? And what can we learn from the designers who get it right?

---

## Who we made this for

Mostly the **researchers** who kept asking us for the data in the first place. But really, anyone curious enough to look at the evidence behind bio-inspired design for themselves, instead of taking any one paper's word for it.

---

## Where to go next

| If you want to... | Go to |
|---|---|
| See the platforms live | [meco.manufacturedecosystems.com](https://meco.manufacturedecosystems.com) |
| Understand how the whole system is built, and why | [`architecture.md`](docs/architecture.md) |
| Know what the data actually means (ecosystem services, the Replace/Enhance/Support labels) | [`data_dictionary.md`](docs/data_dictionary.md) |
| Set the system up from scratch | [`environment_setup.md`](docs/environment_setup.md) |
| Operate it day to day | [`handover.md`](docs/handover.md) |
