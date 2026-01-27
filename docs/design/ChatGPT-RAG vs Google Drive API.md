# RAG vs Google Drive API

**User:** Anonymous (cdorsey@concord.org)  
**Created:** 1/13/2026 11:06:56  
**Updated:** 1/14/2026 0:52:38  
**Exported:** 1/25/2026 14:51:23  
**Link:** [https://chatgpt.com/c/69666d5d-ecdc-832d-a8ba-28271c4dedb5](https://chatgpt.com/c/69666d5d-ecdc-832d-a8ba-28271c4dedb5)  

## Prompt:
“Hi, I want to talk about RAG solutions versus Google Drive API calls.”

00:07

## Response:
Absolutely, happy to chat about that! So, when we're comparing RAG solutions—like retrieval-augmented generation—versus just using the Google Drive API, we’re kind of talking about two different approaches to accessing and working with information.

A RAG solution basically is about using a language model that can pull in information from a specific set of documents or a database on the fly to answer questions. It’s more about dynamically retrieving bits of knowledge and then generating a response based on that.

On the other hand, calling the Google Drive API is more like directly querying a storage system. You’re essentially pulling files, reading their contents, maybe parsing them, and then doing whatever logic you need on top of that. It’s more manual in terms of handling the data.

So, depending on what you need, each approach has its own strengths. Let me know if there's a specific angle you want to dive into!

## Prompt:
“So I'm designing a system for an AI assistant to help me with things that are happening in an organization on a regular basis. One of those things where people are working with documents and using them to prepare for meetings or editing them for submission or what have you, and I want to keep regular track of that activity. One of the things that I want the assistant to be able to do is to pull up a file that is being worked with and give me summaries of different portions of it or search it for specific content. But I also will need to ask questions about historical exchanges that have gone on in the organization, like proposals that were designed five years ago, or all the times that we've worked with a certain client. So what's the beginning of a solution that I'm looking at and why?”

00:55

## Response:
Absolutely, let’s break it down into a couple of pieces to give you a starting point.

### Designing the Solution: An Overview

First, think of your solution as having two main components: a retrieval engine and a conversational layer. The retrieval engine is what will actually go into your organization’s documents, whether they’re on Google Drive or another repository, and find the information you need. The conversational layer is the AI assistant interface that you or your colleagues will interact with to ask questions and get answers.

### Using RAG for Dynamic Retrieval

A retrieval-augmented generation (RAG) approach is great here because it can let your assistant dynamically pull in snippets from all those documents stored in Google Drive (or any other repository you integrate). Essentially, it means the AI can look at the files in real-time, extract relevant pieces of content, and then use those to generate answers. This makes it much easier to get summaries of different portions of documents or find specific content without having to manually open each file.

### Leveraging the Google Drive API

On the other side, the Google Drive API is your gateway to accessing the raw files. You’ll need this to list documents, read their contents, and feed that data into your RAG pipeline. Basically, the Drive API will do the heavy lifting in terms of pulling the actual document contents. After that, your RAG system can do the intelligent retrieval and summarization.

### Historical Queries and Organizational Memory

For historical exchanges—like looking up old proposals or client interactions—you’ll want to have a way to index and tag documents over time. That might mean maintaining a metadata layer or some form of document history so that the AI can quickly pull up all files related to a particular client or project from years ago. Once that’s in place, the assistant can help you recall historical context on demand.

### Why This Approach?

By combining a RAG solution with the Google Drive API, you get the best of both worlds. You have direct, structured access to your document storage and also the flexibility of a language model that can understand and generate natural language responses from that data.

So that’s the starting point: build out the integration with the Drive API for the data source, and then layer on a RAG model to do the smart retrieval and summarization. Once you’ve got those pieces in place, you’ll have a really powerful assistant that can help with both current document tasks and historical lookups.

## Prompt:
“So walk me through some of the use case examples and what layers would be used where. Where would the RAG solution come in? Where would the metadata layer come in? Where would the Google Drive layer come in in a couple obvious use cases?”

00:15

## Response:
Absolutely, let’s walk through a few concrete use cases and break down where each layer would play its role.

### Use Case 1: Summarizing a Document for a Meeting

Imagine you have a big meeting coming up and you know that there’s a report or a document that the team has been working on. You ask the AI assistant, “Can you give me a summary of the latest project report for the meeting?”

*   **Google Drive Layer**: This layer will kick in first to locate the document in your Drive. It will identify the most recent version of the project report based on, say, the title or the folder you’ve specified.
*   **RAG Solution**: Once the document is retrieved, the RAG system will read through its contents and generate a concise summary. This is where the natural language capabilities shine, turning a full-length document into a brief overview that you can review quickly before your meeting.

### Use Case 2: Searching for Specific Content Within Documents

Now let

## Prompt:
“Wait, so stop for a second. On that use case, I was searching the Drive API to find a document source, not the RAG copy of it, or not the RAG store. Why was I searching Google Drive for that first?”

00:14

## Response:
Ah, sure, that's a good point to clarify. The idea here is that the Google Drive layer is essentially your primary source of truth for where documents live. It’s the storage system you’re connecting to in order to find the actual files that people are working on.

The RAG layer, on the other hand, is more about what happens after you’ve got that document in hand. So, in that use case, the Drive API is used first to fetch the document from the organization’s storage. Once you have that document, the RAG system steps in to actually read through it and generate the summary or find the content you need.

In other words, you’re searching Google Drive first because that’s where your documents are stored. The RAG system doesn’t store the documents themselves; it’s more like an intelligent layer that processes them once they’ve been retrieved. Hope that clears it up!

## Prompt:
“So, continue with that use case for a second, would the reg layer would already have a copy of the document, right? It's just that it's embedded and chunked so that it's not the best place to search for the raw document ID itself, is that the case?”

00:15

## Response:
Yes, exactly, you've got it. The RAG layer would typically have an embedded and chunked representation of the document’s content, so it can quickly retrieve snippets or answer questions based on what’s inside the document. But the RAG’s version is more like a processed, pre-digested form of the document rather than the raw file itself.

So when you need the actual document file or you want to ensure you're working with the latest version—like if you want to download it, edit it, or just verify its metadata—you’d go through the Google Drive layer to find that file directly. The RAG layer is fantastic for quickly answering questions and pulling out information, but it’s not the authoritative source for the actual file. So yes, you’re spot on!

## Prompt:
“So let's stay with that for a second before we go to the next use case. What metadata would be kept where in order to enable that use case? And, um...”

00:13

## Response:
Absolutely, let’s dig into the metadata piece

## Prompt:
“Yeah, start with that. Start with that.”

00:02

## Response:
Of course, let’s start there. So in terms of metadata, think of it as a kind of map that helps both the Google Drive layer and the RAG layer know what they’re dealing with.

**For the Google Drive Layer:**  
You’ll have metadata like document titles, IDs, last modified dates, owners, and maybe tags or folders they’re stored in. This is the sort of metadata that the Drive API already handles and it helps you locate the right document when you’re searching for it.

**For the RAG Layer:**  
You’ll have a different kind of metadata that’s more about the content of the document. For example, you might store information about which chunks of text are related to which topics, keywords that appear frequently, or embeddings that represent the meaning of different sections. That way, the RAG layer can quickly retrieve the relevant parts of the document when you ask a question.

**Bridging the Two Layers:**  
The metadata layer is the bridge. It ensures that when you pull a document from Drive, the RAG system knows which embeddings or which chunks of text map back to that particular file. So you have this kind of coordination where the Drive layer is all about the raw file and its basic details, and the RAG layer is all about understanding and indexing the content.

So in a nutshell, the Drive API keeps the structural metadata, and the RAG layer keeps the content-aware metadata. Together, they make the whole solution work smoothly for both fetching documents and answering questions about them.

## Prompt:
“So how much of what you just described is already assumed to be part of a RAG solution, and how much is a new or different metadata layer that appears in parallel or on top of a RAG solution?”

00:12

## Response:
Great question! So, in a typical RAG solution, a good chunk of what I described is already part of the standard approach. For example, the idea of embedding and chunking documents, and keeping track of which chunks relate to which documents, is a core part of how RAG works. That’s how it can pull in relevant snippets when you ask a question.

What might be a bit more custom or layered on top is the explicit coordination with a platform like Google Drive and the kind of structural metadata you’d keep to make sure you’re always working with the right file version. In other words, a RAG solution on its own doesn’t inherently manage your Google Drive files or keep track of which version is the latest or who last edited it. That’s where the Drive API and that additional metadata layer come in.

So, you can think of it like this: the content-aware metadata (like embeddings and chunks) is standard for RAG. The structural, file-level metadata that integrates with a document storage system is the extra piece you’re layering on top. It’s kind of a hybrid approach, combining what RAG does well with a bit of custom organization-specific metadata management.

## Prompt:
“Okay, this is good. We might have to work through this a little bit more. Let's see. How do I have to coordinate the metadata? You just talked about metadata that I'm keeping separate from either the RAG solution or the Google Drive API. What kind of metadata do I need to keep in order to keep coordination between those systems or my use of them?”

00:26

## Response:
Absolutely, let’s dive into that a bit more. So, the coordination metadata is basically the glue that helps your RAG system and your Google Drive system talk to each other seamlessly.

**What Kind of Coordination Metadata Do You Need?**

1.  **Document IDs and Versions:**  
    You’d want to keep track of the unique IDs of the documents in Google Drive and match those IDs to the internal representation that your RAG system uses. That way, if a document is updated or a new version is created, you can keep both systems in sync.
2.  **Last Updated Timestamps:**  
    Having timestamps for when a document was last modified can help the RAG system know when it might need to refresh its embeddings or re-chunk the document. This ensures that the RAG layer isn’t working off outdated content.
3.  **Tagging or Categorization:**  
    You might also want to store some metadata about what type of document it is or which projects or clients it’s related to. This kind of tagging can help the RAG layer quickly filter and find the right documents when you ask a question about a specific topic.
4.  **Mapping to RAG Embeddings:**  
    Finally, you’d have a reference that links each document ID to its corresponding embeddings or chunks in the RAG system. This lets the RAG layer know exactly which piece of content corresponds to which Drive file.

**In Summary:**  
Basically, you’re maintaining a small coordination layer that holds these mappings—like a little index that keeps everything aligned. It doesn’t have to be huge or complicated, but it does ensure that your RAG and Drive layers stay in sync. Let me know if that helps!

## Prompt:
“Yeah, that's good. Review again, what are the high-level features in that coordination catalog?”

00:07

## Response:
Absolutely, let’s do a quick recap of the high-level pieces in that coordination layer.

### High-Level Coordination Pieces

1.  **Document IDs and Versioning**:  
    This is about keeping track of which document in Google Drive corresponds to which representation in the RAG system. By maintaining these IDs and noting version info, you ensure both systems are always referring to the same document even if it gets updated.
2.  **Timestamps for Updates**:  
    By recording when a document was last modified, you help the RAG layer know when it might need to refresh its understanding of the document. This ensures that summaries or searches are always based on the most current content.
3.  **Tags or Categories**:  
    Adding tags or categories helps you quickly filter documents by project, client, or topic. This makes it easier for the RAG layer to find relevant documents when you ask a question about a specific area.
4.  **Mapping to RAG Embeddings**:  
    Finally, you have a mapping that links each Drive document to its corresponding embeddings or chunks in the RAG system. This ensures the RAG layer knows exactly where to look when retrieving content.

And that’s the big picture! All these pieces work together to keep everything coordinated and running smoothly.

## Prompt:
“That's great. It sounds like tags, that tags layer, might be something that overlaps with the RAG functionality. Is that true? And where's the divide between those two?”

00:13

## Response:
Absolutely, you're spot on. There is definitely some overlap when it comes to tagging or categorizing documents, and that can blur the lines a bit between what the RAG layer handles and what the coordination layer manages.

So, here’s how you can think about it:

The RAG layer often uses embeddings that inherently capture some semantic information about the document’s content. That means if you’ve got a document that’s all about a certain project or topic, the RAG layer might naturally understand that just from the content itself.

On the other hand, the coordination layer’s tagging is more explicit and structural. It’s like an added label that you attach to the document, saying “Hey, this document is part of the marketing project” or “This is a client proposal from 2021.” That kind of tagging is more about organization-wide categorization rather than just the content’s meaning.

So the divide is basically this: the RAG layer figures out meaning from the text, while your coordination layer’s tags are more like manual, top-down labels that you attach to keep everything organized and searchable in a structured way. And both can complement each other!

## Prompt:
“That's great. Okay, now other topic. What do I do about edits? I'm working in a system that has lots of people that are frequently editing content, and I know that that can be an issue when RAG systems need to do heavy load embedding. How do I most efficiently deal with that question?”

00:21

## Response:
Absolutely, that’s a really important piece of the puzzle, especially in a collaborative environment where documents are changing a lot.

So to handle frequent edits efficiently, here are a few strategies you can think about:

### Incremental Embedding Updates

Instead of re-embedding the entire document every time there’s a small change, you can use incremental updates. That means if someone edits a paragraph or adds a new section, you only update the embeddings for that changed portion rather than the whole document. This can save a lot of processing time.

### Batch Processing and Scheduling

Another approach is to batch your updates. Instead of reprocessing embeddings immediately every time a tiny edit happens, you can schedule embedding updates to happen at set intervals, maybe once a day or a couple of times a day, depending on how often documents change. That way you’re not constantly re-embedding things in real-time, but you’re still keeping things relatively fresh.

### Versioning and Metadata Flags

Using versioning in your metadata is also helpful. You can flag documents that have changed since the last embedding run, so the RAG system knows which ones need to be refreshed. This way you’re only re-embedding the documents that actually changed rather than everything.

### On-Demand Refresh for Critical Documents

And finally, you can have an on-demand option for critical documents. If there’s a document that’s been heavily edited right before a big meeting, you can trigger a manual refresh of its embeddings so you have the latest version ready.

So it’s really about balancing efficiency and freshness. With a combination of incremental updates, batching, and smart versioning, you can keep your RAG system up-to-date without overloading it.

## Prompt:
“Okay. Now, what if I want to know about those edits? I know this is tricky in Google Drive. I can imagine lots of questions like, an hour before a meeting, who has made what changes and give me a summary of them to the briefing document. How would I find that?”

00:19

## Response:
It looks like we didn’t find any specific internal record of recent edits to the briefing document or who made them. So let me summarize how you might approach this generally.

### Using Google Drive and Version History

In Google Drive, you can actually check version history for a document directly. If you open the document in Google Docs, you can go to “File” > “Version history” > “See version history.” This will show you a timeline of changes and who made them. You can see exactly which edits were made in the last

## Prompt:
“Wait, wait. I think we're on a weird track. I was talking about a hypothetical situation where I might ask that question and need my REG and Google Drive API system to answer the question. How can I find information that would answer a question like that? Give me a summary of which edits were made by person X to the briefing document since yesterday.”

00:25

## Response:
Ah, got it! We’re talking about how to handle that within your RAG and Google Drive integrated system. So, in that hypothetical scenario, you’d want to combine a few approaches.

### Leveraging Google Drive’s Version History Programmatically

First, you can use the Google Drive API to access the version history of a document programmatically. The Drive API can give you metadata about when different versions were created and who made changes. You can list revisions and see the names or email addresses of the editors.

### Using RAG for Summarization

Once you have that revision metadata, your RAG layer can step in to summarize the actual content changes. For instance, once you know that a certain person made edits, you can pull the relevant portions of the document from the updated version and let the RAG system generate a summary of what changed.

### Combining Both Layers

So in practice, you’d first call the Drive API to get the list of revisions and identify which user made changes. Then you’d feed the changed portions of the document into your RAG system to generate a natural language summary of those edits.

That way, you have a coordinated workflow: the Drive API gives you the “who and when,” and the RAG layer gives you the “what changed” in a summarized form. That should give you a neat way to get those quick pre-meeting summaries of recent edits!

## Prompt:
“Keep going, I got cut off.”

00:01

2/2

## Response:
Absolutely! Let’s continue from there.

### Putting It All Together

So, once you’ve got both pieces of information—who made the changes and what changed—you can present a neat summary. For example, you might have your AI assistant say, “In the past hour, Alex updated the introduction to include a new project overview and revised the summary section to add the latest metrics.”

### Automating the Process

You can also think about automating this workflow so that whenever you ask for recent edits, the system automatically pulls the latest revision data from Google Drive, runs it through the RAG summarizer, and delivers a human-friendly summary. That way, you don’t have to manually dig through version history every time.

### A Note on Permissions and Access

Of course, just a quick reminder that you’ll need to make sure your

## Prompt:
“Wait, I missed something, so can you repeat how the specific information about the specific edit content gets into the system?”

00:07

## Response:
Of course, let me break that down again. So the specific edit content gets into the system by using the revision data from the Google Drive API. When you fetch the list of revisions for a document, you get details about what version was created at what time and by whom.

From there, you can use the Drive API to actually pull the content of the document as it was at that particular revision. Once you have the older version and the newer version, you can do a simple comparison to see what text was added, deleted, or changed.

Then you feed those differences into the RAG system. The RAG system can analyze that “diff,” or the difference between versions, and generate a natural language summary of what changed. For example, it might say, “A paragraph was added about the new product launch,” or “A section was updated with the latest figures.”

So in summary, you’re pulling the actual content changes by comparing document versions from the Drive API and then using the RAG layer to turn those raw changes into a nice summary.

## Prompt:
What differences do I feed into the RAG system and how specifically? If I learned that my colleague added four paragraphs to page 2 of a briefing Google Doc for an upcoming meeting and I wanted a summary, what workflow and components would I and my system access specifically and how?

2/2

## Response:
You feed the **change artifact** (a “diff”) into the LLM/RAG layer — not the entire document. Concretely: _the exact paragraphs that were added/modified + just enough surrounding context to make them intelligible_, plus _metadata that lets you attribute the change to a person/time/revision_.

Here’s what that looks like as a workflow + which component does what.

Goal
----

“Colleague X added four paragraphs to page 2 of a Google Doc since yesterday. Summarize those changes.”

Components
----------

*   **Google Drive API**: file identity, permissions, revisions list, revision metadata (“who/when”), export a revision.
*   **Google Docs API**: structured content (paragraph boundaries, locations), optional suggestions/comments, helpful for mapping to “page 2” _approximately_.
*   **Diff engine** (your code): compute “what changed” between two versions.
*   **Coordination catalog** (your metadata store): maps Drive fileId ↔ your internal doc key; tracks last-indexed revisionId, content hash per chunk, chunk→embedding ids, etc.
*   **RAG store** (vector DB + embeddings): used when you need _broader context_ (“what is this doc about?” / “how does this change affect the proposal?”), but for “summarize what changed”, you often don’t need retrieval at all beyond local context.
*   **LLM summarizer**: produces the natural-language summary from the diff artifact.

* * *

Step-by-step workflow
---------------------

### 1) Identify the doc + the comparison window

**Inputs**: “briefing doc” + “since yesterday” + “person X”.

**Calls**

1.  **Drive API** `files.list` (or `files.get` if you already have fileId) to resolve the doc.
2.  **Drive API** `revisions.list(fileId)` to get revision history and metadata (modifiedTime, lastModifyingUser / user, etc.).

**Decision**

*   Choose a **baseline revision**: the latest revision at or before “yesterday” (or your catalog’s last-processed revision).
*   Choose a **target revision**: the latest revision now (or the latest by person X if you’re narrowing first).

**Coordination catalog update**

*   Store: `fileId`, `baselineRevisionId`, `targetRevisionId`, timestamps, and (optionally) “suspected editor(s)”.

* * *

### 2) Get the document content for the two revisions

You need _two snapshots_ to compute a diff.

**Option A (most common): export both revisions via Drive**

*   **Drive API** `revisions.get(fileId, revisionId)` to verify you can export that revision.
*   **Drive API** `files.export(fileId, mimeType="text/plain")` for _current_ content.
*   For historical revision content: Drive supports exporting revisions for Google Docs via `revisions.get` + `alt=media` patterns in some client libs; in practice many teams do:
    *   Export **current** content now.
    *   Export **baseline** content from a stored snapshot (kept in your system), OR
    *   Use **Docs API + periodic snapshots** (see note below).

**Option B (more robust): maintain snapshots**

*   Each time you index, store a “normalized text snapshot” keyed by `fileId + revisionId`.
*   Then you can always diff revision-to-revision without relying on revision export edge cases.

**Docs API enhancement**

*   **Google Docs API** `documents.get(documentId)` for the _current_ structured doc.
*   If you snapshot structure too, you can do paragraph-level diffs and better location references.

* * *

### 3) Compute a “diff artifact” (this is what you feed to the model)

Your diff engine compares **baseline text** vs **target text** and outputs **change records**.

For “four paragraphs added”, a good change record format is:

*   `change_type`: `"insert"`
*   `unit`: `"paragraph"`
*   `location_hint`: something like `{approx_page: 2, section_heading: "Agenda", index_in_doc: 37}`
*   `before_context`: the paragraph immediately before insertion
*   `inserted_text`: the new paragraph text
*   `after_context`: the paragraph immediately after insertion
*   `attribution`: `{author: "Person X", time: "...", revisionId: "..."}`

**Why include before/after context?**  
It prevents the model from summarizing the added paragraphs out of context (e.g., not knowing what “this” refers to).

**How to get “page 2”?**  
Google Docs is flow-layout; “page” depends on rendering. You generally treat “page 2” as:

*   **a best-effort mapping** using Docs API structural indices + (optionally) export to PDF and map text ranges to pages.
*   In practice, you’ll do better saying: “added under heading X / after paragraph starting with …”.

* * *

### 4) Decide whether to use retrieval (RAG) or just summarization

For “summarize these four inserted paragraphs”, you can usually just summarize directly.

Use **RAG retrieval** only to add missing context, for example:

*   The inserted paragraphs reference “the pilot” — retrieve the doc’s “pilot overview” chunk.
*   You want impact framing: “Does this change contradict our agreed scope?” — retrieve relevant scope sections.

So:

*   **Primary input to the LLM**: the change records (diff artifact).
*   **Optional retrieved context**: 1–5 chunks from your vector DB, selected by embedding the inserted text and searching within the same doc (or related docs).

* * *

### 5) Feed the diff artifact to the model “specifically”

You have two common patterns:

#### Pattern 1: “Diff-only summarization” (fastest, cheapest)

Prompt includes:

*   Document title + link/fileId
*   Time window
*   Editor identity
*   The change records (inserted paragraphs + minimal context)  
    Instruction: “Summarize what Person X added, in 3–5 bullets, and note any action items.”

#### Pattern 2: “Retrieval + diff summarization” (when context matters)

*   Retrieve context chunks (RAG step)
*   Provide both:
    *   **Diff artifact**
    *   **Retrieved context excerpts**  
        Instruction: “Summarize additions; also explain how they relate to \[context\].”

Either way, the _thing you feed_ is **not embeddings**; it’s **plain text change records** plus optional retrieved text snippets.

* * *

Where each layer “comes in” for your example
--------------------------------------------

**Example:** “Colleague added four paragraphs to page 2; summarize.”

1.  **Google Drive layer**
    *   Find doc, list revisions, identify the revision(s) by person X and timeframe.
    2.  **Coordination metadata layer**
    *   Decide baseline vs target revision.
*   Track last processed revision for this doc.
*   Provide a stable internal doc key and known chunk boundaries (if you keep them).
    3.  **Docs/Export + Diff layer**
    *   Fetch baseline + target snapshots.
*   Compute paragraph-level inserts (the four paragraphs).
*   Attach attribution + location hints.
    4.  **RAG layer (optional)**
    *   Retrieve related context chunks if the inserts need interpretation.
    5.  **LLM**
    *   Summarize the inserted paragraphs into a meeting-ready brief.

* * *

Practical note: if you want “who changed what” _reliably_, store snapshots
--------------------------------------------------------------------------

Google’s revision metadata is great for **who/when**, but getting **exact content delta** purely from APIs can be fiddly. The most robust system is:

*   On a cadence (or on edit events), export normalized doc text → store snapshot keyed by `revisionId`.
*   Then diff snapshots whenever you ask “since yesterday / by person X”.

That turns your question into a deterministic local operation plus a small Drive metadata call.

* * *

If you want, I can sketch the exact data structure for the coordination catalog table(s) and a concrete “diff artifact JSON schema” that’s friendly to your summarizer prompt.

## Prompt:
How would the snapshots work? You described Option B as:

Option B (more robust): maintain snapshots
	•	Each time you index, store a “normalized text snapshot” keyed by fileId + revisionId.
	•	Then you can always diff revision-to-revision without relying on revision export edge cases.

What exactly would be stored where and when? How would this process relate to the RAG indexing process? Would I store multiple versions of every document? What does normalized mean in this case? How would I avoid storing extravagant amounts of data with this process? And what does "snapshot structure" mean as referred to in later descriptions?

## Response:
Here’s a concrete “snapshot” design that stays sane on storage, plays nicely with RAG, and supports “what changed since X” reliably.

What gets stored, where, and when
---------------------------------

### Systems involved

*   **Drive/Docs**: source of truth + revision metadata.
*   **Snapshot store**: cheap object storage (S3/GCS/Azure blob) or even a database if small.
*   **Coordination catalog** (DB): pointers + hashes + bookkeeping.
*   **RAG index** (vector DB): embeddings per chunk, usually only for the _latest canonical version_.

### When snapshots are created

You create snapshots **when you (re-)index** a document, not on every keystroke.

Typical triggers:

1.  **Scheduled** (e.g., every 15 min / hourly for “hot” folders).
2.  **Webhook-ish** (Drive push notifications) → enqueue doc for re-index.
3.  **On-demand** (right before meeting: “refresh briefing doc”).

On trigger, you:

1.  call Drive to get current `headRevisionId` / `modifiedTime`
2.  if it’s new vs last processed → fetch content → normalize → snapshot → diff → update RAG chunks/embeddings

* * *

What exactly is a “normalized text snapshot”?
---------------------------------------------

A snapshot is a **deterministic, comparable representation** of the doc content at a revision.

“Normalized” means you transform Docs content into a stable text form so tiny formatting noise doesn’t create fake diffs.

### Minimum viable normalized snapshot (text)

Store:

*   `plain_text` with consistent whitespace rules
*   paragraph boundaries preserved
*   stable paragraph IDs derived from structure (or hashes)

Example normalization rules (typical):

*   Convert all line endings to `\n`
*   Collapse runs of spaces/tabs to single spaces (except inside code blocks if you care)
*   Normalize Unicode (NFC)
*   Remove purely visual artifacts (page numbers, headers/footers _if_ you don’t want them)
*   Canonicalize bullets (e.g., “• ”)
*   Preserve paragraph breaks (`\n\n`) so “four paragraphs added” is detectable

So normalized text is not “dumbed down”; it’s “made stable.”

### “Snapshot structure” (optional but powerful)

This means you also store a lightweight structural representation from Docs API, e.g.:

*   paragraph boundaries + their start/end indices
*   headings / named sections
*   list nesting level
*   tables (as row/col text)
*   maybe inline object markers (“\[IMAGE\]”, “(equation)”) if relevant

Why? It lets you say:

*   “Inserted 4 paragraphs under heading ‘Agenda’”  
    instead of
*   “Inserted near character offset 12,384”

Structure snapshot is not the whole document JSON; it’s a **compressed outline of the doc’s content blocks**.

* * *

Do I store multiple versions of every document?
-----------------------------------------------

Not necessarily. You have options:

### Approach 1: Keep snapshots only for “hot” docs (recommended)

Maintain multiple revisions only for documents that change frequently or matter for meetings.

Policy example:

*   Keep every revision snapshot for last **7 days**
*   Keep daily snapshots for last **90 days**
*   Keep monthly snapshots beyond that (or none)

### Approach 2: Store full snapshots only when “meaningful change”

You can decide “meaningful” by hashing normalized content:

*   If the normalized content hash didn’t change → don’t store new snapshot
*   If change is tiny (e.g., < 200 chars) you can store a delta only (see below)

### Approach 3: Store diffs, not full snapshots (most storage-efficient)

Store:

*   full snapshot occasionally (checkpoint)
*   between checkpoints store **delta patches** (like unified diff or a binary diff)

This is more engineering, but reduces storage a lot.

In practice, many teams start with Approach 1 + hash gating, and only add deltas if needed.

* * *

How snapshots relate to RAG indexing
------------------------------------

Think of indexing as two pipelines that share the same “fetch + normalize” step:

### Pipeline A: Snapshot pipeline (for audit/diff)

*   Fetch current revision
*   Normalize
*   Store snapshot (or delta)
*   Update coordination catalog pointers/hashes

### Pipeline B: RAG pipeline (for semantic retrieval)

*   Take normalized snapshot text
*   Chunk it
*   Embed chunks
*   Upsert embeddings into vector DB (usually under “current version” namespace)
*   Store chunk metadata mapping back to fileId/revisionId

**Key point:** the snapshot is the _input artifact_ for chunking/embedding. If the doc changes, you compare snapshots to update only impacted chunks.

* * *

What metadata is stored in the coordination catalog?
----------------------------------------------------

A typical coordination table (relational-ish):

**documents**

*   `doc_key` (internal)
*   `drive_file_id`
*   `title`
*   `last_seen_head_revision_id`
*   `last_indexed_revision_id`
*   `last_indexed_time`

**snapshots**

*   `drive_file_id`
*   `revision_id`
*   `created_time`
*   `normalized_hash` (e.g., SHA-256)
*   `snapshot_uri` (blob location) OR `delta_uri`
*   `base_revision_id` (if delta)
*   `size_bytes`

**chunks**

*   `drive_file_id`
*   `revision_id` (the revision this chunk came from)
*   `chunk_id` (stable)
*   `chunk_hash`
*   `vector_id` (in vector DB)
*   `start_marker` / `end_marker` (paragraph ids or offsets)
*   `section_heading` (optional)

This is the “glue” that lets you:

*   attribute changes to revisions/users
*   diff old/new snapshots
*   update only changed chunks in RAG

* * *

How do you avoid storing extravagant amounts of data?
-----------------------------------------------------

Use **four levers** (you can combine them):

### 1) Hash gating (don’t snapshot if nothing meaningful changed)

*   Compute `normalized_hash`
*   If unchanged vs last snapshot: skip storing + skip embedding

### 2) Retention policies (TTL)

*   Keep dense history only for hot docs and only for recent time windows
*   Auto-delete old snapshots or roll them up (daily/monthly)

### 3) Delta encoding between snapshots

*   Store periodic full snapshots (checkpoints)
*   Store deltas between checkpoints

### 4) Store “normalized + compressed”

Normalized snapshots compress extremely well (gzip/zstd) because Docs text is repetitive.  
A 2–10 MB doc often compresses to a few hundred KB.

Rule of thumb: start with **compressed full snapshots + retention**, then add deltas only if you truly need it.

* * *

How “page 2” works with snapshots
---------------------------------

“Page” is a rendering concept. With snapshots you typically report location as:

*   heading/section + paragraph index
*   or “after the paragraph starting with …”

If you _must_ reference pages, you can:

*   export PDF occasionally and map text ranges to pages (heavier)
*   but most teams avoid promising “page N” and instead use headings.

* * *

Putting it together: the minimal robust implementation
------------------------------------------------------

**Store**

*   Compressed normalized text snapshot for each indexed revision (for hot docs)
*   Coordination metadata: revision pointers + hashes
*   Vector DB embeddings for latest doc version (plus chunk mapping metadata)

**On update**

*   Fetch + normalize
*   If hash changed:
    *   store snapshot
    *   diff vs previous snapshot
    *   re-embed only changed chunks
    *   update mappings

That gives you reliable “what changed by who since when” without ballooning cost.

If you want, I can write a concrete retention policy example (numbers) for an org like yours (lots of Docs, moderate editing, occasional “pre-meeting crunch”), plus a sample chunking strategy that makes incremental re-embedding straightforward.

## Prompt:
Can you break down the store process in more detail, including API calls and tools / tool calls for compression and normalization, and including the process for adding the structure layer. Then describe the RAG pipeline in more detail – does that feed directly from the normalized stored text?

## Response:
Yep. I’ll lay it out as two concrete pipelines that share the same “fetch → normalize → (optionally) structure” step.

Below I’ll assume you’re using:

*   **Google Drive API** for file metadata + revisions + export
*   **Google Docs API** for structured document content (paragraphs/headings/tables)
*   **Object storage** (S3/GCS/Azure) for snapshot blobs
*   **A DB** (Postgres/etc.) for the coordination catalog
*   **A vector DB** for RAG embeddings

I’ll show API calls + where compression/normalization happens + how the structure layer is built.

* * *

A) Snapshot store pipeline (detailed)
-------------------------------------

