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
    #model-select {
        font-family: 'Inter', sans-serif;
        font-size: 13px;
        padding: 0.3rem 0.5rem;
        border: 1px solid #ccc;
        border-radius: 4px;
        background: white;
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

<div id="controls">
    <span style="font-weight: 300;">look up words with embeddings</span>
    <select id="model-select">
        <option value="e5s" selected>e5-small (multilingual, 118 MB)</option>
        <option value="e5b">e5-base (multilingual, 270 MB)</option>
        <option value="ruri">ruri-v3-30m (japanese, 42 MB)</option>
    </select>
</div>
<input type="text" id="search-box" placeholder="search in english or japanese..." disabled>
<div id="status">loading...</div>
<div id="results"></div>

<script type="module">
    import { pipeline, AutoTokenizer } from 'https://cdn.jsdelivr.net/npm/@xenova/transformers@2.17.2';

    const statusEl = document.getElementById('status');
    const searchBox = document.getElementById('search-box');
    const resultsEl = document.getElementById('results');
    const modelSelect = document.getElementById('model-select');

    let cards = null;

    // Each model has: embeddings (Float32Array), dim, embed (async fn query -> vec)
    const models = {
        e5s: { embeddings: null, dim: 384, embed: null, loading: false, loaded: false },
        e5b: { embeddings: null, dim: 768, embed: null, loading: false, loaded: false },
        ruri: { embeddings: null, dim: 256, embed: null, loading: false, loaded: false },
    };

    let activeModel = 'e5s';

    async function loadCards() {
        if (cards) return;
        cards = await fetch('/assets/anki/cards.json').then(r => r.json());
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
        if (key === 'e5s') await loadE5Model('e5s', 'Xenova/multilingual-e5-small', 'emb_e5s.bin', 384);
        else if (key === 'e5b') await loadE5Model('e5b', 'Xenova/multilingual-e5-base', 'emb_e5b.bin', 768);
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

    async function search(query) {
        if (!query.trim()) {
            resultsEl.innerHTML = '';
            return;
        }

        const m = models[activeModel];
        if (!m.loaded) return;

        const qvec = await m.embed(query);
        const dim = m.dim;

        const scores = new Float32Array(cards.length);
        for (let i = 0; i < cards.length; i++) {
            scores[i] = cosineSim(qvec, m.embeddings, i * dim, dim);
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

    // Debounced search
    let timer = null;
    searchBox.addEventListener('input', () => {
        clearTimeout(timer);
        timer = setTimeout(() => search(searchBox.value), 250);
    });

    // Model switching
    modelSelect.addEventListener('change', async () => {
        const key = modelSelect.value;
        activeModel = key;
        searchBox.disabled = true;
        resultsEl.innerHTML = '';

        try {
            await ensureModel(key);
            statusEl.textContent = `ready — ${cards.length} cards (${key})`;
            searchBox.disabled = false;
            searchBox.focus();
            if (searchBox.value.trim()) search(searchBox.value);
        } catch (err) {
            statusEl.textContent = `error: ${err.message}`;
            console.error(err);
        }
    });

    // Init: load cards + default model
    async function init() {
        await loadCards();
        await ensureModel('e5s');
        statusEl.textContent = `ready — ${cards.length} cards (e5s)`;
        searchBox.disabled = false;
        searchBox.focus();
    }

    init().catch(err => {
        statusEl.textContent = `error: ${err.message}`;
        console.error(err);
    });
</script>
