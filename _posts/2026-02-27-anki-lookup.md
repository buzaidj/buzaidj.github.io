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
    #controls {
        display: flex;
        gap: 0.5rem;
        align-items: center;
        margin-bottom: 0.5rem;
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
        font-size: 20px;
    }
    .result-word rt {
        font-weight: 300;
        font-size: 11px;
    }
    .result-word ruby {
        ruby-align: center;
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

I have around 11,000 Anki cards dedicated to Japanese learning. 4,000 of these are works I discovered on my own outside of study materials: found in books, heard in conversation, etc. These cards are mostly targed torwards recognition, which gives me a ton of breadth, but one thing I consistenlty struggle with is recall.

This is a search index over my Anki cards. It uses a few language models and other heuristics to find good search matches:
* meaning - two embeddings models, a multilingual ( ) and a Japanese-specific model turn each card into vectors. This works well for synonyms, but doesn't match well when I only remember a part of the word I want to find.
* readings - embedding models treat kana and kanji as unrelated text. A lot of words in Japanese "optionally" have kanji, so seraching くりかえす matches 繰り返す. Same word, different spelling.
* sound - sometimes I misremember a word and type something that only sounds close. I once misremembered ぐにゃり (flabby)  as ぐんやり. This converts kana to IPA and compares the words by phonemes, so typos that sound the same still match.

All of these are combined with [reciprocal rank fusion](https://learn.microsoft.com/en-us/azure/search/hybrid-search-ranking), so a card that ranks well in *any* index floats to the top, and kana queries lean harder on reading and sound than on meaning.

<div id="controls">
    <span style="font-weight: 300;">look up words with embeddings — meaning, reading, and sound combined</span>
</div>
<input type="text" id="search-box" placeholder="search in english or japanese..." disabled>
<div id="status">loading...</div>
<div id="results"></div>

<script type="module">
    import { pipeline, AutoTokenizer } from 'https://cdn.jsdelivr.net/npm/@xenova/transformers@2.17.2';
    import { kanaToFeatures, weightedFeatureEditDistance } from '/assets/phonetic.js';

    const statusEl = document.getElementById('status');
    const searchBox = document.getElementById('search-box');
    const resultsEl = document.getElementById('results');

    let cards = null;

    // Each model has: embeddings (Float32Array), dim, embed (async fn query -> vec).
    // Both run on every search and are fused together (no model picker).
    const models = {
        e5b: { embeddings: null, dim: 768, embed: null, loading: false, loaded: false },
        ruri: { embeddings: null, dim: 256, embed: null, loading: false, loaded: false },
    };

    // Reading (furigana) layer: normalized kana keys + ruri kana embeddings.
    // Runs alongside whatever display model is active so a kana query
    // (ちゅうとはんぱ) matches a kanji card (中途半端).
    const reading = {
        keys: null,          // array of normalized hiragana strings, card-aligned
        bigrams: null,       // array of Map<bigram,count> per card
        kanaEmb: null,       // Float32Array, ruri 256-dim over reading keys
        kanaDim: 256,
        ruriEmbed: null,     // async query -> ruri vector (shared with ruri model)
        phonTable: null,     // kana -> articulatory feature vectors lookup
        cardPhon: null,      // per-card precomputed feature-vector sequences
        loaded: false,
        loading: false,
    };

    async function loadCards() {
        if (cards) return;
        cards = await fetch('/assets/anki/cards.json').then(r => r.json());
    }

    // Katakana -> hiragana, NFKC, strip everything but kana + 'ー'.
    function normalizeKana(text) {
        if (!text) return '';
        let s = text.normalize('NFKC');
        let out = '';
        for (const ch of s) {
            const code = ch.codePointAt(0);
            if (code >= 0x30A1 && code <= 0x30F6) {
                out += String.fromCodePoint(code - 0x60); // katakana -> hiragana
            } else if ((ch >= '぀' && ch <= 'ゟ') || ch === 'ー') {
                out += ch;
            }
        }
        return out;
    }

    function toBigrams(s) {
        const m = new Map();
        if (s.length === 1) { m.set(s, 1); return m; }
        for (let i = 0; i < s.length - 1; i++) {
            const g = s.slice(i, i + 2);
            m.set(g, (m.get(g) || 0) + 1);
        }
        return m;
    }

    function bigramCosine(qm, dm, dnorm) {
        let dot = 0, qnorm = 0;
        for (const [g, qc] of qm) {
            qnorm += qc * qc;
            const dc = dm.get(g);
            if (dc) dot += qc * dc;
        }
        if (qnorm === 0 || dnorm === 0) return 0;
        return dot / (Math.sqrt(qnorm) * dnorm);
    }

    async function loadReadingLayer() {
        if (reading.loaded || reading.loading) return;
        reading.loading = true;
        const [keys, embBuf, phonTable] = await Promise.all([
            fetch('/assets/anki/readings.json').then(r => r.json()),
            fetch('/assets/anki/emb_ruri_kana.bin').then(r => r.arrayBuffer()),
            fetch('/assets/anki/kana_phon.json').then(r => r.json()),
        ]);
        reading.keys = keys.map(normalizeKana);
        reading.bigrams = reading.keys.map(toBigrams);
        // precompute each card's phonetic feature-vector sequence
        reading.phonTable = phonTable;
        reading.cardPhon = reading.keys.map(k => kanaToFeatures(k, phonTable));
        // precompute each card's bigram norm for cosine
        reading.bigramNorms = reading.bigrams.map(m => {
            let n = 0;
            for (const c of m.values()) n += c * c;
            return Math.sqrt(n);
        });
        reading.kanaEmb = new Float32Array(embBuf);
        // ensure ruri is available to embed kana queries
        await loadRuriModel();
        reading.ruriEmbed = models.ruri.embed;
        reading.loaded = true;
        reading.loading = false;
    }

    async function loadE5Model(key, hfId, embFile, dim) {
        const m = models[key];
        if (m.loaded || m.loading) return;
        m.loading = true;
        statusEl.textContent = `downloading ${key} model...`;

        const [embBuf, pipe] = await Promise.all([
            fetch(`/assets/anki/${embFile}`).then(r => r.arrayBuffer()),
            pipeline('feature-extraction', hfId),
        ]);

        m.embeddings = new Float32Array(embBuf);
        m.embed = async (query) => {
            const out = await pipe(`query: ${query}`, { pooling: 'mean', normalize: true });
            return out.data;
        };
        m.loading = false;
        m.loaded = true;
    }

    async function loadRuriModel() {
        const m = models.ruri;
        if (m.loaded || m.loading) return;
        m.loading = true;
        statusEl.textContent = 'downloading ruri model...';

        const ort = await import('https://cdn.jsdelivr.net/npm/onnxruntime-web@1.17.3/dist/esm/ort.min.js');
        ort.env.wasm.wasmPaths = 'https://cdn.jsdelivr.net/npm/onnxruntime-web@1.17.3/dist/';

        const [embBuf, modelBuf, tokenizer] = await Promise.all([
            fetch('/assets/anki/emb_ruri.bin').then(r => r.arrayBuffer()),
            fetch('/assets/anki/ruri/model.onnx').then(r => r.arrayBuffer()),
            AutoTokenizer.from_pretrained('cl-nagoya/ruri-v3-30m'),
        ]);

        m.embeddings = new Float32Array(embBuf);

        const session = await ort.InferenceSession.create(modelBuf, {
            executionProviders: ['wasm'],
        });

        m.embed = async (query) => {
            const encoded = await tokenizer(query, { padding: false, truncation: true });
            const ids = encoded.input_ids.data;
            const mask = encoded.attention_mask.data;

            const feeds = {
                input_ids: new ort.Tensor('int64', ids, [1, ids.length]),
                attention_mask: new ort.Tensor('int64', mask, [1, mask.length]),
            };
            const results = await session.run(feeds);
            const hidden = results['last_hidden_state'].data;
            const seqLen = ids.length;
            const dim = 256;

            // Mean pooling over attention-masked tokens
            const vec = new Float32Array(dim);
            let count = 0;
            for (let t = 0; t < seqLen; t++) {
                if (Number(mask[t]) === 1) {
                    for (let d = 0; d < dim; d++) {
                        vec[d] += hidden[t * dim + d];
                    }
                    count++;
                }
            }
            for (let d = 0; d < dim; d++) vec[d] /= count;

            // L2 normalize
            let norm = 0;
            for (let d = 0; d < dim; d++) norm += vec[d] * vec[d];
            norm = Math.sqrt(norm);
            for (let d = 0; d < dim; d++) vec[d] /= norm;

            return vec;
        };

        m.loading = false;
        m.loaded = true;
    }

    async function ensureModel(key) {
        if (models[key].loaded) return;
        if (key === 'e5b') await loadE5Model('e5b', 'Xenova/multilingual-e5-base', 'emb_e5b.bin', 768);
        else if (key === 'ruri') await loadRuriModel();
    }

    function cosineSim(a, b, offset, dim) {
        let dot = 0;
        let normB = 0;
        for (let i = 0; i < dim; i++) {
            const bv = b[offset + i];
            dot += a[i] * bv;
            normB += bv * bv;
        }
        return dot / (Math.sqrt(normB) + 1e-8);
    }

    // Rank a score array descending, return index array.
    function rankByScore(scores) {
        const idx = Array.from({ length: scores.length }, (_, i) => i);
        idx.sort((a, b) => scores[b] - scores[a]);
        return idx;
    }

    // Reciprocal Rank Fusion: fuse ranked lists by rank position.
    // weights lets us boost the reading lists for kana/romaji-only queries.
    const RRF_K = 60;
    function rrf(rankedLists, weights) {
        const fused = new Map();
        rankedLists.forEach((ranked, li) => {
            const w = weights[li];
            if (w === 0) return;
            for (let r = 0; r < ranked.length; r++) {
                const id = ranked[r];
                fused.set(id, (fused.get(id) || 0) + w / (RRF_K + r));
            }
        });
        return fused;
    }

    // True if the query is purely kana (after normalization it's non-empty
    // and the original had no latin/kanji) — these are reading lookups.
    function isReadingQuery(query) {
        const kana = normalizeKana(query);
        if (!kana) return false;
        // if normalized kana length ~= original length (minus spaces), it was kana
        const stripped = query.replace(/\s/g, '');
        return kana.length >= stripped.length * 0.8;
    }

    async function search(query) {
        if (!query.trim()) {
            resultsEl.innerHTML = '';
            return;
        }

        const lists = [];
        const weights = [];

        // --- lists 1 & 2: semantic neural (e5-base multilingual + ruri japanese) ---
        for (const key of ['e5b', 'ruri']) {
            const m = models[key];
            if (!m.loaded) continue;
            const qvec = await m.embed(query);
            const dim = m.dim;
            const semScores = new Float32Array(cards.length);
            for (let i = 0; i < cards.length; i++) {
                semScores[i] = cosineSim(qvec, m.embeddings, i * dim, dim);
            }
            lists.push(rankByScore(semScores));
            weights.push(1.0);
        }
        if (!lists.length) return; // models not loaded yet
        const numSemantic = lists.length;

        // reading layer (loads on first use)
        if (!reading.loaded) {
            try { await loadReadingLayer(); } catch (e) { console.warn('reading layer failed', e); }
        }

        if (reading.loaded) {
            const qkana = normalizeKana(query);

            // --- list 2: fuzzy kana bigram ---
            if (qkana) {
                const qbi = toBigrams(qkana);
                const fz = new Float32Array(cards.length);
                for (let i = 0; i < cards.length; i++) {
                    fz[i] = bigramCosine(qbi, reading.bigrams[i], reading.bigramNorms[i]);
                }
                lists.push(rankByScore(fz));
                weights.push(1.0);
            }

            // --- list 3: kana neural (ruri over reading) ---
            try {
                const kvec = await reading.ruriEmbed(qkana || query);
                const kdim = reading.kanaDim;
                const kn = new Float32Array(cards.length);
                for (let i = 0; i < cards.length; i++) {
                    kn[i] = cosineSim(kvec, reading.kanaEmb, i * kdim, kdim);
                }
                lists.push(rankByScore(kn));
                weights.push(1.0);
            } catch (e) { console.warn('kana neural failed', e); }

            // --- list 4: phonetic ("sounds alike") feature edit distance ---
            // Lower distance = closer sound, so rank ascending.
            if (qkana && reading.phonTable) {
                const qphon = kanaToFeatures(qkana, reading.phonTable);
                if (qphon.length) {
                    const w = reading.phonTable.weights;
                    const indel = reading.phonTable.indelCost;
                    const dist = new Float32Array(cards.length);
                    for (let i = 0; i < cards.length; i++) {
                        dist[i] = weightedFeatureEditDistance(qphon, reading.cardPhon[i], w, indel);
                    }
                    const idx = Array.from({ length: cards.length }, (_, i) => i);
                    idx.sort((a, b) => dist[a] - dist[b]);
                    lists.push(idx);
                    weights.push(1.0);
                }
            }

            // boost reading lists when the query is a pure-kana reading lookup.
            // The semantic lists (indices < numSemantic) stay at 1.0; the reading,
            // bigram, kana-neural, and phonetic lists get heavily up-weighted so a
            // kana query is ranked mostly by reading/sound, not meaning.
            if (isReadingQuery(query)) {
                for (let li = numSemantic; li < weights.length; li++) weights[li] *= 4.0;
            }
        }

        const fused = rrf(lists, weights);
        const top = [...fused.entries()]
            .sort((a, b) => b[1] - a[1])
            .slice(0, 20)
            .map(e => e[0]);

        resultsEl.innerHTML = '';
        for (const idx of top) {
            const c = cards[idx];
            const score = fused.get(idx);
            const div = document.createElement('div');
            div.className = 'result';

            let html = '<div>';
            html += `<span class="result-score">${score.toFixed(3)}</span>`;
            html += `<span class="result-word">${furigana(c.r, c.w)}</span>`;
            html += '</div>';
            if (c.m) html += `<div class="result-meaning">${esc(c.m)}</div>`;
            if (c.s) html += `<div class="result-sentence">${esc(c.s)}</div>`;
            if (c.d) html += `<div class="result-deck">${esc(c.d)}</div>`;

            div.innerHTML = html;
            resultsEl.appendChild(div);
        }
    }

    // Convert "乗[の]り遅[おく]れる" -> "<ruby>乗<rt>の</rt></ruby>り<ruby>遅<rt>おく</rt></ruby>れる"
    // If reading has no brackets (e.g. "おくれる"), put it as ruby over the word
    function furigana(reading, word) {
        if (reading && reading.includes('[')) {
            return esc(reading).replace(/ /g, '').replace(/([\u4e00-\u9faf\u3400-\u4dbf]+)\[([^\]]+)\]/g, '<ruby>$1<rt>$2</rt></ruby>');
        }
        if (reading && reading !== word && /[\u4e00-\u9faf]/.test(word)) {
            return `<ruby>${esc(word)}<rt>${esc(reading)}</rt></ruby>`;
        }
        return esc(word);
    }

    function esc(s) {
        const d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    }

    // Debounced search
    let timer = null;
    searchBox.addEventListener('input', () => {
        clearTimeout(timer);
        timer = setTimeout(() => search(searchBox.value), 250);
    });

    // Init: load cards + both neural models (e5-base + ruri), fused on search.
    async function init() {
        await loadCards();
        await Promise.all([ensureModel('e5b'), ensureModel('ruri')]);
        statusEl.textContent = `ready — ${cards.length} cards`;
        searchBox.disabled = false;
        searchBox.focus();
    }

    init().catch(err => {
        statusEl.textContent = `error: ${err.message}`;
        console.error(err);
    });
</script>