### 0) Inputs

*   `drive_file_id`
*   optional: `since_revision_id` or “reindex if modified since last\_indexed\_time”
*   policy: hot/cold doc retention settings

### 1) Discover current head revision + metadata (Drive)

**Drive API**

*   `files.get(fileId, fields="id,name,mimeType,modifiedTime,version,headRevisionId,lastModifyingUser,owners,md5Checksum")`

Notes:

*   For Google Docs, `md5Checksum` often isn’t present; `headRevisionId` is useful.
*   Save `modifiedTime`, `headRevisionId`, and `name` in your coordination DB.

### 2) Fast skip check (coordination DB)

Look up your catalog:

*   `last_indexed_head_revision_id` (or `last_indexed_modified_time`)  
    If head revision hasn’t changed → stop.

### 3) Pull revision list if you need “who changed what” attribution (Drive)

**Drive API**

*   `revisions.list(fileId, fields="revisions(id,modifiedTime,lastModifyingUser,keepForever),nextPageToken")`

Store revision metadata in DB (cheap):

*   revisionId, modifiedTime, user identity

This is how you later answer “edits by person X since yesterday” (which revisions to diff).

### 4) Fetch content for the head revision (two ways)

#### 4A) Text snapshot via Drive export (simple and robust)

**Drive API**

