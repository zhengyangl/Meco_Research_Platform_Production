# How data flows through this platform

This document explains, in plain language, how a paper's classification ends up in the
database — and where a human is involved along the way. There are **three separate
chains**. They don't run on the same schedule, and none of them waits for the others.

For the technical detail behind each script, see `architecture.md` and `handover.md`.
This page is the map, not the manual.

<p align="center"> <svg width="100%" viewBox="0 0 680 560" role="img" xmlns="http://www.w3.org/2000/svg"> <title>MEco pipeline: three independent chains</title> <desc>Chain A (new-data), Chain B (reviewed), and Feedback sync run independently and all write into the shared classifications table.</desc> <defs> <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"> <path d="M2 1L8 5L2 9" fill="none" stroke="#5F5E5A" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/> </marker> </defs> <g font-family="-apple-system,Helvetica,Arial,sans-serif">

<text x="130" y="55" text-anchor="middle" font-size="14" font-weight="600" fill="
#2C2C2A">Chain A</text> <text x="130" y="72" text-anchor="middle" font-size="12" fill="
#5F5E5A">new-data</text> <text x="340" y="55" text-anchor="middle" font-size="14" font-weight="600" fill="
#2C2C2A">Chain B</text> <text x="340" y="72" text-anchor="middle" font-size="12" fill="
#5F5E5A">reviewed</text> <text x="550" y="55" text-anchor="middle" font-size="14" font-weight="600" fill="
#2C2C2A">Feedback</text> <text x="550" y="72" text-anchor="middle" font-size="12" fill="
#5F5E5A">crowd feedback</text>

