/* Blender in-page editor.
 * Enable by appending ?edit to any URL (e.g. blenderai.link/docs.html?edit).
 * Toolbar appears bottom-right with Edit toggle, Save (writes to local file
 * via the File System Access API), and Reset.
 *
 * First Save click: browser prompts you to pick the target file. Subsequent
 * Save clicks in the same session overwrite that file silently.
 * Reloading the page clears the file handle; pick again.
 *
 * Per-page localStorage key keeps edits on each page isolated.
 *
 * File System Access API works in Chromium browsers (Chrome, Edge, Brave,
 * Arc). Not supported in Firefox or Safari; on those browsers Save falls
 * back to a download.
 */
(function () {
    if (!new URLSearchParams(window.location.search).has('edit')) return;

    const pageFile = (location.pathname.split('/').pop() || 'index.html').replace(/^$/, 'index.html') || 'index.html';
    const STORAGE_KEY = 'blender-edits-v1-' + pageFile;
    let fileHandle = null;

    const SELECTORS = [
        'h1', 'h2', 'h3', 'h4', 'h5',
        'p.lead', 'p.lede', 'p.subtitle', 'p.section-blurb', 'p.lineage-caption',
        'p.hero-caption', 'p.brood-coda', 'p.match-coda', 'p.note',
        'p.copyright', 'p.epitaph', 'p.phase-tagline',
        '.docs-body p', '.docs-body li', '.docs-body td',
        '.agent-profile p', '.agent-profile li',
        '.registry p', '.registry li',
        '.phase p', '.phase li',
        '.callout',
        '.section-eyebrow', '.day-num',
        '.common', '.latin', '.cross',
        '.match-name', '.match-species', '.match-token', '.match-pitch',
        '.token-symbol', '.token-name', '.token-tag',
        '.stat-value', '.stat-label',
        '.mechanic-box h4', '.mechanic-box li',
        '.feature-card p', '.feature-card h3',
        '.card p', '.card h3',
        '.archetype-card p', '.archetype-card h4',
        '.specimen p', '.specimen .common', '.specimen .latin',
        '.archetype-tag', '.btn'
    ].join(', ');

    const SKIP_SELECTOR = '.menagerie, .icon-wrap, .legend-dot, .creature, .frame, .glyph, .edit-toolbar, .toc, nav, header, footer, code, pre, [data-no-edit]';

    function tagEditableNodes() {
        let counter = 0;
        document.querySelectorAll(SELECTORS).forEach((el) => {
            if (el.closest(SKIP_SELECTOR)) return;
            if (el.closest('svg')) return;
            if (el.hasAttribute('data-edit-id')) return;
            el.setAttribute('data-edit-id', 'e' + (counter++));
        });
    }

    function loadEdits() {
        let edits = {};
        try { edits = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}'); } catch (e) {}
        document.querySelectorAll('[data-edit-id]').forEach((el) => {
            const id = el.getAttribute('data-edit-id');
            if (edits[id] !== undefined) el.innerHTML = edits[id];
        });
    }

    function saveEditToLocalStorage(el) {
        let edits = {};
        try { edits = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}'); } catch (e) {}
        edits[el.getAttribute('data-edit-id')] = el.innerHTML;
        localStorage.setItem(STORAGE_KEY, JSON.stringify(edits));
    }

    function setEditMode(on) {
        document.querySelectorAll('[data-edit-id]').forEach((el) => {
            el.setAttribute('contenteditable', on ? 'true' : 'false');
            el.classList.toggle('edit-on', on);
            if (on && !el._editBound) {
                el.addEventListener('blur', () => saveEditToLocalStorage(el));
                el._editBound = true;
            }
        });
    }

    function composeHTML(bar) {
        bar.remove();
        document.querySelectorAll('[data-edit-id]').forEach((el) => {
            el.removeAttribute('contenteditable');
            el.classList.remove('edit-on');
        });
        const html = '<!DOCTYPE html>\n' + document.documentElement.outerHTML;
        document.body.appendChild(bar);
        document.querySelectorAll('[data-edit-id]').forEach((el) => {
            if (bar.dataset.editOn === '1') {
                el.setAttribute('contenteditable', 'true');
                el.classList.add('edit-on');
            }
        });
        return html;
    }

    function fallbackDownload(html) {
        const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = pageFile;
        document.body.appendChild(a);
        a.click();
        a.remove();
    }

    async function saveToFile(bar, statusEl) {
        const html = composeHTML(bar);
        if (!('showSaveFilePicker' in window)) {
            fallbackDownload(html);
            statusEl.textContent = 'Downloaded (FSA unsupported)';
            setTimeout(() => { statusEl.textContent = ''; }, 4000);
            return;
        }
        try {
            if (!fileHandle) {
                fileHandle = await window.showSaveFilePicker({
                    suggestedName: pageFile,
                    types: [{ description: 'HTML', accept: { 'text/html': ['.html'] } }]
                });
            }
            const writable = await fileHandle.createWritable();
            await writable.write(html);
            await writable.close();
            statusEl.textContent = 'Saved ' + fileHandle.name;
            setTimeout(() => { statusEl.textContent = ''; }, 4000);
        } catch (err) {
            if (err.name === 'AbortError') return;
            statusEl.textContent = 'Save failed: ' + err.message;
        }
    }

    function buildToolbar() {
        const bar = document.createElement('div');
        bar.className = 'edit-toolbar';
        bar.dataset.editOn = '0';

        const toggle = document.createElement('button');
        toggle.textContent = 'Edit: Off';
        let on = false;
        toggle.addEventListener('click', () => {
            on = !on;
            setEditMode(on);
            bar.dataset.editOn = on ? '1' : '0';
            toggle.textContent = on ? 'Edit: On' : 'Edit: Off';
            toggle.classList.toggle('on', on);
        });

        const saveBtn = document.createElement('button');
        saveBtn.textContent = 'Save';

        const pickBtn = document.createElement('button');
        pickBtn.textContent = 'Pick file...';
        pickBtn.title = 'Force-select the save target file';
        pickBtn.addEventListener('click', async () => {
            if (!('showSaveFilePicker' in window)) return;
            try {
                fileHandle = await window.showSaveFilePicker({
                    suggestedName: pageFile,
                    types: [{ description: 'HTML', accept: { 'text/html': ['.html'] } }]
                });
                statusEl.textContent = 'Target: ' + fileHandle.name;
                setTimeout(() => { statusEl.textContent = ''; }, 4000);
            } catch (e) {}
        });

        const statusEl = document.createElement('span');
        statusEl.className = 'edit-status';

        saveBtn.addEventListener('click', () => saveToFile(bar, statusEl));

        const resetBtn = document.createElement('button');
        resetBtn.textContent = 'Reset';
        resetBtn.addEventListener('click', () => {
            if (confirm('Discard all unsaved edits on this page and reload?')) {
                localStorage.removeItem(STORAGE_KEY);
                location.reload();
            }
        });

        bar.appendChild(toggle);
        bar.appendChild(saveBtn);
        bar.appendChild(pickBtn);
        bar.appendChild(resetBtn);
        bar.appendChild(statusEl);
        document.body.appendChild(bar);
    }

    function injectStyles() {
        const style = document.createElement('style');
        style.textContent = `
            .edit-toolbar {
                position: fixed;
                bottom: 18px;
                right: 18px;
                background: rgba(8, 9, 12, 0.95);
                border: 1px solid #7fb069;
                padding: 8px;
                display: flex;
                gap: 8px;
                align-items: center;
                z-index: 99999;
                font-family: 'JetBrains Mono', monospace, sans-serif;
                font-size: 11px;
                box-shadow: 0 6px 24px rgba(0, 0, 0, 0.5);
            }
            .edit-toolbar button {
                background: transparent;
                color: #7fb069;
                border: 1px solid #7fb069;
                padding: 6px 12px;
                cursor: pointer;
                font-family: inherit;
                font-size: 11px;
                letter-spacing: 1px;
                text-transform: uppercase;
            }
            .edit-toolbar button:hover { background: rgba(127, 176, 105, 0.18); }
            .edit-toolbar button.on { background: #7fb069; color: #08090c; }
            .edit-toolbar button.on:hover { background: #91c47a; }
            .edit-toolbar .edit-status {
                color: #d4a574;
                font-size: 11px;
                max-width: 220px;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            [data-edit-id].edit-on {
                outline: 1px dashed rgba(127, 176, 105, 0.45);
                outline-offset: 2px;
                cursor: text;
            }
            [data-edit-id].edit-on:hover { outline-color: rgba(127, 176, 105, 0.85); }
            [data-edit-id].edit-on:focus { outline: 2px solid #7fb069; }
        `;
        document.head.appendChild(style);
    }

    function init() {
        injectStyles();
        tagEditableNodes();
        loadEdits();
        buildToolbar();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