*   `files.export(fileId, mimeType="text/plain")`  
    or for better fidelity:
*   `files.export(fileId, mimeType="text/html")` then convert to normalized text

Pros: easy  
Cons: less structural fidelity (headings/lists/tables can be flattened)

#### 4B) Structured snapshot via Docs API (best for structure layer)

**Docs API**

*   `documents.get(documentId=fileId)`  
    This returns a JSON document with `body.content[]` elements (paragraphs, tables, etc.).

Pros: paragraph boundaries, headings, lists, tables  
Cons: a bit more parsing work

Most systems do **both**:

*   **Docs API** for structure
*   **Drive export** (plain text or HTML) for a clean text baseline (optional if you can fully reconstruct text from Docs API)

### 5) Normalize (your code)

Normalization is not an API call; it’s a deterministic transform.

**If you start from Docs API JSON**

*   Build a canonical text stream by walking blocks:
    *   paragraph → concatenate text runs
    *   heading → same, but mark as heading
    *   lists → prefix with `-` or `1.` consistently
    *   tables → represent as rows like `| cell | cell |`
*   Preserve paragraph boundaries as `\n\n`

**Normalization rules (typical defaults)**

*   Unicode normalize NFC
*   Convert CRLF → `\n`
*   Trim trailing spaces
*   Collapse multiple spaces to one _inside runs_ (but keep paragraph breaks)
*   Canonicalize bullets and numbering
*   Replace non-text objects with stable tokens (`[IMAGE]`, `[EQUATION]`) if desired
*   Optionally drop headers/footers if you’re exporting HTML/PDF versions