<rect x="40" y="90" width="180" height="40" rx="8" fill="#F1EFE8" stroke="#5F5E5A" stroke-width="0.5"/> <text x="130" y="114" text-anchor="middle" font-size="14" fill="#2C2C2A">Upload to Drive</text> <line x1="130" y1="130" x2="130" y2="150" stroke="#5F5E5A" stroke-width="1.5" marker-end="url(#arrow)"/> <rect x="40" y="150" width="180" height="40" rx="8" fill="#E1F5EE" stroke="#0F6E56" stroke-width="0.5"/> <text x="130" y="174" text-anchor="middle" font-size="14" fill="#085041">Classify (Qwen)</text> <line x1="130" y1="190" x2="130" y2="210" stroke="#5F5E5A" stroke-width="1.5" marker-end="url(#arrow)"/> <line x1="220" y1="170" x2="250" y2="170" stroke="#5F5E5A" stroke-width="1.5" marker-end="url(#arrow)"/> <rect x="40" y="210" width="180" height="40" rx="8" fill="#EAF3DE" stroke="#3B6D11" stroke-width="0.5"/> <text x="130" y="234" text-anchor="middle" font-size="14" fill="#27500A">Auto-ingest</text> <line x1="130" y1="250" x2="130" y2="270" stroke="#5F5E5A" stroke-width="1.5" marker-end="url(#arrow)"/> <rect x="40" y="270" width="180" height="40" rx="8" fill="#EAF3DE" stroke="#3B6D11" stroke-width="0.5"/> <text x="130" y="294" text-anchor="middle" font-size="14" fill="#27500A">Write to DB</text> <line x1="130" y1="310" x2="130" y2="330" stroke="#5F5E5A" stroke-width="1.5" marker-end="url(#arrow)"/> <rect x="40" y="330" width="180" height="40" rx="8" fill="#E1F5EE" stroke="#0F6E56" stroke-width="0.5"/> <text x="130" y="354" text-anchor="middle" font-size="14" fill="#085041">Extract features</text> <line x1="130" y1="370" x2="130" y2="390" stroke="#5F5E5A" stroke-width="1.5" marker-end="url(#arrow)"/> <rect x="40" y="390" width="180" height="40" rx="8" fill="#F1EFE8" stroke="#5F5E5A" stroke-width="0.5"/> <text x="130" y="414" text-anchor="middle" font-size="14" fill="#2C2C2A">Mark processed</text> <rect x="250" y="150" width="180" height="40" rx="8" fill="#FAEEDA" stroke="#854F0B" stroke-width="0.5"/> <text x="340" y="174" text-anchor="middle" font-size="14" fill="#633806">Needs review</text> <line x1="340" y1="190" x2="340" y2="210" stroke="#5F5E5A" stroke-width="1.5" marker-end="url(#arrow)"/> <rect x="250" y="210" width="180" height="40" rx="8" fill="#F1EFE8" stroke="#5F5E5A" stroke-width="0.5"/> <text x="340" y="234" text-anchor="middle" font-size="14" fill="#2C2C2A">Reviewer edits</text> <line x1="340" y1="250" x2="340" y2="270" stroke="#5F5E5A" stroke-width="1.5" marker-end="url(#arrow)"/> <rect x="250" y="270" width="180" height="40" rx="8" fill="#E1F5EE" stroke="#0F6E56" stroke-width="0.5"/> <text x="340" y="294" text-anchor="middle" font-size="14" fill="#085041">Pull reviewed</text> <line x1="340" y1="310" x2="340" y2="330" stroke="#5F5E5A" stroke-width="1.5" marker-end="url(#arrow)"/> <rect x="250" y="330" width="180" height="40" rx="8" fill="#EAF3DE" stroke="#3B6D11" stroke-width="0.5"/> <text x="340" y="354" text-anchor="middle" font-size="14" fill="#27500A">Write to DB</text> <line x1="340" y1="370" x2="340" y2="390" stroke="#5F5E5A" stroke-width="1.5" marker-end="url(#arrow)"/> <rect x="250" y="390" width="180" height="40" rx="8" fill="#E1F5EE" stroke="#0F6E56" stroke-width="0.5"/> <text x="340" y="414" text-anchor="middle" font-size="14" fill="#085041">Extract features</text> <rect x="460" y="90" width="180" height="40" rx="8" fill="#F1EFE8" stroke="#5F5E5A" stroke-width="0.5"/> <text x="550" y="114" text-anchor="middle" font-size="14" fill="#2C2C2A">Visitor reports</text> <line x1="550" y1="130" x2="550" y2="150" stroke="#5F5E5A" stroke-width="1.5" marker-end="url(#arrow)"/> <rect x="460" y="150" width="180" height="40" rx="8" fill="#FBEAF0" stroke="#993556" stroke-width="0.5"/> <text x="550" y="174" text-anchor="middle" font-size="14" fill="#72243E">Feedback sheet</text> <line x1="550" y1="190" x2="550" y2="210" stroke="#5F5E5A" stroke-width="1.5" marker-end="url(#arrow)"/> <rect x="460" y="210" width="180" height="40" rx="8" fill="#F1EFE8" stroke="#5F5E5A" stroke-width="0.5"/> <text x="550" y="234" text-anchor="middle" font-size="14" fill="#2C2C2A">Reviewer approves</text> <line x1="550" y1="250" x2="550" y2="270" stroke="#5F5E5A" stroke-width="1.5" marker-end="url(#arrow)"/> <rect x="460" y="270" width="180" height="40" rx="8" fill="#E1F5EE" stroke="#0F6E56" stroke-width="0.5"/> <text x="550" y="294" text-anchor="middle" font-size="14" fill="#085041">Sync feedback</text> <line x1="550" y1="310" x2="550" y2="330" stroke="#5F5E5A" stroke-width="1.5" marker-end="url(#arrow)"/> <rect x="460" y="330" width="180" height="40" rx="8" fill="#EAF3DE" stroke="#3B6D11" stroke-width="0.5"/> <text x="550" y="354" text-anchor="middle" font-size="14" fill="#27500A">Apply correction</text> <line x1="550" y1="370" x2="550" y2="390" stroke="#5F5E5A" stroke-width="1.5" marker-end="url(#arrow)"/> <rect x="460" y="390" width="180" height="40" rx="8" fill="#F1EFE8" stroke="#5F5E5A" stroke-width="0.5"/> <text x="550" y="414" text-anchor="middle" font-size="14" fill="#2C2C2A">Mark applied</text> <path d="M130,430 L130,448 L250,448 L250,460" fill="none" stroke="#5F5E5A" stroke-width="1.5" marker-end="url(#arrow)"/> <path d="M340,430 L340,460" fill="none" stroke="#5F5E5A" stroke-width="1.5" marker-end="url(#arrow)"/> <path d="M550,430 L550,448 L430,448 L430,460" fill="none" stroke="#5F5E5A" stroke-width="1.5" marker-end="url(#arrow)"/> <rect x="120" y="460" width="440" height="50" rx="8" fill="#EEEDFE" stroke="#534AB7" stroke-width="0.5"/> <text x="340" y="490" text-anchor="middle" font-size="14" fill="#3C3489">classifications table (shared destination)</text> </g> </svg> </p>

