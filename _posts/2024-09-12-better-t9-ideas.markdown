---
layout: post
title:  "Better T9 Keyboards"
date:   2024-10-11 08:05:00 -0700
categories: t9 keyboard ml algorithms data-structures
permalink: /better-t9/
---

<div style="display: flex; flex-direction: row; justify-content: space-between; align-items: center">
    <div style="text-align: center">
        <img src="/assets/cat-s22.jpg" width="200" />
        <div>Cat S22</div>
    </div>
    <div style="text-align: center">
        <img src="/assets/t9.png" width="100" />
        <div>T9 Keyboard</div>
    </div>
    <div style="text-align: center">
        <img src="/assets/t9-misspelled-word.png" width="200" />
        <div>"Abreviations"</div>
    </div>
</div>

The CAT S22 is a $65 flip phone that runs Android. It has a numpad and a small touch screen. I've been using it as my primary phone for the past few months. The screen is so small it's hard to do anything else other than texting, calling, and some basic web surfing. Which is why I bought it.

Although the phone has a numpad, it doesn't come stock with a T9 keyboard application. T9 is a predictive text technology for mobile phones with numeric keypards that makes texting easier. Typing "43556" for example produces "hello". Becasue numeric strings don't uniquely map to words, after typing the numbers one clicks left/right with the D-pad to select their desired word. 

I downloaded the TT9 app which is great and has all the core T9 functionality. The only issue I've run into is that TT9's implementation, like most, isn't very robust to small spelling errors. For example spelling "abbreviations" with one "b" goes horribly wrong. Currently, the numbers you type must all have some mapping to the letters in the word you want. Missing a number, adding an additional number, or mistyping one number for another results in the desired word not appearing in the result set and the user having to start typing the word over again.

![t9 example](/assets/t9_db_example.png){: width="500" }

TT9 uses a SQLite database with T9 sequences and words like the one in the image above and upon each key press queries the dictionary for that sequence. Querying the dictionary produces the set of words that start with that sequence subject to ordering by word length and frequency and a limit. There doesn't appear to be any in memory caching of previous results from prior queries.

One approach to adding "spell correction" is adding all results with edit distance 1 to the result set. We can substitue a character, insert a character in any position, or delete any character. For a five character word we'd have to make an additional 110 queries. The number of queries made grows quadratically with sequence length. This is infeasible.

Another approach is to think of better backing database representations for T9 querying. There's a natural tree / graph structure to this problem. I'm going to attempt one of these solutions and report back in a future post.