Output:

*   `normalized_text` (string)
*   `content_hash = sha256(normalized_text)` (or xxhash64 for speed)

### 6) Decide whether to store a new snapshot

Compare `content_hash` to the last snapshot’s hash for that doc:

*   If same → skip storing blob (but you might still store revision metadata if new revisions exist)
*   If different → store snapshot

### 7) Compression + storage (your code + object store)

Compression is a local step; storage is your blob store SDK.

Typical:

*   `gzip` or `zstd` the normalized text
*   Write to object storage at a key like:
    *   `snapshots/{fileId}/{revisionId}/text.norm.txt.gz`

Store in DB:

*   `fileId`, `revisionId`, `content_hash`, `blob_uri`, `byte_size`, `created_at`

**Avoiding bloat**

*   Always store compressed
*   Apply retention (TTL)
*   Optionally store deltas later (advanced)

### 8) Build and store “structure snapshot”

This is separate from normalized text and comes from Docs API parsing.

Structure snapshot contents (lightweight):

*   `blocks[]` where each block has:
    *   `block_id` (stable hash)
    *   `type` (`heading`, `paragraph`, `list_item`, `table_row`, etc.)
    *   `heading_level` if heading
    *   `text_hash` of the block’s normalized text
    *   `char_start`, `char_end` in the normalized\_text stream (optional but very useful)
    *   `outline_path` (e.g., `["Agenda", "Risks"]`)
    *   `list_level` (optional)
    *   `table_id/row/col` (optional)

Store as:

*   JSON compressed blob:
    *   `snapshots/{fileId}/{revisionId}/structure.json.gz`  
        and/or in DB as JSONB if not huge.

**Why structure matters**

*   Lets your diff engine say “4 paragraphs inserted under heading ‘Agenda’”
*   Lets chunking be stable and incremental (chunk boundaries aligned to headings/blocks)

* * *

B) Diff artifact generation (between snapshots)
-----------------------------------------------

When you need “what changed since yesterday/by person X,” you:

1.  use Drive revision metadata to pick:
    *   `rev_base` (yesterday)
    *   `rev_head` (now) or last revision by person X
2.  load the **two normalized snapshots** from blob store
3.  compute a diff at the **block level** using structure:
    *   match blocks by `block_id` or by sequence + `text_hash`
4.  output change records:
    *   inserted/deleted/modified blocks
    *   include `before/after context` from neighboring blocks
    *   include attribution from revision metadata

Those change records are what you summarize.

* * *

C) RAG pipeline (detailed) — does it feed from normalized stored text?
----------------------------------------------------------------------

Usually yes: the **normalized stored text is your canonical input** for chunking + embedding. The structure snapshot helps you chunk intelligently.

### 1) Choose the indexing target

Most org assistants index:

*   **Latest canonical version** of each doc (for retrieval)  
    Optionally:
*   Keep some historical embeddings for “as of 2021” queries, but that’s a policy choice.

### 2) Chunking (uses normalized text + structure)

Good chunking strategies:

*   **Heading-based**: each section becomes 1–N chunks
*   **Block-based**: group paragraphs into ~500–1,200 tokens chunks
*   Keep chunk boundaries aligned to structure blocks to support incremental updates

Chunk record includes metadata:

*   `fileId`
*   `revisionId` (the revision indexed)
*   `chunk_id` (stable, e.g., hash of outline\_path + block range)
*   `outline_path`
*   `block_start_id`, `block_end_id`
*   `char_start`, `char_end` into normalized text
*   `content_hash` of the chunk

### 3) Incremental embedding update

When a new snapshot is stored:

*   compare structure block hashes and/or chunk hashes vs previous revision
*   only re-embed chunks whose `content_hash` changed

### 4) Embedding + vector DB upsert

For each changed/new chunk:

*   call embedding model
*   upsert into vector DB with metadata above  
    For deleted chunks:
*   delete or tombstone vector entries

### 5) Retrieval at query time

When user asks something:

*   embed query
*   vector search (optionally filter by doc/project/tag/time)
*   return top chunks
*   LLM uses retrieved chunks to answer

### 6) Edit-summary queries are _not_ typical RAG retrieval

For “summarize edits since yesterday,” you don’t usually vector-search.  
You:

*   pick revisions
*   diff snapshots
*   summarize the diff artifact (optionally retrieve context if needed)

So: RAG is for _knowledge Q&A_, snapshots/diffs are for _change tracking_.

* * *

Tooling for normalization + compression
---------------------------------------

No special external “API” is required; you implement these as local functions in your ingestion service:

*   Normalization: your own parser for Docs JSON or HTML
*   Hashing: SHA-256 / xxhash
*   Compression: gzip/zstd libraries
*   Storage: S3/GCS SDK
*   Diff: a text diff lib or a block-level diff you write (structure-guided)

