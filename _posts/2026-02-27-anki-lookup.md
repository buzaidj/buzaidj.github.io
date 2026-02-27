---
layout: post
title: "Anki Lookup"
date: 2026-02-27 12:00:00 -0700
categories: tools
permalink: /anki/
---

<style>
    #search-box {
        width: 100%;
        padding: 0.6rem 0.8rem;
        font-size: 16px;
        font-family: 'Inter', sans-serif;
        border: 1px solid #ccc;
        border-radius: 4px;
        box-sizing: border-box;
        margin-bottom: 0.5rem;
    }
    #search-box:focus {
        outline: none;
        border-color: #888;
    }
    #status {
        font-size: 13px;
        color: #888;
        margin-bottom: 1rem;
        font-weight: 300;
    }
    .result {
        padding: 0.7rem 0;
        border-bottom: 1px solid #eee;
    }
    .result:last-child {
        border-bottom: none;
    }
    .result-word {
        font-weight: 500;
        font-size: 18px;
    }
    .result-reading {
        font-weight: 300;
        color: #666;
        margin-left: 0.4rem;
    }
    .result-meaning {
        margin-top: 0.2rem;
        font-weight: 300;
        font-size: 15px;
    }
    .result-sentence {
        margin-top: 0.2rem;
        font-size: 13px;
        color: #555;
        font-weight: 300;
    }
    .result-deck {
        font-size: 11px;
        color: #aaa;
        margin-top: 0.15rem;
    }
    .result-score {
        font-size: 11px;
        color: #bbb;
        float: right;
        margin-top: 0.15rem;
    }
    #results {
        margin-top: 0.5rem;
    }
</style>

<script>document.querySelector('.two-col').style.width = '100%';</script>

<p style="font-weight: 300; margin-top: 0;">look up words with embeddings</p>

<input type="text" id="search-box" placeholder="search in english or japanese..." disabled>
<div id="status">loading...</div>
<div id="results"></div>

<script type="module">
    import { pipeline } from 'https://cdn.jsdelivr.net/npm/@xenova/transformers@2.17.2';

    const statusEl = document.getElementById('status');
    const searchBox = document.getElementById('search-box');
    const resultsEl = document.getElementById('results');

    let cards = null;
    let embeddings = null;
    let embedder = null;
    const DIM = 384;

    async function init() {
        statusEl.textContent = 'downloading model...';

        const [cardsData, embBuf, pipe] = await Promise.all([
            fetch('/assets/anki/cards.json').then(r => r.json()),
            fetch('/assets/anki/embeddings.bin').then(r => r.arrayBuffer()),
            pipeline('feature-extraction', 'Xenova/multilingual-e5-small'),
        ]);

        cards = cardsData;
        embeddings = new Float32Array(embBuf);
        embedder = pipe;

        statusEl.textContent = `ready — ${cards.length} cards loaded`;
        searchBox.disabled = false;
        searchBox.focus();
    }

    function cosineSim(a, b, offset) {
        let dot = 0;
        let normB = 0;
        for (let i = 0; i < DIM; i++) {
            const bv = b[offset + i];
            dot += a[i] * bv;
            normB += bv * bv;
        }
        return dot / (Math.sqrt(normB) + 1e-8);
    }

    async function search(query) {
        if (!query.trim() || !embedder) return;

        const output = await embedder(`query: ${query}`, { pooling: 'mean', normalize: true });
        const qvec = output.data;

        const scores = new Float32Array(cards.length);
        for (let i = 0; i < cards.length; i++) {
            scores[i] = cosineSim(qvec, embeddings, i * DIM);
        }

        const indices = Array.from({ length: cards.length }, (_, i) => i);
        indices.sort((a, b) => scores[b] - scores[a]);
        const top = indices.slice(0, 20);

        resultsEl.innerHTML = '';
        for (const idx of top) {
            const c = cards[idx];
            const score = scores[idx];
            const div = document.createElement('div');
            div.className = 'result';

            let html = '<div>';
            html += `<span class="result-score">${score.toFixed(3)}</span>`;
            html += `<span class="result-word">${esc(c.w)}</span>`;
            if (c.r && c.r !== c.w) {
                html += `<span class="result-reading">(${esc(c.r)})</span>`;
            }
            html += '</div>';
            if (c.m) html += `<div class="result-meaning">${esc(c.m)}</div>`;
            if (c.s) html += `<div class="result-sentence">${esc(c.s)}</div>`;
            if (c.d) html += `<div class="result-deck">${esc(c.d)}</div>`;

            div.innerHTML = html;
            resultsEl.appendChild(div);
        }
    }

    function esc(s) {
        const d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    }

    let timer = null;
    searchBox.addEventListener('input', () => {
        clearTimeout(timer);
        timer = setTimeout(() => search(searchBox.value), 250);
    });

    init().catch(err => {
        statusEl.textContent = `error: ${err.message}`;
        console.error(err);
    });
</script>