**How to read the colors:** gray boxes are a person doing something (uploading a file,
editing a sheet, clicking approve). Teal boxes are a script running on its own. Green
boxes are the moment something actually gets written to the database. Amber means
"waiting on a person." Pink is where outside input comes in. Purple is the shared table
all three chains eventually feed into.

The one arrow that crosses between columns — from Chain A's **Classify (Qwen)** box over
to Chain B's **Needs review** box — is the actual handoff. Everything else in each chain
runs on its own, without waiting for the other two.

---

## Chain A — new papers coming in

**What starts it:** someone uploads a new Web of Science export file to a shared Google
Drive folder. That's the only trigger — nothing else needs to happen first.

**What happens automatically:** the pipeline notices the new file, downloads it, and asks
an AI model (Qwen) to read each paper and decide which of the 22 ecosystem services it
relates to, and how confident the model is in that answer.

**Where a person comes in:** only for the papers the model *isn't* sure about. If the
model is confident, the paper goes straight into the database with no human involved. If
it's not confident, the paper is set aside and handed off to Chain B instead — a person
has to look at it before it counts.

**Where it ends up:** confident papers land in the database right away, then get a second
pass that pulls out extra details (which country, which institution, which technology
category). The original uploaded file is then moved to a "processed" folder so it doesn't
get picked up again.

**Scripts involved:** `classify.py` (the AI classification step), `ingest_incremental.py`
(writes to the database), `text_analysis.py` (the extra details pass), all coordinated by
`run_pipeline.py new-data`.

---

## Chain B — the papers a person had to check

**What starts it:** this chain has no trigger of its own — it only exists to catch up on
whatever Chain A set aside. It's meant to be run regularly (say, once a day), whether or
not there's anything waiting.

**What happens automatically:** the pipeline checks whether a person has finished
reviewing any of the papers sitting in the review spreadsheet.

**Where a person comes in:** this whole chain *is* the human step. Someone opens the
review spreadsheet, reads the paper's title and the AI's guess, and either confirms the
guess or corrects it. They can correct just one field (say, the ecosystem service) and
leave everything else as the AI suggested.

**Where it ends up:** once a person marks a row as done, it gets pulled back in, written
to the database with their corrections applied, and — same as Chain A — gets the extra
detail pass run on it too.

**Scripts involved:** `classify.py --pull-reviewed`, `ingest_incremental.py`,
`text_analysis.py`, coordinated by `run_pipeline.py reviewed`.

---

## Feedback — when someone spots a mistake after the fact

**What starts it:** anyone browsing the public Data Explorer can flag a paper they think
is misclassified. They look it up, suggest what they think the correct classification
should be, and explain why. This is the only chain that starts from *outside* the team.

**What happens automatically:** their suggestion gets logged to a separate spreadsheet,
completely separate from the one Chain B uses.

**Where a person comes in:** twice. First, someone on the team reads the suggestion and
decides whether to approve it, reject it, or ask for more information — nothing happens
until it's explicitly approved. Second, once it's approved, the correction is applied and
the sheet is updated automatically so the reviewer can see it actually took effect,
without needing to check the database themselves.

**Where it ends up:** the paper's classification is corrected directly in the database.
This is completely separate from the narrative page's published numbers, which are frozen
at their original values and never change no matter how many corrections get applied here
— see `architecture.md` for why that separation exists.

**Scripts involved:** `sync_feedback.py`, coordinated by `run_pipeline.py feedback`.

---

## The one thing all three have in common

None of these three chains waits for either of the other two. Chain A can be mid-upload
while Chain B is picking up yesterday's reviews while a visitor is flagging a paper on the
Explorer — they don't block each other, and a delay in one doesn't stall the others. The
only thing they share is where they end up: the same `classifications` table.