If you want, I can provide a concrete “ingestion worker” pseudo-implementation (TypeScript) showing:

*   Drive/Docs calls
*   normalization function shape
*   structure extraction
*   snapshot write + DB transaction
*   chunking + incremental embedding update logic

## Prompt:
That would be useful, yes

## Response:
```ts
/**
 * ingestion-worker.ts
 *
 * A concrete, end-to-end pseudo-implementation (TypeScript) for:
 *  - Discovering doc changes (Drive)
 *  - Fetching current structured content (Docs)
 *  - Normalizing to stable text
 *  - Extracting a lightweight structure snapshot
 *  - Hashing + compression
 *  - Writing blobs to object storage
 *  - Writing coordination metadata to a DB
 *  - Chunking from normalized text + structure
 *  - Incremental embedding updates + vector DB upserts
 *
 * This is “drop-in shaped” code: you’ll need to wire real SDK clients (Drive/Docs/DB/S3/Embeddings/VectorDB),
 * but the data model, control flow, and boundaries are the important parts.
 */

import { createHash } from "crypto";
import { gzipSync, gunzipSync } from "zlib";

/* ----------------------------- Types: APIs ----------------------------- */

type DriveFile = {
  id: string;
  name: string;
  mimeType: string;
  modifiedTime?: string; // ISO
  headRevisionId?: string;
};

type DriveRevision = {
  id: string;
  modifiedTime?: string; // ISO
  lastModifyingUser?: { displayName?: string; emailAddress?: string };
};

type DocsDocument = {
  documentId: string;
  title?: string;
  body?: {
    content?: Array<any>; // Google Docs "Structural Elements"
  };
};

/** You will implement these with googleapis or your preferred client */
interface DriveClient {
  filesGet(fileId: string): Promise<DriveFile>;
  revisionsList(fileId: string): Promise<DriveRevision[]>;
  // Optional: export plain text as a baseline (not required if you reconstruct from Docs API)
  // filesExport(fileId: string, mimeType: string): Promise<Buffer>;
}

interface DocsClient {
  documentsGet(documentId: string): Promise<DocsDocument>;
}

interface ObjectStore {
  putObject(key: string, bytes: Buffer, contentType: string, contentEncoding?: string): Promise<{ uri: string; size: number }>;
  getObject(key: string): Promise<Buffer>;
}

interface DbClient {
  withTransaction<T>(fn: (tx: DbTx) => Promise<T>): Promise<T>;
  getDocState(fileId: string): Promise<DocState | null>;
}

interface DbTx {
  upsertDocState(state: DocState): Promise<void>;
  insertSnapshotMeta(meta: SnapshotMeta): Promise<void>;
  getLatestSnapshotMeta(fileId: string): Promise<SnapshotMeta | null>;
  getSnapshotMeta(fileId: string, revisionId: string): Promise<SnapshotMeta | null>;
  upsertChunks(chunks: ChunkRecord[]): Promise<void>;
  getChunksByFile(fileId: string): Promise<ChunkRecord[]>;
}

interface Embedder {
  embed(texts: string[]): Promise<number[][]>;
}

interface VectorDb {
  upsert(vectors: Array<{ vectorId: string; embedding: number[]; metadata: Record<string, any> }>): Promise<void>;
  delete(vectorIds: string[]): Promise<void>;
}

/* ------------------------- Types: Our catalog -------------------------- */

type DocState = {
  fileId: string;
  title: string;
  mimeType: string;
  lastSeenHeadRevisionId?: string;
  lastIndexedRevisionId?: string;
  lastIndexedAt?: string; // ISO
  lastIndexedContentHash?: string;
};

type SnapshotMeta = {
  fileId: string;
  revisionId: string;
  createdAt: string; // ISO
  normalizedHash: string;
  textBlobKey: string;      // object key for gzip normalized text
  structureBlobKey: string; // object key for gzip structure json
  sizeBytesText: number;
  sizeBytesStructure: number;
};

type StructureBlockType = "heading" | "paragraph" | "list_item" | "table_row" | "unknown";

type StructureBlock = {
  blockId: string;          // stable id (hash of type + outline path + normalized text hash)
  type: StructureBlockType;
  outlinePath: string[];    // headings stack at this point, e.g., ["Agenda", "Risks"]
  headingLevel?: number;    // 1..6 if heading
  listLevel?: number;       // nesting if list
  textHash: string;         // hash of block text (normalized)
  charStart?: number;       // optional offsets into normalized full text
  charEnd?: number;
};

type StructureSnapshot = {
  fileId: string;
  revisionId: string;
  createdAt: string;
  blocks: StructureBlock[];
};

type NormalizedSnapshot = {
  normalizedText: string;
  normalizedHash: string;
  blocks: StructureBlock[];
};

type ChunkRecord = {
  fileId: string;
  revisionId: string;        // revision indexed
  chunkId: string;           // stable chunk id
  vectorId: string;          // stable vector id (can match chunkId)
  outlinePath: string[];
  blockStartId: string;
  blockEndId: string;
  charStart: number;
  charEnd: number;
  chunkHash: string;
};

/* ------------------------- Ingestion configuration ------------------------- */

type IngestionConfig = {
  // Chunk sizing: tune for your embedding model + desired retrieval granularity
  maxChunkChars: number;      // ex: 4000–8000 chars (roughly 700–1500 tokens)
  minChunkChars: number;      // ex: 800–1500 chars
  hotDocRetentionDays: number; // not implemented here; applied by a separate janitor job
};

const DEFAULT_CONFIG: IngestionConfig = {
  maxChunkChars: 6000,
  minChunkChars: 1200,
  hotDocRetentionDays: 14,
};

/* ----------------------------- Main entrypoint ----------------------------- */

export async function ingestGoogleDoc(params: {
  fileId: string;
  drive: DriveClient;
  docs: DocsClient;
  db: DbClient;
  store: ObjectStore;
  embedder: Embedder;
  vectorDb: VectorDb;
  config?: Partial<IngestionConfig>;
}): Promise<{ status: "skipped" | "indexed"; reason?: string; revisionId?: string }> {
  const config: IngestionConfig = { ...DEFAULT_CONFIG, ...(params.config ?? {}) };
  const { fileId, drive, docs, db, store, embedder, vectorDb } = params;

  // 1) Fetch current file metadata (Drive)
  const file = await drive.filesGet(fileId);
  const headRevisionId = file.headRevisionId; // key to determine if changed
  const title = file.name ?? "(untitled)";
  const mimeType = file.mimeType;

  // 2) Fast skip check
  const state = await db.getDocState(fileId);
  if (state?.lastSeenHeadRevisionId && headRevisionId && state.lastSeenHeadRevisionId === headRevisionId) {
    return { status: "skipped", reason: "headRevisionId unchanged", revisionId: headRevisionId };
  }

  // 3) Revisions list (metadata for attribution; also helps choose baseline later)
  // You may not need this every time; you can fetch only when you plan to answer “who did what” queries
  const revisions = await drive.revisionsList(fileId);
  // Choose the revision we will snapshot/index now. Typically headRevisionId, but revision list gives you certainty.
  const targetRevisionId = headRevisionId ?? (revisions[0]?.id ?? "unknown");

  // 4) Fetch structured doc (Docs API)
  const doc = await docs.documentsGet(fileId);

  // 5) Normalize + extract structure
  const normalized = normalizeDocsDocumentToSnapshot({
    fileId,
    revisionId: targetRevisionId,
    doc,
  });

  // 6) Compare hash vs latest snapshot to avoid pointless storage/indexing
  const latestMeta = await db.withTransaction(async (tx) => tx.getLatestSnapshotMeta(fileId));
  if (latestMeta && latestMeta.normalizedHash === normalized.normalizedHash) {
    // Update doc state’s lastSeenHeadRevisionId even if content hash same (covers no-op revisions)
    await db.withTransaction(async (tx) => {
      await tx.upsertDocState({
        fileId,
        title,
        mimeType,
        lastSeenHeadRevisionId: targetRevisionId,
        lastIndexedRevisionId: latestMeta.revisionId,
        lastIndexedAt: new Date().toISOString(),
        lastIndexedContentHash: latestMeta.normalizedHash,
      });
    });
    return { status: "skipped", reason: "normalized hash unchanged", revisionId: targetRevisionId };
  }

  // 7) Compress + write snapshot blobs
  const createdAt = new Date().toISOString();
  const textBlobKey = `snapshots/${fileId}/${targetRevisionId}/text.norm.txt.gz`;
  const structureBlobKey = `snapshots/${fileId}/${targetRevisionId}/structure.json.gz`;

  const textGz = gzipSync(Buffer.from(normalized.normalizedText, "utf8"), { level: 9 });
  const structureJson = JSON.stringify(
    {
      fileId,
      revisionId: targetRevisionId,
      createdAt,
      blocks: normalized.blocks,
    } satisfies StructureSnapshot,
    null,
    0
  );
  const structureGz = gzipSync(Buffer.from(structureJson, "utf8"), { level: 9 });

  const [textPut, structPut] = await Promise.all([
    store.putObject(textBlobKey, textGz, "text/plain", "gzip"),
    store.putObject(structureBlobKey, structureGz, "application/json", "gzip"),
  ]);

  // 8) Chunk from normalized + structure
  const chunks = chunkFromNormalizedAndStructure({
    fileId,
    revisionId: targetRevisionId,
    normalizedText: normalized.normalizedText,
    blocks: normalized.blocks,
    config,
  });

  // 9) Incremental embedding:
  // Compare new chunk hashes to previously indexed chunks; only embed changed/new.
  const prevChunks = await db.withTransaction(async (tx) => tx.getChunksByFile(fileId));
  const { toUpsert, toDelete } = diffChunks(prevChunks, chunks);

  // Embed only upserts (new/changed)
  const upsertPayload: Array<{ vectorId: string; embedding: number[]; metadata: Record<string, any> }> = [];
  if (toUpsert.length > 0) {
    const texts = toUpsert.map((c) => normalized.normalizedText.slice(c.charStart, c.charEnd));
    const embeddings = await embedder.embed(texts);
    for (let i = 0; i < toUpsert.length; i++) {
      const c = toUpsert[i];
      upsertPayload.push({
        vectorId: c.vectorId,
        embedding: embeddings[i],
        metadata: {
          fileId: c.fileId,
          revisionId: c.revisionId,
          chunkId: c.chunkId,
          outlinePath: c.outlinePath,
          blockStartId: c.blockStartId,
          blockEndId: c.blockEndId,
          charStart: c.charStart,
          charEnd: c.charEnd,
          chunkHash: c.chunkHash,
          title,
        },
      });
    }
  }

  // 10) Persist everything transactionally
  await db.withTransaction(async (tx) => {
    // Snapshot metadata
    const meta: SnapshotMeta = {
      fileId,
      revisionId: targetRevisionId,
      createdAt,
      normalizedHash: normalized.normalizedHash,
      textBlobKey,
      structureBlobKey,
      sizeBytesText: textPut.size,
      sizeBytesStructure: structPut.size,
    };
    await tx.insertSnapshotMeta(meta);

    // Doc state
    await tx.upsertDocState({
      fileId,
      title,
      mimeType,
      lastSeenHeadRevisionId: targetRevisionId,
      lastIndexedRevisionId: targetRevisionId,
      lastIndexedAt: createdAt,
      lastIndexedContentHash: normalized.normalizedHash,
    });

    // Chunks
    await tx.upsertChunks(chunks);
  });

  // 11) Vector DB mutations (outside DB transaction; add retries in production)
  if (toDelete.length > 0) {
    await vectorDb.delete(toDelete.map((c) => c.vectorId));
  }
  if (upsertPayload.length > 0) {
    await vectorDb.upsert(upsertPayload);
  }

  return { status: "indexed", revisionId: targetRevisionId };
}

/* ------------------------- Normalization + Structure ------------------------- */

/**
 * Parses a Docs API document into:
 *  - normalizedText: canonical plain text preserving paragraph boundaries
 *  - blocks: a lightweight “structure snapshot”
 *
 * Important: this is intentionally conservative — it’s easier to add fidelity later.
 */
function normalizeDocsDocumentToSnapshot(params: {
  fileId: string;
  revisionId: string;
  doc: DocsDocument;
}): NormalizedSnapshot {
  const { doc } = params;

  // We walk the doc, tracking headings stack for outlinePath.
  const blocks: StructureBlock[] = [];
  const parts: string[] = [];

  let outlineStack: Array<{ text: string; level: number }> = [];

  let cursor = 0; // character cursor in normalizedText we are building

  const body = doc.body?.content ?? [];
  for (const el of body) {
    // Paragraph
    if (el.paragraph) {
      const p = el.paragraph;
      const style = p.paragraphStyle ?? {};
      const namedStyleType: string | undefined = style.namedStyleType; // e.g., "HEADING_1", "NORMAL_TEXT"
      const headingLevel = headingLevelFromNamedStyle(namedStyleType);

      const text = normalizeInlineElementsToText(p.elements ?? []);

      // Skip empty paragraphs aggressively
      const trimmed = text.trim();
      if (!trimmed) continue;

      const blockType: StructureBlockType =
        headingLevel !== null ? "heading" : isListItem(p) ? "list_item" : "paragraph";

      // Update outline stack on headings
      if (blockType === "heading" && headingLevel !== null) {
        outlineStack = adjustOutlineStack(outlineStack, trimmed, headingLevel);
      }

      const outlinePath = outlineStack.map((h) => h.text);

      // Normalize paragraph text further (stable whitespace)
      const normalizedPara = normalizeText(trimmed);

      // Append to the global normalized text with double newline between blocks
      const sep = parts.length === 0 ? "" : "\n\n";
      const charStart = cursor + sep.length;
      const chunkText = sep + normalizedPara;
      parts.push(chunkText);
      cursor += chunkText.length;
      const charEnd = cursor;

      const textHash = sha256Hex(normalizedPara);

      const blockId = sha256Hex(
        JSON.stringify({
          type: blockType,
          outlinePath,
          headingLevel,
          textHash,
        })
      );

      blocks.push({
        blockId,
        type: blockType,
        outlinePath,
        headingLevel: headingLevel ?? undefined,
        listLevel: listLevelFromParagraph(p) ?? undefined,
        textHash,
        charStart,
        charEnd,
      });
      continue;
    }

    // Tables (optional: represent each row as a block)
    if (el.table) {
      const table = el.table;
      const rows: any[] = table.tableRows ?? [];
      for (const row of rows) {
        const cells: any[] = row.tableCells ?? [];
        const cellTexts: string[] = [];
        for (const cell of cells) {
          const cellContent = cell.content ?? [];
          const cellPlain = extractPlainTextFromDocElements(cellContent);
          cellTexts.push(normalizeText(cellPlain.trim()));
        }
        const rowText = `| ${cellTexts.join(" | ")} |`.trim();
        if (!rowText || rowText === "|  |") continue;

        const outlinePath = outlineStack.map((h) => h.text);
        const sep = parts.length === 0 ? "" : "\n\n";
        const charStart = cursor + sep.length;
        const chunkText = sep + rowText;
        parts.push(chunkText);
        cursor += chunkText.length;
        const charEnd = cursor;

        const textHash = sha256Hex(rowText);
        const blockId = sha256Hex(JSON.stringify({ type: "table_row", outlinePath, textHash }));

        blocks.push({
          blockId,
          type: "table_row",
          outlinePath,
          textHash,
          charStart,
          charEnd,
        });
      }
      continue;
    }

    // Other element types can be handled later (images, drawings, etc.)
  }

  const normalizedText = normalizeGlobalText(parts.join(""));

  return {
    normalizedText,
    normalizedHash: sha256Hex(normalizedText),
    blocks,
  };
}

function normalizeInlineElementsToText(elements: any[]): string {
  // Docs API inline elements often contain textRun.content, plus other embedded objects.
  let out = "";
  for (const e of elements) {
    if (e.textRun?.content) out += e.textRun.content;
    else if (e.inlineObjectElement) out += " [IMAGE] ";
    else if (e.horizontalRule) out += "\n";
    // extend as needed
  }
  return out;
}

function extractPlainTextFromDocElements(content: any[]): string {
  let out = "";
  for (const el of content) {
    if (el.paragraph) {
      const t = normalizeInlineElementsToText(el.paragraph.elements ?? []);
      out += t + "\n";
    } else if (el.table) {
      // nested tables are rare; ignore or recurse if you need
    }
  }
  return out;
}

/* ------------------------- Chunking + Incremental ------------------------- */

function chunkFromNormalizedAndStructure(params: {
  fileId: string;
  revisionId: string;
  normalizedText: string;
  blocks: StructureBlock[];
  config: IngestionConfig;
}): ChunkRecord[] {
  const { fileId, revisionId, normalizedText, blocks, config } = params;

  // Strategy: group consecutive blocks by outlinePath and size, using block boundaries.
  // This keeps chunk boundaries stable and supports incremental updates.
  const chunks: ChunkRecord[] = [];

  let i = 0;
  while (i < blocks.length) {
    const startBlock = blocks[i];
    const startOutline = startBlock.outlinePath.join(" / ");

    let charStart = startBlock.charStart ?? 0;
    let charEnd = startBlock.charEnd ?? charStart;
    let endIndex = i;

    while (endIndex + 1 < blocks.length) {
      const next = blocks[endIndex + 1];
      const nextOutline = next.outlinePath.join(" / ");

      // Prefer not to cross major section boundaries if chunk is already “big enough”
      const wouldCrossSection = nextOutline !== startOutline;

      const nextEnd = next.charEnd ?? charEnd;
      const proposedSize = nextEnd - charStart;

      if (proposedSize > config.maxChunkChars) break;
      if (wouldCrossSection && (charEnd - charStart) >= config.minChunkChars) break;

      // include next block
      charEnd = nextEnd;
      endIndex++;
    }

    // Ensure we have at least min size if possible (unless single block is huge)
    if ((charEnd - charStart) < config.minChunkChars && endIndex + 1 < blocks.length) {
      const next = blocks[endIndex + 1];
      const nextEnd = next.charEnd ?? charEnd;
      if ((nextEnd - charStart) <= config.maxChunkChars) {
        charEnd = nextEnd;
        endIndex++;
      }
    }

    const blockStartId = blocks[i].blockId;
    const blockEndId = blocks[endIndex].blockId;
    const outlinePath = blocks[i].outlinePath;

    const chunkText = normalizedText.slice(charStart, charEnd);
    const chunkHash = sha256Hex(chunkText);

    // Stable chunk id: file + outline + block range
    const chunkId = sha256Hex(JSON.stringify({ fileId, outlinePath, blockStartId, blockEndId }));
    const vectorId = chunkId;

    chunks.push({
      fileId,
      revisionId,
      chunkId,
      vectorId,
      outlinePath,
      blockStartId,
      blockEndId,
      charStart,
      charEnd,
      chunkHash,
    });

    i = endIndex + 1;
  }

  return chunks;
}

function diffChunks(prev: ChunkRecord[], next: ChunkRecord[]): {
  toUpsert: ChunkRecord[];
  toDelete: ChunkRecord[];
} {
  const prevById = new Map(prev.map((c) => [c.chunkId, c]));
  const nextById = new Map(next.map((c) => [c.chunkId, c]));

  const toUpsert: ChunkRecord[] = [];
  const toDelete: ChunkRecord[] = [];

  for (const c of next) {
    const p = prevById.get(c.chunkId);
    if (!p) {
      toUpsert.push(c); // new chunk
      continue;
    }
    if (p.chunkHash !== c.chunkHash || p.revisionId !== c.revisionId) {
      toUpsert.push(c); // changed
    }
  }

  for (const p of prev) {
    if (!nextById.has(p.chunkId)) {
      toDelete.push(p);
    }
  }

  return { toUpsert, toDelete };
}

/* ------------------------- Text normalization helpers ------------------------- */

function normalizeText(s: string): string {
  // Stable, block-level normalization.
  // Be careful: over-normalizing can hide meaningful changes (e.g., double spaces in code).
  // Tune this based on your docs.
  const nfc = s.normalize("NFC");
  const unifiedNewlines = nfc.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  const trimmedLines = unifiedNewlines
    .split("\n")
    .map((line) => line.replace(/[ \t]+/g, " ").trimEnd())
    .join("\n");
  return trimmedLines.trim();
}

function normalizeGlobalText(s: string): string {
  // Global normalization ensures you don't end up with extra blank lines or trailing whitespace.
  // Keep paragraph breaks, collapse 3+ newlines -> 2.
  const unified = s.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  const collapse = unified.replace(/\n{3,}/g, "\n\n").trim();
  return collapse;
}

function sha256Hex(s: string): string {
  return createHash("sha256").update(s, "utf8").digest("hex");
}

/* ------------------------- Docs structure helpers ------------------------- */

function headingLevelFromNamedStyle(namedStyleType?: string): number | null {
  if (!namedStyleType) return null;
  const m = namedStyleType.match(/^HEADING_(\d)$/);
  if (!m) return null;
  const lvl = Number(m[1]);
  return Number.isFinite(lvl) ? lvl : null;
}

function adjustOutlineStack(
  stack: Array<{ text: string; level: number }>,
  headingText: string,
  level: number
): Array<{ text: string; level: number }> {
  // Pop to parent level, then push new heading
  const next = stack.filter((h) => h.level < level);
  next.push({ text: headingText, level });
  return next;
}

function isListItem(paragraph: any): boolean {
  return Boolean(paragraph.bullet);
}

function listLevelFromParagraph(paragraph: any): number | null {
  // Docs API bullets have nestingLevel in some cases; not always present.
  const lvl = paragraph.bullet?.nestingLevel;
  if (lvl === undefined || lvl === null) return null;
  const n = Number(lvl);
  return Number.isFinite(n) ? n : null;
}

/* ------------------------- Snapshot reading (for diffs) ------------------------- */

/** Example: load a snapshot’s normalized text back from object store */
export async function loadNormalizedTextSnapshot(store: ObjectStore, textBlobKey: string): Promise<string> {
  const gz = await store.getObject(textBlobKey);
  const buf = gunzipSync(gz);
  return buf.toString("utf8");
}

/** Example: load structure snapshot back */
export async function loadStructureSnapshot(store: ObjectStore, structureBlobKey: string): Promise<StructureSnapshot> {
  const gz = await store.getObject(structureBlobKey);
  const buf = gunzipSync(gz);
  return JSON.parse(buf.toString("utf8")) as StructureSnapshot;
}
```

If you tell me which Google client library you’re using (`googleapis` in Node, REST, etc.) and which storage/DB you prefer (S3+Postgres, GCS+Firestore, etc.), I can adapt this into a truly runnable version with concrete client wiring and a small local dev harness.

## Prompt:
Can you give me a sketch in Python instead?

## Response:
```python
"""
ingestion_worker.py

A concrete Python sketch for:
  - Detecting changes (Drive)
  - Fetching structured doc (Docs)
  - Normalizing to stable text
  - Building a lightweight structure snapshot
  - Hashing + gzip compression
  - Writing blobs to object storage
  - Writing coordination metadata to a DB
  - Chunking from normalized text + structure
  - Incremental embedding updates + vector DB upserts

This is “runnable-shaped” pseudocode: replace the client stubs (Drive/Docs/DB/ObjectStore/Embedder/VectorDB)
with your real SDK integrations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import gzip
import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Tuple

# ----------------------------- Client interfaces -----------------------------

class DriveClient:
    def files_get(self, file_id: str) -> Dict[str, Any]:
        """Return {id,name,mimeType,modifiedTime,headRevisionId,...}"""
        raise NotImplementedError

    def revisions_list(self, file_id: str) -> List[Dict[str, Any]]:
        """Return list of {id,modifiedTime,lastModifyingUser:{displayName,emailAddress}}"""
        raise NotImplementedError

    # Optional: export plain text / html for alternative normalization
    # def files_export(self, file_id: str, mime_type: str) -> bytes:
    #     raise NotImplementedError

class DocsClient:
    def documents_get(self, document_id: str) -> Dict[str, Any]:
        """Return Google Docs document JSON."""
        raise NotImplementedError

class ObjectStore:
    def put(self, key: str, data: bytes, content_type: str, content_encoding: Optional[str] = None) -> Dict[str, Any]:
        """Store bytes; return {'uri':..., 'size':...}"""
        raise NotImplementedError

    def get(self, key: str) -> bytes:
        raise NotImplementedError

class Db:
    def get_doc_state(self, file_id: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def get_latest_snapshot_meta(self, file_id: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def get_chunks_by_file(self, file_id: str) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def transaction(self):
        """Context manager for a DB transaction."""
        raise NotImplementedError

class DbTx:
    def upsert_doc_state(self, state: Dict[str, Any]) -> None:
        raise NotImplementedError

    def insert_snapshot_meta(self, meta: Dict[str, Any]) -> None:
        raise NotImplementedError

    def upsert_chunks(self, chunks: List[Dict[str, Any]]) -> None:
        raise NotImplementedError

class Embedder:
    def embed(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError

class VectorDB:
    def upsert(self, items: List[Dict[str, Any]]) -> None:
        raise NotImplementedError

    def delete(self, vector_ids: List[str]) -> None:
        raise NotImplementedError

# ----------------------------- Data structures -----------------------------

@dataclass
class IngestionConfig:
    max_chunk_chars: int = 6000
    min_chunk_chars: int = 1200

@dataclass
class StructureBlock:
    block_id: str
    type: str  # heading|paragraph|list_item|table_row|unknown
    outline_path: List[str]
    heading_level: Optional[int] = None
    list_level: Optional[int] = None
    text_hash: str = ""
    char_start: Optional[int] = None
    char_end: Optional[int] = None

@dataclass
class NormalizedSnapshot:
    normalized_text: str
    normalized_hash: str
    blocks: List[StructureBlock]

# ----------------------------- Main ingestion -----------------------------

def ingest_google_doc(
    file_id: str,
    drive: DriveClient,
    docs: DocsClient,
    db: Db,
    store: ObjectStore,
    embedder: Embedder,
    vectordb: VectorDB,
    config: Optional[IngestionConfig] = None,
) -> Dict[str, Any]:
    cfg = config or IngestionConfig()

    # 1) Drive metadata
    f = drive.files_get(file_id)
    title = f.get("name") or "(untitled)"
    mime_type = f.get("mimeType") or ""
    head_revision_id = f.get("headRevisionId")

    # 2) Fast skip check
    state = db.get_doc_state(file_id)
    if state and head_revision_id and state.get("lastSeenHeadRevisionId") == head_revision_id:
        return {"status": "skipped", "reason": "headRevisionId unchanged", "revisionId": head_revision_id}

    # 3) Revisions list (optional but useful)
    revisions = drive.revisions_list(file_id)
    target_revision_id = head_revision_id or (revisions[0]["id"] if revisions else "unknown")

    # 4) Docs API fetch
    doc = docs.documents_get(file_id)

    # 5) Normalize + structure
    snap = normalize_docs_to_snapshot(file_id=file_id, revision_id=target_revision_id, doc=doc)

    # 6) Hash gate vs latest snapshot
    latest = db.get_latest_snapshot_meta(file_id)
    if latest and latest.get("normalizedHash") == snap.normalized_hash:
        # Still update doc state so we know we've seen this head revision
        now = _now_iso()
        with db.transaction() as tx:  # type: ignore
            tx.upsert_doc_state({
                "fileId": file_id,
                "title": title,
                "mimeType": mime_type,
                "lastSeenHeadRevisionId": target_revision_id,
                "lastIndexedRevisionId": latest.get("revisionId"),
                "lastIndexedAt": now,
                "lastIndexedContentHash": latest.get("normalizedHash"),
            })
        return {"status": "skipped", "reason": "normalized hash unchanged", "revisionId": target_revision_id}

    # 7) Compress + store blobs
    created_at = _now_iso()
    text_key = f"snapshots/{file_id}/{target_revision_id}/text.norm.txt.gz"
    struct_key = f"snapshots/{file_id}/{target_revision_id}/structure.json.gz"

    text_gz = gzip.compress(snap.normalized_text.encode("utf-8"), compresslevel=9)
    struct_payload = {
        "fileId": file_id,
        "revisionId": target_revision_id,
        "createdAt": created_at,
        "blocks": [b.__dict__ for b in snap.blocks],
    }
    struct_gz = gzip.compress(json.dumps(struct_payload, separators=(",", ":")).encode("utf-8"), compresslevel=9)

    text_put = store.put(text_key, text_gz, content_type="text/plain", content_encoding="gzip")
    struct_put = store.put(struct_key, struct_gz, content_type="application/json", content_encoding="gzip")

    # 8) Chunking from normalized + structure
    new_chunks = chunk_from_normalized_and_structure(
        file_id=file_id,
        revision_id=target_revision_id,
        normalized_text=snap.normalized_text,
        blocks=snap.blocks,
        cfg=cfg,
    )

    # 9) Incremental embedding (diff old vs new)
    prev_chunks = db.get_chunks_by_file(file_id)
    to_upsert, to_delete = diff_chunks(prev_chunks, new_chunks)

    upsert_items: List[Dict[str, Any]] = []
    if to_upsert:
        texts = [snap.normalized_text[c["charStart"]:c["charEnd"]] for c in to_upsert]
        embeddings = embedder.embed(texts)
        for c, emb in zip(to_upsert, embeddings):
            upsert_items.append({
                "vectorId": c["vectorId"],
                "embedding": emb,
                "metadata": {
                    "fileId": file_id,
                    "revisionId": target_revision_id,
                    "chunkId": c["chunkId"],
                    "outlinePath": c["outlinePath"],
                    "blockStartId": c["blockStartId"],
                    "blockEndId": c["blockEndId"],
                    "charStart": c["charStart"],
                    "charEnd": c["charEnd"],
                    "chunkHash": c["chunkHash"],
                    "title": title,
                }
            })

    # 10) Persist coordination metadata transactionally
    with db.transaction() as tx:  # type: ignore
        tx.insert_snapshot_meta({
            "fileId": file_id,
            "revisionId": target_revision_id,
            "createdAt": created_at,
            "normalizedHash": snap.normalized_hash,
            "textBlobKey": text_key,
            "structureBlobKey": struct_key,
            "sizeBytesText": int(text_put.get("size", 0)),
            "sizeBytesStructure": int(struct_put.get("size", 0)),
        })
        tx.upsert_doc_state({
            "fileId": file_id,
            "title": title,
            "mimeType": mime_type,
            "lastSeenHeadRevisionId": target_revision_id,
            "lastIndexedRevisionId": target_revision_id,
            "lastIndexedAt": created_at,
            "lastIndexedContentHash": snap.normalized_hash,
        })
        tx.upsert_chunks(new_chunks)

    # 11) Vector DB mutations (add retries in production)
    if to_delete:
        vectordb.delete([c["vectorId"] for c in to_delete])
    if upsert_items:
        vectordb.upsert(upsert_items)

    return {"status": "indexed", "revisionId": target_revision_id}

# ----------------------------- Normalization + structure -----------------------------

def normalize_docs_to_snapshot(file_id: str, revision_id: str, doc: Dict[str, Any]) -> NormalizedSnapshot:
    """
    Build:
      - normalized_text: stable plain text preserving paragraph boundaries
      - blocks: lightweight structure blocks with outline paths and char offsets
    """
    blocks: List[StructureBlock] = []
    parts: List[str] = []
    cursor = 0

    outline_stack: List[Tuple[str, int]] = []  # (heading_text, heading_level)

    body = (doc.get("body") or {}).get("content") or []

    for el in body:
        if "paragraph" in el:
            p = el["paragraph"]
            style = p.get("paragraphStyle") or {}
            named_style = style.get("namedStyleType")  # e.g., HEADING_1
            heading_level = _heading_level(named_style)

            text = _inline_elements_to_text(p.get("elements") or [])
            trimmed = text.strip()
            if not trimmed:
                continue

            block_type = "heading" if heading_level is not None else ("list_item" if _is_list_item(p) else "paragraph")

            if block_type == "heading" and heading_level is not None:
                outline_stack = _adjust_outline(outline_stack, trimmed, heading_level)

            outline_path = [h[0] for h in outline_stack]
            norm_block_text = _normalize_block_text(trimmed)

            sep = "" if not parts else "\n\n"
            char_start = cursor + len(sep)
            chunk_text = sep + norm_block_text
            parts.append(chunk_text)
            cursor += len(chunk_text)
            char_end = cursor

            text_hash = _sha256_hex(norm_block_text)
            block_id = _sha256_hex(json.dumps({
                "type": block_type,
                "outlinePath": outline_path,
                "headingLevel": heading_level,
                "textHash": text_hash,
            }, separators=(",", ":"), sort_keys=True))

            blocks.append(StructureBlock(
                block_id=block_id,
                type=block_type,
                outline_path=outline_path,
                heading_level=heading_level,
                list_level=_list_level(p),
                text_hash=text_hash,
                char_start=char_start,
                char_end=char_end,
            ))
            continue

        if "table" in el:
            table = el["table"]
            for row in table.get("tableRows") or []:
                cell_texts: List[str] = []
                for cell in row.get("tableCells") or []:
                    cell_plain = _extract_plain_from_doc_elements(cell.get("content") or [])
                    cell_texts.append(_normalize_block_text(cell_plain.strip()))
                row_text = f"| {' | '.join(cell_texts)} |".strip()
                if not row_text or row_text == "|  |":
                    continue

                outline_path = [h[0] for h in outline_stack]

                sep = "" if not parts else "\n\n"
                char_start = cursor + len(sep)
                chunk_text = sep + row_text
                parts.append(chunk_text)
                cursor += len(chunk_text)
                char_end = cursor

                text_hash = _sha256_hex(row_text)
                block_id = _sha256_hex(json.dumps({
                    "type": "table_row",
                    "outlinePath": outline_path,
                    "textHash": text_hash,
                }, separators=(",", ":"), sort_keys=True))

                blocks.append(StructureBlock(
                    block_id=block_id,
                    type="table_row",
                    outline_path=outline_path,
                    text_hash=text_hash,
                    char_start=char_start,
                    char_end=char_end,
                ))
            continue

        # ignore other element types (inline objects, drawings, etc.) for now

    normalized_text = _normalize_global_text("".join(parts))
    normalized_hash = _sha256_hex(normalized_text)

    # Important: if you normalize global text, offsets can drift if you collapse newlines.
    # Production approach: avoid altering newline counts after offsets are set, OR compute offsets after final normalization.
    # Here, we keep global normalization mild (trim + collapse 3+ newlines).
    return NormalizedSnapshot(normalized_text=normalized_text, normalized_hash=normalized_hash, blocks=blocks)

def _inline_elements_to_text(elements: List[Dict[str, Any]]) -> str:
    out = []
    for e in elements:
        tr = e.get("textRun")
        if tr and tr.get("content"):
            out.append(tr["content"])
        elif e.get("inlineObjectElement"):
            out.append(" [IMAGE] ")
        elif e.get("horizontalRule"):
            out.append("\n")
    return "".join(out)

def _extract_plain_from_doc_elements(content: List[Dict[str, Any]]) -> str:
    out = []
    for el in content:
        if "paragraph" in el:
            out.append(_inline_elements_to_text((el["paragraph"].get("elements") or [])))
            out.append("\n")
    return "".join(out)

def _heading_level(named_style: Optional[str]) -> Optional[int]:
    if not named_style:
        return None
    m = re.match(r"^HEADING_(\d)$", named_style)
    if not m:
        return None
    lvl = int(m.group(1))
    return lvl if 1 <= lvl <= 6 else None

def _adjust_outline(stack: List[Tuple[str, int]], heading_text: str, level: int) -> List[Tuple[str, int]]:
    # Pop to parent
    stack = [(t, lvl) for (t, lvl) in stack if lvl < level]
    stack.append((heading_text, level))
    return stack

def _is_list_item(paragraph: Dict[str, Any]) -> bool:
    return bool(paragraph.get("bullet"))

def _list_level(paragraph: Dict[str, Any]) -> Optional[int]:
    bullet = paragraph.get("bullet") or {}
    lvl = bullet.get("nestingLevel")
    return int(lvl) if isinstance(lvl, int) else None

def _normalize_block_text(s: str) -> str:
    # Stable per-block normalization
    s = s.normalize("NFC") if hasattr(s, "normalize") else s
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    for line in s.split("\n"):
        line = re.sub(r"[ \t]+", " ", line).rstrip()
        lines.append(line)
    return "\n".join(lines).strip()

def _normalize_global_text(s: str) -> str:
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    return s

def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

# ----------------------------- Chunking + incremental -----------------------------

def chunk_from_normalized_and_structure(
    file_id: str,
    revision_id: str,
    normalized_text: str,
    blocks: List[StructureBlock],
    cfg: IngestionConfig,
) -> List[Dict[str, Any]]:
    chunks: List[Dict[str, Any]] = []

    i = 0
    while i < len(blocks):
        start = blocks[i]
        outline_key = " / ".join(start.outline_path)
        char_start = start.char_start or 0
        char_end = start.char_end or char_start
        end_i = i

        while end_i + 1 < len(blocks):
            nxt = blocks[end_i + 1]
            nxt_outline = " / ".join(nxt.outline_path)
            would_cross = nxt_outline != outline_key

            nxt_end = nxt.char_end or char_end
            proposed = nxt_end - char_start

            if proposed > cfg.max_chunk_chars:
                break
            if would_cross and (char_end - char_start) >= cfg.min_chunk_chars:
                break

            char_end = nxt_end
            end_i += 1

        # try to meet min size
        if (char_end - char_start) < cfg.min_chunk_chars and end_i + 1 < len(blocks):
            nxt = blocks[end_i + 1]
            nxt_end = nxt.char_end or char_end
            if (nxt_end - char_start) <= cfg.max_chunk_chars:
                char_end = nxt_end
                end_i += 1

        block_start_id = blocks[i].block_id
        block_end_id = blocks[end_i].block_id
        outline_path = blocks[i].outline_path

        chunk_text = normalized_text[char_start:char_end]
        chunk_hash = _sha256_hex(chunk_text)

        chunk_id = _sha256_hex(json.dumps({
            "fileId": file_id,
            "outlinePath": outline_path,
            "blockStartId": block_start_id,
            "blockEndId": block_end_id,
        }, separators=(",", ":"), sort_keys=True))

        chunks.append({
            "fileId": file_id,
            "revisionId": revision_id,
            "chunkId": chunk_id,
            "vectorId": chunk_id,
            "outlinePath": outline_path,
            "blockStartId": block_start_id,
            "blockEndId": block_end_id,
            "charStart": char_start,
            "charEnd": char_end,
            "chunkHash": chunk_hash,
        })

        i = end_i + 1

    return chunks

def diff_chunks(prev_chunks: List[Dict[str, Any]], new_chunks: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    prev_by_id = {c["chunkId"]: c for c in prev_chunks}
    new_by_id = {c["chunkId"]: c for c in new_chunks}

    to_upsert: List[Dict[str, Any]] = []
    to_delete: List[Dict[str, Any]] = []

    for c in new_chunks:
        p = prev_by_id.get(c["chunkId"])
        if not p:
            to_upsert.append(c)
        elif p.get("chunkHash") != c.get("chunkHash") or p.get("revisionId") != c.get("revisionId"):
            to_upsert.append(c)

    for p in prev_chunks:
        if p["chunkId"] not in new_by_id:
            to_delete.append(p)

    return to_upsert, to_delete

# ----------------------------- Snapshot loading helpers -----------------------------

def load_normalized_text_snapshot(store: ObjectStore, text_blob_key: str) -> str:
    gz = store.get(text_blob_key)
    return gzip.decompress(gz).decode("utf-8")

def load_structure_snapshot(store: ObjectStore, structure_blob_key: str) -> Dict[str, Any]:
    gz = store.get(structure_blob_key)
    return json.loads(gzip.decompress(gz).decode("utf-8"))
```

If you tell me your target stack (e.g., Postgres + S3 + Pinecone/Weaviate/pgvector + OpenAI embeddings), I can map the client stubs to real libraries and show how to implement `DriveClient` / `DocsClient` using `google-api-python-client` and OAuth/service accounts.



---
Powered by [ChatGPT Exporter](https://www.chatgptexporter.com)